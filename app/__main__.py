"""命令行入口：python -m app [--port 8000] [--seed|--reset] [--open] [--backup]"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__, classes, config, db, news
from .domain import notify
from .seed import seed_demo
from .server import make_server, migrate_all_classes


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app", description="班级 Deadline 中心")
    p.add_argument("--host", default=config.HOST, help="监听地址（默认 127.0.0.1）")
    p.add_argument("--port", type=int, default=config.PORT, help="端口（默认 8000）")
    p.add_argument("--db", default=str(config.DB_PATH), help="SQLite 文件路径")
    p.add_argument("--seed", action="store_true", help="空库时写入演示数据")
    p.add_argument("--reset", action="store_true", help="清空并重建演示数据")
    p.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    p.add_argument("--no-notify", action="store_true", help="关闭后台截止提醒扫描")
    p.add_argument("--backup", action="store_true", help="只做一次在线备份后退出（不启动服务）")
    p.add_argument("--backup-out", default="", help="备份目录，默认 data/backup")
    p.add_argument("--list-classes", action="store_true", help="列出已存在的班级库")
    p.add_argument("--new-class", default="", metavar="NAME", help="新建一个空班级库后退出")
    p.add_argument("--slug", default="", help="配合 --new-class 指定目录名，如 jc261")
    p.add_argument("--invite", default="", help="配合 --new-class 指定邀请码")
    p.add_argument("--version", action="version", version=f"ClassHub {__version__}")
    return p


def _backup_one(slug: str, src: Path, dest_dir: Path) -> int:
    if not src.exists():
        return 0
    name = f"{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    dest = dest_dir / name
    size = db.backup_to(str(src), str(dest))
    print(f"[backup] {slug}: {size / 1024:.0f} KB → {dest.name}")
    return 1


def _backup(_db_path: str, out_dir: str = "") -> int:
    """在线备份每个班级库并清理超出保留数的旧备份。返回进程退出码。"""
    dest_dir = Path(out_dir) if out_dir else (config.DATA_DIR / "backup")
    dest_dir.mkdir(parents=True, exist_ok=True)
    targets = list(classes.iter_dbs())
    if not targets:
        src = Path(_db_path)
        if not src.exists():
            print(f"[backup] 数据库不存在：{src}")
            return 1
        targets = [("classhub", src)]
    # 门户资讯缓存不属于任何班级库，单独备份。
    if config.PORTAL_DB.exists():
        targets.append(("portal", config.PORTAL_DB))
    try:
        for slug, src in targets:
            _backup_one(slug, src, dest_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"[backup] 失败：{exc}")
        return 2
    keep = config.BACKUP_KEEP
    if keep > 0:
        for slug, _ in targets:
            olds = sorted(dest_dir.glob(f"{slug}-*.db"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            for old in olds[keep:]:
                try:
                    old.unlink()
                except OSError:
                    pass
    print(f"[backup] 完成，保留最近 {keep} 份")
    return 0



def _notify_loop(db_path: str) -> None:
    """后台提醒扫描：每分钟检查一次 24h/2h/逾期，靠唯一约束保证只提醒一次。"""
    while True:
        targets = classes.iter_dbs() or [("", Path(db_path))]
        for slug, path in targets:
            try:
                with db.connection(path) as conn:
                    sent = notify.due_scan(conn)
                    if sent:
                        print(f"[notify] {slug or 'db'} 本轮发出 {sent} 条截止提醒")
            except Exception as exc:  # noqa: BLE001 —— 后台线程不能挂
                sys.stderr.write(f"[notify] {slug} 扫描失败：{exc}\n")
        time.sleep(config.NOTIFY_INTERVAL)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db

    if args.backup:
        return _backup(db_path, args.backup_out)
    if args.list_classes:
        found = classes.iter_dbs()
        if not found:
            print("[classes] 还没有班级库，用 --new-class 新建")
        for slug, path in found:
            conn = db.connect(path)
            try:
                row = db.one(conn, "SELECT name, invite_code FROM classes LIMIT 1")
                n_users = db.scalar(conn, "SELECT COUNT(*) FROM users")
                n_deadlines = db.scalar(conn, "SELECT COUNT(*) FROM deadlines")
            finally:
                conn.close()
            if row:
                print(f"{slug:16s} {row['name']}  邀请码 {row['invite_code']}  "
                      f"成员 {n_users}  条目 {n_deadlines}")
        return 0
    if args.new_class:
        slug = args.slug or "class-" + datetime.now().strftime("%m%d%H%M")
        path, class_id = classes.create_class_db(
            slug=slug, name=args.new_class, invite_code=args.invite or None
        )
        conn = db.connect(path)
        try:
            row = db.one(conn, "SELECT invite_code FROM classes WHERE id = ?", (class_id,))
        finally:
            conn.close()
        print(f"[classes] 已新建 {args.new_class}（{slug}）→ {path}")
        print(f"[classes] 邀请码 {row['invite_code']}")
        return 0

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        if args.seed or args.reset:
            info = seed_demo(conn, reset=args.reset)
            if info.get("skipped"):
                print(f"[seed] {info['reason']}")
            else:
                print(f"[seed] 已写入演示数据：班级 {info['class_id']}，{info['users']} 个成员，"
                      f"{info['deadlines']} 条 deadline，邀请码 {info['invite_code']}")
        else:
            n_classes = db.scalar(conn, "SELECT COUNT(*) FROM classes")
            if not n_classes and not classes.list_slugs():
                print("[提示] 数据库为空，可使用 --seed 写入演示数据。")
    finally:
        conn.close()

    httpd = make_server(args.host, args.port)
    try:
        migrate_all_classes()
    except Exception as exc:  # 迁移失败不阻止启动
        print(f"[migrate] 跳过：{exc}")
    url = f"http://{args.host}:{args.port}/"
    print(f"\n  班级 Deadline 中心 v{__version__}")
    print(f"  本机访问   {url}")
    print(f"  数据库     {db_path}")
    print("  演示账号   20230101 / class123（班长）  20230102 / class123（团支书）")
    print("             20230103 / class123（同学）  20230000 / class123（管理员）")
    print("  停止服务   Ctrl+C\n")
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    if config.NOTIFY_ENABLED and not args.no_notify:
        threading.Thread(target=_notify_loop, args=(db_path,), daemon=True,
                         name="notify-scan").start()
        print(f"  截止提醒   每 {config.NOTIFY_INTERVAL}s 扫描一次（--no-notify 可关）")
    if config.NEWS_ENABLED:
        threading.Thread(target=news.warmup, daemon=True, name="news-warmup").start()
        print(f"  门户资讯   每 {config.NEWS_TTL_SECONDS}s 刷新（CDH_NEWS=0 可关）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[stop] 服务已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
