"""学院官网资讯抓取与本地缓存。

只抓取微电子学院官网公开的两个栏目；解析、排序、缓存全部使用标准库。
首页请求不会等待远端站点：缓存过期时优先返回旧数据，并在后台刷新。
"""
from __future__ import annotations

import html
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import config, db

SOURCE_HOST = "wdzxy.hfut.edu.cn"
SOURCES = (
    {
        "key": "notice",
        "label": "通知公告",
        "url": "https://wdzxy.hfut.edu.cn/5630/list.htm",
    },
    {
        "key": "news",
        "label": "我院新闻",
        "url": "https://wdzxy.hfut.edu.cn/5628/list.htm",
    },
)
SOURCE_BY_KEY = {item["key"]: item for item in SOURCES}
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_ITEM_RE = re.compile(r'<li\b[^>]*class="[^"]*\bnews\b[^"]*"[^>]*>(.*?)</li>', re.S | re.I)
_HREF_RE = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', re.I)
_H4_RE = re.compile(r"<h4\b[^>]*>(.*?)</h4>", re.S | re.I)
_DESC_RE = re.compile(
    r'<div\b[^>]*class="[^"]*\bdesc\b[^"]*"[^>]*>(.*?)</div>', re.S | re.I
)
_DATE_RE = re.compile(
    r"(20\d{2})\s*[年./-]\s*(\d{1,2})(?:\s*[月./-]\s*(\d{1,2})\s*日?)?"
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portal_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE(category, source_url)
);
CREATE INDEX IF NOT EXISTS idx_portal_news_category
    ON portal_news(category, published_at DESC);
CREATE TABLE IF NOT EXISTS portal_news_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_refresh_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(value: str) -> str:
    value = html.unescape(_TAG_RE.sub(" ", value or ""))
    value = value.replace("\u200b", "").replace("\xa0", " ")
    return _WS_RE.sub(" ", value).strip()


def _safe_url(href: str, base_url: str) -> str:
    """只允许学院官网的 http(s) 链接，并统一升级为 https。"""
    if not href:
        return ""
    try:
        parts = urlsplit(urljoin(base_url, href.strip()))
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https"):
        return ""
    if (parts.hostname or "").lower() != SOURCE_HOST:
        return ""
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))


def _parse_date(text: str, day_hint: str = "") -> str:
    """解析 2026-11-10 或 "10 2026-11" 两类日期；非法日期返回空。"""
    text = _clean_text(text)
    matched = _DATE_RE.search(text)
    if not matched:
        return ""
    year, month, day = matched.group(1), matched.group(2), matched.group(3)
    if not day and day_hint:
        day = day_hint
    if not day:
        # 形如 "16 2026-01" 时，日期块里的第一个两位数是“日”。
        prefix = re.match(r"\s*(\d{1,2})(?!\d)", text)
        if prefix:
            day = prefix.group(1)
    if not day:
        return ""
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        return ""
    return parsed.isoformat()


def parse_list(html_text: str, base_url: str, category: str) -> list[dict]:
    """从栏目列表页提取条目，按发布日期倒序。纯函数，便于离线测试。"""
    if not html_text:
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for block in _ITEM_RE.findall(html_text):
        href_match = _HREF_RE.search(block)
        title_match = _H4_RE.search(block)
        if not href_match or not title_match:
            # 列表模板里的 {缩略图} 占位 li 没有标题和链接，直接跳过。
            continue
        url = _safe_url(href_match.group(1), base_url)
        title = _clean_text(title_match.group(1))
        if not url or not title or url in seen:
            continue
        date_match = re.search(
            r'<div\b[^>]*class="[^"]*\bdate\b[^"]*"[^>]*>(.*?)</div>', block, re.S | re.I
        )
        date_text = _clean_text(date_match.group(1)) if date_match else ""
        day_hint = ""
        if date_match:
            day_match = re.search(r"<em\b[^>]*>(.*?)</em>", date_match.group(1), re.S | re.I)
            if day_match:
                day_hint = _clean_text(day_match.group(1))
        published_at = _parse_date(date_text, day_hint)
        if not published_at:
            continue
        desc_match = _DESC_RE.search(block)
        summary = _clean_text(desc_match.group(1)) if desc_match else ""
        if len(summary) > 220:
            summary = summary[:219].rstrip() + "…"
        seen.add(url)
        items.append(
            {
                "category": category,
                "title": title[:240],
                "summary": summary,
                "url": url,
                "published_at": published_at,
            }
        )
    items.sort(key=lambda item: (item["published_at"], item["url"]), reverse=True)
    return items


def fetch_html(url: str, timeout: int | None = None) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout or config.NEWS_TIMEOUT) as resp:
        raw = resp.read(config.NEWS_MAX_BYTES + 1)
        if len(raw) > config.NEWS_MAX_BYTES:
            raise ValueError("响应体超过大小限制")
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    return db.connect(path or config.PORTAL_DB)


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def _meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM portal_news_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO portal_news_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def read_cached(conn: sqlite3.Connection, limit: int = 3) -> dict:
    items: dict[str, list[dict]] = {}
    for source in SOURCES:
        rows = conn.execute(
            "SELECT category, title, summary, source_url, published_at "
            "FROM portal_news WHERE category = ? "
            "ORDER BY published_at DESC, id DESC LIMIT ?",
            (source["key"], limit),
        ).fetchall()
        items[source["key"]] = [
            {
                "category": row["category"],
                "title": row["title"],
                "summary": row["summary"],
                "url": row["source_url"],
                "published_at": row["published_at"],
            }
            for row in rows
        ]
    return items


def _save_source(conn: sqlite3.Connection, category: str, items: list[dict]) -> None:
    if category not in SOURCE_BY_KEY:
        raise ValueError("未知资讯栏目")
    now = _now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM portal_news WHERE category = ?", (category,))
        conn.executemany(
            "INSERT INTO portal_news(category, title, summary, source_url, published_at, fetched_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            [
                (category, item["title"], item["summary"], item["url"],
                 item["published_at"], now)
                for item in items
            ],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def refresh(conn: sqlite3.Connection, fetcher=fetch_html) -> dict:
    """抓取两个栏目；单个栏目失败不影响另一个，失败时保留旧缓存。"""
    init_schema(conn)
    errors: list[str] = []
    saved = 0
    for source in SOURCES:
        try:
            text = fetcher(source["url"])
            items = parse_list(text, source["url"], source["key"])
            if not items:
                raise ValueError("页面中没有解析到条目")
            _save_source(conn, source["key"], items)
            saved += len(items)
        except Exception as exc:  # noqa: BLE001 - 单个来源失败要降级
            errors.append(f"{source['label']}：{exc}")
    now = _now_iso()
    _set_meta(conn, "last_attempt", now)
    if saved:
        _set_meta(conn, "last_success", now)
    _set_meta(conn, "last_error", "；".join(errors)[:500])
    return {"saved": saved, "errors": errors, "attempted_at": now}


def payload(conn: sqlite3.Connection, limit: int = 3) -> dict:
    init_schema(conn)
    last_success = _meta(conn, "last_success")
    last_attempt = _meta(conn, "last_attempt")
    last_error = _meta(conn, "last_error")
    try:
        age = (
            datetime.now(timezone.utc)
            - datetime.strptime(last_success, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        ).total_seconds()
    except ValueError:
        age = None
    stale = bool(last_error) or age is None or age > config.NEWS_TTL_SECONDS
    return {
        "enabled": config.NEWS_ENABLED,
        "updated_at": last_success,
        "attempted_at": last_attempt,
        "stale": stale,
        "error": last_error,
        "items": read_cached(conn, limit),
    }


def _refresh_in_background() -> None:
    if not _refresh_lock.acquire(blocking=False):
        return

    def work() -> None:
        try:
            conn = connect()
            try:
                refresh(conn)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - 后台线程不能影响请求
            pass
        finally:
            _refresh_lock.release()

    threading.Thread(target=work, daemon=True, name="portal-news-refresh").start()


def get_payload(limit: int = 3, auto_refresh: bool = True) -> dict:
    """返回首页资讯；无缓存时同步抓取一次，有旧缓存时后台刷新。"""
    limit = max(1, min(int(limit or 3), 6))
    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001
        return {
            "enabled": config.NEWS_ENABLED,
            "updated_at": "",
            "attempted_at": "",
            "stale": True,
            "error": str(exc)[:300],
            "items": {source["key"]: [] for source in SOURCES},
        }
    try:
        init_schema(conn)
        current = payload(conn, limit)
        if not auto_refresh or not config.NEWS_ENABLED:
            return current
        has_items = any(current["items"].values())
        if current["stale"]:
            if has_items:
                _refresh_in_background()
            elif _refresh_lock.acquire(blocking=False):
                try:
                    refresh(conn)
                finally:
                    _refresh_lock.release()
                current = payload(conn, limit)
        return current
    finally:
        conn.close()


def warmup() -> None:
    """服务启动时预热缓存；网络失败只记录，不阻塞启动。"""
    if not config.NEWS_ENABLED:
        return
    try:
        get_payload(limit=3)
    except Exception:  # noqa: BLE001
        pass
