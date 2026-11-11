"""HTTP 服务：路由分发、会话、CSRF、静态文件。只用标准库。"""
from __future__ import annotations

import hmac
import json
import mimetypes
import sys
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__, auth, classes, config, db
from .domain import policy
from .errors import (ApiError, internal, invalid, not_found, pending_approval, too_large,
                     unauthenticated)
from .request import Ctx, Response
from .router import match
from . import api  # noqa: F401  —— 导入即注册全部路由

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"ClassHub/{__version__}"
    timeout = 60

    # ------------------------------------------------------------ 入口

    def do_GET(self):        self._handle()
    def do_HEAD(self):       self._handle(head=True)
    def do_POST(self):       self._handle()
    def do_PATCH(self):      self._handle()
    def do_PUT(self):        self._handle()
    def do_DELETE(self):     self._handle()
    def do_OPTIONS(self):    self._handle()

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True

    def _handle(self, head: bool = False) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path) or "/"
        self._sent = False
        is_app = False
        try:
            # 兼容旧的 /daily 挂载前缀；根路径 / 现在留给班级门户首页。
            base = getattr(config, "PUBLIC_BASE", "")
            if base:
                if path == base:
                    query = ("?" + parsed.query) if parsed.query else ""
                    return self._redirect(base + "/" + query, head)
                if path.startswith(base + "/"):
                    path = path[len(base):] or "/"
                    is_app = True

            # /daliy 是 DDL 应用规范路径，/daily 作为兼容别名。
            prefixes = (getattr(config, "APP_PREFIX", ""), *getattr(config, "APP_ALIASES", ()))
            for prefix in prefixes:
                if not prefix:
                    continue
                if path == prefix:
                    query = ("?" + parsed.query) if parsed.query else ""
                    return self._redirect(prefix + "/" + query, head)
                if path.startswith(prefix + "/"):
                    path = path[len(prefix):] or "/"
                    is_app = True
                    break

            # 旧应用外壳在根路径没有入口，避免 /index.html 变成第二个 DDL 首页。
            if not is_app and path == "/index.html":
                query = ("?" + parsed.query) if parsed.query else ""
                return self._redirect("/" + query, head)

            if path == "/api" or path.startswith("/api/"):
                self._serve_api(parsed, path, head)
            else:
                self._serve_static(path, head, is_app=is_app)
        except ApiError as exc:
            self._send_json(exc.status, exc.payload(), head=head)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:  # noqa: BLE001 - 兜底，避免线程崩溃
            traceback.print_exc()
            self._send_json(500, internal().payload(), head=head)

    def _redirect(self, location: str, head: bool = False) -> None:
        self._sent = True
        body = b""
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()
        if not head:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    # ------------------------------------------------------------ API

    def _serve_api(self, parsed, path: str, head: bool) -> None:
        route, params = match(self.command, path)
        if route is None:
            raise not_found("接口不存在")

        raw = self._read_body()
        body: dict = {}
        if raw:
            try:
                parsed_body = json.loads(raw.decode("utf-8"))
            except UnicodeDecodeError:
                raise invalid("请求体必须是 UTF-8 编码的 JSON") from None
            except json.JSONDecodeError:
                raise invalid("请求体不是合法 JSON") from None
            if not isinstance(parsed_body, dict):
                raise invalid("请求体必须是 JSON 对象")
            body = parsed_body

        cookies = self._read_cookies()
        slug = cookies.get(config.COOKIE_CLASS) or ""
        db_path = classes.resolve_cookie(slug)
        conn = db.connect(db_path)
        try:
            session = user = None
            token = cookies.get(config.COOKIE_SID)
            if token:
                found = auth.find_session(conn, token)
                if found:
                    session, user = found

            if route.auth == "required" and user is None:
                raise unauthenticated()
            if user is not None:
                if user["status"] == "disabled":
                    raise ApiError("账号已被停用，请联系班委", code="account_disabled", status=403)
                if user["status"] == "pending" and not route.allow_pending:
                    raise pending_approval()
                if route.csrf and self.command in ("POST", "PATCH", "PUT", "DELETE"):
                    self._check_csrf(session)
                if route.committee:
                    policy.guard_committee(user)
                if user["must_change_password"] and path not in (
                    "/api/auth/change-password", "/api/auth/me", "/api/auth/logout",
                ):
                    raise ApiError(
                        "首次登录请先修改初始密码", code="must_change_password", status=403
                    )

            ctx = Ctx(
                conn=conn,
                method=self.command,
                path=path,
                params=params,
                query=parse_qs(parsed.query, keep_blank_values=True),
                body=body,
                cookies=cookies,
                ip=self._client_ip(),
                ua=self.headers.get("User-Agent", "")[:300],
                user=user,
                session=session,
                headers={k.lower(): v for k, v in self.headers.items()},
                slug=classes.slug_of_path(db_path),
            )
            result = route.handler(ctx)
            self._write_result(result, head)
        finally:
            conn.close()

    def _check_csrf(self, session) -> None:
        if session is None:
            return
        given = self.headers.get(config.CSRF_HEADER) or ""
        expected = session["csrf"] or ""
        if not given or not expected or not hmac.compare_digest(given, expected):
            raise ApiError("CSRF 校验失败，请刷新页面后重试", code="csrf_failed", status=403)

    def _send_raw(self, status: int, data: bytes, content_type: str, *,
                  headers: dict | None = None, cookies: list[str] | None = None,
                  head: bool = False) -> None:
        if self._sent:
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for item in cookies or []:
            self.send_header("Set-Cookie", item)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self._sent = True
        if not head and data:
            self.wfile.write(data)

    def _read_body(self) -> bytes:
        raw_len = self.headers.get("Content-Length")
        if not raw_len:
            return b""
        try:
            length = int(raw_len)
        except ValueError:
            raise invalid("Content-Length 不合法") from None
        if length < 0:
            raise invalid("Content-Length 不合法")
        if length > config.MAX_BODY_BYTES:
            raise too_large()
        return self.rfile.read(length) if length else b""

    def _read_cookies(self) -> dict[str, str]:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return {}
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:  # noqa: BLE001 - 畸形 cookie 直接忽略
            return {}
        return {k: morsel.value for k, morsel in jar.items()}

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
        return (self.client_address[0] if self.client_address else "")[:64]

    def _write_result(self, result, head: bool) -> None:
        if result is None:
            self._send_json(204, None, head=head)
        elif isinstance(result, Response):
            if result.raw is not None:
                self._send_raw(result.status, result.raw, result.content_type,
                               headers=result.headers, cookies=result.cookies, head=head)
            else:
                self._send_json(result.status, result.body, headers=result.headers,
                                cookies=result.cookies, head=head)
        elif isinstance(result, tuple) and len(result) == 2:
            status, payload = result
            self._send_json(status, payload, head=head)
        else:
            self._send_json(200, result, head=head)

    def _send_json(self, status: int, payload, *, headers: dict | None = None,
                   cookies: list[str] | None = None, head: bool = False) -> None:
        if self._sent:
            return
        data = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for item in cookies or []:
            self.send_header("Set-Cookie", item)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self._sent = True
        if not head and data:
            self.wfile.write(data)

    # ------------------------------------------------------------ 静态资源

    def _serve_static(self, path: str, head: bool, *, is_app: bool = False) -> None:
        root = config.WEB_DIR.resolve()
        home = "index.html" if is_app else "home.html"
        if path in ("/", ""):
            path = "/" + home
        rel = path.lstrip("/")
        target = (root / rel).resolve()
        if not target.is_relative_to(root):
            return self._send_plain(404, "Not Found", head)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            # SPA 回退：非静态资源路径交给对应前端入口。
            if Path(rel).suffix == "":
                target = root / home
            else:
                return self._send_plain(404, "Not Found", head)
        try:
            data = target.read_bytes()
        except OSError:
            return self._send_plain(404, "Not Found", head)

        content_type = MIME_TYPES.get(target.suffix.lower())
        if content_type is None:
            guessed, _ = mimetypes.guess_type(str(target))
            content_type = (guessed or "application/octet-stream") + (
                "; charset=utf-8" if (guessed or "").startswith("text/") else "")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self._sent = True
        if not head:
            self.wfile.write(data)

    def _send_plain(self, status: int, message: str, head: bool = False) -> None:
        if self._sent:
            return
        data = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._sent = True
        if not head:
            self.wfile.write(data)

    # ------------------------------------------------------------ 日志

    def log_request(self, code="-", size="-"):
        try:
            sys.stderr.write(f"  {self.command:<6} {self.path[:120]:<60} {code}\n")
        except Exception:  # noqa: BLE001
            pass

    def log_message(self, fmt, *args):
        pass


def migrate_all_classes() -> None:
    """启动时把每个班级库升级到最新 schema（补列 / 建新表，幂等）。"""
    from . import classes

    for slug, path in classes.iter_dbs():
        try:
            conn = db.connect(path)
        except Exception as exc:  # 单个库坏了不影响其它班
            sys.stderr.write(f"[migrate] {slug} 跳过：{exc}\n")
            continue
        try:
            db.init_schema(conn)
        except Exception as exc:
            sys.stderr.write(f"[migrate] {slug} 失败：{exc}\n")
        finally:
            conn.close()


def make_server(host: str, port: int) -> AppServer:
    return AppServer((host, port), Handler)
