# -*- coding: utf-8 -*-
"""把 data/roster_all.json 里多个班的名单导入成「一班一库」。

用法：
    python -m app.import_multi                # 导入全部班（已存在的班只补角色）
    python -m app.import_multi --slug wdz261  # 只处理一个班

规则：
- 名单里字体红色的「班长」→ role=monitor；蓝色的「团支书」→ role=secretary；
- 其他同学 → role=student；新建班级不设 admin（最高管理员只有你一个）；
- 初始密码 = ``Init@`` + 学号后 6 位，首次登录强制改密；
- 已存在的班（例如集成26-1班）不改密码、不删人，只把角色同步成名单里标注的；
- 重复执行安全：已存在的学号跳过。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import auth, classes, config, db
from .util import now_iso

ROSTER = Path(config.DATA_DIR) / "roster_all.json"
ROLE_MAP = {"monitor": "monitor", "secretary": "secretary", "student": "student"}


def initial_password(student_no: str) -> str:
    tail = "".join(ch for ch in student_no if ch.isalnum())[-6:]
    return f"Init@{tail}"


def import_class(entry: dict, college: str, grade: str) -> dict:
    slug = entry["slug"]
    name = entry["name"]
    major = entry.get("major", "")
    path = classes.path_for(slug)
    created_db = False
    if path.is_file():
        conn = db.connect(path)
    else:
        path, _ = classes.create_class_db(slug=slug, name=name, college=college,
                                          major=major, grade=grade)
        created_db = True
        conn = db.connect(path)

    created = updated = skipped = 0
    try:
        cls = db.one(conn, "SELECT * FROM classes LIMIT 1")
        class_id = int(cls["id"])
        # 老库可能班级名为空/不一致，顺手对齐（不覆盖已有广告名）
        if not cls["name"]:
            conn.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))
        for person in entry["students"]:
            no = str(person["student_no"]).strip()
            real_name = str(person["name"]).strip()
            role = ROLE_MAP.get(person.get("role") or "student", "student")
            row = db.one(conn, "SELECT id, role, name FROM users WHERE student_no = ?", (no,))
            if row is None:
                db.execute(
                    conn,
                    "INSERT INTO users (class_id, student_no, name, role, status, password_hash, "
                    "must_change_password, created_at) VALUES (?, ?, ?, ?, 'active', ?, 1, ?)",
                    (class_id, no, real_name, role, auth.hash_password(initial_password(no)),
                     now_iso()),
                )
                created += 1
            else:
                # 不把已有 admin 降级；只同步名单里标出来的班长/团支书
                if row["role"] == "admin":
                    if row["name"] != real_name:
                        conn.execute("UPDATE users SET name = ? WHERE id = ?", (real_name, row["id"]))
                    skipped += 1
                elif row["role"] != role or row["name"] != real_name:
                    conn.execute("UPDATE users SET role = ?, name = ? WHERE id = ?",
                                 (role, real_name, row["id"]))
                    updated += 1
                else:
                    skipped += 1
        conn.commit()
        cls = db.one(conn, "SELECT * FROM classes WHERE id = ?", (class_id,))
        monitors = db.all_(conn, "SELECT name FROM users WHERE role = 'monitor' ORDER BY id")
        secretaries = db.all_(conn, "SELECT name FROM users WHERE role = 'secretary' ORDER BY id")
    finally:
        conn.close()

    return {
        "slug": slug,
        "name": cls["name"],
        "invite_code": cls["invite_code"],
        "db": str(path),
        "created_db": created_db,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": created + updated + skipped,
        "monitors": [r["name"] for r in monitors],
        "secretaries": [r["name"] for r in secretaries],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.import_multi")
    p.add_argument("--roster", default=str(ROSTER))
    p.add_argument("--slug", action="append", default=[], help="只处理指定班级（可重复）")
    p.add_argument("--college", default="微电子学院")
    p.add_argument("--grade", default="2026")
    args = p.parse_args(argv)

    payload = json.loads(Path(args.roster).read_text(encoding="utf-8"))
    college = payload.get("college") or args.college
    grade = payload.get("grade") or args.grade
    wanted = set(args.slug)

    rows = []
    for entry in payload["classes"]:
        if wanted and entry["slug"] not in wanted:
            continue
        info = import_class(entry, college, grade)
        rows.append(info)
        flag = "新建" if info["created_db"] else "已有"
        print(f"[{info['slug']}] {info['name']}（{flag}库）"
              f" 新建{info['created']} 更新{info['updated']} 跳过{info['skipped']}"
              f" | 班长 {','.join(info['monitors']) or '-'}"
              f" | 团支书 {','.join(info['secretaries']) or '-'}"
              f" | 邀请码 {info['invite_code']}")

    total_new = sum(r["created"] for r in rows)
    print(f"\n完成：{len(rows)} 个班，新建账号 {total_new} 个。")
    print("初始密码 = Init@ + 学号后 6 位，首次登录会强制改密。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
