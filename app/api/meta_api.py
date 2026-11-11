"""元信息与健康检查。"""
from __future__ import annotations

import os

from .. import __version__, db
from ..ai import provider
from ..domain import deadlines as dl
from ..domain import policy
from ..router import route
from ..util import now_iso


@route("GET", "/api/health", auth="none")
def health(ctx):
    db_ok = True
    try:
        db.scalar(ctx.conn, "SELECT 1")
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"ok": db_ok, "version": __version__, "time": now_iso(), "db": db_ok}


@route("GET", "/api/meta", auth="none", allow_pending=True)
def meta(ctx):
    user = ctx.user
    totals = dl._totals(ctx.conn, user["class_id"]) if user else (0, 0)
    try:
        provider.load_from_db(ctx.conn)
    except Exception:  # noqa: BLE001 - 配置读取失败按未启用处理
        pass
    class_row = db.one(ctx.conn, "SELECT name, college FROM classes LIMIT 1")
    return {
        "server_time": now_iso(),
        "timezone": "Asia/Shanghai",
        "version": __version__,
        "class_name": class_row["name"] if class_row else "",
        "college": class_row["college"] if class_row else "",
        "categories": [{"value": k, "label": v} for k, v in dl.CATEGORY_LABELS.items()],
        "task_subtypes": [{"value": k, "label": v} for k, v in dl.TASK_SUBTYPES.items()],
        "task_levels": [{"value": k, "label": v} for k, v in dl.TASK_LEVELS.items()],
        "audiences": [{"value": k, "label": v} for k, v in dl.AUDIENCE_LABELS.items()],
        "sources": [{"value": v, "label": v} for v in dl.SOURCE_TYPES],
        "roles": [
            {"value": "student", "label": "同学"},
            {"value": "monitor", "label": "班长"},
            {"value": "secretary", "label": "团支书"},
            {"value": "admin", "label": "管理员"},
        ],
        "class_totals": {"everyone": totals[0], "committee": totals[1]},
        "ai_enabled": provider.enabled(),
        "committee": policy.is_committee(user),
        "active": policy.is_active(user),
    }
