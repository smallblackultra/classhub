"""密码哈希与会话管理（无第三方依赖）。

密码格式：scrypt$N$r$p$salt_hex$hash_hex
会话：Cookie 里放明文 token，库里只存 sha256(token)。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from datetime import timedelta

from . import config
from .errors import unauthenticated, invalid
from .util import iso_utc, new_token, sha256_hex, utcnow

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 6:
        raise invalid("密码至少 6 位", field="password")
    if len(password) > 128:
        raise invalid("密码过长", field="password")
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                        p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = (stored or "").split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(hash_hex)))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# ---------------------------------------------------------------- 会话

def create_session(conn: sqlite3.Connection, user_id: int, ua: str = "", ip: str = "") -> tuple[str, str]:
    token = new_token(32)
    csrf = new_token(16)
    now = utcnow()
    expires = now + timedelta(days=config.SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (id, user_id, csrf, created_at, expires_at, ua, ip) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sha256_hex(token), user_id, csrf, iso_utc(now), iso_utc(expires), (ua or "")[:300], (ip or "")[:64]),
    )
    return token, csrf


def find_session(conn: sqlite3.Connection, token: str):
    """返回 (session_row, user_row)，无效/过期返回 None。"""
    if not token:
        return None
    sid = sha256_hex(token)
    sess = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if sess is None:
        return None
    if sess["expires_at"] <= iso_utc(utcnow()):
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        return None
    user = conn.execute("SELECT * FROM users WHERE id = ?", (sess["user_id"],)).fetchone()
    if user is None:
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        return None
    return sess, user


def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE id = ?", (sha256_hex(token),))


def purge_expired(conn: sqlite3.Connection) -> int:
    cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso_utc(utcnow()),))
    return cur.rowcount or 0


def require_user(user) -> None:
    if user is None:
        raise unauthenticated()
