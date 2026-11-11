"""演示数据：一个班级、9 个成员、10 条 deadline、2 条待审草稿。

口令统一为 class123。仅用于本地演示，生产环境请勿执行。
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from . import auth, db
from .domain import deadlines as dl
from .util import LOCAL_TZ, iso_utc, jdump, local_now, now_iso, sha256_hex

DEMO_PASSWORD = "class123"

TABLES = ("sessions", "notifications", "revisions", "extraction_jobs", "raw_messages", "sources",
          "completions", "deadlines", "audit_logs", "users", "classes", "settings")


def _wipe(conn) -> None:
    for table in TABLES:
        conn.execute(f"DELETE FROM {table}")
    try:
        conn.execute("DELETE FROM sqlite_sequence")
    except Exception:  # noqa: BLE001 - 表不存在时忽略
        pass


def _at(base: datetime, days: int, hh: int, mm: int = 0):
    day = (base + timedelta(days=days)).date()
    return iso_utc(datetime.combine(day, time(hh, mm, 0), tzinfo=LOCAL_TZ))


DEMO_USERS = [
    ("20230000", "系统管理员", "admin", "active"),
    ("20230101", "张明", "monitor", "active"),
    ("20230102", "李婷", "secretary", "active"),
    ("20230103", "王浩", "student", "active"),
    ("20230104", "陈晨", "student", "active"),
    ("20230105", "刘洋", "student", "active"),
    ("20230106", "赵敏", "student", "active"),
    ("20230107", "孙悦", "student", "active"),
    ("20230199", "周杰", "student", "pending"),
]


def seed_demo(conn, *, reset: bool = False) -> dict:
    if reset:
        _wipe(conn)
    existing = db.scalar(conn, "SELECT COUNT(*) FROM classes")
    if existing and not reset:
        return {"skipped": True, "reason": "数据库已有班级数据，跳过演示数据写入"}

    now = now_iso()
    base = local_now()
    pw_hash = auth.hash_password(DEMO_PASSWORD)

    class_id = db.execute(conn, 
        "INSERT INTO classes (name, college, major, grade, invite_code, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("计算机 2301", "信息工程学院", "计算机科学与技术", "2023", "CS2301AB", now),
    )
    users: dict[str, object] = {}
    for student_no, name, role, status in DEMO_USERS:
        uid = db.execute(conn, 
            "INSERT INTO users (class_id, student_no, name, role, status, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (class_id, student_no, name, role, status, pw_hash, now),
        )
        users[student_no] = db.one(conn, "SELECT * FROM users WHERE id = ?", (uid,))
    monitor = users["20230101"]
    secretary = users["20230102"]

    # ---- 原始消息（模拟 QQ 群 / 粘贴） ----
    source_id = db.execute(conn, 
        "INSERT INTO sources (class_id, type, name, config, enabled, token_hash, created_at) "
        "VALUES (?, 'qq_onebot', ?, '{}', 1, ?, ?)",
        (class_id, "2301 班班级群", sha256_hex("demo-qq-token"), now),
    )
    raw_qq = db.execute(conn, 
        "INSERT INTO raw_messages (source_id, external_id, sender_name, sender_id, chat_name, "
        "content, attachments, occurred_at, ingested_at, status) VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?, 'extracted')",
        (source_id, "demo-msg-1", "辅导员-王老师", "10086", "2301 班班级群",
         "@学习委员 学院通知：本周五下午 3 点，在学院楼 302 召开奖学金评定说明会，"
         "请班长、团支书准时参加，会后提交本班材料。", _at(base, -1, 10, 12), now),
    )
    conn.execute(
        "INSERT INTO extraction_jobs (raw_message_id, provider, model, prompt_version, output, parsed, "
        "confidence, status, created_at) VALUES (?, 'rules', 'rules-v1', 'v1', ?, ?, ?, 'ok', ?)",
        (raw_qq, "{\"title\":\"奖学金评定说明会\",\"due\":\"周五 15:00\"}",
         jdump({"title": "奖学金评定说明会", "category": "task", "audience": "committee"}),
         0.82, now),
    )
    raw_paste = db.execute(conn, 
        "INSERT INTO raw_messages (source_id, external_id, sender_name, chat_name, content, attachments, "
        "occurred_at, ingested_at, status) VALUES (?, ?, ?, ?, ?, '[]', ?, ?, 'new')",
        (source_id, "demo-msg-2", "我", "粘贴导入",
         "老师：第 3 次实验报告下周三前交到学习通，记得附上实验截图。", _at(base, 0, 8, 30), now),
    )

    # ---- 条目 ----
    items = [
        dict(title="第 5 章实验报告", category="homework", audience="class", course="操作系统",
             summary="完成进程调度实验，提交实验报告 PDF 与源码压缩包。",
             due=_at(base, 2, 23, 59), due_at_raw="本周四 23:59", by=monitor, source="manual"),
        dict(title="习题 3.1 - 3.5", category="homework", audience="class", course="高等数学",
             summary="写在作业本上，下次课交。", due=_at(base, 1, 22, 0), by=secretary, source="manual"),
        dict(title="医保信息确认表", category="form", audience="class", course="",
             summary="全班同学都要填写，未填写的会被单独提醒。",
             due=_at(base, 3, 23, 59), by=monitor, source="qq", completions=True),
        dict(title="学院评优材料汇总", category="form", audience="committee", course="",
             summary="班长、团支书填写本班评优材料并汇总提交。",
             due=_at(base, 4, 18, 0), by=monitor, source="manual", completions=True),
        dict(title="五四合唱排练报名", category="task", audience="class", course="",
             summary="有意向的同学在群里接龙，周四前确定名单。",
             due=_at(base, 5, 12, 0), by=secretary, source="manual"),
        dict(title="数据结构期中考试", category="exam", audience="class", course="数据结构",
             summary="闭卷，覆盖第 1-6 章。", due=_at(base, 7, 9, 0), location="教三-201",
             by=monitor, source="manual"),
        dict(title="My Campus Life 作文", category="homework", audience="class", course="大学英语",
             summary="不少于 300 词。", due=_at(base, -1, 23, 59), by=secretary, source="manual"),
        dict(title="奖学金评定说明会", category="task", audience="committee", course="",
             summary="学院楼 302，班长与团支书参加。",
             due=_at(base, 6, 15, 0), by=monitor, source="qq", source_ref=f"raw:{raw_qq}",
             status="draft", confidence=0.82, needs_review=1),
        dict(title="第 3 次实验报告", category="homework", audience="class", course="计算机网络",
             summary="下周三前交到学习通，附实验截图。", due=_at(base, 4, 23, 59),
             source="paste", source_ref=f"raw:{raw_paste}", status="draft",
             confidence=0.66, needs_review=1),
        dict(title="习题册 P20", category="homework", audience="class", course="线性代数",
             summary="已过期的旧作业，演示归档状态。", due=_at(base, -10, 23, 59),
             by=monitor, source="manual", status="archived"),
    ]

    created: list[dict] = []
    for item in items:
        payload = {
            "title": item["title"], "category": item["category"], "audience": item["audience"],
            "course": item.get("course", ""), "summary": item.get("summary", ""),
            "due_at": item["due"], "due_at_raw": item.get("due_at_raw", ""),
            "location": item.get("location", ""),
        }
        row = dl.create(
            conn, item.get("by") or monitor, payload,
            status=item.get("status", "published"),
            source_type=item.get("source", "manual"),
            source_ref=item.get("source_ref", ""),
            confidence=item.get("confidence"),
            needs_review=item.get("needs_review", 0),
            dedupe_policy="flag",
            ip="seed",
        )
        created.append({"id": row["id"], "title": row["title"], "item": item})

    # ---- 完成情况 ----
    by_title = {c["title"]: c for c in created}
    form = by_title.get("医保信息确认表")
    if form:
        for student_no in ("20230101", "20230102", "20230104", "20230105", "20230106"):
            conn.execute(
                "INSERT INTO completions (deadline_id, user_id, state, note, updated_at) VALUES (?, ?, 'done', '', ?)",
                (form["id"], users[student_no]["id"], now),
            )
    review = by_title.get("学院评优材料汇总")
    if review:
        conn.execute(
            "INSERT INTO completions (deadline_id, user_id, state, note, updated_at) VALUES (?, ?, 'done', '材料已交', ?)",
            (review["id"], monitor["id"], now),
        )

    # ---- 未解析队列：一条没识别出截止时间的群消息，演示人工接管 ----
    raw_unknown = db.execute(
        conn,
        "INSERT INTO raw_messages (source_id, external_id, sender_name, chat_name, content, "
        "attachments, occurred_at, ingested_at, status) VALUES (?, ?, ?, ?, ?, '[]', ?, ?, 'failed')",
        (source_id, "demo-msg-3", "辅导员-王老师", "2301 班班级群",
         "【学院通知】请各班班委尽快完成本学期班级工作手册的填写，具体要求见群文件。",
         _at(base, 0, 9, 20), now),
    )
    conn.execute(
        "INSERT INTO extraction_jobs (raw_message_id, provider, model, prompt_version, output, "
        "parsed, confidence, status, error, created_at) "
        "VALUES (?, 'rules', 'rules-v1', 'v1', '', '{}', 0.2, 'failed', ?, ?)",
        (raw_unknown, "原文缺少明确的截止时间，需班委人工确认后补录", now),
    )

    # ---- 设置 ----
    for key, value in (("app_name", "班级 Deadline 中心"), ("timezone", "Asia/Shanghai"),
                       ("seeded_at", now), ("schema_version", "1")):
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now),
        )

    return {
        "skipped": False,
        "class_id": class_id,
        "invite_code": "CS2301AB",
        "users": len(DEMO_USERS),
        "deadlines": len(created),
        "password": DEMO_PASSWORD,
    }
