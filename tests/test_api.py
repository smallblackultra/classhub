"""M1 接口冒烟测试：用标准库在随机端口起一个真服务，走完整 HTTP 流程。

运行：python -m unittest tests.test_api -v
说明：测试依赖顺序，每个用例都建立在演示数据（seed_demo）之上。
"""
from __future__ import annotations

import base64
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
from app.seed import seed_demo
from app.server import make_server

DEMO_PW = "class123"


class Client:
    def __init__(self, base: str) -> None:
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self) -> str:
        for cookie in self.jar:
            if cookie.name == config.COOKIE_CSRF:
                return cookie.value
        return ""

    def call(self, method: str, path: str, body=None, *, csrf: bool = True, headers=None):
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if csrf and method in ("POST", "PATCH", "PUT", "DELETE"):
            req.add_header(config.CSRF_HEADER, self.csrf())
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self.opener.open(req, timeout=10) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = {"raw": raw.decode("utf-8", "replace")}
            return exc.code, payload

    def login(self, student_no: str, password: str = DEMO_PW):
        return self.call("POST", "/api/auth/login",
                         {"student_no": student_no, "password": password}, csrf=False)


class ApiFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmp_root = os.path.join(root, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        # 注意：不要用 tempfile.mkdtemp，它创建的目录权限过紧，沙箱下 SQLite 打不开
        cls.tmp = os.path.join(tmp_root, "t" + uuid.uuid4().hex[:12])
        os.makedirs(cls.tmp, exist_ok=True)
        cls.db_path = os.path.join(cls.tmp, "test.db")
        conn = db.connect(cls.db_path)
        db.init_schema(conn)
        info = seed_demo(conn)
        assert not info.get("skipped")
        conn.close()

        cls._old_db_path = config.DB_PATH
        cls._old_classes_dir = config.CLASSES_DIR
        config.CLASSES_DIR = Path(cls.db_path).parent / "no-classes"
        config.DB_PATH = cls.db_path
        cls.server = make_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        cls.monitor = Client(cls.base)
        cls.student = Client(cls.base)
        cls.anon = Client(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        config.DB_PATH = cls._old_db_path
        config.CLASSES_DIR = cls._old_classes_dir
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 基础

    def test_01_health_and_meta(self):
        status, body = self.anon.call("GET", "/api/health", csrf=False)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        status, body = self.anon.call("GET", "/api/meta", csrf=False)
        self.assertEqual(status, 200)
        self.assertEqual(body["timezone"], "Asia/Shanghai")
        self.assertIn("homework", [c["value"] for c in body["categories"]])

    def test_02_anonymous_rejected(self):
        status, body = self.anon.call("GET", "/api/deadlines", csrf=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthenticated")

    def test_03_login_monitor(self):
        status, body = self.monitor.login("20230101")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["role"], "monitor")
        self.assertTrue(body["permissions"]["committee"])
        self.assertEqual(body["class"]["invite_code"], "CS2301AB")

    def test_04_bad_password(self):
        status, body = Client(self.base).login("20230101", "wrong-pass")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "invalid_credentials")

    # ------------------------------------------------------------ 班委视角

    def test_05_committee_sees_all(self):
        status, body = self.monitor.call("GET", "/api/deadlines?limit=100")
        self.assertEqual(status, 200)
        audiences = {item["audience"] for item in body["items"]}
        self.assertIn("committee", audiences)
        self.assertEqual(body["counts"]["drafts"], 2)

    def test_06_drafts_with_raw(self):
        status, body = self.monitor.call("GET", "/api/drafts")
        self.assertEqual(status, 200)
        self.assertEqual(body["total"], 2)
        titles = {d["title"] for d in body["items"]}
        self.assertIn("奖学金评定说明会", titles)
        meeting = next(d for d in body["items"] if d["title"] == "奖学金评定说明会")
        self.assertEqual(meeting["status"], "draft")
        self.assertTrue(meeting["raw"]["content"].startswith("@学习委员"))

    def test_07_csrf_required(self):
        status, body = self.monitor.call("POST", "/api/deadlines",
                                         {"title": "无 CSRF", "category": "task",
                                          "audience": "class", "due_at": "2026-12-01"}, csrf=False)
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "csrf_failed")

    def test_08_create_and_dedupe(self):
        payload = {"title": "实验报告查重测试", "category": "homework", "audience": "class",
                   "due_at": "2026-12-08", "summary": "第一次"}
        status, body = self.monitor.call("POST", "/api/deadlines", payload)
        self.assertEqual(status, 201, body)
        new_id = body["item"]["id"]
        self.assertEqual(body["item"]["status"], "published")

        status, body = self.monitor.call("POST", "/api/deadlines", payload)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "conflict")

        status, body = self.monitor.call("POST", "/api/deadlines",
                                         {"title": "草稿测试条目", "category": "task",
                                          "audience": "class", "due_at": "2026-12-09", "as_draft": 1})
        self.assertEqual(status, 201)
        self.assertEqual(body["item"]["status"], "draft")
        self.monitor.call("DELETE", f"/api/deadlines/{new_id}")

    def test_09_publish_committee_draft(self):
        status, body = self.monitor.call("GET", "/api/drafts")
        meeting = next(d for d in body["items"] if d["title"] == "奖学金评定说明会")
        status, body = self.monitor.call("POST", f"/api/drafts/{meeting['id']}/publish", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["item"]["status"], "published")

    def test_10_patch_and_history(self):
        status, body = self.monitor.call("PATCH", "/api/deadlines/2",
                                         {"summary": "改过的说明", "location": "教二-105"})
        self.assertEqual(status, 200)
        self.assertEqual(body["item"]["summary"], "改过的说明")
        status, body = self.monitor.call("GET", "/api/deadlines/2/history")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(body["items"]), 2)

        status, body = self.monitor.call("PATCH", "/api/deadlines/2", {"category": "bogus"})
        self.assertEqual(status, 400)

    # ------------------------------------------------------------ 同学视角

    def test_11_student_login_and_visibility(self):
        status, body = self.student.login("20230103")
        self.assertEqual(status, 200)
        self.assertFalse(body["permissions"]["committee"])
        self.assertNotIn("invite_code", body["class"])
        self.assertEqual(body["pending_drafts"], 0)

        status, body = self.student.call("GET", "/api/deadlines?limit=100")
        self.assertEqual(status, 200)
        self.assertTrue(all(item["audience"] == "class" for item in body["items"]))
        ids = {item["id"] for item in body["items"]}
        self.assertNotIn(8, ids)  # 学院评优/说明会：班委专属
        self.assertEqual(body["counts"]["drafts"], 0)

    def test_12_student_forbidden_paths(self):
        status, body = self.student.call("GET", "/api/deadlines/8")
        self.assertEqual(status, 404, "班委专属条目对同学必须返回 404 而不是 403")

        status, body = self.student.call("GET", "/api/drafts")
        self.assertEqual(status, 403)

        status, body = self.student.call("GET", "/api/deadlines?status=draft")
        self.assertEqual(status, 403)

        status, body = self.student.call("GET", "/api/admin/users")
        self.assertEqual(status, 403)

        status, body = self.student.call("POST", "/api/deadlines",
                                         {"title": "同学越权创建", "category": "task",
                                          "audience": "class", "due_at": "2026-12-01"})
        self.assertEqual(status, 403)

    def test_13_student_completion(self):
        status, body = self.student.call("POST", "/api/deadlines/1/complete", {"state": "done"})
        self.assertEqual(status, 200)
        self.assertEqual(body["my_completion"], "done")
        self.assertGreaterEqual(body["completion"]["done"], 1)

        status, body = self.student.call("POST", "/api/deadlines/1/complete", {"state": "pending"})
        self.assertEqual(status, 200)
        self.assertIsNone(body["my_completion"])

        status, body = self.student.call("POST", "/api/deadlines/8/complete", {"state": "done"})
        self.assertEqual(status, 404)

    # ------------------------------------------------------------ 注册与审批

    def test_14_register_pending_gate(self):
        fresh = Client(self.base)
        status, body = fresh.call("POST", "/api/auth/register", {
            "student_no": "20230188", "name": "测试同学", "password": "test1234",
            "invite_code": "CS2301AB",
        }, csrf=False)
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["status"], "pending")
        self.assertEqual(body["user"]["name"], "测试同学")

        status, body = fresh.call("GET", "/api/deadlines")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "pending_approval")

        status, body = fresh.call("GET", "/api/auth/me")
        self.assertEqual(status, 200)

        status, body = Client(self.base).call("POST", "/api/auth/register", {
            "student_no": "20230188", "name": "重复", "password": "test1234",
            "invite_code": "CS2301AB",
        }, csrf=False)
        self.assertEqual(status, 409)

        status, body = self.monitor.call("GET", "/api/admin/users?status=pending")
        self.assertEqual(status, 200)
        pending = [u for u in body["items"] if u["student_no"] in ("20230188", "20230199")]
        self.assertEqual(len(pending), 2)

        target = next(u for u in pending if u["student_no"] == "20230188")
        status, body = self.monitor.call("PATCH", f"/api/admin/users/{target['id']}",
                                         {"status": "active"})
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["status"], "active")

        status, body = fresh.call("GET", "/api/deadlines?limit=1")
        self.assertEqual(status, 200)

    def test_15_admin_guard_and_stats(self):
        status, body = self.monitor.call("PATCH", "/api/admin/users/2", {"role": "student"})
        self.assertEqual(status, 403, "不允许修改自己的角色")

        status, body = self.monitor.call("GET", "/api/admin/stats")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["deadlines"]["published"], 7)
        self.assertGreaterEqual(body["users"]["active"], 8)

        status, body = self.monitor.call("GET", "/api/admin/audit?limit=5")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(body["items"]), 5)

    def test_16_completions_detail(self):
        status, body = self.monitor.call("GET", "/api/deadlines/3/completions")
        self.assertEqual(status, 200)
        self.assertEqual(body["stats"]["done"], 5)
        self.assertGreaterEqual(len(body["missing"]), 3)
        self.assertEqual(body["stats"]["done"] + body["stats"]["missing"], body["stats"]["total"])

    def test_17_avatar_roundtrip(self):
        status, body = self.student.call("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertIn("avatar", body["user"])

        avatar = "data:image/png;base64," + base64.b64encode(b"classhub-avatar").decode()
        status, body = self.student.call("POST", "/api/auth/avatar", {"avatar": avatar})
        self.assertEqual(status, 200)
        self.assertEqual(body["avatar"], avatar)

        status, body = self.student.call("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["avatar"], avatar)

        status, _ = self.student.call("POST", "/api/auth/avatar", {"avatar": "data:text/plain;base64,Zm9v"})
        self.assertEqual(status, 400)

        status, body = self.student.call("POST", "/api/auth/avatar", {"avatar": ""})
        self.assertEqual(status, 200)
        self.assertEqual(body["avatar"], "")

    def test_18_personal_client_key_idempotent(self):
        key = "offline-test-idempotent-20261111"
        status, first = self.student.call("POST", "/api/personal", {
            "title": "离线幂等计划",
            "client_key": key,
        })
        self.assertEqual(status, 200)
        status, second = self.student.call("POST", "/api/personal", {
            "title": "离线幂等计划（重复提交）",
            "client_key": key,
        })
        self.assertEqual(status, 200)
        self.assertEqual(first["item"]["id"], second["item"]["id"])

        status, body = self.student.call("GET", "/api/personal?done=all")
        self.assertEqual(status, 200)
        matches = [item for item in body["items"] if item["id"] == first["item"]["id"]]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["title"], "离线幂等计划")


if __name__ == "__main__":
    unittest.main(verbosity=2)
