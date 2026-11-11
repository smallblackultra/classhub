"""按名单建班并开通账号（一班一库）。

用法：
    python -m app.import_roster data/roster.json --slug jc261 \
        --class-name "集成电路26-1班" --admin 2026000000

规则：
- 每个学生一个账号，初始密码 = ``Init@`` + 学号后 6 位；
- 首次登录必须改密（must_change_password=1）；
- ``--admin`` 指定的学号成为本班管理员（唯一最高权限），其余为普通同学；
- 重复执行会跳过已存在的学号，可以安全补录。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import auth, classes, config, db
from .util import now_iso


def initial_password(student_no: str) -> str:
    tail = "".join(ch for ch in student_no if ch.isalnum())[-6:]
    return f"Init@{tail}"


def import_roster(data_path: str, *, slug: str, class_name: str, admin_no: str = "",
                  college: str = "微电子学院", major: str = "集成电路设计与集成系统",
                  grade: str = "2026", invite: str = "") -> dict:
    payload = json.loads(Path(data_path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("students") or []
    if not payload:
        raise SystemExit("名单为空")

    path = classes.path_for(slug)
    if path.is_file():
        class_id = None
    else:
        path, class_id = classes.create_class_db(
            slug=slug, name=class_name, college=college, major=major,
            grade=grade, invite_code=invite or None,
        )

    conn = db.connect(path)
    created = skipped = 0
    try:
        row = db.one(conn, "SELECT * FROM classes LIMIT 1")
        class_id = int(row["id"])
        has_admin = db.scalar(
            conn, "SELECT COUNT(*) FROM users WHERE class_id = ? AND role = 'admin'", (class_id,)
        )
        for person in payload:
            student_no = str(person.get("student_no") or "").strip()
            name = str(person.get("name") or "").strip()
            if not student_no or not name:
                continue
            exists = db.one(conn, "SELECT id FROM users WHERE student_no = ?", (student_no,))
            if exists is not None:
                skipped += 1
                continue
            role = "admin" if (admin_no and student_no == admin_no and not has_admin) else "student"
            db.execute(
                conn,
                "INSERT INTO users (class_id, student_no, name, role, status, password_hash, "
                "must_change_password, created_at) VALUES (?, ?, ?, ?, 'active', ?, 1, ?)",
                (class_id, student_no, name, role, auth.hash_password(initial_password(student_no)),
                 now_iso()),
            )
            created += 1
        conn.commit()
        row = db.one(conn, "SELECT name, invite_code FROM classes WHERE id = ?", (class_id,))
    finally:
        conn.close()
    return {
        "slug": slug,
        "class_name": row["name"],
        "invite_code": row["invite_code"],
        "created": created,
        "skipped": skipped,
        "total": created + skipped,
        "db": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.import_roster")
    p.add_argument("data", help="roster.json 路径")
    p.add_argument("--slug", required=True, help="班级目录名，如 jc261")
    p.add_argument("--class-name", required=True)
    p.add_argument("--admin", default="", help="管理员学号（最高权限，唯一）")
    p.add_argument("--college", default="微电子学院")
    p.add_argument("--major", default="集成电路设计与集成系统")
    p.add_argument("--grade", default="2026")
    p.add_argument("--invite", default="")
    args = p.parse_args(argv)
    info = import_roster(
        args.data, slug=args.slug, class_name=args.class_name, admin_no=args.admin,
        college=args.college, major=args.major, grade=args.grade, invite=args.invite,
    )
    print(f"[import] 班级 {info['class_name']}（{info['slug']}）")
    print(f"[import] 新建 {info['created']} 个账号，跳过已存在 {info['skipped']} 个，共 {info['total']} 人")
    print(f"[import] 邀请码 {info['invite_code']}   数据库 {info['db']}")
    print("[import] 初始密码规则：Init@ + 学号后 6 位，首次登录强制改密")
    return 0


if __name__ == "__main__":
    sys.exit(main())
