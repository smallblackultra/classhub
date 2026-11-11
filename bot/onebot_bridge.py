"""OneBot v11 → ClassHub 桥接服务（NapCat / LLOneBot / go-cqhttp 通用）。

工作方式
--------
1. QQ 机器人框架把「群消息」事件 POST 到本服务的 /onebot（HTTP 上报）。
2. 本服务只处理 **@了机器人** 的群消息，去掉 @ 片段后转发给 ClassHub 的
   ``POST /api/ingest/qq``，由平台侧完成「抽取 → 草稿」，**不会直接发布**。
3. 若配置了 ONEBOT_URL，会在群里回一句结果（已记录/重复/未识别）。

环境变量
--------
CLASSHUB_URL       默认 http://127.0.0.1:8000
CLASSHUB_TOKEN     管理端「数据源」页面生成的一次性令牌（qq_xxx），必填
ONEBOT_URL         OneBot HTTP API 地址，例如 http://127.0.0.1:3000；留空则只在本地记日志
ONEBOT_TOKEN       OneBot HTTP API 的 access token（可选）
ONEBOT_SELF_ID     机器人自己的 QQ 号；用于判断 @ 是否指向自己
BOT_WEBHOOK_SECRET 校验上报方（可选）：请求需带 X-Bot-Secret / Authorization: Bearer /
                   X-Signature: sha1=<HMAC-SHA1(secret, body) 十六进制>（SnowLuma/OneBot 官方风格）
LISTEN_HOST/PORT   本服务监听地址，默认 127.0.0.1:8790
GROUP_NAMES        可选 JSON，例如 {"123456":"计算机 2301 班群"}，用于展示更好看的群名

启动
----
    python bot/onebot_bridge.py

NapCat 侧配置（HTTP 服务端 / HTTP 上报）：
    上报地址 http://127.0.0.1:8790/onebot
    消息格式 array（推荐）或 string 均可
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLASSHUB_URL = os.environ.get("CLASSHUB_URL", "http://127.0.0.1:8000").rstrip("/")
CLASSHUB_TOKEN = os.environ.get("CLASSHUB_TOKEN", "").strip()
ONEBOT_URL = os.environ.get("ONEBOT_URL", "").rstrip("/")
ONEBOT_TOKEN = os.environ.get("ONEBOT_TOKEN", "").strip()
SELF_ID = os.environ.get("ONEBOT_SELF_ID", "").strip()
WEBHOOK_SECRET = os.environ.get("BOT_WEBHOOK_SECRET", "").strip()
HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("LISTEN_PORT", "8790"))
TZ = timezone(timedelta(hours=8))

try:
    GROUP_NAMES = json.loads(os.environ.get("GROUP_NAMES", "{}"))
except json.JSONDecodeError:
    GROUP_NAMES = {}


def log(message: str) -> None:
    stamp = datetime.now(TZ).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 15.0):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def _post_form(url: str, payload: dict, timeout: float = 10.0):
    """兼容大量只接受表单的 OneBot 实现。"""
    import urllib.parse

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def send_group(group_id, text: str, at_user=None) -> None:
    if not ONEBOT_URL:
        log(f"[仅日志] 群 {group_id} 回复：{text}")
        return
    message = []
    if at_user:
        message.append({"type": "at", "data": {"qq": str(at_user)}})
        message.append({"type": "text", "data": {"text": " "}})
    message.append({"type": "text", "data": {"text": text}})
    params = {"group_id": group_id, "message": message}
    if ONEBOT_TOKEN:
        params["access_token"] = ONEBOT_TOKEN
    try:
        _post_json(f"{ONEBOT_URL}/send_group_msg", params)
    except (urllib.error.URLError, OSError) as exc:
        log(f"发送群消息失败，改用表单重试：{exc}")
        try:
            _post_form(f"{ONEBOT_URL}/send_group_msg", {
                "group_id": str(group_id),
                "message": json.dumps(message, ensure_ascii=False),
                **({"access_token": ONEBOT_TOKEN} if ONEBOT_TOKEN else {}),
            })
        except Exception as exc2:  # noqa: BLE001
            log(f"群消息发送最终失败：{exc2}")


def mentions_bot(event: dict) -> tuple[bool, str, str]:
    """返回 (是否需要处理, 去掉 @ 后的纯文本, 引用文本)。"""
    segments = event.get("message")
    text_parts: list[str] = []
    mentioned = False
    reply_text = ""

    if isinstance(segments, list):
        for seg in segments:
            kind = seg.get("type")
            data = seg.get("data") or {}
            if kind == "text":
                text_parts.append(str(data.get("text", "")))
            elif kind == "at":
                qq = str(data.get("qq", ""))
                if SELF_ID and qq == SELF_ID:
                    mentioned = True
                elif not SELF_ID and qq not in ("all", ""):
                    # 没有配置自身 QQ 时，任何 @ 都当作在叫机器人（群里一般只有它会响应）
                    mentioned = True
            elif kind == "reply":
                reply_text = str(data.get("text") or "")
    else:
        text_parts.append(str(segments or ""))

    text = "".join(text_parts).strip()
    if isinstance(segments, str) and segments.strip().startswith("[CQ:at"):
        mentioned = True
    if not mentioned and SELF_ID and f"@{SELF_ID}" in text:
        mentioned = True
    return mentioned, text, reply_text


def handle_event(event: dict) -> None:
    if event.get("post_type") != "message" or event.get("message_type") != "group":
        return
    group_id = event.get("group_id")
    sender = event.get("sender") or {}
    sender_id = sender.get("user_id") or event.get("user_id")
    sender_name = sender.get("card") or sender.get("nickname") or str(sender_id)
    mentioned, text, reply_text = mentions_bot(event)
    if not mentioned or not text:
        return
    if not CLASSHUB_TOKEN:
        log("缺少 CLASSHUB_TOKEN，无法转发；请先在管理端创建 QQ 机器人数据源")
        return

    ts = event.get("time")
    occurred = datetime.fromtimestamp(int(ts), TZ).isoformat() if ts else None
    payload = {
        "group_id": str(group_id),
        "group_name": GROUP_NAMES.get(str(group_id), f"QQ群 {group_id}"),
        "sender_id": str(sender_id),
        "sender_name": sender_name,
        "msg_id": str(event.get("message_id") or event.get("msg_id") or ""),
        "text": text,
        "reply_text": reply_text,
        "occurred_at": occurred,
    }
    try:
        status, body = _post_json(
            f"{CLASSHUB_URL}/api/ingest/qq", payload,
            headers={"X-Classhub-Token": CLASSHUB_TOKEN},
        )
    except (urllib.error.URLError, OSError) as exc:
        log(f"转发 ClassHub 失败：{exc}")
        return
    log(f"转发结果 {status}：{json.dumps(body, ensure_ascii=False)[:300]}")
    if status != 200:
        return

    state = (body or {}).get("status")
    if state == "draft":
        item = body.get("item") or {}
        title = item.get("title") or "新任务"
        due = item.get("due_local") or ""
        send_group(group_id, f"已记下《{title}》{('，截止 ' + due[:16].replace('T', ' ')) if due else ''}，"
                             "等班委确认后进入班级列表。", at_user=sender_id)
    elif state == "duplicate":
        send_group(group_id, "这条消息之前已经记录过啦。", at_user=sender_id)
    elif state in ("ignored", "invalid"):
        send_group(group_id, "这条消息没识别出明确的截止时间，已放进「未解析队列」，班委可以手动补录。",
                   at_user=sender_id)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log(f"{self.address_string()} {fmt % args}")

    def handle_one_request(self) -> None:
        # 上报端（SnowLuma）发完心跳就断开是常态，不让它刷异常栈
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True

    def _reply(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self, raw: bytes = b"") -> bool:
        if not WEBHOOK_SECRET:
            return True
        if hmac.compare_digest(self.headers.get("X-Bot-Secret", ""), WEBHOOK_SECRET):
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {WEBHOOK_SECRET}" or auth == WEBHOOK_SECRET:
            return True
        # SnowLuma / NapCat HTTP 上报风格：X-Signature: sha1=hex(hmac_sha1(secret, body))
        sig = self.headers.get("X-Signature", "")
        if sig.startswith("sha1=") and raw:
            expect = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha1).hexdigest()
            if hmac.compare_digest(sig[5:].strip().lower(), expect):
                return True
        # 也接受 ?access_token=xxx
        if "?" in self.path:
            from urllib.parse import parse_qs
            query = parse_qs(self.path.split("?", 1)[1])
            if (query.get("access_token") or [""])[0] == WEBHOOK_SECRET:
                return True
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", ""):
            self._reply(200, {"ok": True, "classhub": CLASSHUB_URL,
                              "reply_enabled": bool(ONEBOT_URL)})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.split("?", 1)[0].rstrip("/").endswith("/onebot"):
            self._reply(404, {"error": "not found"})
            return
        # 先读 body 再鉴权：否则失败时残留 body 会被当成下一个请求行，刷 400/501
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
        except (ValueError, OSError):
            self.close_connection = True
            self._reply(400, {"error": "bad content-length"})
            return
        if not self._authorized(raw):
            self.close_connection = True
            self._reply(401, {"error": "unauthorized"})
            return
        try:
            event = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._reply(400, {"error": "bad json"})
            return
        # NapCat 的 HTTP 上报可能带 retcode 包装，也可能直接是事件体
        if isinstance(event, dict) and "post_type" not in event and isinstance(event.get("data"), dict):
            event = event["data"]
        self._reply(200, {"ok": True})
        try:
            handle_event(event)
        except Exception as exc:  # noqa: BLE001 - 上报处理失败不能影响 OneBot 重试
            log(f"处理事件异常：{exc}")


def main() -> int:
    if not CLASSHUB_TOKEN:
        log("警告：未设置 CLASSHUB_TOKEN，收到消息后不会转发（仅打印）。")
    log(f"监听 http://{HOST}:{PORT}/onebot  →  {CLASSHUB_URL}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
