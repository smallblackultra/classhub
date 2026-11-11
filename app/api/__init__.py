"""导入各个接口模块以完成路由注册。"""
from __future__ import annotations

from . import (  # noqa: F401
    admin_api,
    ai_admin_api,
    auth_api,
    deadlines_api,
    global_admin_api,
    ingest_api,
    meta_api,
    news_api,
    notify_api,
    personal_api,
    reports_api,
)

__all__ = ["admin_api", "ai_admin_api", "auth_api", "deadlines_api", "global_admin_api",
           "ingest_api", "meta_api", "news_api", "notify_api", "personal_api", "reports_api"]
