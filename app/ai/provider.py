"""LLM Provider：OpenAI 兼容的 chat/completions（默认 DeepSeek）。

只依赖标准库。任何网络/协议异常都抛 `AIError`，由上层降级到规则抽取——
**AI 挂了不能影响草稿入库**。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).with_name("prompts") / f"{PROMPT_VERSION}.md"


class AIError(RuntimeError):
    """AI 调用失败（网络、鉴权、限流、返回格式）。"""


SETTINGS_KEY = "ai_config"
_override: dict = {}


def configure(cfg: dict | None) -> None:
    """由管理员在网页里保存的配置，优先级高于环境变量。"""
    global _override
    _override = dict(cfg or {})


def load_from_db(conn) -> dict:
    from .. import db  # 延迟导入，避免 ai 包反向依赖
    row = db.one(conn, "SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,))
    import json as _json
    cfg: dict = {}
    if row and row["value"]:
        try:
            cfg = _json.loads(row["value"])
        except ValueError:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    configure(cfg)
    return dict(_override)


def save_to_db(conn, cfg: dict) -> dict:
    import json as _json
    from .. import db
    from ..util import now_iso
    clean = {k: cfg.get(k) for k in ("api_key", "base_url", "model") if cfg.get(k)}
    db.execute(
        conn,
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (SETTINGS_KEY, _json.dumps(clean, ensure_ascii=False), now_iso()),
    )
    configure(clean)
    return clean


def _get(name: str, env: str, default: str = "") -> str:
    return (_override.get(name) or os.environ.get(env) or default)


def api_key() -> str:
    return _get("api_key", "CDH_AI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""


def base_url() -> str:
    return (_get("base_url", "CDH_AI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def model() -> str:
    return _get("model", "CDH_AI_MODEL", DEFAULT_MODEL)


def enabled() -> bool:
    return bool(api_key())


def timeout_seconds() -> float:
    try:
        return float(os.environ.get("CDH_AI_TIMEOUT") or 25)
    except ValueError:
        return 25.0


_prompt_cache: str | None = None


def system_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        try:
            _prompt_cache = PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - 文件缺失属于部署错误
            raise AIError(f"读取 prompt 失败：{exc}") from exc
    return _prompt_cache


def complete_json(user_content: str) -> dict:
    """调用模型并解析出 JSON 对象。"""
    key = api_key()
    if not key:
        raise AIError("未配置 AI Key（CDH_AI_API_KEY / DEEPSEEK_API_KEY）")
    payload = {
        "model": model(),
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base_url()}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds()) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
        raise AIError(f"模型返回 HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIError(f"模型请求失败：{exc}") from exc

    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError(f"模型响应结构异常：{body[:200]}") from exc

    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except ValueError as exc:
        raise AIError(f"模型输出不是合法 JSON：{content[:200]}") from exc
    if not isinstance(parsed, dict):
        raise AIError("模型输出不是 JSON 对象")
    parsed["_usage"] = data.get("usage", {})
    parsed["_model"] = data.get("model", model())
    return parsed
