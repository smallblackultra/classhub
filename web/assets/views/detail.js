/* 详情页 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState } = window.preactHooks;
  const { Button, Page, PageHead, Badge, Note, Empty, LoadingList, ErrorView, useApi,
          confirmDialog, CopyBtn, Progress, IconBtn } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  function Meta(props) {
    return html`<div>
      <div class="meta-label">${props.label}</div>
      <div class="meta-value" style=${props.plain ? "font-weight:400" : ""}>${props.children}</div>
    </div>`;
  }

  function Countdown(props) {
    const item = props.item;
    const cd = U.countdown(item);
    if (!item.due_at) {
      return html`<div class="countdown-box"><div class="countdown-txt">未设置截止时间</div></div>`;
    }
    return html`<div class=${"countdown-box " + (cd.tone === "late" ? "late" : cd.tone === "soon" ? "soon" : "")}>
      <div class="countdown-num">${U.dueShort(item)}</div>
      <div class="countdown-txt">${cd.text}${item.all_day ? " · 全天" : ""} · ${U.fmtDateTime(item.due_local)}（北京时间）</div>
    </div>`;
  }

  function CompletionsPanel(props) {
    const { data, loading, error, reload } = useApi(`/api/deadlines/${props.id}/completions`, [props.rev]);
    if (loading && !data) return html`<div class="small muted">正在加载完成情况…</div>`;
    if (error) return html`<${Note} tone="err">${error.message}</${Note}>`;
    if (!data) return null;
    const s = data.stats || { done: 0, skipped: 0, missing: 0, total: 0 };
    const p = U.pct(s.done, s.total);
    const missingText = (data.missing || []).map((u) => `${u.name}（${u.student_no}）`).join("\n");
    return html`<div>
      <div class="spread" style="margin-bottom:8px">
        <div class="small muted">已完成 <b style="color:var(--text)">${s.done}</b> / ${s.total}
          ${s.skipped ? " · 已标记不适用 " + s.skipped : ""}</div>
        <div class="row-flex">
          ${missingText ? html`<${CopyBtn} text=${missingText} label="复制未完成名单" />` : null}
          <${IconBtn} icon="refresh" label="刷新" onClick=${reload} />
        </div>
      </div>
      <${Progress} value=${p} />
      ${(data.missing || []).length
        ? html`<div style="margin-top:14px">
            <div class="meta-label" style="margin-bottom:8px">还没完成的同学（${data.missing.length}）</div>
            <div class="people-grid">
              ${data.missing.map((u) => html`<div class="person missing">
                <div class="name">${u.name}</div><div class="no">${u.student_no}</div>
              </div>`)}
            </div>
          </div>`
        : html`<div class="small muted" style="margin-top:10px">全员已完成 🎉</div>`}
      ${(data.skipped || []).length ? html`<div class="small muted" style="margin-top:10px">
        不适用：${data.skipped.map((u) => u.name).join("、")}</div>` : null}
    </div>`;
  }

  function HistoryPanel(props) {
    const { data, loading } = useApi(`/api/deadlines/${props.id}/history`, [props.rev]);
    if (loading && !data) return html`<div class="small muted">加载中…</div>`;
    const items = (data && data.items) || [];
    if (!items.length) return html`<div class="small muted">暂无变更记录</div>`;
    const ACTION = { create: "创建", update: "修改", publish: "发布", archive: "归档",
                     delete: "删除", complete: "完成打卡", reject: "驳回", restore: "恢复" };
    return html`<div class="stack">
      ${items.map((r) => html`<div class="row-flex" style="align-items:flex-start">
        <span class="badge violet" style="flex:none">${ACTION[r.action] || r.action}</span>
        <div class="grow small">
          <div>${r.actor_name || "系统"} ${r.after && r.after.title ? "· " + r.after.title : ""}</div>
          <div class="muted">${U.fmtDateTime(r.created_at)}</div>
        </div>
      </div>`)}
    </div>`;
  }

  function DetailView(props) {
    const S = API.useStore();
    const id = props.id;
    const [rev, setRev] = useState(0);
    const { data, loading, error, reload } = useApi(`/api/deadlines/${id}`, [S.rev, rev]);
    const item = data && data.item;
    const me = S.me;
    const committee = !!(me && me.permissions && me.permissions.committee);
    const [busy, setBusy] = useState("");

    async function act(kind, fn, okMsg) {
      if (busy) return;
      setBusy(kind);
      try {
        await fn();
        if (okMsg) API.toast(okMsg, "ok");
        setRev((n) => n + 1);
        API.bump();
      } catch (err) {
        API.fail(err);
      } finally {
        setBusy("");
      }
    }

    if (loading && !item) {
      return html`<${Page}><div style="padding:8px 0"><${LoadingList} rows=${4} /></div></${Page}>`;
    }
    if (error) {
      return html`<${Page}><${PageHead} title="条目不存在" back=${() => API.go("list")} />
        <${ErrorView} err=${error} retry=${reload} />
        <div style="margin-top:14px"><${Button} variant="soft" onClick=${() => API.go("list")}>回到列表</${Button}></div>
      </${Page}>`;
    }

    const cat = U.CATEGORY[item.category] || U.CATEGORY.task;
    const sub = item.category === "task" ? U.TASK_SUBTYPE[item.subtype || "other"] : null;
    const level = item.category === "task" ? U.TASK_LEVEL[item.task_level || "class"] : "";
    const done = item.my_completion === "done";
    const skipped = item.my_completion === "skip";

    return html`<${Page}>
      <${PageHead} title="条目详情" back=${() => API.go("list")}
        actions=${committee ? html`
          <${IconBtn} icon="edit" label="编辑" onClick=${() => API.go("edit/" + item.id)} />` : null} />

      <div class="card hero-card">
        <div class="row-flex wrap">
          <span class="badge ${sub ? sub.tone : cat.tone}">${sub ? cat.label + " · " + sub.label : cat.label}</span>
          ${level ? html`<${Badge} tone="amber">${level}级</${Badge}>` : null}
          ${item.audience === "committee" ? html`<${Badge} tone="violet">仅班委</${Badge}>` : html`<${Badge} tone="green">全班</${Badge}>`}
          ${item.target_count ? html`<${Badge} tone="amber">指定 ${item.target_count} 人</${Badge}>` : null}
          ${item.status !== "published" ? html`<${Badge} tone="amber">${item.status_label}</${Badge}>` : null}
          ${item.needs_review ? html`<${Badge} tone="red">待核对</${Badge}>` : null}
        </div>
        <h1 class="hero-title">${item.title}</h1>
        ${item.summary ? html`<div class="hero-summary">${item.summary}</div>` : null}

        <div style="margin-top:16px"><${Countdown} item=${item} /></div>

        <div class="meta-grid">
          <${Meta} label="课程">${item.course || "—"}</${Meta}>
          <${Meta} label="地点">${item.location || "—"}</${Meta}>
          <${Meta} label="发布人">${item.created_by_name || "—"}</${Meta}>
          <${Meta} label="来源">${U.SOURCE[item.source_type] || item.source_type}</${Meta}>
          ${item.confidence != null ? html`<${Meta} label="AI 置信度">${Math.round(item.confidence * 100)}%</${Meta}>` : null}
        </div>

        ${item.link ? html`<div style="margin-top:16px">
          <a class="btn soft" href=${item.link} target="_blank" rel="noopener noreferrer">${icon("link")} 打开链接</a>
        </div>` : null}

        ${(item.attachments || []).length ? html`<div style="margin-top:16px">
          <div class="meta-label" style="margin-bottom:6px">附件</div>
          <div class="stack">
            ${item.attachments.map((a) => html`<a class="row-flex small" href=${a.url} target="_blank" rel="noopener noreferrer">
              ${icon("link")}<span>${a.name || a.url}</span></a>`)}
          </div>
        </div>` : null}
      </div>

      ${item.status === "draft" ? html`<div style="margin-top:14px">
        <${Note} tone="info" icon="sparkles">
          这是<b>草稿</b>，只有班委能看到。确认内容无误后发布，全班的同学才会看到。
        </${Note}>
      </div>` : null}

      <div class="row-flex wrap" style="margin-top:16px">
        ${item.status === "published" ? html`<${Button} variant=${done ? "ok-soft" : "primary"}
            icon=${done ? "check" : "check"} loading=${busy === "complete"}
            onClick=${() => act("complete", () => API.api.post(`/api/deadlines/${item.id}/complete`,
              { state: done ? "pending" : "done" }), done ? "已取消完成标记" : "已完成，真棒！")}>
            ${done ? "已完成" : "标记完成"}</${Button}>` : null}
        ${item.status === "published" && !done ? html`<${Button} variant="ghost"
            loading=${busy === "skip"}
            onClick=${() => act("skip", () => API.api.post(`/api/deadlines/${item.id}/complete`,
              { state: skipped ? "pending" : "skip" }), skipped ? "已恢复" : "已标记不适用")}>
            ${skipped ? "取消不适用" : "不适用"}</${Button}>` : null}
        ${committee && item.status === "draft" ? html`<${Button} variant="primary" icon="send"
            loading=${busy === "publish"}
            onClick=${() => act("publish", () => API.api.post(`/api/deadlines/${item.id}/publish`, {}), "已发布，全班可见")}>
            发布给全班</${Button}>` : null}
        ${committee ? html`<${Button} variant="ghost" icon="archive" loading=${busy === "archive"}
            onClick=${async () => {
              if (await confirmDialog({ title: "归档这条？", body: "归档后不再出现在列表里，但数据仍保留，可以在历史中追溯。", okText: "归档" })) {
                act("archive", () => API.api.post(`/api/deadlines/${item.id}/archive`, {}), "已归档");
              }
            }}>归档</${Button}>` : null}
      </div>

      ${committee ? html`<div class="section">
        <div class="section-head"><div class="section-title">完成情况</div></div>
        <div class="card card-pad"><${CompletionsPanel} id=${item.id} rev=${rev + S.rev} /></div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">变更记录</div></div>
        <div class="card card-pad"><${HistoryPanel} id=${item.id} rev=${rev + S.rev} /></div>
      </div>` : null}

      <div style="height:40px"></div>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Detail = DetailView;
})();

