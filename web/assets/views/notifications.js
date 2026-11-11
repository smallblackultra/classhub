/* 通知中心：截止提醒、新截止日、待审核草稿 */
(function () {
  "use strict";
  const { html, icon } = window.U;
  const { Button, Page, PageHead, Empty, Note, LoadingList, ErrorView, useApi } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  const KIND_ICON = {
    deadline_new: "sparkles",
    draft_pending: "inbox",
    due_24h: "clock",
    due_2h: "clock",
    overdue: "alert",
    system: "bell",
  };
  const KIND_TONE = {
    deadline_new: "violet",
    draft_pending: "amber",
    due_24h: "blue",
    due_2h: "amber",
    overdue: "red",
    system: "",
  };

  function NotificationRow(props) {
    const n = props.item;
    const open = () => {
      if (!n.read) {
        API.api.post("/api/notifications/read", { ids: [n.id] })
          .then(() => { API.bump(); })
          .catch(() => {});
      }
      if (n.deadline_id) API.go("detail/" + n.deadline_id);
    };
    return html`<button type="button" class=${"notif" + (n.read ? "" : " unread")} onClick=${open}>
      <span class=${"notif-icon badge " + (KIND_TONE[n.kind] || "")}>${icon(KIND_ICON[n.kind] || "bell")}</span>
      <span class="notif-main">
        <span class="notif-title">${n.title}</span>
        <span class="notif-body">${n.body}</span>
        <span class="notif-meta">${U.fmtDateTime(n.created_at)} · ${n.kind_label || ""}</span>
      </span>
      ${n.read ? null : html`<span class="notif-dot" aria-label="未读"></span>`}
    </button>`;
  }

  function NotificationsView() {
    const S = API.useStore();
    const [unreadOnly, setUnreadOnly] = window.preactHooks.useState(false);
    const path = "/api/notifications?limit=50" + (unreadOnly ? "&unread=1" : "");
    const api = useApi(path, [S.rev, unreadOnly]);
    const [busy, setBusy] = window.preactHooks.useState(false);

    const data = api.data || { items: [], unread: (S.me && S.me.unread_notifications) || 0 };
    const items = data.items || [];

    function markAll() {
      setBusy(true);
      API.api.post("/api/notifications/read-all", {})
        .then(() => { API.toast("全部标为已读"); API.refreshMe(); API.bump(); })
        .catch((e) => API.toast(e.message || "操作失败", "err"))
        .finally(() => setBusy(false));
    }

    return html`<${Page}>
      <${PageHead} title="通知" sub=${data.unread ? data.unread + " 条未读" : "没有未读消息"}
        back=${() => API.go("list")} />
      <div class="spread" style="margin-bottom:12px">
        <div class="seg">
          <button type="button" data-on=${unreadOnly ? "0" : "1"} onClick=${() => setUnreadOnly(false)}>全部</button>
          <button type="button" data-on=${unreadOnly ? "1" : "0"} onClick=${() => setUnreadOnly(true)}>未读</button>
        </div>
        ${data.unread ? html`<${Button} size="sm" variant="soft" loading=${busy} onClick=${markAll}>全部已读</${Button}>` : null}
      </div>

      ${api.error ? html`<${ErrorView} err=${api.error} retry=${api.reload} />`
        : api.loading && !api.data ? html`<${LoadingList} rows=${4} />`
        : items.length === 0 ? html`<${Empty} icon="bell" title=${unreadOnly ? "没有未读通知" : "还没有通知"}
            hint="截止前 24 小时与 2 小时、逾期、新截止日和待审核草稿都会出现在这里。" />`
        : html`<div class="stack">${items.map((n) => html`<${NotificationRow} key=${n.id} item=${n} />`)}</div>`}
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Notifications = NotificationsView;
})();
