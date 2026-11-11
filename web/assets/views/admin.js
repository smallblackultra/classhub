/* 班委后台：成员 / 邀请码 / 数据源 / 统计 / 审计 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState, useEffect } = window.preactHooks;
  const { Button, Page, PageHead, Field, Badge, Tabs, Empty, Note, LoadingList, ErrorView,
          useApi, confirmDialog, CopyBtn, Avatar, Modal, Spinner } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  const STATUS_TONE = { pending: "amber", active: "green", disabled: "red" };
  const STATUS_LABEL = { pending: "待审批", active: "正常", disabled: "已禁用" };
  const ROLE_LABEL = { student: "同学", monitor: "班长", secretary: "团支书", admin: "管理员" };

  function MembersTab() {
    const S = API.useStore();
    const [filter, setFilter] = useState("all");
    const { data, loading, error, reload } = useApi("/api/admin/users", [S.rev, filter]);
    const [busy, setBusy] = useState(0);

    async function patch(user, body, msg) {
      setBusy(user.id);
      try {
        await API.api.patch(`/api/admin/users/${user.id}`, body);
        API.toast(msg, "ok");
        API.bump();
        reload();
      } catch (err) {
        API.fail(err);
      } finally {
        setBusy(0);
      }
    }

    const counts = (data && data.counts) || {};
    let items = (data && data.items) || [];
    if (filter !== "all") items = items.filter((u) => u.status === filter);

    return html`<div>
      <div class="card card-pad" style="margin-bottom:14px">
        <div class="spread">
          <div>
            <div class="small muted">班级邀请码（注册时填这个）</div>
            <div style="font-size:22px;font-weight:750;letter-spacing:2px;margin-top:2px">
              ${(S.me && S.me.class && S.me.class.invite_code) || "—"}</div>
          </div>
          <div class="row-flex">
            <${CopyBtn} text=${(S.me && S.me.class && S.me.class.invite_code) || ""} label="复制" />
            <${Button} size="sm" variant="ghost" icon="refresh"
              onClick=${async () => {
                if (await confirmDialog({ title: "换一个邀请码？", body: "旧邀请码立即失效，已经注册的同学不受影响。", okText: "换一个" })) {
                  try {
                    const r = await API.api.post("/api/admin/invite/rotate", {});
                    API.toast("新邀请码：" + r.invite_code, "ok");
                    API.refreshMe();
                    API.bump();
                  } catch (err) { API.fail(err); }
                }
              }}>轮换</${Button}>
          </div>
        </div>
      </div>

      <div class="row-flex wrap" style="margin-bottom:12px">
        ${[["all", "全部"], ["pending", "待审批"], ["active", "正常"], ["disabled", "已禁用"]].map(([k, label]) =>
          html`<button type="button" class="chip" data-on=${filter === k ? "1" : "0"}
            onClick=${() => setFilter(k)}>${label}${counts[k] != null ? html`<span class="count">${counts[k]}</span>` : null}</button>`)}
      </div>

      ${loading && !data ? html`<${LoadingList} rows=${4} />`
      : error ? html`<${ErrorView} err=${error} retry=${reload} />`
      : items.length === 0 ? html`<${Empty} icon="users" title="没有成员" hint="把邀请码发给同学，注册后会出现在这里。" />`
      : html`<div class="card">
        ${items.map((u, i) => html`<div class="member" style=${i ? "border-top:1px solid var(--line)" : ""}>
          <${Avatar} name=${u.name} size="small" />
          <div class="grow">
            <div class="name">${u.name}
              ${u.role !== "student" ? html`<${Badge} tone="violet">${ROLE_LABEL[u.role] || u.role}</${Badge}>` : null}
            </div>
            <div class="sub">${u.student_no} · ${u.last_login_at ? "最近登录 " + U.fmtDateTime(u.last_login_at) : "从未登录"}</div>
          </div>
          <div class="row-flex" style="gap:6px">
            <${Badge} tone=${STATUS_TONE[u.status]}>${STATUS_LABEL[u.status]}</${Badge}>
            ${u.id === (S.me && S.me.user.id) ? html`<span class="small muted">我自己</span>` : html`
              ${u.status === "pending" ? html`<${Button} size="sm" variant="primary" loading=${busy === u.id}
                onClick=${() => patch(u, { status: "active" }, "已通过 " + u.name)}>通过</${Button}>` : null}
              ${u.status === "active" ? html`<${Button} size="sm" variant="ghost" loading=${busy === u.id}
                onClick=${() => patch(u, { status: "disabled" }, "已禁用 " + u.name)}>禁用</${Button}>` : null}
              ${u.status === "disabled" ? html`<${Button} size="sm" variant="soft" loading=${busy === u.id}
                onClick=${() => patch(u, { status: "active" }, "已恢复 " + u.name)}>恢复</${Button}>` : null}
              <select class="select" style="width:auto;min-height:31px;height:31px;font-size:12.5px;padding:0 28px 0 10px"
                value=${u.role} onChange=${(e) => patch(u, { role: e.target.value }, u.name + " 已是" + ROLE_LABEL[e.target.value])}>
                ${["student", "monitor", "secretary", "admin"].map((r) =>
                  html`<option value=${r} selected=${u.role === r}>${ROLE_LABEL[r]}</option>`)}
              </select>`}
          </div>
        </div>`)}
      </div>`}
    </div>`;
  }

  function SourcesTab() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/admin/sources", [S.rev]);
    const [form, setForm] = useState({ type: "qq_onebot", name: "" });
    const [created, setCreated] = useState(null);
    const [busy, setBusy] = useState(false);

    async function create() {
      if (busy) return;
      setBusy(true);
      try {
        const r = await API.api.post("/api/admin/sources", { type: form.type, name: form.name });
        setCreated(r);
        setForm({ ...form, name: "" });
        reload();
      } catch (err) {
        API.fail(err);
      } finally {
        setBusy(false);
      }
    }

    const items = (data && data.items) || [];
    const base = location.origin;

    return html`<div>
      <${Note} tone="info" icon="shield">
        机器人 / 书签走<b>独立令牌</b>，不暴露登录态。令牌只在创建时显示一次，请立刻保存。
      </${Note}>

      <div class="card card-pad" style="margin-top:14px">
        <div class="section-title" style="margin-bottom:10px">接入一个数据源</div>
        <div class="form-2">
          <${Field} label="类型">
            <select class="select" value=${form.type}
              onChange=${(e) => setForm({ ...form, type: e.target.value })}>
              <option value="qq_onebot">QQ 群机器人（OneBot v11）</option>
              <option value="bookmarklet">浏览器书签抓取</option>
              <option value="paste">粘贴导入</option>
              <option value="chaoxing">学习通 / 雨课堂</option>
            </select>
          </${Field}>
          <${Field} label="备注名">
            <input class="input" value=${form.name} onInput=${(e) => setForm({ ...form, name: e.target.value })}
              placeholder="例如：计科 2301 班群" />
          </${Field}>
        </div>
        <div style="margin-top:12px">
          <${Button} variant="primary" icon="plus" loading=${busy} onClick=${create}>生成接入令牌</${Button}>
        </div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">已接入</div></div>
        ${loading && !data ? html`<${LoadingList} rows=${2} />`
        : error ? html`<${ErrorView} err=${error} retry=${reload} />`
        : items.length === 0 ? html`<${Empty} icon="link" title="还没有数据源"
            hint="QQ 群机器人需要先在服务器上运行 OneBot 桥接程序。" />`
        : html`<div class="card">
          ${items.map((s) => html`<div class="member" style="border-top:0">
            <span class="badge violet">${U.SOURCE[s.type] || s.type}</span>
            <div class="grow"><div class="name">${s.name}</div>
              <div class="sub">${s.has_token ? "已配置令牌" : "未配置令牌"}
                ${s.last_ok_at ? " · 最近成功 " + U.fmtDateTime(s.last_ok_at) : ""}
                ${s.last_error ? " · " + s.last_error : ""}</div>
            </div>
            <span class="small ${s.enabled ? "muted" : "warn-text"}">${s.enabled ? "启用中" : "已停用"}</span>
          </div>`)}
        </div>`}
      </div>

      <${Modal} open=${!!created} title="令牌只显示这一次" onClose=${() => setCreated(null)}
        footer=${html`<${Button} variant="primary" onClick=${() => setCreated(null)}>我已保存</${Button}>`}>
        ${created ? html`<div class="stack">
          <div class="small muted">数据源：${created.source.name}（${created.source.type}）</div>
          <div class="code-box"><code>${created.token}</code></div>
          <${CopyBtn} text=${created.token} label="复制令牌" />
          ${created.source.type === "qq_onebot" ? html`<div class="small muted">
            OneBot 桥接配置：<code>CDH_INGEST_URL=${base}/api/ingest/qq</code><br />
            每个群消息以 <code>POST ${base}/api/ingest/qq</code>（Header <code>X-Classhub-Token</code>）上报。
          </div>` : null}
          ${created.source.type === "bookmarklet" ? html`<div class="small muted">
            书签地址：<code>${base}/api/ingest/bookmarklet</code>（同样使用该令牌）
          </div>` : null}
        </div>` : null}
      </${Modal}>
    </div>`;
  }

  function StatsTab() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/admin/stats", [S.rev]);
    if (loading && !data) return html`<${LoadingList} rows=${3} />`;
    if (error) return html`<${ErrorView} err=${error} retry=${reload} />`;
    const users = data.users || {};
    const dl = data.deadlines || {};
    const ex = data.extraction || {};
    const cat = data.by_category || {};
    return html`<div>
      <div class="stats" style="margin-top:0">
        <div class="stat"><div class="num">${users.active || 0}</div><div class="lbl">正常成员</div></div>
        <div class="stat warn"><div class="num">${users.pending || 0}</div><div class="lbl">待审批</div></div>
        <div class="stat violet"><div class="num">${dl.published || 0}</div><div class="lbl">已发布条目</div></div>
      </div>
      <div class="stats">
        <div class="stat"><div class="num">${dl.draft || 0}</div><div class="lbl">草稿</div></div>
        <div class="stat"><div class="num">${dl.archived || 0}</div><div class="lbl">已归档</div></div>
        <div class="stat"><div class="num">${users.disabled || 0}</div><div class="lbl">已禁用</div></div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">分类分布（已发布）</div></div>
        <div class="card card-pad">
          ${Object.keys(U.CATEGORY).map((k) => html`<div class="spread" style="margin:6px 0">
            <span class="small">${U.CATEGORY[k].label}</span>
            <span class="mono small">${cat[k] || 0}</span>
          </div>`)}
        </div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">消息抽取</div></div>
        <div class="card card-pad">
          <div class="spread"><span class="small">累计处理消息</span><span class="mono">${ex.messages || 0}</span></div>
          <div class="spread" style="margin-top:6px"><span class="small">成功抽取</span><span class="mono">${ex.extracted || 0}</span></div>
          <div class="spread" style="margin-top:6px"><span class="small">失败</span><span class="mono">${ex.failed || 0}</span></div>
          <div class="spread" style="margin-top:6px"><span class="small">成功率</span>
            <span class="mono">${ex.success_rate == null ? "—" : Math.round(ex.success_rate * 100) + "%"}</span></div>
          <div class="spread" style="margin-top:6px"><span class="small">最近消息</span>
            <span class="small muted">${ex.last_message_at ? U.fmtDateTime(ex.last_message_at) : "—"}</span></div>
        </div>
      </div>
    </div>`;
  }

  function AuditTab() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/admin/audit?limit=100", [S.rev]);
    if (loading && !data) return html`<${LoadingList} rows=${4} />`;
    if (error) return html`<${ErrorView} err=${error} retry=${reload} />`;
    const items = (data && data.items) || [];
    const ACTION_LABEL = {
      "auth.login": "登录", "auth.register": "注册", "auth.logout": "退出",
      "deadline.create": "创建条目", "deadline.update": "修改条目", "deadline.publish": "发布",
      "deadline.archive": "归档", "deadline.delete": "删除", "deadline.complete": "打卡",
      "draft.publish": "发布草稿", "draft.reject": "驳回草稿",
      "admin.user_update": "修改成员", "admin.invite_rotate": "轮换邀请码", "admin.source_create": "创建数据源",
      "ingest.paste": "粘贴抽取", "ingest.qq": "QQ 消息抽取", "ingest.bookmarklet": "书签导入",
    };
    return html`<div class="card">
      ${items.length === 0 ? html`<${Empty} icon="list" title="暂无操作记录" />` : items.map((r, i) => html`
        <div class="member" style=${i ? "border-top:1px solid var(--line);border-top-left-radius:0;border-top-right-radius:0" : ""}>
          <span class="badge violet" style="flex:none">${ACTION_LABEL[r.action] || r.action}</span>
          <div class="grow">
            <div class="small">${r.actor_name || "系统"} <span class="muted">${r.target || ""}</span></div>
            <div class="sub">${U.fmtDateTime(r.created_at)}${r.ip ? " · " + r.ip : ""}</div>
          </div>
        </div>`)}
    </div>`;
  }

  function AiTab() {
    const S = API.useStore();
    const isAdmin = !!(S.me && S.me.user && S.me.user.role === "admin");
    const { data, loading, error, reload } = useApi(isAdmin ? "/api/admin/ai" : null, []);
    const [draft, setDraft] = useState(null);
    const [busy, setBusy] = useState("");
    const [tested, setTested] = useState(null);

    useEffect(() => {
      if (data && !draft) {
        setDraft({ model: data.model || "", base_url: data.base_url || "", api_key: "" });
      }
    }, [data]);

    if (!isAdmin) {
      return html`<${Note}>只有管理员可以配置 AI 助手。<//>`;
    }
    if (loading && !draft) return html`<${LoadingList} rows=${2} />`;
    if (error) return html`<${ErrorView} error=${error} onRetry=${reload} />`;

    const cur = draft || { model: "", base_url: "", api_key: "" };
    function set(key, value) {
      setDraft(Object.assign({}, cur, { [key]: value }));
    }

    async function save() {
      setBusy("save");
      try {
        await API.api.post("/api/admin/ai", cur);
        API.toast("已保存，AI 抽取已启用", "ok");
        setDraft(Object.assign({}, cur, { api_key: "" }));
        reload();
        API.bump();
      } catch (err) {
        API.fail(err);
      } finally {
        setBusy("");
      }
    }

    async function test() {
      setBusy("test");
      setTested(null);
      try {
        const r = await API.api.post("/api/admin/ai/test", {});
        setTested({ ok: true, text: "连接成功" + (r.model ? " · " + r.model : "") });
      } catch (err) {
        setTested({ ok: false, text: err.message || "连接失败" });
      } finally {
        setBusy("");
      }
    }

    return html`<div class="card">
      <div class="row" style="justify-content:space-between;gap:8px">
        <div class="grow">
          <div class="row" style="gap:6px;flex-wrap:wrap">
            <${Badge} tone=${data.enabled ? "green" : "amber"} dot>
              ${data.enabled ? "AI 抽取已启用" : "未配置 · 仅规则抽取"}
            <//>
            <${Badge} tone=${data.has_key ? "green" : "amber"}>${data.has_key ? "Key 已保存" : "无 Key"}<//>
          </div>
          <div class="sub" style="margin-top:6px">填入 DeepSeek 的 API Key 后，群消息与粘贴内容会先交给模型抽取，失败时自动退回规则解析。</div>
        </div>
      </div>

      <div class="divider"></div>

      <${Field} label="API Key" hint="只存在本班数据库的 settings 表里，不会出现在前端；留空表示不修改。">
        <input class="input" type="password" autocomplete="off" placeholder=${data.has_key ? "已保存（留空不改）" : "sk-..."} value=${cur.api_key} onInput=${(e) => set("api_key", e.target.value)} />
      <//>
      <${Field} label="模型" hint="默认 deepseek-chat；也可换 deepseek-reasoner。">
        <input class="input" value=${cur.model} placeholder=${data.default_model} onInput=${(e) => set("model", e.target.value)} />
      <//>
      <${Field} label="接口地址" hint="默认官方地址；用中转或校内模型时替换。">
        <input class="input" value=${cur.base_url} placeholder=${data.default_base_url} onInput=${(e) => set("base_url", e.target.value)} />
      <//>

      ${tested ? html`<${Note} tone=${tested.ok ? "" : "err"}>${tested.text}<//>` : null}

      <div class="row" style="gap:8px;margin-top:12px">
        <${Button} onClick=${save} disabled=${busy !== ""}>${busy === "save" ? "保存中…" : "保存"}</${Button}>
        <${Button} variant="soft" onClick=${test} disabled=${busy !== "" || !data.has_key}>${busy === "test" ? "测试中…" : "测试连接"}</${Button}>
      </div>
    </div>`;
  }

  function AdminView() {
    const S = API.useStore();
    const isAdmin = !!(S.me && S.me.user && S.me.user.role === "admin");
    const [tab, setTab] = useState("members");
    const tabs = [
      { key: "members", label: "成员" },
      { key: "sources", label: "数据源" },
      { key: "stats", label: "统计" },
      { key: "audit", label: "审计" },
    ];
    if (isAdmin) tabs.push({ key: "ai", label: "AI 助手" });
    return html`<${Page}>
      <${PageHead} title="班委后台" sub="成员审批 · 数据源 · 统计"
        back=${() => API.go("list")} />
      <${Tabs} items=${tabs} value=${tab} onChange=${setTab} />
      ${tab === "members" ? html`<${MembersTab} />`
      : tab === "sources" ? html`<${SourcesTab} />`
      : tab === "stats" ? html`<${StatsTab} />`
      : tab === "ai" ? html`<${AiTab} />`
      : html`<${AuditTab} />`}
      <div style="height:40px"></div>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Admin = AdminView;
})();

