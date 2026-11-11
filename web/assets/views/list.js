/* 首页：截止日列表 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState, useEffect, useMemo, useRef } = window.preactHooks;
  const { Button, Chip, Seg, Badge, Empty, Note, LoadingList, ErrorView, useApi, Stat } = window.CDH.ui;
  const U = window.U;

  const CAT_ORDER = ["homework", "task", "exam"];
  const SUB_ORDER = ["form", "quiz", "study", "other"];
  const LEVEL_ORDER = ["college", "class"];

  function greeting() {
    const hour = U.bjParts().hh;
    if (hour >= 5 && hour < 11) return "早上好";
    if (hour >= 11 && hour < 13) return "中午好";
    if (hour >= 13 && hour < 18) return "下午好";
    if (hour >= 18 && hour < 23) return "晚上好";
    return "夜深了";
  }

  function ItemRow(props) {
    const item = props.item;
    const cat = U.CATEGORY[item.category] || U.CATEGORY.task;
    const sub = item.category === "task" ? U.TASK_SUBTYPE[item.subtype || "other"] : null;
    const level = item.category === "task" ? U.TASK_LEVEL[item.task_level || "class"] : "";
    const cd = U.countdown(item);
    const done = item.my_completion === "done";
    const total = item.completion && item.completion.total;
    const finished = item.completion && item.completion.done;
    const showProgress = total > 0 && (item.category === "task" || item.category === "exam");

    return html`<div class="item" data-tone=${item.category === "task" && sub ? sub.tone : cat.tone}
      data-done=${done ? "1" : "0"}
      role="button" tabindex="0"
      onClick=${props.onClick}
      onKeyDown=${(e) => { if (e.key === "Enter") props.onClick(); }}>
      <div class="item-main">
        <div class="item-title">
          <span>${item.title}</span>
          ${item.audience === "committee" ? html`<${Badge} tone="violet">班委</${Badge}>` : null}
          ${item.target_count ? html`<${Badge} tone="amber">指定 ${item.target_count} 人</${Badge}>` : null}
          ${item.status !== "published" ? html`<${Badge} tone=${item.status === "draft" ? "amber" : "green"}>${U.STATUS[item.status]}</${Badge}>` : null}
        </div>
        <div class="item-sub">
          <span class="badge ${sub ? sub.tone : cat.tone}" style="padding:1px 7px;font-size:11px">${sub ? sub.label : cat.label}</span>
          ${level ? html`<span class="dot"></span><span>${level}级</span>` : null}
          ${item.course ? html`<span class="dot"></span><span>${item.course}</span>` : null}
          ${item.location ? html`<span class="dot"></span><span>${item.location}</span>` : null}
          ${showProgress ? html`<span class="dot"></span><span class="mono">${finished}/${total} 已完成</span>` : null}
        </div>
      </div>
      <div class="item-side">
        <div class=${"due-main " + (item.is_overdue ? "late" : cd.tone === "soon" ? "soon" : "")}>
          ${U.dueShort(item)}
        </div>
        <div class="due-sub" style=${cd.tone === "late" ? "color:var(--danger)" : ""}>${cd.text}</div>
      </div>
      ${done ? html`<span class="check-mark">${icon("check")}</span>` : null}
    </div>`;
  }

  function DraftBanner(props) {
    const n = props.count;
    if (!n) return null;
    return html`<div class="card card-pad" style="margin-top:14px;cursor:pointer;border-color:#ddd9ff"
      onClick=${() => window.API.go("drafts")}>
      <div class="spread">
        <div class="row-flex">
          <span class="badge violet">${icon("sparkles")}</span>
          <div>
            <div style="font-weight:650">有 ${n} 条 AI 抽取的草稿待审核</div>
            <div class="small muted">来自 QQ 群消息，确认后才对全班可见</div>
          </div>
        </div>
        ${icon("chevron", "muted")}
      </div>
    </div>`;
  }

  const WEEK_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

  function calendarDays(offset) {
    const t = U.bjParts();
    const monday = Date.UTC(t.y, t.m - 1, t.d)
      - ((t.w + 6) % 7) * 86400000
      + offset * 7 * 86400000;
    return [0, 1, 2, 3, 4, 5, 6].map((i) => {
      const d = new Date(monday + i * 86400000);
      return {
        date: `${d.getUTCFullYear()}-${U.pad(d.getUTCMonth() + 1)}-${U.pad(d.getUTCDate())}`,
        m: d.getUTCMonth() + 1,
        d: d.getUTCDate(),
        label: WEEK_LABELS[i],
      };
    });
  }

  function itemTone(item) {
    if (item.category === "task" && item.subtype && U.TASK_SUBTYPE[item.subtype]) {
      return U.TASK_SUBTYPE[item.subtype].tone;
    }
    return (U.CATEGORY[item.category] || U.CATEGORY.task).tone;
  }

  function shortDue(date) {
    if (!date) return "";
    const p = date.split("-");
    return p.length === 3 ? `${+p[1]}.${+p[2]} 截止` : "";
  }

  function WeekCalendar(props) {
    const items = props.items || [];
    const days = useMemo(() => calendarDays(props.offset), [props.offset]);
    const today = U.todayStr();
    const weekStart = days[0].date;
    const weekEnd = days[6].date;
    const byDay = {};
    items.forEach((it) => {
      if (!it.due_date) return;
      if (!byDay[it.due_date]) byDay[it.due_date] = [];
      byDay[it.due_date].push(it);
    });

    // One lane per in-progress or due-this-week task. Each lane runs from
    // Monday to its deadline (Sunday for cross-week work), so the week reads
    // as a staircase of commitments rather than seven disconnected boxes.
    const lanes = items
      .filter((it) => it.due_date)
      .map((it) => {
        const due = it.due_date;
        const dueInWeek = due >= weekStart && due <= weekEnd;
        const inProgress = due > weekEnd;
        if (!dueInWeek && !inProgress) return null;
        const endIdx = Math.max(0, Math.min(6, U.dayDiff(weekStart, due)));
        return { it, startIdx: 0, endIdx, dueInWeek, dueLabel: shortDue(due) };
      })
      .filter(Boolean)
      .sort((a, b) => (a.it.due_date < b.it.due_date ? -1 : a.it.due_date > b.it.due_date ? 1 : 0));
    const shown = lanes.slice(0, 8);
    const weekCount = lanes.filter((l) => l.dueInWeek).length;
    const acrossCount = lanes.length - weekCount;
    const total = days.reduce((n, d) => n + (byDay[d.date] || []).length, 0);
    const range = `${days[0].m}月${days[0].d}日 – ${days[6].m}月${days[6].d}日`;
    const summary = `本周 ${weekCount} 项${acrossCount ? ` · 跨周 ${acrossCount} 项` : ""}${props.overdue ? ` · 逾期 ${props.overdue} 项` : ""}`;

    return html`<section class="week-calendar card" aria-labelledby="week-cal-title">
      <header class="wcal-head">
        <div>
          <div class="section-title" id="week-cal-title">任务周历</div>
          <div class="small muted">${range} · ${summary}</div>
        </div>
        <div class="wcal-nav">
          <button type="button" class="wcal-nav-btn" aria-label="上一周" onClick=${() => props.onOffset(props.offset - 1)}>‹</button>
          <button type="button" class="wcal-nav-btn wcal-today" onClick=${() => props.onOffset(0)}>本周</button>
          <button type="button" class="wcal-nav-btn" aria-label="下一周" onClick=${() => props.onOffset(props.offset + 1)}>›</button>
        </div>
      </header>

      <div class="wcal-scroll">
        <div class="wcal-board">
          <div class="wcal-days">
            ${days.map((day) => {
              const selected = props.selected === day.date;
              const count = (byDay[day.date] || []).length;
              return html`<button type="button"
                class=${"wcal-day" + (day.date === today ? " is-today" : "") + (selected ? " is-selected" : "")}
                aria-pressed=${selected ? "true" : "false"}
                aria-label=${`${day.m}月${day.d}日，${count} 项任务`}
                onClick=${() => props.onSelect(selected ? "" : day.date)}>
                <span class="wcal-dow">周${day.label}${day.date === today ? " · 今" : ""}</span>
                <span class="wcal-date">${day.d}</span>
                <span class="wcal-count">${count ? `${count} 项` : "—"}</span>
              </button>`;
            })}
          </div>

          <div class="wcal-body">
            <div class="wcal-columns" aria-hidden="true">
              ${days.map((day) => html`<span class=${"wcal-col" + (day.date === today ? " is-today" : "") + (props.selected === day.date ? " is-selected" : "")}></span>`)}
            </div>
            <div class="wcal-rows">
              ${shown.length ? shown.map((lane) => {
                const selected = props.selected === lane.it.due_date;
                return html`<div class="wcal-row">
                  <button type="button"
                    class=${"wcal-bar" + (selected ? " is-selected" : "")}
                    data-tone=${itemTone(lane.it)}
                    style=${`grid-column:${lane.startIdx + 1} / ${lane.endIdx + 2}`}
                    aria-pressed=${selected ? "true" : "false"}
                    aria-label=${`${lane.it.title}，${lane.dueLabel}`}
                    title=${`${lane.it.title} · ${lane.dueLabel}`}
                    onClick=${() => props.onSelect(selected ? "" : lane.it.due_date)}>
                    <span class="wcal-bar-title">${lane.it.title}</span>
                    <span class="wcal-bar-due">${lane.dueLabel}</span>
                  </button>
                </div>`;
              }) : html`<div class="wcal-empty">本周还没有任务，先把要做的事记下来。</div>`}
            </div>
          </div>
        </div>
      </div>
      <p class="wcal-hint">点日期或任务条，只看相关任务；再点一次取消。<span class="wcal-scroll-hint">小屏可左右滑动查看整周。</span></p>
    </section>`;
  }

  function ListView() {
    const S = window.API.useStore();
    const [cat, setCat] = useState("all");
    const [sub, setSub] = useState("");
    const [level, setLevel] = useState("");
    const [q, setQ] = useState("");
    const [sort, setSort] = useState("due");
    const [tick, setTick] = useState(0);
    const [weekOffset, setWeekOffset] = useState(0);
    const [selectedDay, setSelectedDay] = useState("");
    const personalRef = useRef(null);

    const { data, loading, error, reload } = useApi(
      `/api/deadlines?status=published&sort=${sort}&limit=200`, [S.rev]);

    useEffect(() => {
      const t = setInterval(() => setTick((n) => n + 1), 60000);
      return () => clearInterval(t);
    }, []);

    const [personalVisible, setPersonalVisible] = useState(false);
    useEffect(() => {
      const el = document.getElementById("my-personal");
      if (!el || !window.IntersectionObserver) return;
      const io = new IntersectionObserver((es) => {
        setPersonalVisible(!!(es[0] && es[0].isIntersecting));
      }, { rootMargin: "0px 0px -30px 0px", threshold: 0.25 });
      io.observe(el);
      return () => io.disconnect();
    }, []);

    const items = (data && data.items) || [];
    const counts = (data && data.counts) || { today: 0, week: 0, overdue: 0, drafts: 0 };
    const me = S.me;
    const user = me && me.user;
    const cls = me && me.class;
    const isCommittee = !!(me && me.permissions && me.permissions.committee);

    const filtered = useMemo(() => {
      let list = items;
      if (selectedDay) list = list.filter((it) => it.due_date === selectedDay);
      if (cat !== "all") list = list.filter((it) => it.category === cat);
      if (cat === "task") {
        if (sub) list = list.filter((it) => (it.subtype || "other") === sub);
        if (level) list = list.filter((it) => (it.task_level || "class") === level);
      }
      const kw = q.trim().toLowerCase();
      if (kw) {
        list = list.filter((it) =>
          (it.title || "").toLowerCase().includes(kw) ||
          (it.course || "").toLowerCase().includes(kw) ||
          (it.summary || "").toLowerCase().includes(kw));
      }
      return list;
    }, [items, cat, sub, level, q, tick, selectedDay]);

    const byCat = {};
    items.forEach((it) => { byCat[it.category] = (byCat[it.category] || 0) + 1; });

    const groups = [];
    const map = {};
    filtered.forEach((it) => {
      const key = U.groupOf(it);
      if (!map[key]) { map[key] = []; groups.push(key); }
      map[key].push(it);
    });
    const orderedKeys = U.GROUPS.map((g) => g.key).filter((k) => map[k]);

    const today = new Date();
    const nowTxt = `${today.getMonth() + 1}月${today.getDate()}日 ${U.WEEK[U.bjParts().w]}`;

    function focusPersonal() {
      if (personalRef.current) personalRef.current();
      const el = document.getElementById("my-personal");
      if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    return html`<div class="shell"><div class="page">
      <div class="hero-card card" style="margin-top:6px">
        <div class="spread">
          <div>
            <div class="small muted">${nowTxt} · ${cls ? cls.name : ""}</div>
            <div class="hero-title">${greeting()}，${user ? user.name : ""}</div>
          </div>
        </div>
        <div class="stats">
          <div class="stat violet"><div class="num">${counts.today}</div><div class="lbl">今天截止</div></div>
          <div class="stat warn"><div class="num">${counts.week}</div><div class="lbl">本周待交</div></div>
          <div class="stat ${counts.overdue ? "danger" : ""}"><div class="num">${counts.overdue}</div><div class="lbl">已逾期</div></div>
        </div>
      </div>

      ${isCommittee ? html`<${DraftBanner} count=${me.pending_drafts} />` : null}

      <${WeekCalendar} items=${items} offset=${weekOffset} overdue=${counts.overdue}
        selected=${selectedDay}
        onOffset=${(n) => { setWeekOffset(n); setSelectedDay(""); }}
        onSelect=${(d) => setSelectedDay(d)} />

      ${selectedDay ? html`<div class="wcal-filter">
        <span>只看 ${selectedDay.slice(5, 7).replace(/^0/, "")} 月 ${selectedDay.slice(8, 10).replace(/^0/, "")} 日的任务</span>
        <button type="button" onClick=${() => setSelectedDay("")}>显示全部</button>
      </div>` : null}

      <div style="margin-top:18px">
        <div class="row-flex wrap" style="margin-bottom:10px">
          <div class="search-box">
            ${icon("search")}
            <input class="input" placeholder="搜索标题、课程…" value=${q}
              onInput=${(e) => setQ(e.target.value)} />
          </div>
          <${Seg} items=${[{ key: "due", label: "按截止" }, { key: "created", label: "最新" }]}
            value=${sort} onChange=${setSort} />
        </div>
        <div class="chips chips-main">
          <${Chip} on=${cat === "all"} onClick=${() => { setCat("all"); setSub(""); setLevel(""); }} count=${items.length}>全部</${Chip}>
          ${CAT_ORDER.map((k) => html`<${Chip} on=${cat === k} count=${byCat[k] || 0}
            onClick=${() => { setCat(k); setSub(""); setLevel(""); }}>${U.CATEGORY[k].label}</${Chip}>`)}
        </div>
        ${cat === "task" ? html`<div class="chips" style="margin-top:8px">
          <${Chip} on=${sub === ""} onClick=${() => setSub("")}>全部类型</${Chip}>
          ${SUB_ORDER.map((k) => html`<${Chip} on=${sub === k} onClick=${() => setSub(k)}>${U.TASK_SUBTYPE[k].label}</${Chip}>`)}
          <span style="width:10px"></span>
          <${Chip} on=${level === ""} onClick=${() => setLevel("")}>全部层级</${Chip}>
          ${LEVEL_ORDER.map((k) => html`<${Chip} on=${level === k} onClick=${() => setLevel(k)}>${U.TASK_LEVEL[k]}</${Chip}>`)}
        </div>` : null}
      </div>

      <div style="margin-top:14px">
        ${loading && !data ? html`<${LoadingList} rows=${5} />`
        : error ? html`<${ErrorView} err=${error} retry=${reload} />`
        : filtered.length === 0 ? html`<${Empty} icon="check" title=${items.length ? "没有匹配的条目" : "暂时没有要交的东西"}
            hint=${items.length ? "换个筛选条件试试" : "班委发布后会出现在这里"} />`
        : orderedKeys.map((key) => {
          const g = U.GROUPS.find((x) => x.key === key);
          return html`<div class="day-group">
            <div class="day-head">
              <span class=${"day-title " + (key === "overdue" ? "overdue" : "")}>${g.label}</span>
              <span class="day-count">${map[key].length} 项</span>
            </div>
            <div class="item-list">
              ${map[key].map((it) => html`<${ItemRow} item=${it}
                onClick=${() => window.API.go("detail/" + it.id)} />`)}
            </div>
          </div>`;
        })}
      </div>

      <div id="my-personal" class="section" style="margin-top:30px">
        <div class="section-head">
          <div class="section-title">我的个人待办</div>
          <div class="small muted">仅自己可见</div>
        </div>
        <${window.CDH.PersonalPanel} embedded=${true}
          onReady=${(fn) => { personalRef.current = fn; }} />
      </div>
      <div style="height:56px"></div>

      <button type="button" class=${"fab" + (personalVisible ? " fab-away" : "")}
        title=${isCommittee ? "添加事项" : "添加个人待办"}
        aria-label=${isCommittee ? "添加事项" : "添加个人待办"}
        onClick=${() => { if (isCommittee) window.API.go("new"); else focusPersonal(); }}>
        ${icon("plus")}<span>${isCommittee ? "添加事项" : "添加待办"}</span>
      </button>
    </div></div>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.List = ListView;
  window.CDH.ItemRow = ItemRow;
})();
