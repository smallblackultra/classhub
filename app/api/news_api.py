"""门户首页资讯接口：公开只读，缓存由 app.news 维护。"""
from __future__ import annotations

from .. import news
from ..router import route


@route("GET", "/api/news", auth="none", csrf=False)
def news_list(ctx):
    raw = (ctx.query.get("limit") or ["3"])[0]
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = 3
    return news.get_payload(limit=limit)
