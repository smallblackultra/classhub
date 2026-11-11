#!/usr/bin/env python3
"""Build the static portal shell for the remote 1Panel host.

Default (demo) mode keeps the original no-backend preview: DDL is shown as
planned and `/daliy/` is a static placeholder.  `--full` builds the real portal
that talks to the ClassHub API through OpenResty and links to the live DDL app.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = ROOT / ".tmp" / "remote-site"

CANONICAL = "https://www.2026hfutintegratedcircuit1.com/"
SOURCE_FILES = (
    "assets/home.css",
    "assets/home.js",
    "assets/home-data.js",
    "assets/offline.js",
    "assets/home/logo.png",
    "assets/home/brand.png",
    "assets/home/favicon.png",
    "assets/home/campus.jpg",
    "assets/icons/icon-192.png",
    "assets/icons/icon-512.png",
    "assets/icons/icon-maskable-512.png",
    "assets/icons/apple-touch-icon.png",
    "manifest.webmanifest",
    "sw.js",
)

STATIC_SHIM = r"""/* Cloud preview guard: the remote host is a static site without the ClassHub API. */
(function () {
  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      if (url.indexOf("/api/auth/me") !== -1) {
        return Promise.resolve(new Response(
          JSON.stringify({ code: 401, message: "static preview" }),
          {
            status: 401,
            statusText: "Unauthorized",
            headers: { "Content-Type": "application/json" }
          }
        ));
      }
      return nativeFetch.apply(this, arguments);
    };
  }

  function markGuest() {
    var name = document.getElementById("user-name");
    var avatar = document.getElementById("user-avatar");
    var chip = document.getElementById("user-chip");
    var profile = document.getElementById("profile-link");
    if (name) name.textContent = "访客";
    if (avatar) avatar.textContent = "访";
    if (chip) {
      chip.setAttribute("href", "/daliy/");
      chip.setAttribute("aria-label", "访客：云端演示版暂未接入班级系统");
      chip.setAttribute("title", "云端演示版暂未接入班级系统");
    }
    if (profile) profile.setAttribute("href", "/daliy/");
  }

  function scheduleGuestMark() {
    window.setTimeout(markGuest, 0);
  }

  if (document.readyState === "complete") {
    scheduleGuestMark();
  } else {
    window.addEventListener("load", scheduleGuestMark, { once: true });
  }
})();
"""

DDL_PLACEHOLDER = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0b1020">
  <meta name="description" content="DDL 查询在云端演示版中暂未接入。">
  <title>DDL 查询 · 云端演示版</title>
  <style>
    :root {
      --brand: #4f46e5;
      --brand-deep: #312e81;
      --ink: #0b1020;
      --muted: #5b6478;
      --line: #e6e8f2;
      --paper: #f6f7fb;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px 18px;
      color: var(--ink);
      background:
        radial-gradient(900px 420px at 18% -10%, rgba(99, 102, 241, .22), transparent 60%),
        radial-gradient(720px 360px at 100% 8%, rgba(14, 165, 233, .14), transparent 62%),
        linear-gradient(180deg, #eef1fb 0%, var(--paper) 54%, #ffffff 100%);
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
    }
    .card {
      width: min(760px, 100%);
      padding: clamp(26px, 5vw, 54px);
      border: 1px solid rgba(255, 255, 255, .8);
      border-radius: 30px;
      background: rgba(255, 255, 255, .92);
      box-shadow: 0 26px 80px rgba(30, 41, 88, .14);
      backdrop-filter: blur(18px);
    }
    .back {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
    }
    .back:hover { color: var(--brand); }
    .badge {
      display: flex;
      width: fit-content;
      align-items: center;
      gap: 7px;
      margin-top: 30px;
      padding: 7px 12px;
      border: 1px solid #dcd9ff;
      border-radius: 999px;
      color: var(--brand-deep);
      background: #f0efff;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .06em;
    }
    .badge::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--brand);
    }
    .icon {
      width: 76px;
      height: 76px;
      display: grid;
      place-items: center;
      margin: 30px 0 24px;
      border-radius: 22px;
      color: #fff;
      background: linear-gradient(145deg, #6366f1, #4338ca);
      box-shadow: 0 14px 30px rgba(79, 70, 229, .3);
      font-size: 18px;
      font-weight: 900;
      letter-spacing: -.02em;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 5.2vw, 44px);
      line-height: 1.2;
      letter-spacing: -.04em;
    }
    .lead {
      margin: 18px 0 0;
      max-width: 58ch;
      color: var(--muted);
      font-size: clamp(15px, 2vw, 17px);
      line-height: 1.9;
    }
    .note {
      margin-top: 28px;
      padding: 18px 20px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: #fafbff;
      color: #414b62;
      font-size: 14px;
      line-height: 1.9;
    }
    .note strong { color: var(--ink); }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 28px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 46px;
      padding: 0 20px;
      border-radius: 14px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 800;
    }
    .btn-primary {
      color: #fff;
      background: linear-gradient(145deg, #6366f1, #4338ca);
      box-shadow: 0 10px 22px rgba(79, 70, 229, .22);
    }
    .btn-ghost {
      color: var(--ink);
      border: 1px solid var(--line);
      background: #fff;
    }
    .foot {
      margin: 30px 0 0;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      color: #7a8398;
      font-size: 12px;
      line-height: 1.8;
    }
    @media (max-width: 480px) {
      .card { border-radius: 24px; padding: 24px 20px 26px; }
      .actions .btn { flex: 1 1 100%; }
    }
  </style>
</head>
<body>
  <main class="card">
    <a class="back" href="/"><span aria-hidden="true">←</span> 返回班级门户</a>
    <span class="badge">云端演示版 · 功能占位</span>
    <div class="icon" aria-hidden="true">DDL</div>
    <h1>DDL 查询<br>暂未接入云端</h1>
    <p class="lead">
      当前公开地址只部署了班级门户首页。DDL 查询、账号登录、归寝登记、活动报名等班级系统功能仍保留在本地站点，没有上传到这台服务器。
    </p>
    <div class="note">
      <strong>已部署：</strong>首页、新闻示例、各模块入口与说明。<br>
      <strong>未部署：</strong>DDL 数据、登录会话、数据库、QQ 消息抓取、班委后台。
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="/">返回首页</a>
      <a class="btn btn-ghost" href="/#/activities">看看班级活动占位</a>
    </div>
    <p class="foot">微电子学院 · 集成电路设计与集成系统26-1班</p>
  </main>
</body>
</html>
"""


def copy_source(relative: str) -> None:
    source = WEB / relative
    target = OUT / relative
    if not source.is_file():
        raise SystemExit(f"missing source file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build(demo: bool = True) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    home = (WEB / "home.html").read_text(encoding="utf-8")
    if demo:
        old_description = (
            '<meta name="description" content="微电子学院 · 集成电路设计与集成系统26-1班'
            '班级门户：DDL 查询、新闻资讯、班级活动、精彩瞬间、课程信息与归寝登记。">'
        )
        new_description = (
            '<meta name="description" content="微电子学院 · 集成电路设计与集成系统26-1班'
            '班级门户（云端演示）：新闻资讯、班级活动、精彩瞬间、课程信息与归寝登记。">'
        )
        if old_description not in home:
            raise SystemExit("expected home description not found")
        home = home.replace(old_description, new_description, 1)

    canonical = f'  <link rel="canonical" href="{CANONICAL}">\n'
    if "</head>" not in home:
        raise SystemExit("home.html has no </head>")
    home = home.replace("</head>", canonical + "</head>", 1)

    if demo:
        script_marker = '  <script defer src="assets/home.js'
        if script_marker not in home:
            raise SystemExit("home.html has no deferred home.js script")
        shim_script = (
            '  <script defer src="assets/static-shim.js"></script>\n'
            + script_marker
        )
        home = home.replace(script_marker, shim_script, 1)

    (OUT / "index.html").write_text(home, encoding="utf-8")
    for relative in SOURCE_FILES:
        copy_source(relative)

    if not demo:
        # 个人中心是真实登录页面，只随完整站点发布。
        for relative in ("assets/personalcenter.css", "assets/personalcenter.js"):
            copy_source(relative)
        personal = WEB / "personalcenter"
        if not personal.is_dir():
            raise SystemExit(f"missing personal center directory: {personal}")
        shutil.copytree(personal, OUT / "personalcenter", dirs_exist_ok=True)

    if demo:
        (OUT / "assets" / "static-shim.js").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "assets" / "static-shim.js").write_text(STATIC_SHIM, encoding="utf-8")

        (OUT / "daliy").mkdir(parents=True, exist_ok=True)
        (OUT / "daliy" / "index.html").write_text(DDL_PLACEHOLDER, encoding="utf-8")

    print(f"built ({'demo' if demo else 'full'}): {OUT}")
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(OUT)}  ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="build the real portal for the live DDL backend")
    build(demo=not parser.parse_args().full)
