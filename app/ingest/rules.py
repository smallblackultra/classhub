"""规则抽取：不依赖 LLM 的兜底解析。

LLM 不可用时（没配 key、超时、返回垃圾），这里的输出就是草稿的唯一来源；
LLM 可用时，它既提供兜底字段，也负责**密级覆写**和**时间交叉校验**。
"""
from __future__ import annotations

import re
from datetime import datetime

from ..domain import datetime_cn
from ..util import LOCAL_TZ, now_iso, parse_iso

# 判断“像不像一件事”
TASK_WORDS = (
    "截止", "截止时间", "deadline", "提交", "上交", "交", "完成", "填写", "填报",
    "报名", "考试", "补考", "测验", "测试", "作业", "报告", "实验", "论文", "大作业",
    "小组", "汇报", "展示", "答辩", "签到", "上传", "打卡", "接龙", "统计", "收集",
    "选课", "缴费", "领取", "班会", "开会", "会议",
)
CHAT_WORDS = ("哈哈", "收到", "谢谢", "早安", "晚安", "在吗", "有人吗", "表情包", "？?", "?")

CATEGORY_KEYWORDS = (
    ("exam", ("考试", "补考", "期末", "期中", "测验", "考场", "监考", "重修", "缓考", "笔试", "机考")),
    ("form", ("表格", "填写", "填报", "信息表", "登记表", "统计表", "收集表", "接龙", "问卷",
              "核对", "完善信息", "报名表", "名单", "收集一下", "填一下")),
    ("task", ("学院", "教务", "辅导员", "团委", "年级", "学工", "班会", "开会", "会议", "讲座",
              "签到", "打卡", "领取", "缴费", "选课", "评教", "评优", "材料")),
    ("homework", ("作业", "实验报告", "报告", "论文", "习题", "第*章", "实验", "课程设计",
                  "大作业", "小组作业", "预习", "复习")),
)

COMMITTEE_ORG = ("学院", "教务", "辅导员", "团委", "年级", "学工", "教务处", "系里", "学院办")
COMMITTEE_TARGET = ("班委", "班长", "团支书", "各位班干", "班干部", "各班", "各班委", "学生干部")
CLASS_TARGET = ("全班", "各位同学", "所有同学", "全体同学", "大家", "每位同学", "所有人", "同学们")

RE_MENTION = re.compile(r"[@＠](?:全体成员|所有人|[\w\u4e00-\u9fa5．·]{1,16})(?=\s|$|[，。：:！!？?])")
RE_CQ_AT = re.compile(r"\[CQ:at,qq=\d+\]")
RE_CQ_OTHER = re.compile(r"\[CQ:[^\]]+\]")
RE_URL = re.compile(r"https?://[^\s<>\"'）)】]+")
RE_COURSE = re.compile(r"《([^》]{1,40})》")
RE_COURSE_LABEL = re.compile(r"(?:课程|科目|学科)\s*[:：]\s*([^\s，。；,;]{1,30})")
RE_PREFIX = re.compile(
    r"^(?:通知|提醒|公告|紧急通知|重要通知|关于|【[^】]{1,20}】|\[[^\]]{1,20}\]|@全体成员)\s*[:：\-—]?\s*"
)
RE_SALUTATION = re.compile(
    r"^(?:各位同学|全体同学|所有同学|同学们|各位班委|班委们|大家|各位|班长|团支书|学委)\s*[:：,，]?\s*"
)
RE_TAIL_NOISE = re.compile(r"(?:收到请回复|收到请扣1|谢谢大家|麻烦大家|请知悉|特此通知)[。！!]?$")
RE_SENTENCE_END = re.compile(r"[。；;！!？?]")
RE_CLAUSE_SPLIT = re.compile(r"[，。；;！!？?]")
RE_DATE_ONLY = re.compile(r"^[\d\s:：.\-/年月日号点分上午下午晚上第周期周星期礼拜]+$")
RE_TIMEISH = re.compile(
    r"(?:上午|下午|晚上|中午|凌晨)?\s*\d{1,2}\s*[:：]\s*\d{2}"
    r"(?:\s*[-~—至]\s*\d{1,2}\s*[:：]\s*\d{2})?"
)


def clean_text(raw: str) -> str:
    s = RE_CQ_AT.sub("", raw or "")
    s = RE_CQ_OTHER.sub("", s)
    s = RE_MENTION.sub(" ", s)
    return s.strip()


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def find_link(text: str) -> str:
    m = RE_URL.search(text)
    if not m:
        return ""
    url = m.group(0).rstrip("，。；,;、")
    return url


def find_course(text: str) -> str:
    m = RE_COURSE.search(text) or RE_COURSE_LABEL.search(text)
    return m.group(1).strip() if m else ""


def infer_category(text: str) -> tuple[str, bool]:
    """返回 (category, 是否有明确关键词)。"""
    for cat, words in CATEGORY_KEYWORDS:
        for w in words:
            if w == "第*章":
                if re.search(r"第\s*\d+\s*章", text):
                    return cat, True
            elif w in text:
                return cat, True
    return "homework", False


def infer_audience(text: str, category: str) -> tuple[str, str, bool]:
    """返回 (audience, 理由, 是否高置信)。

    顺序即优先级：学院→班委 最硬；考试必须全班可见；整班称呼→全班。
    其余一律取严（committee）并交给人工确认。
    """
    has_org = any(w in text for w in COMMITTEE_ORG)
    has_ctarget = any(w in text for w in COMMITTEE_TARGET)
    if has_org and has_ctarget:
        return "committee", "学院/教务下发给班委的任务", True
    if category == "exam" or any(w in text for w in ("考试", "考场", "监考")):
        return "class", "考试信息全班必须可见", True
    if any(w in text for w in CLASS_TARGET):
        return "class", "原文点名全班同学", True
    if category == "homework":
        course = find_course(text)
        if course or re.search(r"第\s*\d+\s*章|实验|作业|报告|论文", text):
            return "class", "课程作业面向全班", True
    if category == "form" and any(w in text for w in ("填", "接龙", "统计", "收集")):
        return "committee", "未点名全班，先按班委事项处理", False
    return "committee", "未识别到明确受众，取严处理", False


def _score_line(ln: str, due_raw: str) -> int:
    score = 0
    if due_raw and due_raw in ln:
        score += 3
    if any(w in ln for w in TASK_WORDS):
        score += 2
    if 4 <= len(ln) <= 60:
        score += 1
    if RE_URL.fullmatch(ln.strip()):
        score -= 5
    if ln.endswith(("吗", "呢", "呀")):
        score -= 2
    return score


def _score_clause(cl: str, due_raw: str) -> int:
    core = cl.replace(due_raw, "") if due_raw else cl
    core = RE_TIMEISH.sub(" ", core).strip(" ：:，,于在至到")
    if len(core) < 3 or RE_DATE_ONLY.match(core):
        return -6
    score = 0
    if due_raw and due_raw in cl:
        score += 3
    if any(w in cl for w in TASK_WORDS):
        score += 2
    if 3 <= len(core) <= 34:
        score += 2
    if "：" in cl or ":" in cl:
        score -= 1
    return score


def _clauses(ln: str) -> list[str]:
    out: list[str] = []
    for part in RE_CLAUSE_SPLIT.split(ln):
        part = part.strip()
        if not part:
            continue
        idx = part.find("：")
        if idx < 0:
            idx = part.find(":")
        if 1 <= idx <= 16:
            head, tail = part[:idx].strip(), part[idx + 1:].strip()
            if head:
                out.append(head)
            if tail:
                out.append(tail)
        else:
            out.append(part)
    return out


def _strip_salutation(s: str) -> str:
    return RE_SALUTATION.sub("", s)


def _clean_title(ln: str, due_raw: str) -> str:
    best, best_score = ln, -99
    for cl in _clauses(ln):
        sc = _score_clause(cl, due_raw)
        if sc > best_score:
            best, best_score = cl, sc
    t = best.strip()
    t = _strip_salutation(t)
    t = RE_PREFIX.sub("", t)
    if due_raw:
        due = re.escape(due_raw)
        t = re.sub(rf"(?:于|在)?\s*{due}\s*(?:之前|以前|前)", "", t)
        t = re.sub(rf"(?:于|在)\s*{due}", "", t)
        t = re.sub(due, "", t)
        t = re.sub(r"截止(?:时间|日期)?", "", t).replace("之前", "").replace("以前", "")
        t = re.sub(r"(?<=[\u4e00-\u9fa5])前(?=[\s，,。]|$)", " ", t)
    t = RE_TIMEISH.sub(" ", t)
    t = re.sub(r"[于在]\s+(?=(?:提交|完成|交|填|上传|报名|参加|领取))", "", t)
    t = RE_TAIL_NOISE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" ，。；;：:、-—")
    if len(t) < 2:
        t = RE_PREFIX.sub("", _strip_salutation(ln)).strip()
    if len(t) > 40:
        m = RE_SENTENCE_END.search(t)
        if m and m.start() >= 8:
            t = t[:m.start()]
    if len(t) > 80:
        t = t[:77].rstrip() + "…"
    return t


def extract_by_rules(text: str, *, occurred_at: str | None = None,
                     hints: dict | None = None) -> dict:
    hints = hints or {}
    occurred = parse_iso(occurred_at) if occurred_at else datetime.now(LOCAL_TZ)
    body = clean_text(text)
    lines = _lines(body)

    due = None
    if hints.get("due_text"):
        due = datetime_cn.parse_due(hints["due_text"], occurred)
    if due is None:
        due = datetime_cn.parse_due(body, occurred)

    due_iso = datetime_cn.due_to_iso(due) if due else None
    due_raw = (due or {}).get("raw", "") or hints.get("due_text", "")

    title = (hints.get("title") or "").strip()
    if not title and lines:
        ranked = sorted(lines, key=lambda ln: _score_line(ln, due_raw), reverse=True)
        title = _clean_title(ranked[0], due_raw) if ranked else ""
    if not title:
        title = (body[:40] or "").strip()

    category, cat_explicit = infer_category(body)
    if hints.get("category"):
        category = hints["category"]
        cat_explicit = True

    audience, reason, aud_confident = infer_audience(body, category)
    if hints.get("audience"):
        audience, aud_confident = hints["audience"], True

    course = hints.get("course") or find_course(body)
    link = hints.get("link") or find_link(body)

    is_task = bool(due or any(w in body for w in TASK_WORDS)) and not (
        len(body) <= 12 and any(w in body for w in CHAT_WORDS)
    )
    if not lines:
        is_task = False

    missing = []
    if not due_iso:
        missing.append("due_at")
    if len(title) < 2:
        missing.append("title")

    confidence = 0.55
    if due_iso:
        confidence += 0.20
    if cat_explicit:
        confidence += 0.10
    if aud_confident:
        confidence += 0.08
    if len(title) >= 4:
        confidence += 0.04
    if not is_task:
        confidence = min(confidence, 0.3)
    confidence = round(min(confidence, 0.95), 2)

    needs_review = bool(missing) or not aud_confident or confidence < 0.65 or not due_iso

    return {
        "is_task": is_task,
        "title": title,
        "category": category,
        "audience": audience,
        "audience_reason": reason,
        "audience_confident": aud_confident,
        "course": course,
        "due_at": due_iso,
        "due_at_raw": due_raw,
        "missing_fields": missing,
        "confidence": confidence,
        "needs_review": needs_review,
        "link": link,
        "engine": "rules",
    }


if __name__ == "__main__":
    samples = [
        "【通知】@全体成员 学院要求各班班委于11月10日前提交本班医保信息表，谢谢大家。",
        "各位同学：下周三前提交第5章实验报告，学习通上传，截止 23:59。",
        "期末考试安排：11月20日 上午9:00-11:00，教三201，务必带学生证。",
        "哈哈哈哈",
    ]
    for s in samples:
        print("-" * 60)
        print(s)
        print(extract_by_rules(s, occurred_at="2026-11-04T15:00:00+08:00"))
