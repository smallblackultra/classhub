# -*- coding: utf-8 -*-
"""口令可逆加密（仅供管理员后台查看初始/当前口令）。

设计取舍：登录校验仍然只用 scrypt 哈希；这里额外保存一份用本机密钥加密的
口令副本，只有全站最高管理员能通过接口解密查看。密钥保存在
``data/.secret``（首次自动生成，权限 600），不在代码或数据库里。

安全边界：
- 拿到数据库但没拿到 ``data/.secret`` 的人无法还原口令；
- 拿到整机的人可以还原——这是「管理员能看口令」这一需求的固有限制，
  上线前请确认这符合你们的预期（文档 03 有说明）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path

from . import config

_SECRET_FILE = Path(config.DATA_DIR) / ".secret"
_cache: bytes | None = None


def _key() -> bytes:
    global _cache
    if _cache is not None:
        return _cache
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SECRET_FILE.is_file():
        raw = _SECRET_FILE.read_bytes()
    else:
        raw = os.urandom(32)
        _SECRET_FILE.write_bytes(raw)
        try:
            os.chmod(_SECRET_FILE, 0o600)
        except OSError:
            pass
    _cache = hashlib.sha256(b"classhub-db-v1|" + raw).digest()
    return _cache


def _keystream(nonce: bytes, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(_key() + nonce + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:size])


def encrypt(plain: str) -> str:
    data = (plain or "").encode("utf-8")
    nonce = os.urandom(8)
    body = bytes(a ^ b for a, b in zip(data, _keystream(nonce, len(data))))
    tag = hmac.new(_key(), nonce + body, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + body + tag).decode("ascii")


def decrypt(token: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except Exception:
        return ""
    if len(raw) < 24:
        return ""
    nonce, body, tag = raw[:8], raw[8:-16], raw[-16:]
    expect = hmac.new(_key(), nonce + body, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expect):
        return ""
    data = bytes(a ^ b for a, b in zip(body, _keystream(nonce, len(body))))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
