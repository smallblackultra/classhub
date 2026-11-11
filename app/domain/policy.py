"""权限判定的唯一实现处。

原则：
- 可见性只由 audience（class / committee）决定，与 category 无关。
- 草稿、归档只对班委可见。
- 越权读取一律 404（不泄露资源是否存在），越权写入 403。
"""
from __future__ import annotations

from ..errors import forbidden, not_found, pending_approval

COMMITTEE_ROLES = ("monitor", "secretary", "admin")


def is_active(user) -> bool:
    return user is not None and user["status"] == "active"


def is_committee(user) -> bool:
    return user is not None and user["role"] in COMMITTEE_ROLES


def same_class(user, item) -> bool:
    return user is not None and item is not None and user["class_id"] == item["class_id"]


def can_view(user, item) -> bool:
    if not is_active(user):
        return False
    if not same_class(user, item):
        return False
    if item["status"] == "published":
        return item["audience"] == "class" or is_committee(user)
    return is_committee(user)


def can_write(user, item=None) -> bool:
    if not is_active(user) or not is_committee(user):
        return False
    return item is None or same_class(user, item)


def can_review(user) -> bool:
    return is_active(user) and is_committee(user)


def visible_audiences(user) -> tuple[str, ...]:
    return ("class", "committee") if is_committee(user) else ("class",)


def guard_view(user, item) -> None:
    """不可见时抛 404，避免用 403 暴露条目存在性。"""
    if item is None or not can_view(user, item):
        raise not_found("条目不存在")


def guard_write(user, item=None) -> None:
    if not is_active(user):
        raise pending_approval()
    if not can_write(user, item):
        raise forbidden("只有班委可以执行该操作")


def guard_committee(user) -> None:
    if not is_active(user):
        raise pending_approval()
    if not is_committee(user):
        raise forbidden("只有班委可以执行该操作")
