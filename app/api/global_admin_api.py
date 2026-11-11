# -*- coding: utf-8 -*-
"""全站管理员后台：跨班查看登录状况、口令与账号分布。

只有 ``role == "admin"``（全站唯一，即集成26-1班的全站管理员）能访问。
其他班的班长/团支书即使 committee 也不行——他们的权限只在自己的班级库里。
"""
from __future__ import annotations

import sqlite3

from .. import classes, crypto, db
from ..errors import forbidden, invalid, not_found
from ..router import route

ROLE_CN = {"admin": "管理员", "monitor": "班长", "secretary": "团支书", "student": "同学"}


def guard_root(user) -> None:
    role = user["role"] if user is not None else None
    if role != "admin":
        raise forbidden("只有全站管理员可以访问")


def initial_password(student_no: str) -> str:
    tail = "".join(ch for ch in str(student_no) if ch.isalnum())[-6:]
    return f"Init@{tail}"


def _open(path):
    conn = db.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _each_class():
    """遍历所有班级库，yield (slug, class_row, conn)；调用方负责 close。"""
    for slug, path in classes.iter_dbs():
        conn = _open(path)
        try:
            cls = db.one(conn, "SELECT * FROM classes LIMIT 1")
        except sqlite3.Error:
            conn.close()
            raise
        if cls is None:
            conn.close()
            continue
        yield slug, cls, conn


def _password_of(row) -> tuple[str, str]:
    """返回 (明文, 来源)。来源：stored=管理员可解密；initial=从未改密的初始密码；none=历史账号。"""
    enc = row["password_enc"] if "password_enc" in row.keys() else None
    if enc:
        plain = crypto.decrypt(enc)
        if plain:
            return plain, "stored"
    if row["must_change_password"]:
        return initial_password(row["student_no"]), "initial"
    return "", "none"


@route("GET", "/api/admin/global/classes")
def global_classes(ctx):
    guard_root(ctx.user)
    out = []
    for slug, cls, conn in _each_class():
        try:
            total = db.scalar(conn, "SELECT COUNT(*) FROM users") or 0
            active = db.scalar(conn, "SELECT COUNT(*) FROM users WHERE status='active'") or 0
            pending = db.scalar(conn, "SELECT COUNT(*) FROM users WHERE status='pending'") or 0
            changed = db.scalar(conn, "SELECT COUNT(*) FROM users WHERE must_change_password=0 "
                                      "AND status='active'") or 0
            logins = db.scalar(conn, "SELECT SUM(login_count) FROM users") or 0
            last = db.scalar(conn, "SELECT MAX(last_login_at) FROM users") or ""
            deadlines = db.scalar(conn, "SELECT COUNT(*) FROM deadlines WHERE status='published'") or 0
        finally:
            conn.close()
        out.append({
            "slug": slug,
            "name": cls["name"],
            "invite_code": cls["invite_code"],
            "total": total, "active": active, "pending": pending,
            "activated": changed, "logins": logins, "last_login_at": last,
            "deadlines": deadlines,
        })
    return {"items": out}


@route("GET", "/api/admin/global/users")
def global_users(ctx):
    guard_root(ctx.user)
    want_slug = (ctx.q("slug") or "").strip()
    keyword = (ctx.q("q") or "").strip().lower()
    only = (ctx.q("filter") or "").strip()  # all | never | pending | changed
    items = []
    for slug, cls, conn in _each_class():
        try:
            rows = db.all_(conn, "SELECT * FROM users ORDER BY student_no")
            for row in rows:
                plain, source = _password_of(row)
                if only == "never" and (row["login_count"] or 0) > 0:
                    continue
                if only == "pending" and row["status"] != "pending":
                    continue
                if only == "changed" and row["must_change_password"]:
                    continue
                if want_slug and slug != want_slug:
                    continue
                if keyword and keyword not in (
                    (row["name"] or "").lower() + " " + (row["student_no"] or "").lower()
                ):
                    continue
                items.append({
                    "slug": slug,
                    "class_name": cls["name"],
                    "id": row["id"],
                    "student_no": row["student_no"],
                    "name": row["name"],
                    "role": row["role"],
                    "role_label": ROLE_CN.get(row["role"], row["role"]),
                    "status": row["status"],
                    "password": plain,
                    "password_source": source,
                    "must_change_password": bool(row["must_change_password"]),
                    "login_count": int(row["login_count"] or 0),
                    "last_login_at": row["last_login_at"],
                    "last_ip": row["last_ip"],
                })
        finally:
            conn.close()
    return {"items": items, "total": len(items)}


@route("GET", "/api/admin/global/logins")
def global_logins(ctx):
    guard_root(ctx.user)
    try:
        limit = max(1, min(int(ctx.q("limit") or 200), 1000))
    except ValueError:
        limit = 200
    items = []
    for slug, cls, conn in _each_class():
        try:
            rows = db.all_(
                conn,
                "SELECT a.id, a.action, a.actor_id, a.ip, a.created_at, "
                "u.name, u.student_no, u.role "
                "FROM audit_logs a LEFT JOIN users u ON u.id = a.actor_id "
                "WHERE a.action IN ('auth.login','auth.register','auth.change_password') "
                "ORDER BY a.id DESC LIMIT ?",
                (limit,),
            )
            for r in rows:
                items.append({
                    "slug": slug,
                    "class_name": cls["name"],
                    "id": r["id"],
                    "action": r["action"],
                    "name": r["name"] or "（已删除）",
                    "student_no": r["student_no"] or "",
                    "role": r["role"] or "",
                    "ip": r["ip"] or "",
                    "created_at": r["created_at"],
                })
        finally:
            conn.close()
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"items": items[:limit]}


@route("POST", "/api/admin/global/reset-password")
def global_reset(ctx):
    guard_root(ctx.user)
    slug = str(ctx.body.get("slug") or "").strip()
    student_no = str(ctx.body.get("student_no") or "").strip()
    if not slug or not student_no:
        raise invalid("缺少班级或学号")
    target = classes.path_for(slug)
    if not target.is_file():
        raise not_found("班级不存在")
    conn = _open(target)
    try:
        row = db.one(conn, "SELECT * FROM users WHERE student_no = ?", (student_no,))
        if row is None:
            raise not_found("账号不存在")
        plain = initial_password(student_no)
        from .. import auth

        conn.execute(
            "UPDATE users SET password_hash = ?, password_enc = ?, must_change_password = 1 "
            "WHERE id = ?",
            (auth.hash_password(plain), crypto.encrypt(plain), row["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "student_no": student_no, "password": plain, "must_change_password": True}
