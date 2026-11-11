"""审计日志。所有写操作都尽量留痕，方便追责与排障。"""
from __future__ import annotations

import sqlite3

from .util import jdump, now_iso


def log(conn: sqlite3.Connection, actor_id: int | None, action: str, target: str = "",
        meta: dict | None = None, ip: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs (actor_id, action, target, meta, ip, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (actor_id, action, (target or "")[:120], jdump(meta or {}), (ip or "")[:64], now_iso()),
    )
