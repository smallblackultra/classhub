/* 草稿审核（班委） */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState } = window.preactHooks;
  const { Button, Page, PageHead, Badge, Empty, Note, LoadingList, ErrorView, useApi,
          confirmDialog, CopyBtn } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  const ACTION = { ok: "已抽取", failed: "抽取失败", pending: "处理中", skipped: "已跳过", duplicate: "重复" };

  function DraftCard(props) {
    const d = props.draft;
    const cat = U.CATEGORY[d.category] || U.CATEGORY.task;
    const [busy, setBusy] = useState("");
    async function run(kind, fn, msg) {
      if (busy) return;
      setBusy(kind);
      try {
        await fn();
        API.toast(msg, "ok");
        API.bump();
        props.reload();
      } catch (err) {
        API.fail(err);
      } finally {
        setBusy("");
      }
    }
    const conf = d.confidence != null ? Math.round(d.confidence * 100) : null;

    return html`<div class="card card-pad ai-card" style="margin-bottom:12px">
      <div class="spread" style="align-items:flex-start">
        <div class="grow">
          <div class="row-flex wrap" style="margin-bottom:6px">
            <span class="badge ${cat.tone}">${cat.label}</span>
            ${d.audience === "committee" ? html`<${Badge} tone="violet">仅班委</${Badge}>` : html`<${Badge} tone="green">全班</${Badge}>`}
            ${d.needs_review ? html`<${Badge} tone="red">需人工核对</${Badge}>` : null}
            ${conf != null ? html`<span class="badge violet">AI ${conf}%</span>` : null}
          </div>
          <div style="font-size:16px;font-weight:700;line-height:1.35">${d.title || "（未识别出标题）"}</div>
          <div class="small muted" style="margin-top:4px">
            ${d.course ? d.course + " · " : ""}${d.due_local ? "截止 " + U.fmtDateTime(d.due_local) : "截止时间未识别"}
          </div>
          ${d.summary ? html`<div class="small" style="margin-top:6px;color:var(--text-2)">${d.summary}</div>` : null}
        </div>
      </div>

      ${d.raw ? html`<div class="quote" style="margin-top:12px">
        <div class="ai-row" style="margin-bottom:4px">
          <b>${d.raw.sender_name || "未知"}</b>
          <span>· ${d.raw.chat_name || "QQ 群"}</span>
          <span>· ${U.fmtDateTime(d.raw.occurred_at) || ""}</span>
        </div>
        <div style="white-space:pre-wrap;font-size:13px;color:var(--text-2)">${d.raw.content}</div>
      </div>` : html`<div class="small muted" style="margin-top:10px">手动创建的草稿，没有原始消息。</div>`}

      ${d.ai && d.ai.output ? html`<details style="margin-top:8px">
        <summary class="small muted" style="cursor:pointer">查看 AI 抽取结果</summary>
        <pre class="small" style="white-space:pre-wrap;word-break:break-all;background:var(--surface-3);padding:10px;border-radius:10px;margin-top:6px;overflow:auto">${d.ai.output}</pre>
      </details>` : null}

      <div class="row-flex wrap" style="margin-top:14px">
        <${Button} variant="primary" icon="check" loading=${busy === "publish"}
          onClick=${() => run("publish", () => API.api.post(`/api/drafts/${d.id}/publish`, {}), "已发布")}>
          确认发布</${Button}>
        <${Button} variant="ghost" icon="edit" onClick=${() => API.go("edit/" + d.id)}>编辑后再发</${Button}>
        <${Button} variant="ghost" loading=${busy === "reject"}
          onClick=${async () => {
            if (await confirmDialog({ title: "驳回这条草稿？", body: "驳回后不会出现在列表里。如果识别有误，可以先「编辑后再发」。", okText: "驳回", danger: true })) {
              run("reject", () => API.api.post(`/api/drafts/${d.id}/reject`, { reason: "班委驳回" }), "已驳回");
            }
          }}>驳回</${Button}>
      </div>
    </div>`;
  }

  function DraftsView() {
    const S = API.useStore();
    const { data, loading, error, reload } = useApi("/api/drafts", [S.rev]);
    const items = (data && data.items) || [];

    return html`<${Page}>
      <${PageHead} title="待审核草稿" sub="AI 从 QQ 群消息中抽取，确认后才会对全班可见"
        back=${() => API.go("list")}
        actions=${html`<${Button} size="sm" variant="soft" icon="sparkles"
          onClick=${() => API.go("ingest")}>粘贴消息</${Button}>`} />

      <${Note} tone="info" icon="shield">
        AI 只负责<b>整理</b>，不负责<b>拍板</b>。所有条目都先落在草稿箱，由班委确认截止时间与可见范围后发布。
      </${Note}>

      <div style="margin-top:16px">
        ${loading && !data ? html`<${LoadingList} rows=${3} />`
        : error ? html`<${ErrorView} err=${error} retry=${reload} />`
        : items.length === 0 ? html`<${Empty} icon="inbox" title="没有待审核草稿"
            hint="QQ 群收到 @机器人 的消息后，会自动出现在这里。">
            <${Button} variant="soft" icon="sparkles" onClick=${() => API.go("ingest")}>手动粘贴一条消息</${Button}>
          </${Empty}>`
        : items.map((d) => html`<${DraftCard} draft=${d} reload=${reload} />`)}
      </div>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Drafts = DraftsView;
})();
