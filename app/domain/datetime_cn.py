"""中文相对/绝对时间解析（规则兜底，纯标准库）。

设计目标：**不追求全对，追求可解释**。凡是拿不准的，返回 has_date=False 或让
调用方标记 needs_review，绝不悄悄猜一个错的日期。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from ..util import LOCAL_TZ

WEEKDAY_INDEX = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

RE_ISO = re.compile(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?")
RE_CN_MD = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
RE_SLASH = re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])")
# 「11-10」「11.10」这类简写：只有两位月+两位日、或月份 ≥10 时才认，
# 避免把「习题 3.1 - 3.5」里的章节号当成 3 月 1 日。
RE_DASH_MD = re.compile(r"(?<![\d.\-/])(\d{1,2})\s*[.\-]\s*(\d{1,2})(?![\d.\-/])")
RE_WEEK_PREFIXED = re.compile(r"(下下|下|本|这)\s*(?:周|星期|礼拜)\s*([一二三四五六日天1-7])")
RE_WEEK_PLAIN = re.compile(r"(?:周|星期|礼拜)\s*([一二三四五六日天1-7])")
RE_RELATIVE = re.compile(r"(大后天|后天|明天|明日|明晚|今晚|今天|今日)")
RE_TIME = re.compile(
    r"(上午|下午|晚上|中午|凌晨|早上)?\s*(\d{1,2})\s*(?:[:：点时])\s*(\d{1,2})?\s*分?"
)
RE_MONTH_ONLY = re.compile(r"(?<!\d)(\d{1,2})\s*月(?!\s*\d)")

RELATIVE_OFFSET = {
    "今天": 0, "今日": 0, "今晚": 0,
    "明天": 1, "明日": 1, "明晚": 1,
    "后天": 2, "大后天": 3,
}


def _today(now: datetime | None = None) -> date:
    now = now or datetime.now(LOCAL_TZ)
    return now.astimezone(LOCAL_TZ).date()


def parse_time(text: str) -> tuple[int, int, str] | None:
    """返回 (hour, minute, 匹配文本)。"""
    m = RE_TIME.search(text)
    if not m:
        return None
    prefix, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
    if hh > 23 or mm > 59:
        return None
    if prefix in ("下午", "晚上") and hh < 12:
        hh += 12
    elif prefix == "中午" and hh < 11:
        hh += 12
    elif prefix == "凌晨" and hh == 12:
        hh = 0
    # “今晚8点”“明晚 7 点半”：时间前的“晚”不在前缀里，单独处理
    before = text[max(0, m.start() - 6):m.start()]
    if hh < 12 and "晚" in before:
        hh += 12
    if hh == 24:
        hh = 0
    return hh, mm, m.group(0).strip()


def _md_date(month: int, day: int, today: date) -> date | None:
    """月/日 → 日期；12 月收到 1、2 月的日期视为跨年。"""
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    # 明显跨年：消息在 12 月、日期在 1/2 月
    if d < today - timedelta(days=200):
        try:
            d = date(today.year + 1, month, day)
        except ValueError:
            return None
    return d


def parse_date(text: str, now: datetime | None = None) -> tuple[date, str] | None:
    """从文本里找最可能的日期，返回 (日期, 命中的原文片段)。"""
    today = _today(now)

    m = RE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m.group(0).strip()
        except ValueError:
            return None

    m = RE_CN_MD.search(text)
    if m:
        d = _md_date(int(m.group(1)), int(m.group(2)), today)
        if d is not None:
            return d, m.group(0).strip()

    m = RE_DASH_MD.search(text)
    if m:
        raw_m, raw_d = m.group(1), m.group(2)
        if (len(raw_m) == 2 and len(raw_d) == 2) or int(raw_m) >= 10:
            d = _md_date(int(raw_m), int(raw_d), today)
            if d is not None:
                return d, m.group(0).strip()

    m = RE_SLASH.search(text)
    if m:
        d = _md_date(int(m.group(1)), int(m.group(2)), today)
        if d is not None:
            return d, m.group(0).strip()

    m = RE_WEEK_PREFIXED.search(text)
    if m:
        prefix, wd = m.group(1), WEEKDAY_INDEX[m.group(2)]
        week_start = today - timedelta(days=today.weekday())
        weeks = {"本": 0, "这": 0, "下": 1, "下下": 2}[prefix]
        return week_start + timedelta(days=wd + 7 * weeks), m.group(0).strip()

    m = RE_WEEK_PLAIN.search(text)
    if m:
        wd = WEEKDAY_INDEX[m.group(1)]
        week_start = today - timedelta(days=today.weekday())
        d = week_start + timedelta(days=wd)
        if d < today:
            d += timedelta(days=7)
        return d, m.group(0).strip()

    m = RE_RELATIVE.search(text)
    if m:
        return today + timedelta(days=RELATIVE_OFFSET[m.group(1)]), m.group(0).strip()

    return None


def parse_due(text: str, now: datetime | None = None) -> dict | None:
    """解析“什么时候截止”。

    返回 {"date": date, "time": "23:59"|None, "has_time": bool, "raw": str, "date_raw": str}。
    完全没找到日期时返回 None，由上层决定是进“未解析队列”还是标记缺字段。
    """
    if not text:
        return None
    found = parse_date(text, now)
    if not found:
        return None
    d, date_raw = found
    t = parse_time(text)
    if t:
        hh, mm, time_raw = t
        return {"date": d, "time": f"{hh:02d}:{mm:02d}", "has_time": True,
                "raw": f"{date_raw} {time_raw}".strip(), "date_raw": date_raw}
    return {"date": d, "time": None, "has_time": False, "raw": date_raw, "date_raw": date_raw}


def due_to_iso(parsed: dict) -> str:
    """把 parse_due 的结果转成带 +08:00 的 ISO 字符串。"""
    hh, mm = (parsed["time"] or "23:59").split(":")
    dt = datetime.combine(parsed["date"], time(int(hh), int(mm), 0), tzinfo=LOCAL_TZ)
    return dt.isoformat()


def week_table(now: datetime | None = None) -> str:
    """给 LLM 的“本周日期表”，避免它把“下周三”算错。"""
    today = _today(now)
    monday = today - timedelta(days=today.weekday())
    lines = []
    for i, name in enumerate(WEEKDAY_NAMES):
        d = monday + timedelta(days=i)
        mark = "（今天）" if d == today else ""
        lines.append(f"{name} {d.month:02d}-{d.day:02d}{mark}")
    return "；".join(lines)


def normalize_due_input(value: str, now: datetime | None = None) -> str | None:
    """把“11月11日 23:59”“下周三”这类人类输入转成 ISO；失败返回 None。"""
    parsed = parse_due(value, now)
    return due_to_iso(parsed) if parsed else None


if __name__ == "__main__":  # 手工自测
    for s in ("11月11日 23:59 前提交", "下周三前交报告", "今晚8点前", "2026-11-20 18:00",
              "这周五", "10天后？", "第5章实验报告"):
        print(s, "=>", parse_due(s))
