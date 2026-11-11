/* 个人待办模块：嵌在首页底部，也可独立成页；仅创建者可见 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState, useEffect, useRef } = window.preactHooks;
  const { Button, Empty, LoadingList, ErrorView, useApi, DateField } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  function dueText(item) {
    if (!item.due_local) return "";
    const d = U.fmtDate(item.due_local);
    const t = item.due_local.slice(11, 16);
    return t === "23:59" ? d : d + " " + t;
  }

  function PersonalPanel(props) {
    const embedded = !!props.embedded;
    const S = API.useStore();
    const [title, setTitle] = useState("");
    const [due, setDue] = useState("");
    const [saving, setSaving] = useState(false);
    const inputRef = useRef(null);
    const { data, loading, error, reload } = useApi("/api/personal?done=all", [S.rev]);

    const items = (data && data.items) || [];
    const counts = (data && data.counts) || { total: 0, open: 0, done: 0 };

    useEffect(() => {
      if (props.onReady) props.onReady(() => inputRef.current && inputRef.current.focus());
    }, []);

    function add() {
      const text = title.trim();
      if (!text) {
        API.toast("先写点内容", "err");
        return;
      }
      setSaving(true);
      const body = { title: text };
      if (due) body.due_at = due + "T23:59:00+08:00";
      API.api.post("/api/personal", body)
        .then(() => {
          setTitle("");
          setDue("");
          API.toast("已加入我的待办", "ok");
          reload();
          API.refreshMe();
        })
        .catch((e) => API.toast(e.message || "保存失败", "err"))
        .then(() => setSaving(false));
    }

    function toggle(item) {
      API.api.patch(`/api/personal/${item.id}`, { done: !item.done })
        .then(() => { reload(); })
        .catch((e) => API.toast(e.message || "操作失败", "err"));
    }

    function remove(item) {
      if (!window.confirm("删除这条个人待办？")) return;
      API.api.del(`/api/personal/${item.id}`)
        .then(() => { reload(); })
        .catch((e) => API.toast(e.message || "删除失败", "err"));
    }

    return html`<div>
      <div class=${embedded ? "" : "card card-pad"} style=${embedded ? "" : "margin-top:12px"}>
        <div class="small muted" style="margin-bottom:8px">${embedded ? "只属于你自己，别人看不到" : "这些待办只有你自己能看到，不会出现在班级列表里"}</div>
        <div class="row-flex personal-form" style="gap:8px;flex-wrap:wrap">
          <input ref=${inputRef} class="input grow" style="min-width:180px" maxlength="120"
            placeholder="例如：买高数练习册 / 周三交实验报告"
            value=${title}
            onInput=${(e) => setTitle(e.target.value)}
            onKeyDown=${(e) => { if (e.key === "Enter") add(); }} />
          <${DateField} value=${due} onChange=${setDue} style="width:150px" />
          <${Button} variant="primary" onClick=${add} disabled=${saving}>${saving ? "保存中…" : "添加"}</${Button}>
        </div>
      </div>

      <div class="section" style="margin-top:16px">
        <div class="section-head">
          <div class="section-title">我的待办</div>
          <div class="small muted">${counts.open} 条未完成 · 共 ${counts.total} 条</div>
        </div>
        ${loading && !data ? html`<${LoadingList} rows=${3} />`
        : error ? html`<${ErrorView} err=${error} retry=${reload} />`
        : items.length === 0 ? html`<${Empty} icon="check" title="还没有个人待办"
            hint="上面写一条，回车即可添加。"
            />`
        : html`<div class="item-list">
            ${items.map((item) => html`<div class="item" data-tone=${item.done ? "green" : "violet"}
              data-done=${item.done ? "1" : "0"}>
              <button type="button" class="check-btn" aria-label="切换完成"
                onClick=${() => toggle(item)}>${item.done ? icon("check") : ""}</button>
              <div class="item-main">
                <div class="item-title">${item.title}</div>
                <div class="item-sub">
                  ${item.due_local ? html`<span>${dueText(item)}</span>` : html`<span class="muted">未设时间</span>`}
                  ${item.note ? html`<span class="dot"></span><span>${item.note}</span>` : null}
                </div>
              </div>
              <div class="item-side">
                <button type="button" class="icon-btn" title="删除" aria-label="删除"
                  onClick=${() => remove(item)}>${icon("trash")}</button>
              </div>
            </div>`)}
          </div>`}
      </div>
    </div>`;
  }

  function PersonalView() {
    const API = window.API;
    return html`<${window.CDH.ui.Page}>
      <${window.CDH.ui.PageHead} title="我的待办" back=${() => API.go("list")} />
      <${PersonalPanel} />
      <div style="height:40px"></div>
    </${window.CDH.ui.Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.PersonalPanel = PersonalPanel;
  window.CDH.views.Personal = PersonalView;
})();



