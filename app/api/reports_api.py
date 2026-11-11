"""统计报表、CSV 导出、整库备份。

- 报表只对班委开放（普通同学看不到完成度，避免“谁没交”被围观）。
- CSV 用 UTF-8 BOM，Excel 直接双击不乱码。
- 备份走 SQLite 在线备份 API，不直接复制正在写入的 db 文件。
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import re
import sqlite3

from .. import config, db
from ..domain import deadlines as dl
from ..errors import forbidden, invalid, not_found
from ..request import Response
from ..router import route
from ..util import local_date_str, today_local

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def _download(name: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store"}


def _query_one(ctx, name: str, default: str = "") -> str:
    values = ctx.query.get(name) or []
    return values[0] if values else default


def _date_param(ctx, name: str) -> str | None:
    value = _query_one(ctx, name, "").strip()
    if not value:
        return None
    if not DATE_RE.match(value):
        raise invalid(f"{name} 需为 YYYY-MM-DD", field=name)
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise invalid(f"{name} 不是合法日期", field=name) from None
    return value


def _targets(conn: sqlite3.Connection, class_id: int) -> tuple[int, int]:
    everyone = int(db.scalar(
        conn, "SELECT COUNT(*) FROM users WHERE class_id = ? AND status = 'active'", (class_id,)))
    committee = int(db.scalar(
        conn,
        "SELECT COUNT(*) FROM users WHERE class_id = ? AND status = 'active' "
        "AND role IN ('monitor','secretary','admin')",
        (class_id,),
    ))
    return everyone, committee


@route("GET", "/api/reports/overview", committee=True)
def reports_overview(ctx):
    class_id = ctx.class_id
    date_from = _date_param(ctx, "from")
    date_to = _date_param(ctx, "to")
    clauses = ["d.class_id = ?", "d.status IN ('published','archived')"]
    params: list = [class_id]
    if date_from:
        clauses.append("d.due_at IS NOT NULL AND d.due_at >= ?")
        params.append(f"{date_from}T00:00:00+08:00")
    if date_to:
        clauses.append("d.due_at IS NOT NULL AND d.due_at <= ?")
        params.append(f"{date_to}T23:59:59+08:00")
    rows = db.all_(
        ctx.conn,
        f"""SELECT d.*,
                   (SELECT COUNT(*) FROM completions c
                     WHERE c.deadline_id = d.id AND c.state = 'done') AS done
              FROM deadlines d
             WHERE {' AND '.join(clauses)}
             ORDER BY (d.due_at IS NULL), d.due_at, d.id""",
        tuple(params),
    )
    everyone, committee = _targets(ctx.conn, class_id)
    items = []
    by_cat: dict[str, dict] = {}
    total_pct = 0.0
    for row in rows:
        total = committee if row["audience"] == "committee" else everyone
        done = int(row["done"] or 0)
        pct = round(done * 100.0 / total, 1) if total else 0.0
        item = {
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "category_label": dl.CATEGORY_LABELS.get(row["category"], row["category"]),
            "audience": row["audience"],
            "audience_label": dl.AUDIENCE_LABELS.get(row["audience"], row["audience"]),
            "status": row["status"],
            "due_local": dl.iso_local(dl.parse_iso(row["due_at"])) if row["due_at"] else None,
            "done": done,
            "total": total,
            "missing": max(0, total - done),
            "pct": pct,
        }
        items.append(item)
        bucket = by_cat.setdefault(row["category"], {
            "category": row["category"],
            "label": item["category_label"],
            "total": 0, "done": 0, "pct_sum": 0.0,
        })
        bucket["total"] += 1
        bucket["done"] += done
        bucket["pct_sum"] += pct
        total_pct += pct
    categories = []
    for bucket in by_cat.values():
        categories.append({
            "category": bucket["category"],
            "label": bucket["label"],
            "total": bucket["total"],
            "done": bucket["done"],
            "avg_pct": round(bucket["pct_sum"] / bucket["total"], 1) if bucket["total"] else 0.0,
        })
    categories.sort(key=lambda c: c["total"], reverse=True)
    published = sum(1 for i in items if i["status"] == "published")
    archived = sum(1 for i in items if i["status"] == "archived")
    overdue = 0
    now = _dt.datetime.now(_dt.timezone.utc)
    for item in items:
        if item["status"] != "published" or not item["due_local"]:
            continue
        due = _dt.datetime.fromisoformat(item["due_local"])
        if due < now:
            overdue += 1
    return {
        "items": items,
        "categories": categories,
        "summary": {
            "published": published,
            "archived": archived,
            "overdue": overdue,
            "avg_pct": round(total_pct / len(items), 1) if items else 0.0,
            "everyone": everyone,
            "committee": committee,
        },
        "range": {"from": date_from, "to": date_to},
        "generated_at": dl.iso_local(dl.utcnow()),
    }


@route("GET", "/api/reports/completions.csv", committee=True)
def completions_csv(ctx):
    raw = _query_one(ctx, "deadline_id", "")
    try:
        deadline_id = int(raw)
    except ValueError:
        raise invalid("deadline_id 必须是整数", field="deadline_id") from None
    row = db.one(ctx.conn, "SELECT * FROM deadlines WHERE id = ? AND class_id = ?",
                 (deadline_id, ctx.class_id))
    if row is None:
        raise not_found("deadline 不存在")
    data = dl.completions(ctx.conn, ctx.user, row)
    lines: list[list] = []
    for label, entries in (("已完成", data["done"]), ("不适用", data["skipped"]),
                           ("未完成", data["missing"])):
        for person in entries:
            lines.append([person["name"], person["student_no"], label,
                          person.get("note") or "", person.get("updated_at") or ""])
    body = _csv_bytes(["姓名", "学号", "状态", "备注", "更新时间"], lines)
    return Response(200, raw=body, content_type="text/csv; charset=utf-8",
                    headers=_download(f"completions-{deadline_id}.csv"))


@route("GET", "/api/reports/deadlines.csv", committee=True)
def deadlines_csv(ctx):
    date_from = _date_param(ctx, "from")
    date_to = _date_param(ctx, "to")
    clauses = ["d.class_id = ?", "d.status IN ('published','archived')"]
    params: list = [ctx.class_id]
    if date_from:
        clauses.append("d.due_at IS NOT NULL AND d.due_at >= ?")
        params.append(f"{date_from}T00:00:00+08:00")
    if date_to:
        clauses.append("d.due_at IS NOT NULL AND d.due_at <= ?")
        params.append(f"{date_to}T23:59:59+08:00")
    rows = db.all_(
        ctx.conn,
        f"""SELECT d.*,
                   (SELECT COUNT(*) FROM completions c
                     WHERE c.deadline_id = d.id AND c.state = 'done') AS done
              FROM deadlines d WHERE {' AND '.join(clauses)}
             ORDER BY d.due_at IS NULL, d.due_at, d.id""",
        tuple(params),
    )
    everyone, committee = _targets(ctx.conn, ctx.class_id)
    lines = []
    for row in rows:
        total = committee if row["audience"] == "committee" else everyone
        lines.append([
            dl.CATEGORY_LABELS.get(row["category"], row["category"]),
            dl.AUDIENCE_LABELS.get(row["audience"], row["audience"]),
            row["title"],
            row["course"],
            local_date_str(row["due_at"]) or "",
            dl.iso_local(dl.parse_iso(row["due_at"]))[:16].replace("T", " ") if row["due_at"] else "",
            dl.STATUS_LABELS.get(row["status"], row["status"]),
            f'{int(row["done"] or 0)}/{total}',
            row["source_type"],
        ])
    body = _csv_bytes(["类别", "受众", "标题", "课程", "截止日期", "截止时间", "状态",
                       "完成情况", "来源"], lines)
    return Response(200, raw=body, content_type="text/csv; charset=utf-8",
                    headers=_download("deadlines.csv"))


@route("GET", "/api/admin/backup", committee=True)
def backup_db(ctx):
    """在线备份：把当前库完整复制成一个可下载的 .db 文件（仅管理员）。"""
    if ctx.user["role"] != "admin":
        raise forbidden("只有系统管理员可以下载整库备份")
    stamp = dl.utcnow().strftime("%Y%m%d-%H%M%S")
    path = config.DATA_DIR / f".backup-{stamp}.db"
    try:
        dest = sqlite3.connect(str(path))
        try:
            ctx.conn.backup(dest)
            dest.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            dest.close()
        data = path.read_bytes()
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    return Response(
        200, raw=data, content_type="application/vnd.sqlite3",
        headers=_download(f"classhub-backup-{stamp}.db"),
    )
