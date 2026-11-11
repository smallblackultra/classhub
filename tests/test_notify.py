"""M3 测试：站内通知、提醒扫描、完成报表、CSV 导出、整库备份。

运行：python -m unittest tests.test_notify -v
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
import json
import os
import shutil
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from app import config, db
from app.domain import notify
from app.seed import seed_demo
from app.server import make_server
from app.util import LOCAL_TZ

DEMO_PW = "class123"


class Client:
    def __init__(self, base: str) -> None:
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self) -> str:
        for cookie in self.jar:
            if cookie.name == config.COOKIE_CSRF:
                return cookie.value
        return ""

    def call(self, method: str, path: str, body=None, *, csrf: bool = True, raw: bool = False):
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        if csrf and method in ("POST", "PATCH", "PUT", "DELETE"):
            req.add_header(config.CSRF_HEADER, self.csrf())
        try:
            resp = self.opener.open(req, timeout=10)
        except urllib.error.HTTPError as exc:
            resp = exc
        payload = resp.read()
        if raw:
            return resp.status, dict(resp.headers), payload
        return resp.status, (json.loads(payload.decode("utf-8")) if payload else None)

    def login(self, student_no: str, password: str = DEMO_PW):
        return self.call("POST", "/api/auth/login",
                         {"student_no": student_no, "password": password}, csrf=False)


class NotifyFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmp_root = os.path.join(root, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = os.path.join(tmp_root, "n" + uuid.uuid4().hex[:12])
        os.makedirs(cls.tmp, exist_ok=True)
        cls.db_path = os.path.join(cls.tmp, "test.db")
        conn = db.connect(cls.db_path)
        db.init_schema(conn)
        assert not seed_demo(conn).get("skipped")
        conn.close()

        cls._old_db_path = config.DB_PATH
        cls._old_classes_dir = config.CLASSES_DIR
        config.CLASSES_DIR = Path(cls.db_path).parent / "no-classes"
        config.DB_PATH = cls.db_path
        cls.server = make_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        cls.monitor = Client(cls.base)
        cls.student = Client(cls.base)
        cls.admin = Client(cls.base)
        cls.monitor.login("20230101")
        cls.student.login("20230105")
        cls.admin.login("20230000")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        config.DB_PATH = cls._old_db_path
        config.CLASSES_DIR = cls._old_classes_dir
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 通知

    def test_01_publish_notifies_students(self):
        status, body = self.monitor.call("POST", "/api/deadlines", {
            "title": "通知测试：提交课程论文",
            "category": "homework", "audience": "class",
            "due_at": "2026-12-01 23:59",
        })
        self.assertEqual(status, 201, body)
        deadline_id = body["item"]["id"]
        status, body = self.student.call("GET", "/api/notifications")
        self.assertEqual(status, 200)
        hits = [n for n in body["items"] if n["deadline_id"] == deadline_id]
        self.assertTrue(hits, "学生没有收到新截止日通知")
        self.assertEqual(hits[0]["kind"], "deadline_new")
        self.assertIn("课程论文", hits[0]["title"])
        self.assertFalse(hits[0]["read"])

    def test_02_draft_pending_notifies_committee(self):
        status, body = self.monitor.call("POST", "/api/ingest/paste", {
            "text": "各位同学：下周三前提交第 3 章实验报告。",
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "draft")
        status, body = self.monitor.call("GET", "/api/notifications")
        hits = [n for n in body["items"] if n["kind"] == "draft_pending"]
        self.assertTrue(hits, "班委没有收到待审核提醒")
        self.assertEqual(body["unread"], len([n for n in body["items"] if not n["read"]]))

    def test_03_mark_read(self):
        status, body = self.student.call("GET", "/api/notifications?unread=1")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["unread"], 1)
        first = body["items"][0]["id"]
        status, body = self.student.call("POST", "/api/notifications/read", {"ids": [first]})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["marked"], 1)
        status, body = self.student.call("POST", "/api/notifications/read-all")
        self.assertEqual(status, 200)
        self.assertEqual(body["unread"], 0)

    def test_04_due_scan_is_idempotent(self):
        due = (dt.datetime.now(LOCAL_TZ) + dt.timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M")
        status, body = self.monitor.call("POST", "/api/deadlines", {
            "title": "提醒扫描测试", "category": "task", "audience": "class", "due_at": due,
        })
        self.assertEqual(status, 201, body)
        deadline_id = body["item"]["id"]
        conn = db.connect(self.db_path)
        try:
            first = notify.due_scan(conn)
            second = notify.due_scan(conn)
            count = int(db.scalar(
                conn,
                "SELECT COUNT(*) FROM notifications WHERE deadline_id = ? AND kind = 'due_2h'",
                (deadline_id,),
            ))
        finally:
            conn.close()
        self.assertGreaterEqual(first, 1)
        self.assertEqual(second, 0, "重复扫描不应重复提醒")
        self.assertGreaterEqual(count, 1)

    # ------------------------------------------------------------ 报表与导出

    def test_05_reports_committee_only(self):
        status, body = self.monitor.call("GET", "/api/reports/overview")
        self.assertEqual(status, 200)
        self.assertGreater(len(body["items"]), 0)
        self.assertIn("avg_pct", body["summary"])
        status, body = self.student.call("GET", "/api/reports/overview")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_06_csv_export(self):
        status, headers, payload = self.monitor.call(
            "GET", "/api/reports/deadlines.csv", raw=True)
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"), "CSV 缺少 UTF-8 BOM")
        self.assertIn("标题".encode("utf-8"), payload)
        status, body = self.monitor.call("GET", "/api/deadlines?status=published")
        deadline_id = body["items"][0]["id"]
        status, headers, payload = self.monitor.call(
            "GET", f"/api/reports/completions.csv?deadline_id={deadline_id}", raw=True)
        self.assertEqual(status, 200)
        self.assertIn("学号".encode("utf-8"), payload)

    def test_07_backup_admin_only(self):
        status, headers, payload = self.admin.call("GET", "/api/admin/backup", raw=True)
        self.assertEqual(status, 200)
        self.assertTrue(payload.startswith(b"SQLite format 3\x00"))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        status, body = self.monitor.call("GET", "/api/admin/backup")
        self.assertEqual(status, 403)

    def test_08_profile_unread_badge(self):
        status, body = self.student.login("20230105")
        self.assertEqual(status, 200)
        self.assertIn("unread_notifications", body)
        self.assertIsInstance(body["unread_notifications"], int)


if __name__ == "__main__":
    unittest.main()
