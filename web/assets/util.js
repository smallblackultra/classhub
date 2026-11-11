/* 工具层：h / html、时间格式化、图标、常量 */
(function () {
  "use strict";
  const { h, Fragment } = window.preact;
  const html = window.htm.bind(h);

  const pad = (n) => String(n).padStart(2, "0");
  const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

  /* 用“北京时间”计算今天，避免浏览器时区不同导致分组错位 */
  function bjParts(epoch) {
    const d = new Date((epoch == null ? Date.now() : epoch) + 8 * 3600 * 1000);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(),
             hh: d.getUTCHours(), mm: d.getUTCMinutes(), w: d.getUTCDay() };
  }
  function dateToUTC(str) {
    const [y, m, d] = str.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  }
  function dayDiff(a, b) { return Math.round((dateToUTC(b) - dateToUTC(a)) / 86400000); }
  function todayStr() { const p = bjParts(); return `${p.y}-${pad(p.m)}-${pad(p.d)}`; }

  /* 解析后端返回的本地时间串 2026-11-06T23:59:00+08:00 */
  function parseLocal(iso) {
    if (!iso) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
    if (!m) return null;
    return { y: +m[1], m: +m[2], d: +m[3], hh: +m[4], mm: +m[5],
             date: `${m[1]}-${m[2]}-${m[3]}`, w: new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay() };
  }

  function fmtDate(iso) {
    const p = parseLocal(iso);
    return p ? `${p.m}月${p.d}日 ${WEEK[p.w]}` : "";
  }
  function fmtDateTime(iso) {
    const p = parseLocal(iso);
    return p ? `${p.m}-${pad(p.d)} ${WEEK[p.w]} ${pad(p.hh)}:${pad(p.mm)}` : "";
  }
  function fmtTime(iso) {
    const p = parseLocal(iso);
    return p ? `${pad(p.hh)}:${pad(p.mm)}` : "";
  }

  /* “今天 23:59 / 明天 09:00 / 周四 23:59 / 11-12 23:59” */
  function dueShort(item) {
    if (!item || !item.due_local) return "未设置截止";
    const p = parseLocal(item.due_local);
    const diff = dayDiff(todayStr(), p.date);
    const hm = item.all_day ? "" : ` ${pad(p.hh)}:${pad(p.mm)}`;
    if (diff === 0) return "今天" + hm;
    if (diff === 1) return "明天" + hm;
    if (diff === 2) return "后天" + hm;
    if (diff > 1 && diff < 7) return WEEK[p.w] + hm;
    return `${pad(p.m)}-${pad(p.d)}` + hm;
  }

  /* 倒计时：{ text, tone } */
  function countdown(item) {
    if (!item || !item.due_at) return { text: "无截止时间", tone: "muted" };
    const ms = Date.parse(item.due_at) - Date.now();
    if (ms < 0) {
      const days = Math.ceil(-ms / 86400000);
      return { text: days >= 1 ? `已逾期 ${days} 天` : "已逾期", tone: "late", days: -days };
    }
    const hours = ms / 3600000;
    if (hours < 1) return { text: `剩 ${Math.max(1, Math.round(ms / 60000))} 分钟`, tone: "soon", days: 0 };
    if (hours < 24) return { text: `剩 ${Math.round(hours)} 小时`, tone: "soon", days: 0 };
    const days = Math.floor(hours / 24);
    return { text: `剩 ${days} 天`, tone: days <= 3 ? "soon" : "normal", days };
  }

  function groupOf(item) {
    if (!item) return "later";
    if (item.is_overdue) return "overdue";
    if (!item.due_date) return "none";
    const diff = dayDiff(todayStr(), item.due_date);
    if (diff === 0) return "today";
    if (diff === 1) return "tomorrow";
    if (diff > 1 && diff <= 7) return "week";
    return "later";
  }
  const GROUPS = [
    { key: "overdue", label: "已逾期" },
    { key: "today", label: "今天" },
    { key: "tomorrow", label: "明天" },
    { key: "week", label: "本周内" },
    { key: "later", label: "更晚" },
    { key: "none", label: "无截止时间" },
  ];

  const CATEGORY = {
    homework: { label: "作业", tone: "blue", icon: "book" },
    task: { label: "任务", tone: "green", icon: "megaphone" },
    exam: { label: "考试", tone: "red", icon: "exam" },
  };
  const TASK_SUBTYPE = {
    form: { label: "表格", tone: "amber" },
    quiz: { label: "答题", tone: "violet" },
    study: { label: "学习", tone: "blue" },
    other: { label: "其他", tone: "green" },
  };
  const TASK_LEVEL = { college: "学院", class: "班级" };
  const ROLE = { student: "同学", monitor: "班长", secretary: "团支书", admin: "管理员" };
  const SOURCE = { manual: "手动录入", qq: "QQ 群", paste: "粘贴导入", bookmarklet: "书签抓取",
                   chaoxing: "学习通", yuketang: "雨课堂", import: "批量导入" };
  const STATUS = { draft: "草稿", published: "已发布", archived: "已归档" };

  function initials(name) {
    if (!name) return "?";
    const s = String(name).trim();
    return s.length <= 2 ? s : s.slice(0, 1);
  }
  function pct(done, total) {
    if (!total) return 0;
    return Math.min(100, Math.round((done / total) * 100));
  }

  const ICONS = {
    clock: ["M12 7v5l3 2", "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"],
    check: ["M20 6L9 17l-5-5"],
    plus: ["M12 5v14", "M5 12h14"],
    edit: ["M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"],
    trash: ["M3 6h18", "M8 6V4h8v2", "M19 6l-1 14H6L5 6", "M10 11v5", "M14 11v5"],
    archive: ["M3 4h18v4H3z", "M5 8v12h14V8", "M10 12h4"],
    users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M22 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
    user: ["M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2", "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"],
    logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
    close: ["M18 6L6 18", "M6 6l12 12"],
    chevron: ["M9 6l6 6-6 6"],
    back: ["M15 18l-6-6 6-6"],
    sparkles: ["M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z", "M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z"],
    book: ["M4 19.5A2.5 2.5 0 0 1 6.5 17H20", "M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"],
    clipboard: ["M9 2h6v4H9z", "M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2", "M9 12h6", "M9 16h4"],
    megaphone: ["M3 11l18-7v16L3 13v-2z", "M7 13v6a2 2 0 0 0 4 0v-4"],
    exam: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M9 15l2 2 4-4"],
    bell: ["M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9", "M13.7 21a2 2 0 0 1-3.4 0"],
    link: ["M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5", "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"],
    pin: ["M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z", "M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
    search: ["M21 21l-4.3-4.3", "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z"],
    refresh: ["M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"],
    copy: ["M9 9h10v12H9z", "M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"],
    send: ["M22 2L11 13", "M22 2l-7 20-4-9-9-4 20-7z"],
    calendar: ["M4 5h16v16H4z", "M8 3v4", "M16 3v4", "M4 10h16"],
    inbox: ["M4 4h16v12H4z", "M4 16l3 4h10l3-4", "M8 10h8"],
    alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
    shield: ["M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6l8-4z", "M9 12l2 2 4-4"],
    settings: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"],
    list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
    clock2: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 6v6l4 2"],
  };

  function icon(name, cls) {
    const paths = ICONS[name] || ICONS.alert;
    return html`<svg class=${cls || ""} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      ${paths.map((d) => html`<path d=${d} />`)}
    </svg>`;
  }

  function copyText(text) {
    const s = String(text || "");
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(s);
    }
    return new Promise((resolve, reject) => {
      try {
        const ta = document.createElement("textarea");
        ta.value = s; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); document.body.removeChild(ta); resolve();
      } catch (e) { reject(e); }
    });
  }

  window.U = {
    h, Fragment, html, icon,
    pad, WEEK, bjParts, todayStr, dayDiff, parseLocal,
    fmtDate, fmtDateTime, fmtTime, dueShort, countdown, groupOf, GROUPS,
    CATEGORY, TASK_SUBTYPE, TASK_LEVEL, ROLE, SOURCE, STATUS, initials, pct, copyText,
  };
})();


