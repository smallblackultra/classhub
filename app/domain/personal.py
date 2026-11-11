# -*- coding: utf-8 -*-
"""个人待办：每个登录用户自己的私有清单，互相不可见。

权限模型与班级 deadline 完全分开：
- 任何登录用户（包括普通同学）都能增删改查**自己**的条目；
- 查询永远带 ``user_id`` 过滤，别人的条目一律 404（不暴露存在性）；
- 与班级 deadline 不共享表、不参与完成度统计。
"""
from __future__ import annotations

import re
import sqlite3

from .. import db
from ..errors import invalid, not_found
from ..util import iso_utc, now_iso, parse_iso

MAX_TITLE = 120
MAX_NOTE = 2000
MAX_CLIENT_KEY = 80
_CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _clean_title(value) -> str:
    title = str(value or "").strip()
    if not title:
        raise invalid("请填写待办内容", field="title")
    if len(title) > MAX_TITLE:
        raise invalid(f"待办内容最多 {MAX_TITLE} 字", field="title")
    return title


def _clean_due(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return iso_utc(parse_iso(text))
    except Exception:
        raise invalid("时间格式应为 ISO 时间（如 2026-11-10T23:59:00+08:00）", field="due_at") from None


def _clean_client_key(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) > MAX_CLIENT_KEY or not _CLIENT_KEY_RE.match(text):
        raise invalid("同步标识格式不正确", field="client_key")
    return text


def serialize(row) -> dict:
    due_local = None
    if row["due_at"]:
        try:
            from ..util import iso_local

            due_local = iso_local(parse_iso(row["due_at"]))
        except Exception:
            due_local = row["due_at"]
    return {
        "id": row["id"],
        "title": row["title"],
        "note": row["note"] or "",
        "due_at": row["due_at"],
        "due_local": due_local,
        "done": bool(row["done"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_items(conn, user, *, done: str = "all") -> list[dict]:
    sql = "SELECT * FROM personal_items WHERE user_id = ? AND class_id = ?"
    params: list = [user["id"], user["class_id"]]
    if done == "open":
        sql += " AND done = 0"
    elif done == "done":
        sql += " AND done = 1"
    sql += " ORDER BY done ASC, (due_at IS NULL) ASC, due_at ASC, id DESC"
    return [serialize(r) for r in db.all_(conn, sql, params)]


def create(conn, user, data: dict) -> dict:
    title = _clean_title(data.get("title"))
    note = str(data.get("note") or "").strip()[:MAX_NOTE]
    due = _clean_due(data.get("due_at"))
    client_key = _clean_client_key(data.get("client_key"))

    # 离线恢复的同一条计划可能被重复提交：client_key 让创建变成幂等操作。
    if client_key:
        existing = db.one(
            conn,
            "SELECT * FROM personal_items WHERE user_id = ? AND class_id = ? "
            "AND client_key = ?",
            (user["id"], user["class_id"], client_key),
        )
        if existing is not None:
            return serialize(existing)

    now = now_iso()
    try:
        item_id = db.execute(
            conn,
            "INSERT INTO personal_items (class_id, user_id, title, note, due_at, done, "
            "client_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (user["class_id"], user["id"], title, note, due, client_key, now, now),
        )
    except sqlite3.IntegrityError:
        if not client_key:
            raise
        existing = db.one(
            conn,
            "SELECT * FROM personal_items WHERE user_id = ? AND class_id = ? "
            "AND client_key = ?",
            (user["id"], user["class_id"], client_key),
        )
        if existing is None:
            raise
        return serialize(existing)
    return serialize(_get(conn, user, item_id))


def _get(conn, user, item_id: int):
    row = db.one(conn, "SELECT * FROM personal_items WHERE id = ? AND user_id = ?",
                 (item_id, user["id"]))
    if row is None:
        raise not_found("待办不存在")
    return row


def update(conn, user, item_id: int, data: dict) -> dict:
    row = _get(conn, user, item_id)
    sets: list[str] = []
    params: list = []
    if "title" in data:
        sets.append("title = ?")
        params.append(_clean_title(data.get("title")))
    if "note" in data:
        sets.append("note = ?")
        params.append(str(data.get("note") or "").strip()[:MAX_NOTE])
    if "due_at" in data:
        sets.append("due_at = ?")
        params.append(_clean_due(data.get("due_at")))
    if "done" in data:
        sets.append("done = ?")
        params.append(1 if data.get("done") else 0)
    if not sets:
        raise invalid("没有需要修改的内容")
    sets.append("updated_at = ?")
    params.append(now_iso())
    params.append(row["id"])
    conn.execute(f"UPDATE personal_items SET {', '.join(sets)} WHERE id = ?", params)
    return serialize(_get(conn, user, item_id))


def delete(conn, user, item_id: int) -> None:
    row = _get(conn, user, item_id)
    conn.execute("DELETE FROM personal_items WHERE id = ?", (row["id"],))
