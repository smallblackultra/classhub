/* 全站管理员后台：跨班概览、账号与密码、登录记录（仅 role=admin） */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState } = window.preactHooks;
  const { Button, Badge, Seg, Empty, Note, LoadingList, ErrorView, useApi, Page, PageHead, CopyBtn } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  const ROLE = { admin: "管理员", monitor: "班长", secretary: "团支书", student: "同学" };
  const ROLE_TONE = { admin: "violet", monitor: "amber", secretary: "green", student: "" };

  function fmt(iso) {
    if (!iso) return "—";
    return U.fmtDateTime(iso);
  }

  function ClassTab() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/admin/global/classes", [S.rev]);
    const items = (data && data.items) || [];
    if (loading && !data) return html`<${LoadingList} rows=${4} />`;
    if (error) return html`<${ErrorView} err=${error} retry=${reload} />`;
    const totalUsers = items.reduce((n, c) => n + (c.total || 0), 0);
    const totalLogins = items.reduce((n, c) => n + (c.logins || 0), 0);
    return html`<div>
      <div class="stats" style="margin-top:14px">
        <div class="stat violet"><div class="num">${items.length}</div><div class="lbl">班级</div></div>
        <div class="stat"><div class="num">${totalUsers}</div><div class="lbl">账号</div></div>
        <div class="stat warn"><div class="num">${totalLogins}</div><div class="lbl">累计登录</div></div>
      </div>
      <div class="stack" style="margin-top:14px;gap:10px">
        ${items.map((c) => html`<div class="card card-pad">
          <div class="spread">
            <div>
              <div style="font-weight:700;font-size:15px">${c.name}</div>
              <div class="small muted" style="margin-top:2px">
                ${c.total} 人 · 已激活 ${c.activated} · 待审批 ${c.pending} · 已发布 ${c.deadlines} 条
              </div>
            </div>
            <${Badge} tone=${c.pending ? "amber" : "green"}>${c.logins} 次登录</${Badge}>
          </div>
          <div class="kv" style="margin-top:10px;gap:14px">
            <div><span class="k">邀请码</span><span class="mono">${c.invite_code}</span></div>
            <div><span class="k">最近登录</span>${fmt(c.last_login_at)}</div>
          </div>
        </div>`)}
      </div>
    </div>`;
  }

  function AccountRow(props) {
    const row = props.row;
    const [show, setShow] = useState(false);
    const [busy, setBusy] = useState(false);
    const password = row.password || "";
    function reset() {
      if (!window.confirm(`把 ${row.name}（${row.student_no}）的密码重置为初始密码？\n该账号下次登录会被要求立即修改密码。`)) return;
      setBusy(true);
      API.api.post("/api/admin/global/reset-password", { slug: row.slug, student_no: row.student_no })
        .then((res) => {
          API.toast(`已重置为 ${res.password}`, "ok");
          props.reload();
        })
        .catch((e) => API.toast(e.message || "重置失败", "err"))
        .then(() => setBusy(false));
    }
    return html`<div class="item" data-tone=${row.login_count ? "green" : "violet"}>
      <div class="item-main">
        <div class="item-title">
          <span>${row.name}</span>
          <${Badge} tone=${ROLE_TONE[row.role]}>${ROLE[row.role] || row.role}</${Badge}>
          ${row.status === "pending" ? html`<${Badge} tone="amber">待审批</${Badge}>` : null}
          ${row.must_change_password ? html`<${Badge} tone="">未改密</${Badge}>` : null}
        </div>
        <div class="item-sub">
          <span class="mono">${row.student_no}</span>
          <span class="dot"></span><span>${row.class_name}</span>
          <span class="dot"></span><span>登录 ${row.login_count} 次</span>
          ${row.last_login_at ? html`<span class="dot"></span><span>${fmt(row.last_login_at)}</span>` : null}
          ${row.last_ip ? html`<span class="dot"></span><span class="mono small">${row.last_ip}</span>` : null}
        </div>
        <div class="item-sub" style="margin-top:4px">
          <span class="muted">密码：</span>
          <span class="mono">${password ? (show ? password : "••••••••") : "（用户已自行修改，无法查看）"}</span>
          ${password ? html`<button type="button" class="link-btn" onClick=${() => setShow(!show)}>${show ? "隐藏" : "显示"}</button>` : null}
        </div>
      </div>
      <div class="item-side">
        <${Button} variant="soft" size="sm" disabled=${busy} onClick=${reset}>重置</${Button}>
      </div>
    </div>`;
  }

  function UsersTab() {
    const S = API.useStore();
    const [q, setQ] = useState("");
    const [appliedQ, setAppliedQ] = useState("");
    const [slug, setSlug] = useState("");
    const [filter, setFilter] = useState("all");
    const query = `q=${encodeURIComponent(appliedQ)}&slug=${encodeURIComponent(slug)}&filter=${encodeURIComponent(filter)}`;
    const { data, loading, error, reload } = useApi(`/api/admin/global/users?${query}`, [S.rev]);
    const items = (data && data.items) || [];
    return html`<div>
      <div class="card card-pad" style="margin-top:14px">
        <div class="row-flex" style="gap:8px;flex-wrap:wrap">
          <input class="input grow" style="min-width:160px" placeholder="搜索姓名或学号"
            value=${q} onInput=${(e) => setQ(e.target.value)}
            onKeyDown=${(e) => { if (e.key === "Enter") setAppliedQ(q.trim()); }} />
          <${Button} variant="soft" onClick=${() => setAppliedQ(q.trim())}>搜索</${Button}>
        </div>
        <div class="chips" style="margin-top:10px">
          ${[["all", "全部"], ["never", "从未登录"], ["pending", "待审批"], ["changed", "已改密"]].map(([k, label]) =>
            html`<${window.CDH.ui.Chip} on=${filter === k} onClick=${() => setFilter(k)}>${label}</${window.CDH.ui.Chip}>`)}
        </div>
        <div class="small muted" style="margin-top:8px">共 ${items.length} 个账号 · 密码列只对“尚未自行改密”的账号显示</div>
      </div>
      <div style="margin-top:12px">
        ${loading && !data ? html`<${LoadingList} rows=${6} />`
        : error ? html`<${ErrorView} err=${error} retry=${reload} />`
        : items.length === 0 ? html`<${Empty} icon="users" title="没有匹配的账号" />`
        : html`<div class="item-list">${items.map((row) => html`<${AccountRow} row=${row} reload=${reload} />`)}</div>`}
      </div>
    </div>`;
  }

  const ACTION = { "auth.login": "登录", "auth.register": "注册", "auth.change_password": "修改密码" };

  function LoginsTab() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/admin/global/logins?limit=100", [S.rev]);
    const items = (data && data.items) || [];
    if (loading && !data) return html`<${LoadingList} rows=${6} />`;
    if (error) return html`<${ErrorView} err=${error} retry=${reload} />`;
    return html`<div>
      <${Note} tone="info" icon="shield">
        最近 100 条登录/注册/改密记录，按时间倒序。IP 为服务器看到的来源地址。
      </${Note}>
      <div class="item-list" style="margin-top:12px">
        ${items.length === 0 ? html`<${Empty} icon="list" title="还没有记录" />` : null}
        ${items.map((r) => html`<div class="item" data-tone="violet">
          <div class="item-main">
            <div class="item-title"><span>${r.name}</span>
              <${Badge} tone="">${ACTION[r.action] || r.action}</${Badge}></div>
            <div class="item-sub">
              <span class="mono">${r.student_no}</span>
              <span class="dot"></span><span>${r.class_name}</span>
              ${r.ip ? html`<span class="dot"></span><span class="mono small">${r.ip}</span>` : null}
            </div>
          </div>
          <div class="item-side"><div class="due-sub">${fmt(r.created_at)}</div></div>
        </div>`)}
      </div>
    </div>`;
  }

  function GlobalView() {
    const S = API.useStore();
    const [tab, setTab] = useState("classes");
    const me = S.me;
    if (!me || me.user.role !== "admin") {
      return html`<${Page}><${PageHead} title="管理后台" back=${() => API.go("list")} />
        <${Empty} icon="shield" title="仅全站管理员可用" hint="这个页面只对全站管理员的账号开放。" /></${Page}>`;
    }
    return html`<${Page}>
      <${PageHead} title="管理后台" back=${() => { window.location.assign("/personalcenter/"); }} />
      <div class="row-flex" style="justify-content:center">
        <${Seg} items=${[{ key: "classes", label: "班级" }, { key: "users", label: "账号密码" }, { key: "logins", label: "登录记录" }]}
          value=${tab} onChange=${setTab} />
      </div>
      ${tab === "classes" ? html`<${ClassTab} />` : null}
      ${tab === "users" ? html`<${UsersTab} />` : null}
      ${tab === "logins" ? html`<${LoginsTab} />` : null}
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Global = GlobalView;
})();
