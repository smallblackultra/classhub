"""极简路由表：装饰器注册 + 路径模板匹配。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_ROUTES: list["Route"] = []


def _compile(path: str) -> re.Pattern:
    parts = []
    for seg in [s for s in path.strip("/").split("/") if s != ""]:
        if seg.startswith("{") and seg.endswith("}"):
            parts.append(f"(?P<{seg[1:-1]}>[^/]+)")
        else:
            parts.append(re.escape(seg))
    return re.compile("^/" + "/".join(parts) + "/?$")


@dataclass
class Route:
    method: str
    pattern: re.Pattern
    handler: Callable
    auth: str = "required"      # required | none
    committee: bool = False     # 仅班委
    csrf: bool = True           # 需要 X-CSRF 双提交
    allow_pending: bool = False  # pending 用户也放行（仅 /auth/me 等）


def route(method: str, path: str, *, auth: str = "required", committee: bool = False,
          csrf: bool = True, allow_pending: bool = False):
    def deco(fn: Callable):
        _ROUTES.append(Route(method.upper(), _compile(path), fn, auth, committee, csrf, allow_pending))
        return fn
    return deco


def match(method: str, path: str):
    """返回 (route, params) 或 (None, 允许的方法集合)。"""
    allowed = set()
    for r in _ROUTES:
        m = r.pattern.match(path)
        if not m:
            continue
        if r.method == method:
            return r, m.groupdict()
        allowed.add(r.method)
    return None, allowed


def all_routes() -> list[Route]:
    return list(_ROUTES)
