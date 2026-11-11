"""运行时配置。全部可用环境变量覆盖，方便本机/局域网部署。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
WEB_DIR = BASE_DIR / "web"
DOCS_DIR = BASE_DIR / "docs"
DATA_DIR = Path(os.environ.get("CDH_DATA_DIR") or (BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("CDH_DB") or (DATA_DIR / "classhub.db"))
# 一班一库：每个班一个 data/classes/<slug>/classhub.db；DB_PATH 只作为单库模式回退。
CLASSES_DIR = Path(os.environ.get("CDH_CLASSES_DIR") or (DATA_DIR / "classes"))
# 门户资讯缓存独立于班级库，可单独备份；不保存任何校园账号信息。
PORTAL_DB = Path(os.environ.get("CDH_PORTAL_DB") or (DATA_DIR / "portal.db"))

HOST = os.environ.get("CDH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CDH_PORT", "8000"))

# 历史挂载前缀：/daily/ 以前是整站入口，现在只作为 DDL 应用的兼容别名保留。
PUBLIC_BASE = (os.environ.get("CDH_BASE", "/daily")).rstrip("/")
if PUBLIC_BASE and not PUBLIC_BASE.startswith("/"):
    PUBLIC_BASE = "/" + PUBLIC_BASE

# DDL 应用规范路径；根路径 / 留给班级门户首页。
APP_PREFIX = "/daliy"
APP_ALIASES = ("/daily",)

ENV = os.environ.get("CDH_ENV", "dev")

TIMEZONE = "Asia/Shanghai"
SESSION_TTL_DAYS = int(os.environ.get("CDH_SESSION_DAYS", "14"))

COOKIE_SID = "cdh_sid"
COOKIE_CSRF = "cdh_csrf"
COOKIE_CLASS = "cdh_cls"
CSRF_HEADER = "X-CSRF"

MAX_BODY_BYTES = 1024 * 1024

# 生产（HTTPS）下给 Cookie 加 Secure；本机 http 调试时关闭
SECURE_COOKIES = ENV == "prod"

# 邀请码字符集（去掉易混淆的 0/O/1/I）
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# 登录限流
LOGIN_MAX_FAILS = 8
LOGIN_WINDOW_SECONDS = 300

# 站内提醒扫描（后台线程；测试/单次脚本可用 CDH_NOTIFY=0 关掉）
NOTIFY_ENABLED = os.environ.get("CDH_NOTIFY", "1") != "0"
NOTIFY_INTERVAL = max(15, int(os.environ.get("CDH_NOTIFY_INTERVAL", "60")))

# 备份保留份数，0 = 不清理
BACKUP_KEEP = int(os.environ.get("CDH_BACKUP_KEEP", "14"))

# 门户资讯：只抓取学院官网公开栏目；缓存 30 分钟，失败时继续展示旧缓存。
NEWS_ENABLED = os.environ.get("CDH_NEWS", "1") != "0"
NEWS_TTL_SECONDS = max(60, int(os.environ.get("CDH_NEWS_TTL", "1800")))
NEWS_TIMEOUT = max(3, int(os.environ.get("CDH_NEWS_TIMEOUT", "12")))
NEWS_MAX_BYTES = 2 * 1024 * 1024
