"""请求上下文与响应对象。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .errors import invalid


@dataclass
class Response:
    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)
    raw: bytes | None = None
    content_type: str = "application/json; charset=utf-8"


@dataclass
class Ctx:
    conn: sqlite3.Connection
    method: str
    path: str
    params: dict
    query: dict[str, list[str]]
    body: dict
    cookies: dict[str, str]
    ip: str
    ua: str
    user: sqlite3.Row | None = None
    session: sqlite3.Row | None = None
    headers: dict[str, str] = field(default_factory=dict)
    slug: str = ""

    # ---------- 入参读取 ----------
    def q(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        if not values:
            return default
        return values[0]

    def qall(self, name: str) -> list[str]:
        return list(self.query.get(name) or [])

    def b(self, name: str, default=None):
        return self.body.get(name, default)

    def need(self, name: str, *, maxlen: int = 200) -> str:
        value = self.body.get(name)
        if not isinstance(value, str) or not value.strip():
            raise invalid(f"{name} 不能为空", field=name)
        return value.strip()[:maxlen]

    @property
    def class_id(self) -> int:
        return int(self.user["class_id"])

    @property
    def user_id(self) -> int:
        return int(self.user["id"])


def cookie(name: str, value: str, *, max_age: int | None = None, http_only: bool = False,
           secure: bool = False, same_site: str = "Lax", path: str = "/") -> str:
    parts = [f"{name}={value}", f"Path={path}", f"SameSite={same_site}"]
    if max_age is not None:
        parts.append(f"Max-Age={int(max_age)}")
    if http_only:
        parts.append("HttpOnly")
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
