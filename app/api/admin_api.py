"""管理端接口：成员审批、邀请码、数据源、统计、审计。"""
from __future__ import annotations

from .. import audit, db
from ..ai import provider
from ..domain import policy
from ..errors import forbidden, invalid, not_found
from ..router import route
from ..util import jload, new_invite_code, new_token, now_iso, sha256_hex, one_of, text

ROLES = ("student", "monitor", "secretary", "admin")
STATUSES = ("pending", "active", "disabled")
SOURCE_KINDS = ("qq_onebot", "bookmarklet", "paste", "chaoxing")


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "student_no": row["student_no"],
        "name": row["name"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


@route("GET", "/api/admin/users", committee=True)
def list_users(ctx):
    policy.guard_committee(ctx.user)
    status = ctx.q("status", "all")
    sql = "SELECT * FROM users WHERE class_id = ?"
    params: list = [ctx.user["class_id"]]
    if status != "all":
        if status not in STATUSES:
            raise invalid("status 取值不合法", field="status")
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 ELSE 2 END, role, student_no"
    rows = db.all_(ctx.conn, sql, params)
    counts = {s: 0 for s in STATUSES}
    for r in db.all_(ctx.conn, "SELECT status, COUNT(*) AS n FROM users WHERE class_id = ? GROUP BY status",
                     (ctx.user["class_id"],)):
        counts[r["status"]] = r["n"]
    return {"items": [_user_public(r) for r in rows], "counts": counts}


@route("PATCH", "/api/admin/users/{user_id}", committee=True)
def patch_user(ctx):
    policy.guard_committee(ctx.user)
    try:
        target_id = int(ctx.params.get("user_id", ""))
    except (TypeError, ValueError):
        raise not_found("成员不存在") from None
    if target_id == ctx.user["id"]:
        raise forbidden("不能修改自己的角色或状态")
    target = db.one(ctx.conn, "SELECT * FROM users WHERE id = ? AND class_id = ?",
                    (target_id, ctx.user["class_id"]))
    if target is None:
        raise not_found("成员不存在")

    patch: dict = {}
    if "role" in ctx.body:
        role = one_of(ctx.body["role"], ROLES, "role")
        if role == "admin" and ctx.user["role"] != "admin":
            raise forbidden("只有最高管理员可以授予管理员权限")
        patch["role"] = role
    if "status" in ctx.body:
        patch["status"] = one_of(ctx.body["status"], STATUSES, "status")
    if "name" in ctx.body:
        patch["name"] = text(ctx.body["name"], "name", maxlen=30, required=True)
    if not patch:
        raise invalid("没有需要修改的字段")

    sets = ", ".join(f"{k} = ?" for k in patch)
    ctx.conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*patch.values(), target_id))
    audit.log(ctx.conn, ctx.user["id"], "admin.user_update", f"user:{target_id}",
              {"before": {"role": target["role"], "status": target["status"]}, "after": patch}, ctx.ip)
    fresh = db.one(ctx.conn, "SELECT * FROM users WHERE id = ?", (target_id,))
    return {"user": _user_public(fresh)}


@route("POST", "/api/admin/invite/rotate", committee=True)
def rotate_invite(ctx):
    policy.guard_committee(ctx.user)
    code = new_invite_code(8)
    ctx.conn.execute("UPDATE classes SET invite_code = ? WHERE id = ?", (code, ctx.user["class_id"]))
    audit.log(ctx.conn, ctx.user["id"], "admin.invite_rotate", f"class:{ctx.user['class_id']}", {}, ctx.ip)
    return {"invite_code": code}


@route("GET", "/api/admin/sources", committee=True)
def list_sources(ctx):
    policy.guard_committee(ctx.user)
    rows = db.all_(ctx.conn, "SELECT * FROM sources WHERE class_id = ? ORDER BY id", (ctx.user["class_id"],))
    return {"items": [{
        "id": r["id"], "type": r["type"], "name": r["name"], "enabled": bool(r["enabled"]),
        "config": jload(r["config"], {}), "has_token": bool(r["token_hash"]),
        "last_ok_at": r["last_ok_at"], "last_error": r["last_error"], "created_at": r["created_at"],
    } for r in rows]}


@route("POST", "/api/admin/sources", committee=True)
def create_source(ctx):
    policy.guard_committee(ctx.user)
    kind = one_of(ctx.b("type"), SOURCE_KINDS, "type")
    name = text(ctx.b("name"), "name", maxlen=60) or kind
    token = f"{kind.split('_')[0]}_{ctx.user['class_id']}_{new_token(16)}"
    now = now_iso()
    sid = db.execute(ctx.conn, 
        "INSERT INTO sources (class_id, type, name, config, enabled, token_hash, created_at) "
        "VALUES (?, ?, ?, '{}', 1, ?, ?)",
        (ctx.user["class_id"], kind, name, sha256_hex(token), now),
    )
    audit.log(ctx.conn, ctx.user["id"], "admin.source_create", f"source:{sid}", {"type": kind}, ctx.ip)
    return 201, {"source": {"id": sid, "type": kind, "name": name}, "token": token}


@route("GET", "/api/admin/stats", committee=True)
def stats(ctx):
    policy.guard_committee(ctx.user)
    cid = ctx.user["class_id"]
    users = {s: int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM users WHERE class_id = ? AND status = ?",
                              (cid, s))) for s in STATUSES}
    users["total"] = sum(users.values())
    dl_counts = {s: int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM deadlines WHERE class_id = ? AND status = ?",
                                  (cid, s))) for s in ("published", "draft", "archived")}
    by_category = {r["category"]: r["n"] for r in db.all_(
        ctx.conn, "SELECT category, COUNT(*) AS n FROM deadlines WHERE class_id = ? AND status = 'published' "
                  "GROUP BY category", (cid,))}
    messages = int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM raw_messages"))
    extracted = int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM raw_messages WHERE status = 'extracted'"))
    failed = int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM raw_messages WHERE status = 'failed'"))
    last_msg = db.scalar(ctx.conn, "SELECT MAX(ingested_at) FROM raw_messages", (), None)
    return {
        "users": users,
        "deadlines": dl_counts,
        "by_category": by_category,
        "extraction": {
            "messages": messages, "extracted": extracted, "failed": failed,
            "success_rate": round(extracted / messages, 3) if messages else None,
            "last_message_at": last_msg,
        },
    }


@route("GET", "/api/admin/audit", committee=True)
def audit_list(ctx):
    policy.guard_committee(ctx.user)
    try:
        limit = min(max(int(ctx.q("limit", "100") or 100), 1), 500)
    except ValueError:
        limit = 100
    rows = db.all_(
        ctx.conn,
        "SELECT a.*, u.name AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id = a.actor_id "
        "ORDER BY a.id DESC LIMIT ?",
        (limit,),
    )
    return {"items": [{
        "id": r["id"], "actor_id": r["actor_id"], "actor_name": r["actor_name"],
        "action": r["action"], "target": r["target"], "meta": jload(r["meta"], {}),
        "ip": r["ip"], "created_at": r["created_at"],
    } for r in rows]}
