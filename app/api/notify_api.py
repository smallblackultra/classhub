"""站内通知接口。"""
from __future__ import annotations

from ..domain import notify
from ..errors import invalid
from ..router import route
from ..util import truthy_int


def _int(value, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def _query_one(ctx, name: str, default: str = "") -> str:
    values = ctx.query.get(name) or []
    return values[0] if values else default


@route("GET", "/api/notifications")
def list_notifications(ctx):
    items, total = notify.list_for_user(
        ctx.conn, ctx.user["id"],
        unread_only=bool(truthy_int(_query_one(ctx, "unread", "0"))),
        limit=_int(_query_one(ctx, "limit", "30"), 30, 1, 100),
        offset=_int(_query_one(ctx, "offset", "0"), 0, 0, 100000),
    )
    return {
        "items": items,
        "total": total,
        "unread": notify.unread_count(ctx.conn, ctx.user["id"]),
    }


@route("POST", "/api/notifications/read")
def mark_read(ctx):
    ids = ctx.b("ids")
    if ids is None:
        ids = []
    if not isinstance(ids, list) or any(not isinstance(i, int) for i in ids):
        raise invalid("ids 必须是整数数组", field="ids")
    marked = notify.mark_read(ctx.conn, ctx.user["id"], ids or None)
    return {"marked": marked, "unread": notify.unread_count(ctx.conn, ctx.user["id"])}


@route("POST", "/api/notifications/read-all")
def mark_all_read(ctx):
    marked = notify.mark_all_read(ctx.conn, ctx.user["id"])
    return {"marked": marked, "unread": 0}
