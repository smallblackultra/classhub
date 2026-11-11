"""门户资讯抓取与缓存测试：全部离线，不访问学院官网。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import news

NOTICE_HTML = """
<ul>
<li class="news n1 clearfix"><a href="/2026/1110/c5630a324408/page.htm">
  <div class="date"><em>10</em><span>2026-11</span></div>
  <div class="txt"><h4>  大型仪器收费公示  </h4><div class="desc">通知摘要</div></div>
</a></li>
<li class="news n1 clearfix"><a href="/2021/1108/c5630a250000/page.htm">
  <div class="date"><em>08</em><span>2021-11</span></div>
  <div class="txt"><h4>诚聘英才</h4><div class="desc">旧公告</div></div>
</a></li>
<li class="news n1 clearfix"><a href="https://evil.example/x">
  <div class="date"><em>01</em><span>2026-10</span></div>
  <div class="txt"><h4>站外链接</h4></div>
</a></li>
<li class="news n1 clearfix"><a href="/2026/1009/c5630a323613/page.htm">
  <div class="date"><em>09</em><span>2026-10</span></div>
  <div class="txt"><h4>精英赛名单</h4><div class="desc">第二条</div></div>
</a></li>
<li class="news n1 clearfix"><div class="txt">{缩略图}</div></li>
</ul>
"""

NEWS_HTML = """
<ul>
<li class="news n1 clearfix"><a href="/2026/1110/c5628a324405/page.htm">
  <div class="date"><span>2026-11-10</span></div>
  <div class="txt"><h4>消防安全演练</h4><div class="desc">新闻摘要</div></div>
</a></li>
</ul>
"""


class NewsParserTest(unittest.TestCase):
    def test_parse_list_sorts_and_whitelists(self):
        items = news.parse_list(NOTICE_HTML, "https://wdzxy.hfut.edu.cn/5630/list.htm", "notice")
        self.assertEqual([item["title"] for item in items], ["大型仪器收费公示", "精英赛名单", "诚聘英才"])
        self.assertEqual(items[0]["published_at"], "2026-11-10")
        self.assertEqual(items[0]["summary"], "通知摘要")
        self.assertTrue(items[0]["url"].startswith("https://wdzxy.hfut.edu.cn/"))
        self.assertNotIn("站外链接", [item["title"] for item in items])

    def test_parse_iso_date(self):
        items = news.parse_list(NEWS_HTML, "https://wdzxy.hfut.edu.cn/5628/list.htm", "news")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"], "2026-11-10")

    def test_empty_and_bad_html(self):
        self.assertEqual(news.parse_list("", "https://wdzxy.hfut.edu.cn/", "notice"), [])
        self.assertEqual(news.parse_list("<ul><li>nothing</li></ul>", "https://wdzxy.hfut.edu.cn/", "notice"), [])


class NewsCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = news.connect(Path(self.tmp.name) / "portal.db")
        news.init_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    @staticmethod
    def fetcher(url: str) -> str:
        return NOTICE_HTML if "5630" in url else NEWS_HTML

    def test_refresh_and_payload(self):
        result = news.refresh(self.conn, fetcher=self.fetcher)
        self.assertEqual(result["saved"], 4)
        self.assertEqual(result["errors"], [])
        data = news.payload(self.conn, 3)
        self.assertFalse(data["stale"])
        self.assertEqual(len(data["items"]["notice"]), 3)
        self.assertEqual(len(data["items"]["news"]), 1)
        self.assertEqual(data["items"]["notice"][0]["title"], "大型仪器收费公示")
        self.assertEqual(data["items"]["notice"][-1]["title"], "诚聘英才")

    def test_error_keeps_old_cache_and_marks_stale(self):
        news.refresh(self.conn, fetcher=self.fetcher)

        def broken(url: str) -> str:
            raise OSError("offline")

        result = news.refresh(self.conn, fetcher=broken)
        self.assertEqual(result["saved"], 0)
        self.assertTrue(result["errors"])
        data = news.payload(self.conn, 3)
        self.assertTrue(data["stale"])
        self.assertIn("offline", data["error"])
        self.assertTrue(data["items"]["notice"])

    def test_no_cache_and_errors_yield_empty_items(self):
        def broken(url: str) -> str:
            raise OSError("offline")

        news.refresh(self.conn, fetcher=broken)
        data = news.payload(self.conn, 3)
        self.assertEqual(data["items"], {"notice": [], "news": []})


if __name__ == "__main__":
    unittest.main()
