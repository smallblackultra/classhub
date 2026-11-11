"""消息接入 API：粘贴 / QQ 机器人回调 / 书签抓取 / 未解析队列。"""
from __future__ import annotations

from .. import db
from ..domain import deadlines
from ..errors import invalid, not_found, unauthenticated
from ..ingest import service
from ..router import route

QUEUE_SQL = """
SELECT r.id, r.content, r.sender_name, r.chat_name, r.occurred_at, r.status,
       s.type AS source_type, s.name AS source_name,
       j.status AS job_status, j.provider AS job_provider, j.error AS job_error,
       d.id AS deadline_id
FROM raw_messages r
JOIN sources s ON s.id = r.source_id
LEFT JOIN extraction_jobs j
       ON j.id = (SELECT MAX(id) FROM extraction_jobs WHERE raw_message_id = r.id)
LEFT JOIN deadlines d ON d.source_ref = ('raw:' || r.id) AND d.status != 'archived'
WHERE s.class_id = ? AND d.id IS NULL
ORDER BY r.id DESC
LIMIT ?
"""


def _token(ctx) -> str:
    return str(ctx.headers.get("x-classhub-token") or ctx.b("token") or "").strip()


def _item(ctx, deadline_id):
    row = deadlines.fetch(ctx.conn, deadline_id)
    return deadlines.serialize(ctx.conn, row, ctx.user) if row else None


def _ai_meta(result: dict) -> dict:
    meta = result.get("meta") or {}
    return {
        "engine": meta.get("engine", "rules"),
        "provider": meta.get("provider", "rules"),
        "model": meta.get("model", ""),
        "used_ai": bool(meta.get("used_ai")),
        "error": meta.get("error", ""),
        "warnings": list(meta.get("warnings") or []),
        "audience_reason": meta.get("audience_reason", ""),
    }


@route("POST", "/api/ingest/paste", committee=True)
def ingest_paste(ctx):
    text = ctx.b("text")
    if not isinstance(text, str) or not text.strip():
        raise invalid("粘贴内容不能为空", field="text")
    hint = str(ctx.b("source_hint") or "粘贴导入")[:80]
    source = service.ensure_source(ctx.conn, ctx.class_id, "paste", hint)
    result = service.ingest_text(
        ctx.conn, class_id=ctx.class_id, source=source, text=text, source_type="paste",
        sender_name=ctx.user["name"], chat_name=hint,
        hints={"source_hint": hint}, use_ai=True, actor_id=ctx.user_id,
    )
    body = {"status": result["status"], "raw_id": result["raw_id"],
            "job_id": result.get("job_id"), "ai": _ai_meta(result)}
    if result.get("deadline_id"):
        body["item"] = _item(ctx, result["deadline_id"])
    return body


@route("POST", "/api/ingest/qq", auth="none", csrf=False)
def ingest_qq(ctx):
    source = service.find_source_by_token(ctx.conn, _token(ctx))
    if not str(source["type"]).startswith("qq"):
        raise unauthenticated("该令牌不是 QQ 机器人令牌")

    text = ctx.b("text")
    if not isinstance(text, str) or not text.strip():
        raise invalid("text 不能为空", field="text")
    reply = str(ctx.b("reply_text") or "").strip()
    if reply:
        text = f"{text}\n（引用消息：{reply[:1500]}）"
    msg_id = str(ctx.b("msg_id") or "").strip()
    result = service.ingest_text(
        ctx.conn, class_id=source["class_id"], source=source, text=text, source_type="qq",
        occurred_at=ctx.b("occurred_at"), sender_name=str(ctx.b("sender_name") or ""),
        sender_id=str(ctx.b("sender_id") or ""), chat_name=str(ctx.b("group_name") or ""),
        external_id=f"qq:{msg_id}" if msg_id else None,
        hints={"source_hint": f"QQ群 · {ctx.b('group_name') or '班级群'}"},
        use_ai=True,
    )
    return {"ok": True, "status": result["status"], "raw_id": result["raw_id"],
            "deadline_id": result.get("deadline_id"), "ai": _ai_meta(result),
            "item": _item(ctx, result["deadline_id"]) if result.get("deadline_id") else None,
            "fields": result.get("fields") if result["status"] != "draft" else None}


@route("POST", "/api/ingest/bookmarklet", auth="none", csrf=False)
def ingest_bookmarklet(ctx):
    source = service.find_source_by_token(ctx.conn, _token(ctx))
    platform = str(ctx.b("platform") or source["type"] or "bookmarklet")[:40]
    page_url = str(ctx.b("page_url") or "")[:500]
    items = ctx.b("items")
    result = service.ingest_bookmarklet(
        ctx.conn, class_id=source["class_id"], source=source, platform=platform,
        page_url=page_url, items=items or [], actor_id=None,
    )
    for entry in result["results"]:
        if entry.get("deadline_id"):
            entry["item"] = _item(ctx, entry["deadline_id"]) if ctx.user else None
    return result


@route("GET", "/api/ingest/queue", committee=True)
def ingest_queue(ctx):
    limit = max(1, min(int(ctx.q("limit") or 30), 100))
    rows = db.all_(ctx.conn, QUEUE_SQL, (ctx.class_id, limit))
    return {
        "items": [{
            "id": r["id"],
            "content": r["content"],
            "sender_name": r["sender_name"],
            "chat_name": r["chat_name"],
            "source_type": r["source_type"],
            "source_name": r["source_name"],
            "occurred_at": r["occurred_at"],
            "status": r["status"],
            "job": ({"status": r["job_status"], "provider": r["job_provider"],
                     "error": r["job_error"]} if r["job_status"] else None),
        } for r in rows],
        "total": len(rows),
    }


@route("POST", "/api/ingest/queue/{raw_id}/retry", committee=True)
def ingest_retry(ctx):
    try:
        raw_id = int(ctx.params["raw_id"])
    except (KeyError, TypeError, ValueError):
        raise not_found("原始消息不存在") from None
    raw = db.one(
        ctx.conn,
        "SELECT r.* FROM raw_messages r JOIN sources s ON s.id = r.source_id "
        "WHERE r.id = ? AND s.class_id = ?",
        (raw_id, ctx.class_id),
    )
    if raw is None:
        raise not_found("原始消息不存在")
    result = service.retry_raw(ctx.conn, raw, use_ai=True, actor_id=ctx.user_id)
    body = {"status": result["status"], "raw_id": result["raw_id"],
            "job_id": result.get("job_id"), "ai": _ai_meta(result)}
    if result.get("deadline_id"):
        body["item"] = _item(ctx, result["deadline_id"])
    return body


@route("POST", "/api/ingest/queue/{raw_id}/manual", committee=True)
def ingest_manual(ctx):
    try:
        raw_id = int(ctx.params["raw_id"])
    except (KeyError, TypeError, ValueError):
        raise not_found("原始消息不存在") from None
    raw = db.one(
        ctx.conn,
        "SELECT r.* FROM raw_messages r JOIN sources s ON s.id = r.source_id "
        "WHERE r.id = ? AND s.class_id = ?",
        (raw_id, ctx.class_id),
    )
    if raw is None:
        raise not_found("原始消息不存在")
    row = service.manual_from_raw(ctx.conn, raw, ctx.user, ctx.body)
    return 201, {"item": _item(ctx, row["id"])}
