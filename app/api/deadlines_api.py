"""条目接口：列表、详情、增删改、发布/归档、完成打卡、完成名单、历史。"""
from __future__ import annotations

from .. import audit, db
from ..domain import deadlines as dl
from ..domain import notify, policy
from ..errors import forbidden, invalid, not_found
from ..router import route
from ..util import truthy_int


@route("GET", "/api/deadlines")
def list_deadlines(ctx):
    return dl.list_items(ctx.conn, ctx.user, ctx.query)


@route("GET", "/api/deadlines/{deadline_id}")
def get_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    return {"item": dl.serialize(ctx.conn, row, ctx.user)}


@route("POST", "/api/deadlines", committee=True)
def create_deadline(ctx):
    policy.guard_committee(ctx.user)
    as_draft = truthy_int(ctx.b("as_draft", 0))
    body = dict(ctx.body or {})
    targets = body.pop("target_user_ids", None)
    row = dl.create(
        ctx.conn, ctx.user, body,
        status="draft" if as_draft else "published",
        source_type="manual",
        dedupe_policy="error",
        ip=ctx.ip,
        target_ids_=targets,
    )
    item = dl.serialize(ctx.conn, row, ctx.user)
    if row["status"] == "published":
        notify.fanout_new_deadline(ctx.conn, ctx.class_id, item, ctx.user["id"])
    return 201, {"item": item}


@route("PATCH", "/api/deadlines/{deadline_id}", committee=True)
def patch_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    body = dict(ctx.body or {})
    targets = body.pop("target_user_ids", None)
    fresh = dl.update(ctx.conn, ctx.user, row, body, ip=ctx.ip, target_ids_=targets)
    return {"item": dl.serialize(ctx.conn, fresh, ctx.user)}


@route("DELETE", "/api/deadlines/{deadline_id}", committee=True)
def delete_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    dl.delete(ctx.conn, ctx.user, row, ip=ctx.ip)
    return {"ok": True, "id": row["id"]}


@route("POST", "/api/deadlines/{deadline_id}/publish", committee=True)
def publish_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    fresh = dl.set_status(ctx.conn, ctx.user, row, "published", ip=ctx.ip)
    item = dl.serialize(ctx.conn, fresh, ctx.user)
    notify.fanout_new_deadline(ctx.conn, ctx.class_id, item, ctx.user["id"])
    return {"item": item}


@route("POST", "/api/deadlines/{deadline_id}/archive", committee=True)
def archive_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    fresh = dl.archive(ctx.conn, ctx.user, row, ip=ctx.ip)
    return {"item": dl.serialize(ctx.conn, fresh, ctx.user)}


@route("POST", "/api/deadlines/{deadline_id}/complete")
def complete_deadline(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    state = ctx.b("state") or "done"
    note = ctx.b("note") or ""
    if not isinstance(note, str):
        raise invalid("note 必须是字符串", field="note")
    result = dl.set_completion(ctx.conn, ctx.user, row, state, note[:200])
    fresh = dl.fetch(ctx.conn, row["id"])
    result["completion"] = dl.serialize(ctx.conn, fresh, ctx.user)["completion"]
    return result


@route("GET", "/api/deadlines/{deadline_id}/completions", committee=True)
def deadline_completions(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    return dl.completions(ctx.conn, ctx.user, row)


@route("GET", "/api/deadlines/{deadline_id}/history", committee=True)
def deadline_history(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    return {"items": dl.history(ctx.conn, row)}


# ---------------------------------------------------------------- 草稿

DRAFT_SQL = (
    "SELECT d.*, r.id AS raw_id, r.content AS raw_content, r.sender_name AS raw_sender, "
    "       r.chat_name AS raw_chat, r.occurred_at AS raw_occurred_at, "
    "       j.output AS ai_output, j.confidence AS ai_confidence, j.status AS ai_status "
    "FROM deadlines d "
    "LEFT JOIN raw_messages r ON d.source_ref = ('raw:' || r.id) "
    "LEFT JOIN extraction_jobs j ON j.id = ("
    "    SELECT MAX(id) FROM extraction_jobs WHERE raw_message_id = r.id) "
    "WHERE d.class_id = ? AND d.status = ? ORDER BY d.created_at DESC, d.id DESC LIMIT ?"
)


@route("GET", "/api/drafts", committee=True)
def list_drafts(ctx):
    policy.guard_committee(ctx.user)
    rows = db.all_(ctx.conn, DRAFT_SQL, (ctx.user["class_id"], "draft", 200))
    items = dl.serialize_many(ctx.conn, rows, ctx.user)
    by_id = {row["id"]: row for row in rows}
    for item in items:
        raw = by_id[item["id"]]
        item["raw"] = None if raw["raw_id"] is None else {
            "id": raw["raw_id"],
            "content": raw["raw_content"],
            "sender_name": raw["raw_sender"],
            "chat_name": raw["raw_chat"],
            "occurred_at": raw["raw_occurred_at"],
        }
        item["ai"] = None if raw["ai_output"] is None else {
            "output": raw["ai_output"],
            "confidence": raw["ai_confidence"],
            "status": raw["ai_status"],
        }
    return {"items": items, "total": len(items)}


@route("POST", "/api/drafts/{deadline_id}/publish", committee=True)
def publish_draft(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    if row["status"] != "draft":
        raise invalid("该条目不是草稿")
    fresh = dl.set_status(ctx.conn, ctx.user, row, "published", ip=ctx.ip)
    return {"item": dl.serialize(ctx.conn, fresh, ctx.user)}


@route("POST", "/api/drafts/{deadline_id}/reject", committee=True)
def reject_draft(ctx):
    row = dl.get_visible(ctx.conn, ctx.user, _id(ctx.params))
    if row["status"] != "draft":
        raise invalid("该条目不是草稿")
    reason = (ctx.b("reason") or "").strip()[:200]
    fresh = dl.set_status(ctx.conn, ctx.user, row, "archived", ip=ctx.ip, reason=reason or "reject")
    return {"item": dl.serialize(ctx.conn, fresh, ctx.user)}


# ---------------------------------------------------------------- 工具

def _id(params: dict) -> int:
    raw = params.get("deadline_id", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise not_found("条目不存在") from None
    if value <= 0:
        raise not_found("条目不存在")
    return value
