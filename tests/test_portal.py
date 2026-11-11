"""首页与路由测试：验证门户静态页、/daliy 入口和静态资源。

不依赖数据库或演示数据，专门守住“根路径是门户、DDL 在 /daliy”的路由契约。
运行：python -m unittest tests.test_portal -v
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest

from app.server import make_server


class PortalRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path: str, method: str = "GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            body = resp.read()
            headers = {key.lower(): value for key, value in resp.getheaders()}
            return resp.status, headers, body
        finally:
            conn.close()

    def text(self, path: str):
        status, headers, body = self.request(path)
        self.assertEqual(status, 200, path)
        return headers, body.decode("utf-8")

    # ------------------------------------------------------------ 门户首页

    def test_01_root_is_portal(self):
        headers, body = self.text("/")
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("微电子学院", body)
        self.assertIn("集成电路设计与集成系统26-1班", body)
        self.assertIn("厚德 · 笃行", body)
        self.assertIn("崇实 · 尚新", body)
        self.assertNotIn("把班级的每一件事", body)
        self.assertIn("assets/home/brand.png", body)
        self.assertIn("新闻资讯", body)
        self.assertIn('data-news-column="notice"', body)
        self.assertIn('data-news-column="news"', body)
        self.assertIn("https://wdzxy.hfut.edu.cn/5630/list.htm", body)
        self.assertIn("https://wdzxy.hfut.edu.cn/5628/list.htm", body)
        self.assertNotIn("badge-sample", body)
        self.assertIn("归寝登记", body)
        self.assertIn('href="https://dorm-check.hfut.ycr10.cn/quick.html"', body)
        self.assertIn("前往登记", body)
        self.assertIn("活动报名", body)
        self.assertIn('href="/daliy/"', body)
        self.assertNotIn('class="status-chip"', body)
        self.assertNotIn("DDL 查询</a>", body)
        self.assertNotIn("先去看看 DDL 查询", body)
        self.assertIn("背景图：合肥工业大学校园实景", body)
        self.assertIn("assets/home.js", body)
        self.assertIn("assets/home/logo.png", body)
        self.assertIn("assets/home/campus.jpg", body)
        self.assertIn('href="/personalcenter/"', body)
        self.assertNotIn('id="account-modal"', body)
        self.assertIn('class="quote-mark quote-mark--close"', body)
        self.assertNotIn("已接入", body)
        self.assertNotIn("规划中", body)
        self.assertNotIn("学院官网 · 每 30 分钟同步", body)
        self.assertNotIn("作业截止、学院资讯、班级活动与归寝登记，从一个页面抵达。", body)
        self.assertIn("no-cache", headers.get("cache-control", ""))

    def test_02_portal_assets(self):
        for path, content_type in (
            ("/assets/home.css", "text/css"),
            ("/assets/home.js", "javascript"),
            ("/assets/home-data.js", "javascript"),
            ("/assets/home/logo.png", "image/png"),
            ("/assets/home/brand.png", "image/png"),
            ("/assets/home/favicon.png", "image/png"),
            ("/assets/home/campus.jpg", "image/jpeg"),
        ):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200, path)
                self.assertIn(content_type, headers["content-type"])
                self.assertGreater(len(body), 0)

    def test_02b_personal_center(self):
        _, body = self.text("/personalcenter/")
        self.assertIn("个人中心", body)
        self.assertIn('id="pc-login-form"', body)
        self.assertIn('id="pc-account"', body)
        self.assertIn('class="pc-date-field"', body)
        self.assertIn("年/月/日", body)
        self.assertIn("assets/personalcenter.css", body)
        self.assertIn("assets/personalcenter.js", body)
        for path, content_type in (
            ("/assets/personalcenter.css", "text/css"),
            ("/assets/personalcenter.js", "javascript"),
        ):
            with self.subTest(path=path):
                status, headers, payload = self.request(path)
                self.assertEqual(status, 200, path)
                self.assertIn(content_type, headers["content-type"])
                self.assertGreater(len(payload), 0)

    def test_02c_root_pwa_offline_shell(self):
        _, home = self.text("/")
        self.assertIn('rel="manifest"', home)
        self.assertIn("assets/offline.js", home)

        _, manifest_text = self.text("/manifest.webmanifest")
        manifest = json.loads(manifest_text)
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertTrue(manifest["icons"])

        _, sw = self.text("/sw.js")
        self.assertIn("classhub-shell-v28", sw)
        self.assertIn("const SHELL", sw)
        self.assertIn("/daliy/", sw)
        self.assertNotIn("caches.match('/api/", sw)

        _, offline = self.text("/assets/offline.js")
        self.assertIn("CDH_OFFLINE_SYNC", offline)
        self.assertIn("client_key", offline)

        _, ddl = self.text("/daliy/")
        self.assertIn("assets/offline.js", ddl)
        self.assertIn('href="/manifest.webmanifest"', ddl)

        for icon in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
            with self.subTest(icon=icon):
                status, headers, payload = self.request(f"/assets/icons/{icon}")
                self.assertEqual(status, 200)
                self.assertIn("image/png", headers["content-type"])
                self.assertGreater(len(payload), 0)

    # ------------------------------------------------------------ DDL 路由

    def test_03_daliy_canonical_redirect(self):
        status, headers, _ = self.request("/daliy?x=1")
        self.assertEqual(status, 302)
        self.assertEqual(headers["location"], "/daliy/?x=1")

    def test_04_daliy_app_shell(self):
        for path in ("/daliy/", "/daily/"):
            with self.subTest(path=path):
                _, body = self.text(path)
                self.assertIn("正在加载班级截止日", body)
                self.assertIn("assets/app.js", body)
        _, app = self.text("/daliy/assets/app.js")
        self.assertIn("个人中心", app)
        self.assertNotIn("<span>我的</span>", app)
        self.assertIn("brand-mark-logo", app)
        self.assertIn("/assets/home/logo.png", app)
        self.assertIn('alt="微电子学院院徽" />', app)
        self.assertIn("topbar-home", app)
        _, login = self.text("/daliy/assets/views/login.js")
        self.assertIn("auth-back", login)

        _, css = self.text("/daliy/assets/app.css")
        self.assertIn(".brand-mark-logo", css)

    def test_05_legacy_index_redirects_to_portal(self):
        status, headers, _ = self.request("/index.html")
        self.assertEqual(status, 302)
        self.assertEqual(headers["location"], "/")

    # ------------------------------------------------------------ 兼容与边界

    def test_06_root_api_unchanged(self):
        status, headers, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["content-type"])
        self.assertTrue(json.loads(body)["ok"])

    def test_07_missing_static_is_404(self):
        status, _, _ = self.request("/assets/home/not-found.css")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
