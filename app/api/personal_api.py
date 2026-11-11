# -*- coding: utf-8 -*-
"""个人待办接口（所有登录用户可用，仅本人可见）。"""
from __future__ import annotations

from ..domain import personal
from ..router import route


@route("GET", "/api/personal")
def list_personal(ctx):
    done = (ctx.q("done") or "all").strip()
    if done not in ("all", "open", "done"):
        done = "all"
    items = personal.list_items(ctx.conn, ctx.user, done=done)
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "open": sum(1 for i in items if not i["done"]),
            "done": sum(1 for i in items if i["done"]),
        },
    }


@route("POST", "/api/personal")
def create_personal(ctx):
    item = personal.create(ctx.conn, ctx.user, ctx.body)
    ctx.conn.commit()
    return {"item": item}


@route("PATCH", "/api/personal/{item_id}")
def update_personal(ctx):
    item = personal.update(ctx.conn, ctx.user, int(ctx.params["item_id"]), ctx.body)
    ctx.conn.commit()
    return {"item": item}


@route("DELETE", "/api/personal/{item_id}")
def delete_personal(ctx):
    personal.delete(ctx.conn, ctx.user, int(ctx.params["item_id"]))
    ctx.conn.commit()
    return {"ok": True}
