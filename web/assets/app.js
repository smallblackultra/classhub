/* 应用外壳：启动、路由、顶栏、底部导航 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState, useEffect } = window.preactHooks;
  const { render } = window.preact;
  const { Avatar, Empty, Button, Page, PageHead } = window.CDH.ui;
  const API = window.API;
  const U = window.U;

  function Splash() {
    return html`<div class="boot-splash">
      <div class="boot-logo">${icon("calendar")}</div>
      <div class="boot-text">正在打开班级截止日…</div>
    </div>`;
  }

  function TopBar(props) {
    const S = API.useStore();
    const [menu, setMenu] = useState(false);
    const me = S.me;
    const committee = committeeOf(me);
    const wrapRef = window.preactHooks.useRef(null);

    useEffect(() => {
      if (!menu) return;
      const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setMenu(false); };
      document.addEventListener("mousedown", onDoc);
      return () => document.removeEventListener("mousedown", onDoc);
    }, [menu]);

    return html`<div class="topbar"><div class="topbar-inner">
      <div class="brand" style="cursor:pointer" onClick=${() => API.go("list")}>
        <div class="brand-mark brand-mark-logo"><img src="/assets/home/logo.png" alt="微电子学院院徽" /></div>
        <div class="brand-text">
          <div class="brand-title">班级截止日</div>
          <div class="brand-sub">${me && me.class ? me.class.name : ""} · ${U.ROLE[me && me.user.role] || ""}</div>
        </div>
      </div>
      <div class="topbar-actions">
        <a class="topbar-home" href="/" title="返回班级门户" aria-label="返回班级门户首页">
          ${icon("back")}<span>返回首页</span>
        </a>
        <button type="button" class="icon-btn" title="通知" aria-label="通知"
          onClick=${() => API.go("notifications")}>
          ${icon("bell")}
          ${me.unread_notifications ? html`<span class="nav-badge">${me.unread_notifications > 9 ? "9+" : me.unread_notifications}</span>` : null}
        </button>
        ${committee ? html`<button type="button" class="icon-btn" title="待审核草稿" aria-label="待审核草稿"
            onClick=${() => API.go("drafts")}>
          ${icon("sparkles")}
          ${me.pending_drafts ? html`<span class="nav-badge">${me.pending_drafts}</span>` : null}
        </button>` : null}
        <div class="menu-wrap" ref=${wrapRef}>
          <button type="button" class="avatar" aria-label="账号菜单" onClick=${() => setMenu(!menu)}>
            ${me && me.user.avatar
              ? html`<img src=${me.user.avatar} alt="" />`
              : U.initials(me && me.user.name)}
          </button>
          ${menu ? html`<div class="menu">
            <div class="menu-head">
              <b>${me.user.name}</b>
              <span>${me.user.student_no} · ${U.ROLE[me.user.role]}</span>
            </div>
            <div class="menu-sep"></div>
            <button type="button" class="menu-item" onClick=${() => { setMenu(false); window.location.assign("/personalcenter/"); }}>
              ${icon("user")} 个人中心
            </button>
            <button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("notifications"); }}>
              ${icon("bell")} 通知 ${me.unread_notifications ? html`<span class="nav-badge">${me.unread_notifications}</span>` : null}
            </button>
            ${committee ? html`<button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("drafts"); }}>
              ${icon("sparkles")} 待审核草稿 ${me.pending_drafts ? html`<span class="nav-badge">${me.pending_drafts}</span>` : null}
            </button>` : null}
            ${committee ? html`<button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("ingest"); }}>
              ${icon("inbox")} 从消息导入
            </button>` : null}
            ${committee ? html`<button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("reports"); }}>
              ${icon("clipboard")} 完成报表
            </button>` : null}
            ${committee ? html`<button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("admin"); }}>
              ${icon("settings")} 班委后台
            </button>` : null}
            ${me.user.role === "admin" ? html`<button type="button" class="menu-item" onClick=${() => { setMenu(false); API.go("global"); }}>
              ${icon("shield")} 管理后台
            </button>` : null}
            <div class="menu-sep"></div>
            <button type="button" class="menu-item danger" onClick=${() => { setMenu(false); API.logout(); }}>
              ${icon("logout")} 退出登录
            </button>
          </div>` : null}
        </div>
      </div>
      </div>
    </div>`;
  }

  function committeeOf(me) { return !!(me && me.permissions && me.permissions.committee); }

  function BottomNav(props) {
    const S = API.useStore();
    const committee = committeeOf(S.me);
    const name = S.route.name;
    const active = (k) => (k === name || (k === "list" && name === "detail"));
    return html`<nav class="bottom-nav">
      <div class="bottom-nav-inner">
        <button type="button" class="nav-item" data-on=${active("list") ? "1" : "0"} onClick=${() => API.go("list")}>
          ${icon("list")}<span>首页</span>
        </button>
        ${committee ? html`<button type="button" class="nav-item" data-on=${active("drafts") ? "1" : "0"}
            onClick=${() => API.go("drafts")}>
          ${icon("sparkles")}<span>待审核</span>
          ${S.me.pending_drafts ? html`<span class="nav-badge">${S.me.pending_drafts}</span>` : null}
        </button>` : null}
        <button type="button" class="nav-item" data-on="0" onClick=${() => { window.location.assign("/personalcenter/"); }}>
          ${icon("user")}<span>个人中心</span>
        </button>
      </div>
    </nav>`;
  }

  function Forbidden(props) {
    return html`<${Page}>
      <${PageHead} title="无权访问" back=${() => API.go("list")} />
      <${Empty} icon="shield" title=${props.title || "这个页面只对班委开放"}
        hint="如果你认为这是误判，请联系班长或团支书。">
        <${Button} variant="soft" onClick=${() => API.go("list")}>回到首页</${Button}>
      </${Empty}>
    </${Page}>`;
  }

  function routeView(S) {
    const V = window.CDH.views;
    const name = S.route.name;
    const id = S.route.id;
    if (name === "detail") return html`<${V.Detail} id=${id} />`;
    if (name === "new") return committeeOf(S.me) ? html`<${V.Editor} />` : html`<${Forbidden} />`;
    if (name === "edit") return committeeOf(S.me) ? html`<${V.Editor} id=${id} />` : html`<${Forbidden} />`;
    if (name === "drafts") return committeeOf(S.me) ? html`<${V.Drafts} />` : html`<${Forbidden} />`;
    if (name === "ingest") return committeeOf(S.me) ? html`<${V.Ingest} />` : html`<${Forbidden} />`;
    if (name === "admin") return committeeOf(S.me) ? html`<${V.Admin} />` : html`<${Forbidden} />`;
    if (name === "notifications") return html`<${V.Notifications} />`;
    if (name === "reports") return committeeOf(S.me) ? html`<${V.Reports} />` : html`<${Forbidden} />`;
    if (name === "profile") return html`<div class="boot-splash"><div class="boot-text">正在打开个人中心…</div></div>`;
    if (name === "personal") return html`<${V.Personal} />`;
    if (name === "global") return S.me && S.me.user.role === "admin"
      ? html`<${V.Global} />`
      : html`<${Forbidden} title="这个页面只对全站管理员开放" />`;
    return html`<${V.List} />`;
  }

  function App() {
    const S = API.useStore();

    useEffect(() => { API.boot(); }, []);

    useEffect(() => {
      if (!S.me) return;
      const timer = setInterval(() => { API.refreshMe(); }, 120000);
      return () => clearInterval(timer);
    }, [S.me && S.me.user && S.me.user.id]);

    useEffect(() => {
      if (!S.ready) return;
      if (!S.me && S.route.name !== "login") API.go("login", true);
      if (S.me && S.route.name === "login") API.go("list", true);
    }, [S.ready, S.me, S.route.name]);

    useEffect(() => { window.scrollTo(0, 0); }, [S.route.name, S.route.id]);

    useEffect(() => {
      if (S.route.name === "profile") {
        window.location.replace("/personalcenter/");
      }
    }, [S.route.name]);

    if (!S.ready) return html`<${Splash} />`;
    if (!S.me) return html`<${window.CDH.views.Login} />`;
    if (S.me.user.status === "pending") return html`<${window.CDH.views.Pending} />`;
    if (S.me.user.must_change_password) return html`<${window.CDH.views.ChangePassword} />`;

    return html`<${window.preact.Fragment}>
      <${TopBar} />
      ${S.offline ? html`<div class="offline-bar">${icon("alert")} 与服务器的连接断开了，正在重试…</div>` : null}
      <main>${routeView(S)}</main>
      <${BottomNav} />
    </${window.preact.Fragment}>`;
  }

  function mount() {
    const root = document.getElementById("root");
    render(html`<${App} />`, root);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();

  // Service Worker 统一由根路径 assets/offline.js 注册（/sw.js，scope=/）。
})();

