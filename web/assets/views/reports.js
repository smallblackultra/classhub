/* 完成报表：按类别/日期看完成率，导出 CSV 或单人名单 */
(function () {
  "use strict";
  const { html, icon } = window.U;
  const {
    Button, Page, PageHead, Badge, Empty, Note, LoadingList, ErrorView, useApi, Stat,
  } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  function pctTone(pct) { return pct >= 80 ? "green" : pct >= 40 ? "amber" : "red"; }

  function ReportRow(props) {
    const r = props.item;
    return html`<div class="report-row">
      <div class="report-main">
        <div class="report-title">
          <a href=${"#/detail/" + r.id} onClick=${(e) => { e.preventDefault(); API.go("detail/" + r.id); }}>
            ${r.title}
          </a>
          ${r.status === "archived" ? html`<span class="badge">已归档</span>` : null}
        </div>
        <div class="report-sub">
          <span class=${"badge " + U.CATEGORY[r.category].tone}>${r.category_label}</span>
          <span class="badge ${r.audience === "committee" ? "violet" : ""}">${r.audience_label}</span>
          <span>${r.due_local ? "截止 " + U.fmtDateTime(r.due_local) : "未设截止"}</span>
        </div>
      </div>
      <div class="report-progress">
        <div class="progress"><i style=${"width:" + r.pct + "%;background:" + (r.pct >= 80 ? "var(--ok)" : r.pct >= 40 ? "var(--warn)" : "var(--danger)")}></i></div>
        <div class="report-num"><b>${r.done}</b> / ${r.total} <span class="muted">(${r.pct}%)</span></div>
      </div>
      <div class="report-actions">
        <a class="btn sm soft" href=${window.API.url("/api/reports/completions.csv?deadline_id=" + r.id)}>名单 CSV</a>
      </div>
    </div>`;
  }

  function ReportsView() {
    const S = API.useStore();
    const [from, setFrom] = window.preactHooks.useState("");
    const [to, setTo] = window.preactHooks.useState("");
    const [applied, setApplied] = window.preactHooks.useState({ from: "", to: "" });
    const qs = (applied.from ? "&from=" + applied.from : "") + (applied.to ? "&to=" + applied.to : "");
    const api = useApi("/api/reports/overview?" + qs, [S.rev, applied.from, applied.to]);
    const data = api.data || {};
    const summary = data.summary || {};
    const items = data.items || [];

    function apply() { setApplied({ from: from.trim(), to: to.trim() }); }

    return html`<${Page}>
      <${PageHead} title="完成报表" sub="只有班委能看；数据实时统计"
        back=${() => API.go("list")} />

      ${api.error ? html`<${ErrorView} err=${api.error} retry=${api.reload} />` : null}

      <div class="stats four" style="margin-bottom:14px">
        <${Stat} num=${summary.avg_pct != null ? summary.avg_pct + "%" : "—"} label="平均完成率" tone="violet" />
        <${Stat} num=${summary.published != null ? summary.published : "—"} label="已发布" />
        <${Stat} num=${summary.overdue != null ? summary.overdue : "—"} label="已逾期" tone="danger" />
        <${Stat} num=${summary.everyone != null ? summary.everyone + " / " + summary.committee : "—"} label="全班 / 班委" />
      </div>

      <div class="card card-pad" style="margin-bottom:14px">
        <div class="field-row">
          <label class="field grow"><span>开始日期</span>
            <input class="input" type="date" value=${from}
              onInput=${(e) => setFrom(e.target.value)} /></label>
          <label class="field grow"><span>结束日期</span>
            <input class="input" type="date" value=${to}
              onInput=${(e) => setTo(e.target.value)} /></label>
          <div class="field" style="justify-content:flex-end">
            <span>&nbsp;</span>
            <${Button} variant="primary" onClick=${apply}>查询</${Button}>
          </div>
        </div>
        <div class="spread" style="margin-top:10px">
          <span class="small muted">导出全部条目（含完成数）：</span>
          <a class="btn sm soft" href=${window.API.url("/api/reports/deadlines.csv?" + qs)}>
            ${icon("clipboard")} deadlines.csv
          </a>
        </div>
      </div>

      ${api.loading && !api.data ? html`<${LoadingList} rows=${5} />`
        : items.length === 0 ? html`<${Empty} icon="clipboard" title="这个时间段还没有条目" hint="换个日期范围试试。" />`
        : html`<div class="stack">${items.map((r) => html`<${ReportRow} key=${r.id} item=${r} />`)}</div>`}

      <div style="height:14px"></div>
      <${Note} tone="info">
        “平均完成率”按条目平均，不是总人次；<b>班委条目</b>的分母是班委人数，<b>全班条目</b>的分母是全班人数。
        点名名单 CSV 含“已完成 / 不适用 / 未完成”三组，可直接发群里催填。
      </${Note}>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Reports = ReportsView;
})();
