"""抽取编排：规则优先兜底，LLM 可用时融合，并做时间合理性校验。

输出是「可入库的字段 + 可展示的元信息」，不直接碰数据库。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from ..domain import datetime_cn
from ..ingest import rules
from ..util import LOCAL_TZ, iso_utc, now_iso, parse_iso
from . import provider

CATEGORIES = ("homework", "form", "task", "exam")
AUDIENCES = ("class", "committee")
WEEK_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
RELATIVE_WORDS = ("今天", "今日", "明天", "明日", "后天", "下周", "本周", "这周", "周")


def _as_iso(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip().replace(" ", "T", 1) if len(value) > 10 else value.strip()
    try:
        dt = parse_iso(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).isoformat(timespec="seconds")


def context_block(occurred_at: str | None, source_hint: str = "") -> str:
    occurred = parse_iso(occurred_at) if occurred_at else now_iso()
    occurred = occurred.astimezone(LOCAL_TZ)
    lines = [
        f"消息发送时间：{occurred:%Y-%m-%d %H:%M}（{WEEK_CN[occurred.weekday()]}，Asia/Shanghai）",
        f"本周日期表：{datetime_cn.week_table(occurred)}",
    ]
    if source_hint:
        lines.append(f"消息来源：{source_hint}")
    return "\n".join(lines)


def _user_message(text: str, occurred_at: str | None, hints: dict) -> str:
    parts = [context_block(occurred_at, hints.get("source_hint", ""))]
    if hints.get("title"):
        parts.append(f"页面标题（可作为 title 参考）：{hints['title']}")
    if hints.get("course"):
        parts.append(f"课程提示：{hints['course']}")
    if hints.get("due_text"):
        parts.append(f"截止时间提示：{hints['due_text']}")
    parts.append("消息原文：\n\"\"\"\n" + text.strip()[:2000] + "\n\"\"\"")
    return "\n\n".join(parts)


def check_due(due_iso: str | None, occurred_at: str | None, text: str,
              rule_due_iso: str | None) -> list[str]:
    warnings: list[str] = []
    if not due_iso:
        return ["未能解析出截止时间"]
    due = parse_iso(due_iso)
    occurred = parse_iso(occurred_at) if occurred_at else datetime.now(LOCAL_TZ)
    if due.tzinfo is None:
        due = due.replace(tzinfo=LOCAL_TZ)
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=LOCAL_TZ)
    if due < occurred - timedelta(days=1):
        warnings.append("截止时间早于消息时间，可能是过去的事项")
    if due > occurred + timedelta(days=400):
        warnings.append("截止时间超过一年，请确认是否写错年份")
    if rule_due_iso and any(w in text for w in RELATIVE_WORDS):
        gap = abs((parse_iso(due_iso) - parse_iso(rule_due_iso)).total_seconds()) / 86400
        if gap > 2:
            warnings.append(f"关键词解析与模型结果相差 {gap:.1f} 天")
    return warnings


def _merge(rule_res: dict, ai: dict, text: str, occurred_at: str | None) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    fields = dict(rule_res)

    ai_task = ai.get("is_task")
    if ai_task is False and not rule_res.get("due_at"):
        fields["is_task"] = False

    title = str(ai.get("title") or "").strip()
    if 2 <= len(title) <= 60:
        fields["title"] = title

    category = str(ai.get("category") or "")
    if category in CATEGORIES:
        fields["category"] = category

    ai_aud = str(ai.get("audience") or ai.get("audience_guess") or "")
    if not rule_res.get("audience_confident") and ai_aud in AUDIENCES:
        fields["audience"] = ai_aud
        fields["audience_reason"] = str(ai.get("audience_reason") or "模型判断")

    course = str(ai.get("course") or "").strip()
    if course:
        fields["course"] = course[:100]

    ai_due = _as_iso(ai.get("due_at"))
    rule_due = rule_res.get("due_at")
    if ai_due:
        fields["due_at"] = ai_due
        warnings.extend(check_due(ai_due, occurred_at, text, rule_due))
        if rule_due and any(w in text for w in RELATIVE_WORDS):
            gap = abs((parse_iso(ai_due) - parse_iso(rule_due)).total_seconds()) / 86400
            if gap > 2:
                warnings.append(f"规则解析结果（{rule_due[:16]}）与模型差 {gap:.1f} 天")
    elif rule_due:
        warnings.append("模型未给出截止时间，已采用规则解析结果")

    link = str(ai.get("link") or "")
    if link.startswith(("http://", "https://")):
        fields["link"] = link[:1000]

    try:
        conf = float(ai.get("confidence"))
        if 0 <= conf <= 1:
            fields["confidence"] = round(conf, 2)
    except (TypeError, ValueError):
        pass

    raw = str(ai.get("due_at_raw") or "").strip()
    if raw:
        fields["due_at_raw"] = raw[:100]

    missing = []
    if not fields.get("due_at"):
        missing.append("due_at")
    if len(str(fields.get("title") or "")) < 2:
        missing.append("title")
    fields["missing_fields"] = missing
    fields["needs_review"] = bool(
        missing or warnings or fields.get("confidence", 0) < 0.7
        or not fields.get("audience_confident")
    )
    return fields, warnings


def extract(text: str, *, occurred_at: str | None = None, hints: dict | None = None,
            use_ai: bool = True) -> dict:
    """返回 {"fields": {...}, "meta": {...}}。永不抛异常（除非代码 bug）。"""
    hints = hints or {}
    rule_res = rules.extract_by_rules(text, occurred_at=occurred_at, hints=hints)
    meta = {
        "engine": "rules",
        "provider": "rules",
        "model": "",
        "prompt_version": provider.PROMPT_VERSION,
        "used_ai": False,
        "error": "",
        "warnings": [],
        "raw": "",
        "audience_reason": rule_res.get("audience_reason", ""),
    }

    ai_ok = False
    if use_ai and provider.enabled():
        try:
            parsed = provider.complete_json(_user_message(text, occurred_at, hints))
        except provider.AIError as exc:
            meta["error"] = str(exc)
            meta["warnings"].append(f"AI 不可用，已用规则解析：{exc}")
        else:
            ai_ok = True
            fields, warnings = _merge(rule_res, parsed, text, occurred_at)
            meta.update({
                "engine": "ai+rules",
                "provider": "deepseek",
                "model": str(parsed.get("_model") or provider.model()),
                "used_ai": True,
                "raw": json.dumps(parsed, ensure_ascii=False)[:4000],
                "warnings": warnings,
                "audience_reason": fields.get("audience_reason", ""),
            })
            return {"fields": fields, "meta": meta}

    if not ai_ok:
        rule_res["needs_review"] = bool(
            rule_res.get("needs_review") or not rule_res.get("due_at")
        )
        meta["warnings"] = meta["warnings"] + list(rule_res.get("missing_fields") or [])
    return {"fields": rule_res, "meta": meta}
