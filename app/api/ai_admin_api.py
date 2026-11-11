"""AI 助手配置（仅管理员）：网页里填 DeepSeek Key，无需改环境变量。"""
from __future__ import annotations

from .. import audit
from ..ai import provider
from ..errors import forbidden, invalid
from ..router import route


def _admin_only(ctx) -> None:
    if not ctx.user or ctx.user["role"] != "admin":
        raise forbidden("只有管理员可以配置 AI 助手")


@route("GET", "/api/admin/ai")
def get_ai(ctx):
    _admin_only(ctx)
    provider.load_from_db(ctx.conn)
    return {
        "enabled": provider.enabled(),
        "base_url": provider.base_url(),
        "model": provider.model(),
        "has_key": bool(provider.api_key()),
        "default_base_url": provider.DEFAULT_BASE_URL,
        "default_model": provider.DEFAULT_MODEL,
    }


@route("POST", "/api/admin/ai")
def set_ai(ctx):
    _admin_only(ctx)
    current = provider.load_from_db(ctx.conn)
    cfg = dict(current)
    for field in ("api_key", "base_url", "model"):
        if field in ctx.body:
            value = ctx.body.get(field)
            cfg[field] = str(value).strip() if isinstance(value, str) else ""
    if cfg.get("base_url") and not cfg["base_url"].startswith(("http://", "https://")):
        raise invalid("base_url 必须是 http(s) 地址", field="base_url")
    provider.save_to_db(ctx.conn, cfg)
    audit.log(ctx.conn, ctx.user_id, "admin.ai_config", "settings:ai",
              {"model": cfg.get("model"), "has_key": bool(cfg.get("api_key"))}, ctx.ip)
    return {
        "ok": True,
        "enabled": provider.enabled(),
        "has_key": bool(provider.api_key()),
        "base_url": provider.base_url(),
        "model": provider.model(),
    }


@route("POST", "/api/admin/ai/test")
def test_ai(ctx):
    _admin_only(ctx)
    provider.load_from_db(ctx.conn)
    if not provider.enabled():
        raise invalid("还没有填 API Key", field="api_key")
    try:
        result = provider.complete_json('请只回复一个 JSON 对象：{"ok": true}')
    except provider.AIError as exc:
        raise invalid(f"调用失败：{exc}", field="api_key") from None
    return {"ok": bool(result.get("ok")), "model": result.get("_model", provider.model())}
