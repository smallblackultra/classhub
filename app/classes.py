"""一班一库。

每个班级一个独立的 SQLite 文件：``data/classes/<slug>/classhub.db``。
浏览器里用 ``cdh_cls`` cookie 记住当前班级；登录页在没有 cookie 时回落到
默认库（单班部署时就是唯一那个班）。
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from . import config, db
from .util import new_invite_code, now_iso

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def classes_dir() -> Path:
    path = Path(config.CLASSES_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_for(slug: str) -> Path:
    return classes_dir() / slug / "classhub.db"


def resolve(slug: str | None) -> Path | None:
    """把 cookie 里的 slug 换成真实存在的数据库路径。"""
    if not slug or not SLUG_RE.match(slug):
        return None
    candidate = path_for(slug)
    return candidate if candidate.is_file() else None


def list_slugs() -> list[str]:
    root = classes_dir()
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "classhub.db").is_file():
            found.append(child.name)
    return found


def default_db_path() -> Path:
    """没有班级 cookie 时用哪个库：优先 CDH_DEFAULT_CLASS，否则第一个班。"""
    slugs = list_slugs()
    preferred = (os.environ.get("CDH_DEFAULT_CLASS") or "jc261").strip()
    if preferred in slugs:
        return path_for(preferred)
    if slugs:
        return path_for(slugs[0])
    return Path(config.DB_PATH)


def resolve_cookie(value: str | None) -> Path:
    return resolve(value) or default_db_path()


def slug_of_path(path: str | Path) -> str:
    path = Path(path)
    try:
        return path.parent.name if path.parent.parent == classes_dir() else ""
    except OSError:
        return ""


def find_by_invite(code: str) -> tuple[str, Path] | None:
    """按邀请码找到班级库（班委轮换邀请码后也能找到）。"""
    code = (code or "").strip().upper()
    if not code:
        return None
    for slug in list_slugs():
        path = path_for(slug)
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
            try:
                row = conn.execute(
                    "SELECT 1 FROM classes WHERE invite_code = ? LIMIT 1", (code,)
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            continue
        if row:
            return slug, path
    return None


def create_class_db(*, slug: str, name: str, college: str = "", major: str = "",
                    grade: str = "", invite_code: str | None = None) -> tuple[Path, int]:
    if not SLUG_RE.match(slug):
        raise ValueError("slug 只能是小写字母/数字/短横线，长度 2-32")
    path = path_for(slug)
    if path.exists():
        raise ValueError(f"班级 {slug} 已存在")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(path)
    try:
        db.init_schema(conn)
        class_id = db.execute(
            conn,
            "INSERT INTO classes (name, college, major, grade, invite_code, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, college, major, grade, invite_code or new_invite_code(), now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return path, int(class_id)


def iter_dbs() -> list[tuple[str, Path]]:
    return [(slug, path_for(slug)) for slug in list_slugs()]


def ensure_demo_default() -> None:
    """单库老数据迁移：data/classhub.db → data/classes/<slug>/classhub.db。

    只在 classes 目录还是空的时候做一次，避免重复搬运。
    """
    if list_slugs():
        return
    legacy = Path(config.DB_PATH)
    if not legacy.is_file():
        return
    slug = os.environ.get("CDH_CLASS_SLUG", "class-1")
    target = path_for(slug)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(legacy))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
