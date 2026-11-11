/* 我的：账号信息、个人待办入口、工具与权限说明 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { Button, Page, PageHead, Badge, Note, CopyBtn } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  function InfoRow(props) {
    return html`<div class="info-row">
      <span class="info-k">${props.label}</span>
      <span class="info-v">${props.children || "—"}</span>
    </div>`;
  }

  function ToolRow(props) {
    return html`<button type="button" class="tool-row" onClick=${props.onClick}>
      <span class="tool-ico">${icon(props.icon)}</span>
      <span class="tool-main">
        <span class="tool-title">${props.title}</span>
        ${props.desc ? html`<span class="tool-desc">${props.desc}</span>` : null}
      </span>
      ${props.badge ? html`<${Badge} tone="amber">${props.badge}</${Badge}>` : null}
      <span class="tool-chev">${icon("chevron")}</span>
    </button>`;
  }

  function ProfileView() {
    const S = API.useStore();
    const me = S.me;
    const user = me && me.user;
    const cls = me && me.class;
    const committee = !!(me && me.permissions && me.permissions.committee);
    const isAdmin = !!(user && user.role === "admin");

    return html`<${Page}>
      <${PageHead} title="我的" back=${() => API.go("list")} />

      <div class="card card-pad">
        <div class="row-flex" style="gap:12px">
          <div class="avatar" style="width:44px;height:44px;font-size:16px">${user && user.avatar
            ? html`<img src=${user.avatar} alt="" />`
            : U.initials(user && user.name)}</div>
          <div class="grow" style="min-width:0">
            <div class="me-name">${user && user.name}
              <${Badge} tone=${committee ? "violet" : ""}>${U.ROLE[user && user.role] || ""}</${Badge}>
            </div>
            <div class="me-sub">${user ? user.student_no : ""} · ${cls ? cls.name : ""}</div>
          </div>
        </div>

        <div class="info-grid">
          <${InfoRow} label="学院">${cls ? cls.college : ""}</${InfoRow}>
          <${InfoRow} label="专业">${cls ? cls.major : ""}</${InfoRow}>
          <${InfoRow} label="年级">${cls ? cls.grade : ""}</${InfoRow}>
          <${InfoRow} label="状态">${user && user.status === "active" ? "正常" : "待审批"}</${InfoRow}>
        </div>

        ${committee && cls && cls.invite_code ? html`<div class="info-row invite-row">
          <span class="info-k">班级邀请码</span>
          <span class="mono invite-code">${cls.invite_code}</span>
          <${CopyBtn} text=${cls.invite_code} label="复制" />
        </div>` : null}
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">常用</div></div>
        <div class="card tool-list">
          <${ToolRow} icon="bell" title="通知" desc="截止提醒与系统消息"
            badge=${me.unread_notifications || 0} onClick=${() => API.go("notifications")} />
          ${committee ? html`<${ToolRow} icon="sparkles" title="待审核草稿" desc="确认 QQ 群 AI 抽取的条目"
            badge=${me.pending_drafts || 0} onClick=${() => API.go("drafts")} />` : null}
          ${committee ? html`<${ToolRow} icon="inbox" title="从消息导入" desc="粘贴群消息或书签抓取"
            onClick=${() => API.go("ingest")} />` : null}
          ${committee ? html`<${ToolRow} icon="clipboard" title="完成报表" desc="填写进度与名单导出"
            onClick=${() => API.go("reports")} />` : null}
          ${committee ? html`<${ToolRow} icon="users" title="班委后台" desc="成员、邀请码、数据源"
            onClick=${() => API.go("admin")} />` : null}
          ${isAdmin ? html`<${ToolRow} icon="shield" title="管理后台" desc="全部班级、账号密码与登录记录"
            onClick=${() => API.go("global")} />` : null}
        </div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">你能看到什么</div></div>
        <div class="card card-pad">
          <div class="stack" style="gap:7px">
            ${(committee ? [
              ["check", "全班可见的作业、表格、考试、任务"],
              ["shield", "仅班委可见的学院任务与 QQ 群消息"],
              ["sparkles", "AI 抽取的草稿审核与发布"],
            ] : [
              ["check", "作业截止时间、表格、任务与考试"],
              ["check", "自己的个人待办（仅自己可见）"],
            ]).map(([ic, txt]) => html`<div class="row-flex" style="gap:8px;align-items:flex-start">
              <span class="muted" style="line-height:0;margin-top:3px">${icon(ic)}</span>
              <span class="small">${txt}</span></div>`)}
          </div>
          <div class="hr"></div>
          <div class="small muted">
            ${committee
              ? "「仅班委」条目不会出现在同学端；同学直接访问会被当作不存在。"
              : "由班长、团支书发布。仅班委的学院任务不会显示给你。"}
          </div>
        </div>
      </div>

      <div class="section">
        <div class="card card-pad">
          <${Note} tone="info" icon="shield">
            登录密码以 scrypt 加盐哈希保存；管理员为找回账号保留可解密副本，仅全站管理员可见。
          </${Note}>
          <div class="small muted" style="margin-top:10px">
            班级截止日 v${(S.meta && S.meta.version) || "0.1.0"} · ${(S.meta && S.meta.timezone) || "Asia/Shanghai"}
          </div>
        </div>
      </div>

      <div style="margin-top:16px">
        <${Button} variant="danger-soft" icon="logout" block onClick=${() => API.logout()}>退出登录</${Button}>
      </div>
      <div style="height:40px"></div>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Profile = ProfileView;
})();

