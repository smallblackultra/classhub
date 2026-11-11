"""认证相关接口：注册、登录、登出、当前用户。"""
from __future__ import annotations

import re
import threading
import time

from .. import audit, auth, classes, config, crypto, db
from ..domain import notify, policy
from ..errors import ApiError, conflict, forbidden, invalid, rate_limited, unauthenticated
from ..request import Response, cookie
from ..router import route
from ..util import now_iso

STUDENT_NO_RE = re.compile(r"^[A-Za-z0-9]{4,20}$")
AVATAR_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
AVATAR_MAX_CHARS = 400_000

_fail_lock = threading.Lock()
_fails: dict[str, list[float]] = {}


def _too_many_fails(key: str) -> bool:
    now = time.time()
    with _fail_lock:
        stamps = [t for t in _fails.get(key, []) if now - t < config.LOGIN_WINDOW_SECONDS]
        _fails[key] = stamps
        return len(stamps) >= config.LOGIN_MAX_FAILS


def _record_fail(key: str) -> None:
    with _fail_lock:
        _fails.setdefault(key, []).append(time.time())


def _clear_fails(key: str) -> None:
    with _fail_lock:
        _fails.pop(key, None)


def profile(conn, user) -> dict:
    cls = db.one(conn, "SELECT * FROM classes WHERE id = ?", (user["class_id"],))
    committee = policy.is_committee(user)
    drafts = 0
    if committee:
        drafts = db.scalar(
            conn, "SELECT COUNT(*) FROM deadlines WHERE class_id = ? AND status = 'draft'",
            (user["class_id"],),
        )
    class_info = {
        "id": cls["id"], "name": cls["name"], "college": cls["college"],
        "major": cls["major"], "grade": cls["grade"],
    }
    if committee:
        class_info["invite_code"] = cls["invite_code"]
    return {
        "user": {
            "id": user["id"],
            "student_no": user["student_no"],
            "name": user["name"],
            "role": user["role"],
            "status": user["status"],
            "must_change_password": bool(user["must_change_password"]),
            "avatar": (user["avatar"] if "avatar" in user.keys() else "") or "",
            "last_login_at": user["last_login_at"],
        },
        "class": class_info,
        "pending_drafts": int(drafts),
        "unread_notifications": notify.unread_count(conn, user["id"]),
        "permissions": {
            "committee": committee,
            "write": committee,
            "review": committee,
        },
        "server_time": now_iso(),
    }


def _session_cookies(token: str, csrf: str, slug: str = "") -> list[str]:
    max_age = config.SESSION_TTL_DAYS * 86400
    cookies = [
        cookie(config.COOKIE_SID, token, max_age=max_age, http_only=True,
               secure=config.SECURE_COOKIES, path="/"),
        cookie(config.COOKIE_CSRF, csrf, max_age=max_age, http_only=False,
               secure=config.SECURE_COOKIES, path="/"),
    ]
    if slug:
        cookies.append(cookie(config.COOKIE_CLASS, slug, max_age=max_age, http_only=False,
                              secure=config.SECURE_COOKIES, path="/"))
    return cookies


@route("POST", "/api/auth/register", auth="none", csrf=False)
def register(ctx):
    student_no = ctx.need("student_no", maxlen=20)
    if not STUDENT_NO_RE.match(student_no):
        raise invalid("学号应为 4-20 位字母或数字", field="student_no")
    name = ctx.need("name", maxlen=30)
    password = ctx.b("password")
    invite_code = (ctx.b("invite_code") or "").strip().upper()
    if not invite_code:
        raise invalid("请输入班级邀请码", field="invite_code")

    target = classes.find_by_invite(invite_code)
    if target is not None:
        slug, db_path = target
        conn = ctx.conn if classes.slug_of_path(db_path) == ctx.slug else db.connect(db_path)
        own = conn is ctx.conn
    else:
        slug, conn, own = ctx.slug, ctx.conn, True
    try:
        cls = db.one(conn, "SELECT * FROM classes WHERE invite_code = ?", (invite_code,))
        if cls is None:
            raise invalid("邀请码无效，请向班委确认", field="invite_code")

        exists = db.one(conn, "SELECT id FROM users WHERE student_no = ?", (student_no,))
        if exists is not None:
            raise conflict("该学号已注册，请直接登录", field="student_no")

        password_hash = auth.hash_password(password)
        now = now_iso()
        uid = db.execute(conn,
            "INSERT INTO users (class_id, student_no, name, role, status, password_hash, "
            "password_enc, created_at) VALUES (?, ?, ?, 'student', 'pending', ?, ?, ?)",
            (cls["id"], student_no, name, password_hash, crypto.encrypt(password), now),
        )
        token, csrf = auth.create_session(conn, uid, ctx.ua, ctx.ip)
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, uid))
        user = db.one(conn, "SELECT * FROM users WHERE id = ?", (uid,))
        audit.log(conn, uid, "auth.register", f"user:{uid}",
                  {"class_id": cls["id"], "student_no": student_no}, ctx.ip)
        return Response(201, profile(conn, user), cookies=_session_cookies(token, csrf, slug))
    finally:
        if not own:
            conn.close()


def _match_user(conn, student_no: str, password: str):
    user = db.one(conn, "SELECT * FROM users WHERE student_no = ?", (student_no,))
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return None
    return user


def _locate_user(ctx, student_no: str, password: str):
    """先查当前班级库；找不到再跨班查（一班一库，学号唯一）。

    返回 ``(conn, slug, user, owned)``；``owned=False`` 表示 conn 是临时打开的，
    调用方负责关闭。
    """
    user = _match_user(ctx.conn, student_no, password)
    if user is not None:
        return ctx.conn, ctx.slug, user, True
    for slug, path in classes.iter_dbs():
        if slug == ctx.slug:
            continue
        try:
            conn = db.connect(path)
        except Exception:
            continue
        try:
            user = _match_user(conn, student_no, password)
        except Exception:
            user = None
        if user is not None:
            return conn, slug, user, False
        conn.close()
    return None, "", None, True


@route("POST", "/api/auth/login", auth="none", csrf=False)
def login(ctx):
    student_no = ctx.need("student_no", maxlen=20)
    password = ctx.b("password") or ""
    if _too_many_fails(ctx.ip):
        raise rate_limited("登录尝试过于频繁，请 5 分钟后再试")

    conn, slug, user, owned = _locate_user(ctx, student_no, password)
    if user is None:
        _record_fail(ctx.ip)
        raise ApiError("学号或密码错误", code="invalid_credentials", status=401)
    try:
        if user["status"] == "disabled":
            raise forbidden("账号已被停用，请联系班委")

        _clear_fails(ctx.ip)
        now = now_iso()
        token, csrf = auth.create_session(conn, user["id"], ctx.ua, ctx.ip)
        conn.execute(
            "UPDATE users SET last_login_at = ?, "
            "login_count = COALESCE(login_count, 0) + 1, last_ip = ?, last_ua = ? WHERE id = ?",
            (now, ctx.ip, ctx.ua, user["id"]),
        )
        audit.log(conn, user["id"], "auth.login", f"user:{user['id']}", {"slug": slug}, ctx.ip)
        fresh = db.one(conn, "SELECT * FROM users WHERE id = ?", (user["id"],))
        auth.purge_expired(conn)
        return Response(200, profile(conn, fresh),
                        cookies=_session_cookies(token, csrf, slug))
    finally:
        if not owned:
            conn.close()


@route("POST", "/api/auth/change-password")
def change_password(ctx):
    old = ctx.b("old_password") or ""
    new = ctx.b("new_password") or ""
    if not auth.verify_password(old, ctx.user["password_hash"]):
        raise invalid("原密码不正确", field="old_password")
    if len(new) < 8:
        raise invalid("新密码至少 8 位", field="new_password")
    if len(new) > 64:
        raise invalid("新密码最多 64 位", field="new_password")
    if new == old:
        raise invalid("新密码不能与原密码相同", field="new_password")
    ctx.conn.execute(
        "UPDATE users SET password_hash = ?, password_enc = ?, must_change_password = 0 "
        "WHERE id = ?",
        (auth.hash_password(new), crypto.encrypt(new), ctx.user_id),
    )
    audit.log(ctx.conn, ctx.user_id, "auth.change_password", f"user:{ctx.user_id}", {}, ctx.ip)
    return {"ok": True}


@route("POST", "/api/auth/avatar", allow_pending=True)
def update_avatar(ctx):
    """保存用户上传的方形头像（前端已压缩为 256px data URL）。"""
    avatar = ctx.b("avatar")
    if not isinstance(avatar, str):
        raise invalid("头像数据格式不正确", field="avatar")
    avatar = avatar.strip()
    if avatar:
        if len(avatar) > AVATAR_MAX_CHARS:
            raise invalid("头像文件过大，请重新选择", field="avatar")
        if not AVATAR_RE.match(avatar):
            raise invalid("仅支持 PNG、JPEG 或 WebP 头像", field="avatar")
    ctx.conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar, ctx.user_id))
    audit.log(ctx.conn, ctx.user_id, "auth.update_avatar", f"user:{ctx.user_id}",
              {"bytes": len(avatar)}, ctx.ip)
    return {"ok": True, "avatar": avatar}


@route("POST", "/api/auth/logout", auth="none", csrf=False)
def logout(ctx):
    token = ctx.cookies.get(config.COOKIE_SID)
    if token:
        auth.revoke_session(ctx.conn, token)
    clear = [
        cookie(config.COOKIE_SID, "", max_age=0, http_only=True, path="/"),
        cookie(config.COOKIE_CSRF, "", max_age=0, path="/"),
    ]
    return Response(200, {"ok": True}, cookies=clear)


@route("GET", "/api/auth/me", allow_pending=True)
def me(ctx):
    if ctx.user is None:
        raise unauthenticated()
    return profile(ctx.conn, ctx.user)
