"""M2 接入链路测试：QQ 令牌 / 粘贴 / 书签 / 未解析队列 / 人工接管。

运行：python -m unittest tests.test_ingest -v
"""
from __future__ import annotations

import os
import threading
import unittest
import uuid
from pathlib import Path
from datetime import timedelta

from app import config, db
from app.seed import seed_demo
from app.server import make_server
from app.util import LOCAL_TZ, utcnow
from tests.test_api import Client

DEMO_QQ_TOKEN = "demo-qq-token"


def future_date(days: int = 7) -> str:
    day = (utcnow().astimezone(LOCAL_TZ) + timedelta(days=days)).date()
    return f"{day.month}月{day.day}日"


class IngestFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmp_root = os.path.join(root, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = os.path.join(tmp_root, "i" + uuid.uuid4().hex[:12])
        os.makedirs(cls.tmp, exist_ok=True)
        cls.db_path = os.path.join(cls.tmp, "test.db")
        conn = db.connect(cls.db_path)
        db.init_schema(conn)
        seed_demo(conn)
        conn.close()

        cls._old_db_path = config.DB_PATH
        cls._old_classes_dir = config.CLASSES_DIR
        config.CLASSES_DIR = Path(cls.db_path).parent / "no-classes"
        config.DB_PATH = cls.db_path
        cls.server = make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        cls.monitor = Client(cls.base)
        cls.student = Client(cls.base)
        cls.monitor.login("20230101")
        cls.student.login("20230105")

        cls.bookmark_token = ""
        cls.shared_raw = 0
        cls.shared_deadline = 0

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        config.DB_PATH = cls._old_db_path
        config.CLASSES_DIR = cls._old_classes_dir

    # -------------------------------------------------- QQ 机器人
    def test_01_qq_rejects_bad_token(self):
        status, body = self.monitor.call(
            "POST", "/api/ingest/qq",
            {"text": "测试", "group_name": "2301 班班级群"},
            headers={"X-Classhub-Token": "definitely-wrong-token"},
        )
        self.assertEqual(status, 401, body)

    def test_02_qq_creates_committee_draft(self):
        due = future_date(3)
        status, body = self.monitor.call(
            "POST", "/api/ingest/qq",
            {"text": f"@学习委员 学院要求各班班委于{due}前提交本班医保信息表，收到请回复。",
             "group_name": "2301 班班级群", "sender_name": "辅导员-王老师",
             "msg_id": "test-qq-001"},
            headers={"X-Classhub-Token": DEMO_QQ_TOKEN},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "draft", body)
        self.assertTrue(body["deadline_id"])
        self.assertEqual(body["ai"]["engine"], "rules")
        IngestFlowTest.shared_raw = body["raw_id"]
        IngestFlowTest.shared_deadline = body["deadline_id"]

        status, detail = self.monitor.call("GET", f"/api/deadlines/{body['deadline_id']}")
        self.assertEqual(status, 200)
        item = detail["item"]
        self.assertEqual(item["status"], "draft")
        self.assertEqual(item["audience"], "committee")
        # 旧版把“表格”当成 category=form；现在统一为 task + subtype=form（见 domain/deadlines.py）。
        self.assertEqual(item["category"], "task")
        self.assertEqual(item["subtype"], "form")
        self.assertIn("医保", item["title"])

    def test_03_qq_is_idempotent(self):
        status, body = self.monitor.call(
            "POST", "/api/ingest/qq",
            {"text": "重复消息不应该再生成草稿", "group_name": "2301 班班级群",
             "msg_id": "test-qq-001"},
            headers={"X-Classhub-Token": DEMO_QQ_TOKEN},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "duplicate")
        self.assertEqual(body["deadline_id"], self.shared_deadline)

    # -------------------------------------------------- 粘贴
    def test_04_paste_homework(self):
        due = future_date(5)
        status, body = self.monitor.call(
            "POST", "/api/ingest/paste",
            {"text": f"各位同学：{due}前提交第 5 章实验报告，交到学习通，记得附上截图。",
             "source_hint": "学习通课后通知"},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "draft")
        item = body["item"]
        self.assertEqual(item["category"], "homework")
        self.assertEqual(item["audience"], "class")
        self.assertTrue(item["due_date"])

    def test_05_paste_requires_committee(self):
        status, body = self.student.call("POST", "/api/ingest/paste", {"text": "同学不能粘贴"})
        self.assertEqual(status, 403, body)

    # -------------------------------------------------- 书签
    def test_06_bookmarklet_creates_drafts(self):
        status, created = self.monitor.call(
            "POST", "/api/admin/sources", {"type": "bookmarklet", "name": "学习通作业页"},
        )
        self.assertEqual(status, 201, created)
        token = created["token"]
        IngestFlowTest.bookmark_token = token

        status, body = self.monitor.call(
            "POST", "/api/ingest/bookmarklet",
            {"platform": "chaoxing", "page_url": "https://mooc1.chaoxing.com/work/list",
             "items": [
                 {"title": "第 6 章作业", "course": "操作系统",
                  "due_text": f"{future_date(2)} 23:59", "category": "homework"},
                 {"title": "课程问卷调查", "course": "操作系统", "due_text": future_date(4)},
             ]},
            headers={"X-Classhub-Token": token},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["created"], 2, body)
        for entry in body["results"]:
            self.assertEqual(entry["status"], "draft", entry)
            self.assertTrue(entry["deadline_id"])

    # -------------------------------------------------- 未解析队列
    def test_07_queue_and_manual_takeover(self):
        status, body = self.monitor.call(
            "POST", "/api/ingest/qq",
            {"text": "哈哈哈哈哈", "group_name": "2301 班班级群", "msg_id": "test-qq-chat"},
            headers={"X-Classhub-Token": DEMO_QQ_TOKEN},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "ignored")

        status, queue = self.monitor.call("GET", "/api/ingest/queue")
        self.assertEqual(status, 200, queue)
        ids = [row["id"] for row in queue["items"]]
        self.assertIn(body["raw_id"], ids)

        status, created = self.monitor.call(
            "POST", f"/api/ingest/queue/{body['raw_id']}/manual",
            {"title": "群里口头通知的临时任务", "category": "task", "audience": "class"},
        )
        self.assertEqual(status, 201, created)
        self.assertEqual(created["item"]["status"], "draft")

        status, conflict = self.monitor.call(
            "POST", f"/api/ingest/queue/{body['raw_id']}/retry",
        )
        self.assertEqual(status, 409, conflict)


if __name__ == "__main__":
    unittest.main()
