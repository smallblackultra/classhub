"""deadlines 领域服务：字段校验、CRUD、可见性查询、完成度统计。

本模块不接触 HTTP，所有入参已是解析好的 dict / sqlite3.Row。
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import audit, db
from ..errors import conflict, forbidden, invalid, not_found, pending_approval, rule_violation
from ..util import (day_bounds_utc, iso_local, iso_utc, jdump, jload, local_date_str,
                    normalize_title, now_iso, parse_due_input, parse_iso, sha256_hex,
                    text, one_of, today_local, utcnow)
from . import policy

CATEGORIES = ("homework", "task", "exam")
AUDIENCES = ("class", "committee")
SOURCE_TYPES = ("manual", "qq", "paste", "bookmarklet", "chaoxing", "yuketang", "import")
STATUSES = ("draft", "published", "archived")

# 任务模块的细分（表格已并入任务）
TASK_SUBTYPES = {
    "form": "表格",
    "quiz": "答题",
    "study": "学习",
    "other": "其他",
}
TASK_LEVELS = {"college": "学院", "class": "班级"}

CATEGORY_LABELS = {
    "homework": "作业",
    "task": "任务",
    "exam": "考试",
}
AUDIENCE_LABELS = {"class": "全班", "committee": "班委"}
STATUS_LABELS = {"draft": "草稿", "published": "已发布", "archived": "已归档"}


# ---------------------------------------------------------------- 校验

def _attachments(value) -> str:
    if value is None:
        return "[]"
    if not isinstance(value, (list, tuple)):
        raise invalid("attachments 必须是数组", field="attachments")
    out = []
    for item in list(value)[:20]:
        if isinstance(item, str):
            name, url = item.strip()[:200], ""
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()[:200]
            url = str(item.get("url") or "").strip()[:1000]
        else:
            raise invalid("attachments 元素格式不正确", field="attachments")
        if not name and not url:
            continue
        out.append({"name": name, "url": url})
    return jdump(out)


def _link(value) -> str:
    s = text(value, "link", maxlen=1000)
    if s and not (s.startswith("http://") or s.startswith("https://")):
        raise invalid("链接必须以 http:// 或 https:// 开头", field="link")
    return s


def validate_fields(data: dict, *, partial: bool = False) -> dict:
    """把客户端提交的字段规范化。partial=True 时只处理出现的键。"""
    if not isinstance(data, dict):
        raise invalid("请求体必须是 JSON 对象")
    out: dict = {}
    present = data.keys()

    if "title" in present:
        out["title"] = text(data["title"], "title", maxlen=200, required=True)
    elif not partial:
        raise invalid("标题不能为空", field="title")

    if "summary" in present:
        out["summary"] = text(data["summary"], "summary", maxlen=2000)
    if "course" in present:
        out["course"] = text(data["course"], "course", maxlen=100)
    if "location" in present:
        out["location"] = text(data["location"], "location", maxlen=200)
    if "due_at_raw" in present:
        out["due_at_raw"] = text(data["due_at_raw"], "due_at_raw", maxlen=100)
    if "link" in present:
        out["link"] = _link(data["link"])
    if "attachments" in present:
        out["attachments"] = _attachments(data["attachments"])

    raw_category = data.get("category")
    forced_subtype = None
    if raw_category == "form":  # 兼容旧客户端/旧 AI 输出：表格并入任务
        raw_category = "task"
        forced_subtype = "form"
    if "category" in present or not partial:
        out["category"] = one_of(raw_category, CATEGORIES, "category", default="homework")
    if "audience" in present or not partial:
        out["audience"] = one_of(data.get("audience"), AUDIENCES, "audience", default="class")

    cat_after = out.get("category", data.get("category"))
    if cat_after == "task":
        if forced_subtype and "subtype" not in present:
            out["subtype"] = forced_subtype
        elif "subtype" in present:
            out["subtype"] = one_of(data.get("subtype"), tuple(TASK_SUBTYPES), "subtype",
                                    default="other")
        elif not partial:
            out["subtype"] = "other"
        if "task_level" in present:
            out["task_level"] = one_of(data.get("task_level"), tuple(TASK_LEVELS), "task_level",
                                       default="class")
        elif not partial:
            out["task_level"] = "class"
    else:
        if "subtype" in present:
            out["subtype"] = None
        if "task_level" in present:
            out["task_level"] = None

    if "due_at" in present:
        due_iso, all_day = parse_due_input(data["due_at"])
        out["due_at"] = due_iso
        if "all_day" in present:
            from ..util import truthy_int
            out["all_day"] = truthy_int(data["all_day"])
        else:
            out["all_day"] = all_day
    elif "all_day" in present:
        from ..util import truthy_int
        out["all_day"] = truthy_int(data["all_day"])

    # 业务校验：截止时间不能早于 2000 年，或晚于 10 年后（明显录入错误）
    if out.get("due_at"):
        dt = parse_iso(out["due_at"])
        if dt.year < 2000 or dt.year > utcnow().year + 10:
            raise rule_violation("截止时间超出合理范围", field="due_at")
    return out


def dedupe_key_for(class_id: int, title: str, due_at: str | None) -> str:
    day = local_date_str(due_at) or "none"
    return sha256_hex(f"{class_id}|{normalize_title(title)}|{day}")


# ---------------------------------------------------------------- 指定参与人

def target_ids(conn: sqlite3.Connection, deadline_id: int) -> list[int]:
    return [r["user_id"] for r in db.all_(
        conn, "SELECT user_id FROM deadline_targets WHERE deadline_id = ? ORDER BY user_id",
        (deadline_id,))]


def set_targets(conn: sqlite3.Connection, class_id: int, deadline_id: int, ids) -> list[int]:
    """设置参与人。传空 / 覆盖全班时清空（= 全班都参与）。"""
    cleaned: list[int] = []
    seen: set[int] = set()
    for raw in ids or []:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        cleaned.append(uid)
    active = {r["id"] for r in db.all_(
        conn, "SELECT id FROM users WHERE class_id = ? AND status = 'active'", (class_id,))}
    cleaned = [uid for uid in cleaned if uid in active]
    if cleaned and set(cleaned) >= active:
        cleaned = []
    conn.execute("DELETE FROM deadline_targets WHERE deadline_id = ?", (deadline_id,))
    if cleaned:
        conn.executemany(
            "INSERT INTO deadline_targets (deadline_id, user_id) VALUES (?, ?)",
            [(deadline_id, uid) for uid in cleaned],
        )
    return cleaned


def can_see(conn: sqlite3.Connection, user, row: sqlite3.Row | None) -> bool:
    """带参与人判断的可见性（policy.can_view 的 SQL 增强版）。"""
    if row is None or user is None:
        return False
    if not policy.same_class(user, row) or not policy.is_active(user):
        return False
    if row["status"] != "published":
        return policy.is_committee(user)
    if policy.is_committee(user):
        return True
    if row["audience"] != "class":
        return False
    ids = target_ids(conn, row["id"])
    return not ids or user["id"] in ids


# ---------------------------------------------------------------- 读写

def fetch(conn: sqlite3.Connection, deadline_id: int) -> sqlite3.Row | None:
    return db.one(conn, "SELECT * FROM deadlines WHERE id = ?", (deadline_id,))


def get_visible(conn: sqlite3.Connection, user, deadline_id: int) -> sqlite3.Row:
    row = fetch(conn, deadline_id)
    if not can_see(conn, user, row):
        raise not_found("条目不存在")
    return row


def create(conn: sqlite3.Connection, user, data: dict, *, status: str = "published",
           source_type: str = "manual", source_ref: str = "",
           confidence: float | None = None, needs_review: int = 0,
           dedupe_policy: str = "error", ip: str = "", target_ids_: list | None = None) -> sqlite3.Row:
    if status not in STATUSES:
        raise invalid("status 不合法")
    fields = validate_fields(data)
    now = now_iso()
    key = dedupe_key_for(user["class_id"], fields["title"], fields.get("due_at"))

    dup = db.one(
        conn,
        "SELECT id, title, status FROM deadlines "
        "WHERE class_id = ? AND dedupe_key = ? AND status != 'archived' ORDER BY id LIMIT 1",
        (user["class_id"], key),
    )
    if dup is not None:
        if dedupe_policy == "error":
            raise conflict(f"已存在相同条目（#{dup['id']} {dup['title']}）")
        needs_review = 1

    rowid = db.execute(conn, 
        "INSERT INTO deadlines (class_id, title, summary, category, subtype, task_level, audience, "
        "course, due_at, due_at_raw, all_day, location, link, attachments, source_type, source_ref, "
        "status, confidence, needs_review, dedupe_key, created_by, reviewed_by, published_at, "
        "created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user["class_id"], fields["title"], fields.get("summary", ""), fields["category"],
            fields.get("subtype"), fields.get("task_level"), fields["audience"],
            fields.get("course", ""), fields.get("due_at"),
            fields.get("due_at_raw", ""), fields.get("all_day", 0), fields.get("location", ""),
            fields.get("link", ""), fields.get("attachments", "[]"), source_type, source_ref,
            status, confidence, needs_review, key,
            user["id"] if status == "published" or source_type == "manual" else None,
            user["id"] if status == "published" else None,
            now if status == "published" else None,
            now, now,
        ),
    )
    if target_ids_ is not None and fields["audience"] == "class":
        set_targets(conn, user["class_id"], rowid, target_ids_)
    row = fetch(conn, rowid)
    revision(conn, rowid, user["id"], "create", {}, _row_dict(row))
    audit.log(conn, user["id"], f"deadline.{status == 'draft' and 'create_draft' or 'create'}",
              f"deadline:{rowid}", {"title": fields["title"], "duplicate": dup is not None if dup else False}, ip)
    return row


def update(conn: sqlite3.Connection, user, row: sqlite3.Row, patch: dict, ip: str = "",
           target_ids_: list | None = None) -> sqlite3.Row:
    policy.guard_write(user, row)
    fields = validate_fields(patch, partial=True)
    if not fields and target_ids_ is None:
        return row

    before = _row_dict(row)
    merged = dict(before)
    merged.update(fields)
    if "due_at" in fields or "title" in fields:
        merged["dedupe_key"] = dedupe_key_for(row["class_id"], merged["title"], merged.get("due_at"))

    set_sql = ", ".join(f"{k} = ?" for k in merged if k not in ("id", "created_at"))
    values = [merged[k] for k in merged if k not in ("id", "created_at")]
    conn.execute(f"UPDATE deadlines SET {set_sql} WHERE id = ?", (*values, row["id"]))
    fresh = fetch(conn, row["id"])
    revision(conn, row["id"], user["id"], "update", before, _row_dict(fresh))
    audit.log(conn, user["id"], "deadline.update", f"deadline:{row['id']}",
              {"fields": sorted(fields.keys())}, ip)
    return fresh


def set_status(conn: sqlite3.Connection, user, row: sqlite3.Row, status: str, ip: str = "",
               reason: str = "") -> sqlite3.Row:
    policy.guard_write(user, row)
    if status not in STATUSES:
        raise invalid("status 不合法")
    if row["status"] == status:
        return row
    before = _row_dict(row)
    now = now_iso()
    published_at = now if status == "published" else row["published_at"]
    reviewed_by = user["id"] if status == "published" else row["reviewed_by"]
    conn.execute(
        "UPDATE deadlines SET status = ?, updated_at = ?, published_at = ?, reviewed_by = ?, "
        "needs_review = 0 WHERE id = ?",
        (status, now, published_at, reviewed_by, row["id"]),
    )
    fresh = fetch(conn, row["id"])
    revision(conn, row["id"], user["id"], status, before, _row_dict(fresh))
    audit.log(conn, user["id"], f"deadline.{status}", f"deadline:{row['id']}",
              {"reason": reason} if reason else {}, ip)
    return fresh


def archive(conn: sqlite3.Connection, user, row: sqlite3.Row, ip: str = "") -> sqlite3.Row:
    return set_status(conn, user, row, "archived", ip=ip, reason="archive")


def delete(conn: sqlite3.Connection, user, row: sqlite3.Row, ip: str = "") -> None:
    """软删除：归档 + 审计，不物理删除，保留追溯能力。"""
    policy.guard_write(user, row)
    now = now_iso()
    conn.execute("UPDATE deadlines SET status = 'archived', updated_at = ? WHERE id = ?", (now, row["id"]))
    revision(conn, row["id"], user["id"], "delete", _row_dict(row), {"status": "archived"})
    audit.log(conn, user["id"], "deadline.delete", f"deadline:{row['id']}", {}, ip)


def set_completion(conn: sqlite3.Connection, user, row: sqlite3.Row, state: str, note: str = "") -> dict:
    if not policy.is_active(user):
        raise pending_approval()
    if not can_see(conn, user, row):
        raise not_found("条目不存在")
    if state not in ("done", "skip", "pending"):
        raise invalid("state 必须是 done / skip / pending", field="state")
    if state == "pending":
        conn.execute("DELETE FROM completions WHERE deadline_id = ? AND user_id = ?", (row["id"], user["id"]))
    else:
        conn.execute(
            "INSERT INTO completions (deadline_id, user_id, state, note, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(deadline_id, user_id) "
            "DO UPDATE SET state = excluded.state, note = excluded.note, updated_at = excluded.updated_at",
            (row["id"], user["id"], state, (note or "")[:200], now_iso()),
        )
    return {"deadline_id": row["id"], "my_completion": None if state == "pending" else state}


# ---------------------------------------------------------------- 查询

def _visible_where(user) -> tuple[str, list]:
    if policy.is_committee(user):
        return "d.class_id = ?", [user["class_id"]]
    return (
        "d.class_id = ? AND d.audience = 'class' AND ("
        " NOT EXISTS (SELECT 1 FROM deadline_targets t WHERE t.deadline_id = d.id)"
        " OR EXISTS (SELECT 1 FROM deadline_targets t WHERE t.deadline_id = d.id AND t.user_id = ?)"
        ")",
        [user["class_id"], user["id"]],
    )


def _parse_day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise invalid(f"{field} 必须是 YYYY-MM-DD", field=field) from None


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_items(conn: sqlite3.Connection, user, query: dict) -> dict:
    if not policy.is_active(user):
        raise pending_approval()

    status = (query.get("status") or ["published"])[0]
    if status not in ("published", "draft", "archived", "all"):
        raise invalid("status 取值不合法", field="status")
    if status != "published" and not policy.is_committee(user):
        raise forbidden("无权查看草稿或归档条目")

    where, params = _visible_where(user)
    clauses = [where]
    if status != "all":
        clauses.append("d.status = ?")
        params.append(status)

    raw_categories = (query.get("category") or [""])[0]
    if raw_categories:
        cats = [c.strip() for c in raw_categories.split(",") if c.strip()]
        bad = [c for c in cats if c not in CATEGORIES]
        if bad:
            raise invalid("category 取值不合法", field="category")
        clauses.append("d.category IN (%s)" % ",".join("?" * len(cats)))
        params.extend(cats)

    audience = (query.get("audience") or [""])[0]
    if audience and policy.is_committee(user):
        if audience not in AUDIENCES:
            raise invalid("audience 取值不合法", field="audience")
        clauses.append("d.audience = ?")
        params.append(audience)

    subtype = (query.get("subtype") or [""])[0]
    if subtype:
        if subtype not in TASK_SUBTYPES:
            raise invalid("subtype 取值不合法", field="subtype")
        clauses.append("d.subtype = ?")
        params.append(subtype)

    task_level = (query.get("task_level") or [""])[0]
    if task_level:
        if task_level not in TASK_LEVELS:
            raise invalid("task_level 取值不合法", field="task_level")
        clauses.append("d.task_level = ?")
        params.append(task_level)

    q = (query.get("q") or [""])[0].strip()
    if q:
        pattern = _like(q)
        clauses.append("(d.title LIKE ? ESCAPE '\\' OR d.course LIKE ? ESCAPE '\\' OR d.summary LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern, pattern])

    if (query.get("from") or [""])[0]:
        start, _ = day_bounds_utc(_parse_day(query["from"][0], "from"))
        clauses.append("d.due_at IS NOT NULL AND d.due_at >= ?")
        params.append(start)
    if (query.get("to") or [""])[0]:
        _, end = day_bounds_utc(_parse_day(query["to"][0], "to"))
        clauses.append("d.due_at IS NOT NULL AND d.due_at < ?")
        params.append(end)

    sort = (query.get("sort") or ["due"])[0]
    order = {
        "due": "ORDER BY (d.due_at IS NULL) ASC, d.due_at ASC, d.id DESC",
        "created": "ORDER BY d.created_at DESC, d.id DESC",
        "updated": "ORDER BY d.updated_at DESC, d.id DESC",
    }.get(sort)
    if order is None:
        raise invalid("sort 取值不合法", field="sort")

    try:
        limit = min(max(int((query.get("limit") or ["300"])[0]), 1), 500)
    except ValueError:
        limit = 300

    sql = (f"SELECT d.* FROM deadlines d WHERE {' AND '.join(clauses)} {order} LIMIT ?")
    rows = db.all_(conn, sql, (*params, limit))
    return {
        "items": serialize_many(conn, rows, user),
        "counts": counts(conn, user),
        "total": len(rows),
    }


def counts(conn: sqlite3.Connection, user) -> dict:
    where, params = _visible_where(user)
    today = today_local()
    day_start, day_end = day_bounds_utc(today)
    now = iso_utc(utcnow())
    week_end = iso_utc(utcnow() + timedelta(days=7))
    row = db.one(
        conn,
        "SELECT "
        " SUM(CASE WHEN d.due_at IS NOT NULL AND d.due_at >= ? AND d.due_at < ? THEN 1 ELSE 0 END), "
        " SUM(CASE WHEN d.due_at IS NOT NULL AND d.due_at >= ? AND d.due_at < ? THEN 1 ELSE 0 END), "
        " SUM(CASE WHEN d.due_at IS NOT NULL AND d.due_at < ? THEN 1 ELSE 0 END) "
        f"FROM deadlines d WHERE {where} AND d.status = 'published'",
        (day_start, day_end, now, week_end, now, *params),
    )
    drafts = 0
    if policy.is_committee(user):
        drafts = db.scalar(conn, "SELECT COUNT(*) FROM deadlines WHERE class_id = ? AND status = 'draft'",
                           (user["class_id"],))
    return {
        "today": int(row[0] or 0),
        "week": int(row[1] or 0),
        "overdue": int(row[2] or 0),
        "drafts": int(drafts),
    }


# ---------------------------------------------------------------- 序列化

def _row_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def _totals(conn: sqlite3.Connection, class_id: int) -> tuple[int, int]:
    everyone = db.scalar(conn, "SELECT COUNT(*) FROM users WHERE class_id = ? AND status = 'active'", (class_id,))
    committee = db.scalar(
        conn,
        "SELECT COUNT(*) FROM users WHERE class_id = ? AND status = 'active' "
        "AND role IN ('monitor','secretary','admin')",
        (class_id,),
    )
    return int(everyone), int(committee)


def serialize(conn: sqlite3.Connection, row: sqlite3.Row, user, *,
              totals: tuple[int, int] | None = None,
              done_map: dict[int, int] | None = None,
              mine: dict[int, str] | None = None,
              creator_names: dict[int, str] | None = None) -> dict:
    totals = totals or _totals(conn, row["class_id"])
    tids = target_ids(conn, row["id"]) if row["audience"] == "class" else []
    if row["audience"] == "class":
        total = len(tids) if tids else totals[0]
    else:
        total = totals[1]
    if done_map is None:
        done = int(db.scalar(conn, "SELECT COUNT(*) FROM completions WHERE deadline_id = ? "
                                   "AND state = 'done'", (row["id"],)))
    else:
        done = done_map.get(row["id"], 0)
    my_state = (mine or {}).get(row["id"])
    if mine is None and user is not None:
        my_state = db.scalar(conn, "SELECT state FROM completions WHERE deadline_id = ? AND user_id = ?",
                             (row["id"], user["id"]), None)
    due = row["due_at"]
    is_overdue = bool(due) and row["status"] == "published" and parse_iso(due) < utcnow()
    creator = None
    if row["created_by"]:
        if creator_names is not None:
            creator = creator_names.get(row["created_by"])
        else:
            creator = db.scalar(conn, "SELECT name FROM users WHERE id = ?", (row["created_by"],), None)
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "category": row["category"],
        "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
        "subtype": row["subtype"],
        "subtype_label": TASK_SUBTYPES.get(row["subtype"], "") if row["subtype"] else "",
        "task_level": row["task_level"],
        "task_level_label": TASK_LEVELS.get(row["task_level"], "") if row["task_level"] else "",
        "target_count": len(tids),
        "target_user_ids": tids if policy.is_committee(user) else [],
        "audience": row["audience"],
        "audience_label": AUDIENCE_LABELS.get(row["audience"], row["audience"]),
        "course": row["course"],
        "due_at": due,
        "due_local": iso_local(parse_iso(due)) if due else None,
        "due_date": local_date_str(due),
        "due_at_raw": row["due_at_raw"],
        "all_day": bool(row["all_day"]),
        "location": row["location"],
        "link": row["link"],
        "attachments": jload(row["attachments"], []),
        "source_type": row["source_type"],
        "source_ref": row["source_ref"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "confidence": row["confidence"],
        "needs_review": bool(row["needs_review"]),
        "created_by": row["created_by"],
        "created_by_name": creator,
        "published_at": row["published_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_overdue": is_overdue,
        "my_completion": my_state,
        "completion": {"done": done, "total": total},
        "can_edit": policy.can_write(user, row),
    }


def serialize_many(conn: sqlite3.Connection, rows: list[sqlite3.Row], user) -> list[dict]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    done_map: dict[int, int] = {}
    mine: dict[int, str] = {}
    for r in db.all_(
        conn,
        f"SELECT deadline_id, COUNT(*) AS n FROM completions WHERE deadline_id IN ({marks}) "
        "AND state = 'done' GROUP BY deadline_id",
        ids,
    ):
        done_map[r["deadline_id"]] = r["n"]
    for r in db.all_(
        conn,
        f"SELECT deadline_id, state FROM completions WHERE deadline_id IN ({marks}) AND user_id = ?",
        (*ids, user["id"]),
    ):
        mine[r["deadline_id"]] = r["state"]
    creator_ids = sorted({r["created_by"] for r in rows if r["created_by"]})
    names: dict[int, str] = {}
    if creator_ids:
        for r in db.all_(
            conn,
            f"SELECT id, name FROM users WHERE id IN ({','.join('?' * len(creator_ids))})",
            creator_ids,
        ):
            names[r["id"]] = r["name"]
    totals = _totals(conn, rows[0]["class_id"])
    return [serialize(conn, r, user, totals=totals, done_map=done_map, mine=mine,
                      creator_names=names) for r in rows]


# ---------------------------------------------------------------- 完成名单

def completions(conn: sqlite3.Connection, user, row: sqlite3.Row) -> dict:
    policy.guard_committee(user)
    tids = target_ids(conn, row["id"]) if row["audience"] == "class" else []
    if tids:
        marks = ",".join("?" * len(tids))
        people = db.all_(
            conn,
            "SELECT id, name, student_no, role FROM users WHERE class_id = ? AND status = 'active' "
            f"AND id IN ({marks}) ORDER BY role, student_no",
            (row["class_id"], *tids),
        )
    else:
        role_sql = "" if row["audience"] == "class" else "AND role IN ('monitor','secretary','admin')"
        people = db.all_(
            conn,
            "SELECT id, name, student_no, role FROM users WHERE class_id = ? AND status = 'active' "
            f"{role_sql} ORDER BY role, student_no",
            (row["class_id"],),
        )
    entries = {r["user_id"]: r for r in db.all_(
        conn, "SELECT user_id, state, note, updated_at FROM completions WHERE deadline_id = ?", (row["id"],))}
    done, skipped, missing = [], [], []
    for p in people:
        entry = entries.get(p["id"])
        item = {"id": p["id"], "name": p["name"], "student_no": p["student_no"], "role": p["role"]}
        if entry is None:
            missing.append(item)
        elif entry["state"] == "done":
            done.append({**item, "updated_at": entry["updated_at"], "note": entry["note"]})
        else:
            skipped.append({**item, "updated_at": entry["updated_at"], "note": entry["note"]})
    return {
        "deadline_id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "done": done,
        "skipped": skipped,
        "missing": missing,
        "stats": {"done": len(done), "skipped": len(skipped), "missing": len(missing), "total": len(people)},
    }


# ---------------------------------------------------------------- 修订

def revision(conn: sqlite3.Connection, deadline_id: int, actor_id: int | None, action: str,
             before: dict, after: dict) -> None:
    conn.execute(
        "INSERT INTO revisions (deadline_id, actor_id, action, before, after, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (deadline_id, actor_id, action, jdump(before), jdump(after), now_iso()),
    )


def history(conn: sqlite3.Connection, row: sqlite3.Row, limit: int = 50) -> list[dict]:
    rows = db.all_(
        conn,
        "SELECT r.*, u.name AS actor_name FROM revisions r "
        "LEFT JOIN users u ON u.id = r.actor_id WHERE r.deadline_id = ? "
        "ORDER BY r.id DESC LIMIT ?",
        (row["id"], limit),
    )
    return [
        {"id": r["id"], "action": r["action"], "actor_name": r["actor_name"],
         "before": jload(r["before"], {}), "after": jload(r["after"], {}),
         "created_at": r["created_at"]}
        for r in rows
    ]
