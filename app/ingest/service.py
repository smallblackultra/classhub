"""接入管线：原始消息落库 → 抽取 → 草稿（永远不直接发布）。"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3

from .. import audit, db
from ..ai import extract as ai_extract
from ..ai import provider
from ..domain import deadlines, notify
from ..errors import conflict, invalid, not_found, unauthenticated
from ..util import iso_utc, jdump, now_iso, parse_iso, sha256_hex

AI_SOURCE_TYPES = ("qq", "paste", "bookmarklet", "chaoxing", "yuketang", "import")


def _norm_time(value: str | None) -> str:
    if not value:
        return now_iso()
    try:
        return iso_utc(parse_iso(value))
    except Exception:
        raise invalid("occurred_at 不是合法时间") from None


def find_source_by_token(conn: sqlite3.Connection, token: str, kind: str | None = None):
    """机器人/书签令牌校验：库里只存 sha256(token)。"""
    token = (token or "").strip()
    if len(token) < 8:
        raise unauthenticated("缺少或格式不正确的接入令牌")
    digest = sha256_hex(token)
    for row in db.all_(conn, "SELECT * FROM sources WHERE enabled = 1 AND token_hash IS NOT NULL"):
        if kind and row["type"] != kind:
            continue
        if hmac.compare_digest(row["token_hash"], digest):
            return row
    raise unauthenticated("接入令牌无效或已轮换")


def ensure_source(conn: sqlite3.Connection, class_id: int, kind: str, name: str):
    row = db.one(conn, "SELECT * FROM sources WHERE class_id = ? AND type = ? ORDER BY id LIMIT 1",
                 (class_id, kind))
    if row:
        return row
    source_id = db.execute(
        conn,
        "INSERT INTO sources (class_id, type, name, enabled, created_at) VALUES (?,?,?,1,?)",
        (class_id, kind, name, now_iso()),
    )
    return db.one(conn, "SELECT * FROM sources WHERE id = ?", (source_id,))


def _actor(class_id: int, actor_id: int | None = None) -> dict:
    return {"id": actor_id, "class_id": class_id, "role": "admin"}


def draft_of_raw(conn: sqlite3.Connection, raw_id: int):
    return db.one(conn, "SELECT * FROM deadlines WHERE source_ref = ? AND status != 'archived' "
                        "ORDER BY id LIMIT 1", (f"raw:{raw_id}",))


def _job_record(conn: sqlite3.Connection, raw_id: int, meta: dict, fields: dict, status: str,
                error: str = "") -> int:
    return db.execute(
        conn,
        "INSERT INTO extraction_jobs (raw_message_id, provider, model, prompt_version, output, "
        "parsed, confidence, status, error, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (raw_id, meta.get("provider", "rules"), meta.get("model", ""),
         meta.get("prompt_version", "v1"),
         (meta.get("raw") or json.dumps(fields, ensure_ascii=False))[:8000],
         jdump(fields), fields.get("confidence"), status, (error or meta.get("error") or "")[:1000],
         now_iso()),
    )


def _run_extraction(conn: sqlite3.Connection, *, raw_id: int, body: str, source: sqlite3.Row,
                    source_type: str, occurred: str, hints: dict, use_ai: bool,
                    actor_id: int | None) -> dict:
    class_id = source["class_id"]
    try:
        provider.load_from_db(conn)
    except Exception:  # noqa: BLE001 - 读配置失败就退回环境变量
        pass
    result = ai_extract.extract(body, occurred_at=occurred, hints=hints, use_ai=use_ai)
    fields = result["fields"]
    meta = result["meta"]

    is_task = bool(fields.get("is_task")) and len(str(fields.get("title") or "")) >= 2
    if not is_task:
        job_id = _job_record(conn, raw_id, meta, fields, "invalid")
        db.execute(conn, "UPDATE raw_messages SET status = 'ignored' WHERE id = ?", (raw_id,))
        return {"status": "ignored", "raw_id": raw_id, "job_id": job_id,
                "deadline_id": None, "fields": fields, "meta": meta}

    data = {
        "title": str(fields["title"])[:200],
        "category": fields.get("category") or "homework",
        "audience": fields.get("audience") or "committee",
        "course": fields.get("course") or "",
        "due_at": fields.get("due_at"),
        "due_at_raw": fields.get("due_at_raw") or "",
        "link": fields.get("link") or "",
        "summary": "",
    }
    row = deadlines.create(
        conn, _actor(class_id, actor_id), data, status="draft", source_type=source_type,
        source_ref=f"raw:{raw_id}", confidence=fields.get("confidence"),
        needs_review=1 if fields.get("needs_review") else 0, dedupe_policy="flag",
    )
    notify.notify_draft_pending(
        conn, class_id, row["id"], row["title"],
        sender=str(hints.get("sender_name") or ""),
        source_label=str(source["name"] or "QQ 群"),
    )
    job_id = _job_record(conn, raw_id, meta, fields, "ok")
    db.execute(conn, "UPDATE raw_messages SET status = 'extracted' WHERE id = ?", (raw_id,))
    db.execute(conn, "UPDATE sources SET last_ok_at = ? WHERE id = ?", (now_iso(), source["id"]))
    audit.log(conn, actor_id, "ingest.draft", f"deadline:{row['id']}",
              {"raw_id": raw_id, "source": source_type, "engine": meta.get("engine")})
    return {"status": "draft", "raw_id": raw_id, "job_id": job_id, "deadline_id": row["id"],
            "fields": fields, "meta": meta}


def ingest_text(conn: sqlite3.Connection, *, class_id: int, source: sqlite3.Row, text: str,
                source_type: str, occurred_at: str | None = None, sender_name: str = "",
                sender_id: str = "", chat_name: str = "", external_id: str | None = None,
                hints: dict | None = None, use_ai: bool = True,
                actor_id: int | None = None) -> dict:
    body = (text or "").strip()
    if not body:
        raise invalid("消息内容不能为空", field="text")
    body = body[:8000]

    if external_id:
        existing = db.one(conn, "SELECT * FROM raw_messages WHERE source_id = ? AND external_id = ?",
                          (source["id"], external_id))
        if existing is not None:
            draft = draft_of_raw(conn, existing["id"])
            return {"status": "duplicate", "raw_id": existing["id"],
                    "deadline_id": draft["id"] if draft else None, "fields": {}, "meta": {}}

    occurred = _norm_time(occurred_at)
    raw_id = db.execute(
        conn,
        "INSERT INTO raw_messages (source_id, external_id, sender_name, sender_id, chat_name, "
        "content, occurred_at, ingested_at, status) VALUES (?,?,?,?,?,?,?,?, 'new')",
        (source["id"], external_id, sender_name[:80], str(sender_id)[:80], chat_name[:120],
         body, occurred, now_iso()),
    )

    merged_hints = dict(hints or {})
    merged_hints.setdefault("source_hint", chat_name or source["name"] or source_type)
    merged_hints.setdefault("sender_name", sender_name)
    return _run_extraction(conn, raw_id=raw_id, body=body, source=source,
                           source_type=source_type, occurred=occurred, hints=merged_hints,
                           use_ai=use_ai, actor_id=actor_id)


def retry_raw(conn: sqlite3.Connection, raw: sqlite3.Row, *, use_ai: bool = True,
              actor_id: int | None = None) -> dict:
    source = db.one(conn, "SELECT * FROM sources WHERE id = ?", (raw["source_id"],))
    if source is None:
        raise not_found("原始消息对应的数据源不存在")
    if draft_of_raw(conn, raw["id"]) is not None:
        raise conflict("这条消息已经生成过草稿了")
    hints = {"source_hint": raw["chat_name"] or source["name"]}
    result = _run_extraction(conn, raw_id=raw["id"], body=raw["content"], source=source,
                             source_type=source["type"], occurred=raw["occurred_at"],
                             hints=hints, use_ai=use_ai, actor_id=actor_id)
    return result


def manual_from_raw(conn: sqlite3.Connection, raw: sqlite3.Row, user, data: dict) -> sqlite3.Row:
    """抽取失败时，班委直接拿原文手动建草稿。"""
    if draft_of_raw(conn, raw["id"]) is not None:
        raise conflict("这条消息已经生成过草稿了")
    body = {
        "title": data.get("title") or raw["content"].strip().splitlines()[0][:80],
        "category": data.get("category") or "task",
        "audience": data.get("audience") or "committee",
        "course": data.get("course") or "",
        "due_at": data.get("due_at"),
        "due_at_raw": data.get("due_at_raw") or "",
        "location": data.get("location") or "",
        "link": data.get("link") or "",
        "summary": raw["content"][:1000],
    }
    row = deadlines.create(conn, user, body, status="draft",
                           source_type="paste", source_ref=f"raw:{raw['id']}",
                           needs_review=0, dedupe_policy="flag")
    db.execute(conn, "UPDATE raw_messages SET status = 'extracted' WHERE id = ?", (raw["id"],))
    return row


def ingest_bookmarklet(conn: sqlite3.Connection, *, class_id: int, source: sqlite3.Row,
                       platform: str, page_url: str, items: list[dict],
                       actor_id: int | None = None) -> dict:
    """书签抓取：每个作业/考试条目独立走一次管线。"""
    if not isinstance(items, list) or not items:
        raise invalid("items 不能为空", field="items")
    results = []
    for idx, item in enumerate(items[:50]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        due_text = str(item.get("due_text") or "").strip()
        text = title
        if item.get("course"):
            text += f"，课程：{item['course']}"
        if due_text:
            text += f"，截止时间：{due_text}"
        hints = {k: v for k, v in {
            "title": title[:200],
            "course": str(item.get("course") or "")[:100],
            "due_text": due_text[:100],
            "link": str(item.get("link") or "")[:1000],
            "category": str(item.get("category") or ""),
        }.items() if v}
        source_type = platform if platform in ("chaoxing", "yuketang") else "bookmarklet"
        try:
            res = ingest_text(
                conn, class_id=class_id, source=source,
                text=text + f"\n（来源：{platform} {page_url[:200]}）",
                source_type=source_type, sender_name="书签抓取", chat_name=platform,
                external_id=f"bm:{platform}:{idx}:{title[:80]}:{due_text[:40]}",
                hints=hints, use_ai=False, actor_id=actor_id,
            )
        except Exception as exc:  # 单条失败不影响其它条目
            results.append({"title": title, "status": "error", "error": str(exc)})
            continue
        results.append({"title": title, **{k: res.get(k) for k in
                                           ("status", "deadline_id", "raw_id", "fields")}})
    created = sum(1 for r in results if r.get("status") in ("draft", "duplicate"))
    return {"platform": platform, "results": results, "created": created}
