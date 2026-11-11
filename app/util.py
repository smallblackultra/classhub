"""时间 / 字符串 / JSON 等无依赖工具函数。"""
from __future__ import annotations

import hashlib
import json
import secrets
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import invalid


def _china_tz():
    """Windows 上未装 tzdata 时 zoneinfo 找不到 Asia/Shanghai；中国无夏令时，固定 +08:00 等价。"""
    try:
        return ZoneInfo("Asia/Shanghai")
    except (ZoneInfoNotFoundError, ValueError):
        return timezone(timedelta(hours=8), "Asia/Shanghai")


LOCAL_TZ = _china_tz()
UTC = timezone.utc


# ---------------------------------------------------------------- 时间

def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def now_iso() -> str:
    return iso_utc(utcnow())


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_local(dt: datetime) -> str:
    return dt.astimezone(LOCAL_TZ).isoformat(timespec="seconds")


def local_now() -> datetime:
    return datetime.now(UTC).astimezone(LOCAL_TZ)


def parse_iso(value: str) -> datetime:
    """解析 ISO8601；无时区按北京时间理解；统一返回 UTC。"""
    if not isinstance(value, str) or not value.strip():
        raise invalid("时间格式不正确", field="due_at")
    s = value.strip()
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise invalid("时间格式不正确，应为 ISO8601（如 2026-11-11T23:59）", field="due_at") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(UTC).replace(microsecond=0)


def parse_due_input(value) -> tuple[str | None, int]:
    """把前端提交的 due_at 规范化成 (UTC ISO 字符串或 None, all_day 0/1)。

    接受 "2026-11-11"（视为当天 23:59:59，all_day=1）或完整 ISO 时间。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, 0
    if not isinstance(value, str):
        raise invalid("due_at 必须是字符串", field="due_at")
    s = value.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = date.fromisoformat(s)
        except ValueError:
            raise invalid("日期格式不正确，应为 YYYY-MM-DD", field="due_at") from None
        dt = datetime.combine(d, time(23, 59, 59), tzinfo=LOCAL_TZ)
        return iso_utc(dt), 1
    return iso_utc(parse_iso(s)), 0


def day_bounds_utc(d: date) -> tuple[str, str]:
    """本地某一天 00:00:00 ~ 23:59:59 对应的 UTC 字符串。"""
    start = datetime.combine(d, time(0, 0, 0), tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return iso_utc(start), iso_utc(end)


def local_date_str(dt_or_iso) -> str | None:
    """UTC 时间/字符串 → 本地日期 YYYY-MM-DD。"""
    if dt_or_iso is None:
        return None
    if isinstance(dt_or_iso, str):
        try:
            dt = parse_iso(dt_or_iso)
        except Exception:
            return None
    else:
        dt = dt_or_iso
    return dt.astimezone(LOCAL_TZ).date().isoformat()


def today_local() -> date:
    return local_now().date()


# ---------------------------------------------------------------- 字符串

def text(value, field: str, *, maxlen: int, required: bool = False,
         default: str = "") -> str:
    if value is None:
        if required:
            raise invalid(f"{field} 不能为空", field=field)
        return default
    if not isinstance(value, str):
        raise invalid(f"{field} 必须是字符串", field=field)
    s = value.strip()
    if required and not s:
        raise invalid(f"{field} 不能为空", field=field)
    if len(s) > maxlen:
        raise invalid(f"{field} 不能超过 {maxlen} 个字符", field=field)
    return s


def one_of(value, allowed: tuple[str, ...], field: str, default: str | None = None) -> str:
    if value is None:
        if default is not None:
            return default
        raise invalid(f"{field} 必填", field=field)
    if not isinstance(value, str) or value not in allowed:
        raise invalid(f"{field} 取值必须是 {'/'.join(allowed)}", field=field)
    return value


def normalize_title(title: str) -> str:
    """标题归一化：全半角、大小写、空白，用于去重指纹。"""
    s = unicodedata.normalize("NFKC", title or "").lower()
    s = "".join(ch for ch in s if not ch.isspace())
    s = s.strip("。.,，、:：;；!！?？()（）[]【】")
    return s


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def new_token(nbytes: int = 32) -> str:
    return secrets.token_hex(nbytes)


def new_invite_code(length: int = 8) -> str:
    from .config import INVITE_ALPHABET
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(length))


# ---------------------------------------------------------------- JSON

def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def jload(raw, default=None):
    if raw is None or raw == "":
        return default if default is not None else {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default if default is not None else {}


def truthy_int(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("1", "true", "yes", "on") else 0
    return 0


def clamp_page(value, default: int = 1, maximum: int = 500) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))
