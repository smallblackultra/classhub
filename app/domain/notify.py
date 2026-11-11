"""站内通知：新截止日、待审核草稿、截止提醒、逾期提醒。

设计要点：
- 站内通知即时投递：插入即 status='sent'、sent_at=now；read_at 为空表示未读。
- 幂等：依赖 notifications 的 UNIQUE(user_id, deadline_id, kind, channel)，
  `INSERT OR IGNORE` 保证同一件事只提醒一次（提醒扫描可以每分钟跑）。
- 受众与 deadline.audience 对齐：class 条目发给全班，committee 条目只发班委。
- 只通知 status='active' 的成员；不通知触发者本人。
"""
from __future__ import annotations

import sqlite3

from .. import db
from ..util import iso_local, now_iso, parse_iso, utcnow

KIND_LABELS = {
    "deadline_new": "新截止日",
    "draft_pending": "待审核草稿",
    "due_24h": "明天截止",
    "due_2h": "即将截止",
    "overdue": "已逾期",
    "system": "系统通知",
}

COMMITTEE_ROLES = ("monitor", "secretary", "admin")


def _active_user_ids(conn: sqlite3.Connection, class_id: int) -> list[int]:
    return [r["id"] for r in db.all_(
        conn, "SELECT id FROM users WHERE class_id = ? AND status = 'active'", (class_id,))]


def _committee_ids(conn: sqlite3.Connection, class_id: int) -> list[int]:
    marks = ",".join("?" for _ in COMMITTEE_ROLES)
    return [r["id"] for r in db.all_(
        conn,
        f"SELECT id FROM users WHERE class_id = ? AND status = 'active' AND role IN ({marks})",
        (class_id, *COMMITTEE_ROLES),
    )]


def push(conn: sqlite3.Connection, *, user_id: int, class_id: int | None, kind: str,
         title: str, body: str = "", deadline_id: int | None = None,
         channel: str = "web") -> bool:
    """插入一条站内通知；重复时返回 False。"""
    now = now_iso()
    cur = conn.execute(
        """INSERT OR IGNORE INTO notifications
             (user_id, deadline_id, channel, kind, scheduled_at, sent_at, status,
              class_id, title, body, read_at)
           VALUES (?, ?, ?, ?, ?, ?, 'sent', ?, ?, ?, NULL)""",
        (user_id, deadline_id, channel, kind, now, now, class_id, title[:200], body[:500]),
    )
    return cur.rowcount > 0


def _due_text(item: dict) -> str:
    due = item.get("due_local") or ""
    if not due:
        return "未设置截止时间"
    return due[5:16].replace("T", " ")


def fanout_new_deadline(conn: sqlite3.Connection, class_id: int, item: dict,
                        actor_id: int | None = None) -> int:
    """发布一条 deadline 后通知目标受众（触发者本人除外）。"""
    if item.get("audience") == "committee":
        targets = _committee_ids(conn, class_id)
    elif item.get("target_count"):
        targets = list(item.get("target_user_ids") or [])
    else:
        targets = _active_user_ids(conn, class_id)
    label = item.get("category_label") or ""
    body = f"截止 {_due_text(item)}"
    if item.get("course"):
        body += f" · {item['course']}"
    sent = 0
    for uid in targets:
        if actor_id and uid == actor_id:
            continue
        if push(conn, user_id=uid, class_id=class_id, kind="deadline_new",
                title=f"新{label}：{item.get('title')}", body=body,
                deadline_id=item.get("id")):
            sent += 1
    return sent


def notify_draft_pending(conn: sqlite3.Connection, class_id: int, deadline_id: int,
                         title: str, sender: str = "", source_label: str = "QQ 群") -> int:
    """AI 抽取出一条草稿后提醒班委审核。"""
    who = sender.strip() or "AI 助手"
    body = f"{who} 从{source_label}的消息里提取到《{title}》，请核对截止时间与发布范围。"
    sent = 0
    for uid in _committee_ids(conn, class_id):
        if push(conn, user_id=uid, class_id=class_id, kind="draft_pending",
                title="有新的待审核草稿", body=body, deadline_id=deadline_id):
            sent += 1
    return sent


def due_scan(conn: sqlite3.Connection, now=None) -> int:
    """扫描已发布且有截止时间的条目：24 小时内、2 小时内、已逾期各提醒一次。"""
    now = now or utcnow()
    rows = db.all_(
        conn,
        "SELECT * FROM deadlines WHERE status = 'published' AND due_at IS NOT NULL AND due_at <> ''",
    )
    sent = 0
    for row in rows:
        try:
            due = parse_iso(row["due_at"])
        except ValueError:
            continue
        hours = (due - now).total_seconds() / 3600.0
        if hours < 0:
            if hours < -24 * 7:  # 一周以前的逾期不再打扰
                continue
            kind = "overdue"
            title = f"已逾期：{row['title']}"
            body = f"截止时间 {iso_local(due)[:16].replace('T', ' ')} 已过，如仍未完成请尽快处理。"
        elif hours <= 2:
            kind = "due_2h"
            title = f"即将截止：{row['title']}"
            body = f"还有不到 2 小时（{iso_local(due)[:16].replace('T', ' ')}），别忘了完成。"
        elif hours <= 24:
            kind = "due_24h"
            title = f"明天截止：{row['title']}"
            body = f"截止时间 {iso_local(due)[:16].replace('T', ' ')}，记得安排时间。"
        else:
            continue
        targets = _committee_ids(conn, row["class_id"]) if row["audience"] == "committee" \
            else _active_user_ids(conn, row["class_id"])
        done = {r["user_id"] for r in db.all_(
            conn, "SELECT user_id FROM completions WHERE deadline_id = ?", (row["id"],))}
        for uid in targets:
            if uid in done:
                continue
            if push(conn, user_id=uid, class_id=row["class_id"], kind=kind,
                    title=title, body=body, deadline_id=row["id"]):
                sent += 1
    return sent


def _serialize(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "kind_label": KIND_LABELS.get(row["kind"], row["kind"]),
        "title": row["title"],
        "body": row["body"],
        "deadline_id": row["deadline_id"],
        "deadline_title": row["deadline_title"] if "deadline_title" in row.keys() else None,
        "read": bool(row["read_at"]),
        "created_at": row["scheduled_at"],
        "created_local": iso_local(parse_iso(row["scheduled_at"])) if row["scheduled_at"] else None,
    }


def list_for_user(conn: sqlite3.Connection, user_id: int, *, unread_only: bool = False,
                  limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
    where = "n.user_id = ? AND n.status = 'sent'"
    params: list = [user_id]
    if unread_only:
        where += " AND n.read_at IS NULL"
    total = int(db.scalar(
        conn, f"SELECT COUNT(*) FROM notifications n WHERE {where}", tuple(params)))
    rows = db.all_(
        conn,
        f"""SELECT n.*, d.title AS deadline_title
              FROM notifications n
              LEFT JOIN deadlines d ON d.id = n.deadline_id
             WHERE {where}
             ORDER BY n.id DESC
             LIMIT ? OFFSET ?""",
        (*params, max(1, min(limit, 100)), max(0, offset)),
    )
    return [_serialize(r) for r in rows], total


def unread_count(conn: sqlite3.Connection, user_id: int) -> int:
    return int(db.scalar(
        conn,
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND status = 'sent' AND read_at IS NULL",
        (user_id,),
    ))


def mark_read(conn: sqlite3.Connection, user_id: int, ids: list[int] | None = None) -> int:
    now = now_iso()
    if ids:
        marks = ",".join("?" for _ in ids)
        cur = conn.execute(
            f"UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL "
            f"AND id IN ({marks})",
            (now, user_id, *ids),
        )
    else:
        cur = conn.execute(
            "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
            (now, user_id),
        )
    return cur.rowcount


def mark_all_read(conn: sqlite3.Connection, user_id: int) -> int:
    return mark_read(conn, user_id, None)
