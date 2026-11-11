"""DB 访问层：连接、schema 初始化、小事务封装。"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA_PATH = config.APP_DIR / "schema.sql"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)


# 轻量迁移：老库缺列时补列（SQLite 的 ALTER TABLE ADD COLUMN 很便宜）
_NOTIFICATION_COLUMNS = (
    ("class_id", "INTEGER"),
    ("title", "TEXT NOT NULL DEFAULT ''"),
    ("body", "TEXT NOT NULL DEFAULT ''"),
    ("read_at", "TEXT"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(notifications)")}
    for name, ddl in _NOTIFICATION_COLUMNS:
        if cols and name not in cols:
            conn.execute(f"ALTER TABLE notifications ADD COLUMN {name} {ddl}")
    user_cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if user_cols and "must_change_password" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password "
                     "INTEGER NOT NULL DEFAULT 0")
    for name, ddl in (
        ("password_enc", "TEXT"),
        ("avatar", "TEXT NOT NULL DEFAULT ''"),
        ("login_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_ip", "TEXT"),
        ("last_ua", "TEXT"),
    ):
        if user_cols and name not in user_cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user "
                 "ON notifications(user_id, read_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_deadline "
                 "ON notifications(deadline_id, kind)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS personal_items ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " class_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " title TEXT NOT NULL,"
        " note TEXT NOT NULL DEFAULT '',"
        " due_at TEXT,"
        " done INTEGER NOT NULL DEFAULT 0,"
        " client_key TEXT,"
        " created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL"
        ")"
    )
    personal_cols = {row["name"] for row in conn.execute("PRAGMA table_info(personal_items)")}
    if personal_cols and "client_key" not in personal_cols:
        conn.execute("ALTER TABLE personal_items ADD COLUMN client_key TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_personal_user "
                 "ON personal_items(user_id, done)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_client "
                 "ON personal_items(user_id, client_key) "
                 "WHERE client_key IS NOT NULL AND client_key <> ''")

    # ---- deadlines：任务细分（表格/答题/学习）与学院/班级层级 + 指定参与人
    dl_cols = {row["name"] for row in conn.execute("PRAGMA table_info(deadlines)")}
    for name, ddl in (("subtype", "TEXT"), ("task_level", "TEXT")):
        if dl_cols and name not in dl_cols:
            conn.execute(f"ALTER TABLE deadlines ADD COLUMN {name} {ddl}")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS deadline_targets ("
        " deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,"
        " user_id INTEGER NOT NULL REFERENCES users(id),"
        " PRIMARY KEY (deadline_id, user_id)"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dl_targets_user "
                 "ON deadline_targets(user_id)")
    # 旧数据：表格类别并入任务模块
    if dl_cols:
        conn.execute("UPDATE deadlines SET category = 'task', subtype = COALESCE(subtype, 'form') "
                     "WHERE category = 'form'")


@contextmanager
def connection(db_path: str | Path | None = None):
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def all_(conn: sqlite3.Connection, sql: str, params=()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def one(conn: sqlite3.Connection, sql: str, params=()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def scalar(conn: sqlite3.Connection, sql: str, params=(), default=0):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def execute(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return conn.execute(sql, params).lastrowid


def backup_to(db_path: str, dest_path: str) -> int:
    """在线备份（SQLite backup API，不锁库、可在服务运行时执行）。返回字节数。"""
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()
    return os.path.getsize(dest_path)
