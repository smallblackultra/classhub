/* 登录 / 注册 / 待审批 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState } = window.preactHooks;
  const { Button, Field, Note, Spinner, CopyBtn } = window.CDH.ui;

  function nextPath() {
    try {
      const next = new URLSearchParams(location.search).get("next") || "";
      if (next.charAt(0) !== "/" || next.charAt(1) === "/") return "";
      // 解析后仍须同源，挡住 /\evil、编码换行等绕过 // 的写法。
      const target = new URL(next, location.origin);
      if (target.origin !== location.origin) return "";
      return target.pathname + target.search + target.hash;
    } catch (e) {
      /* 忽略非法回跳参数 */
    }
    return "";
  }

  function afterAuth() {
    const next = nextPath();
    if (next) {
      location.assign(next);
      return;
    }
    window.API.go("list");
  }

  function BackHome() {
    return html`<a class="auth-back" href="/" title="返回班级门户">
      ${icon("back")}<span>返回首页</span>
    </a>`;
  }

  function Logo(props) {
    return html`<div class=${"auth-brand"}>
      <div class="auth-logo">${icon("calendar")}</div>
      <div>
        <div class="auth-title">班级截止日</div>
        <div class="auth-sub">作业 · 表格 · 任务 · 考试，一处看清</div>
      </div>
    </div>`;
  }

  function Login() {
    const S = window.API.useStore();
    const [mode, setMode] = useState("login");
    const [form, setForm] = useState({ student_no: "", password: "", name: "", invite_code: "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [pending, setPending] = useState(false);

    const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

    async function submit(e) {
      e.preventDefault();
      if (busy) return;
      setError(null);
      if (!form.student_no.trim()) return setError("请输入学号");
      if (!form.password) return setError("请输入密码");
      if (mode === "register") {
        if (!form.name.trim()) return setError("请输入姓名");
        if (!form.invite_code.trim()) return setError("请输入班级邀请码");
        if (form.password.length < 6) return setError("密码至少 6 位");
      }
      setBusy(true);
      try {
        if (mode === "login") {
          const profile = await window.API.login(form.student_no.trim(), form.password);
          if (profile.user.status === "pending") setPending(true);
          else if (profile.user.must_change_password) window.API.go("list");
          else afterAuth();
        } else {
          const profile = await window.API.register({
            student_no: form.student_no.trim(),
            password: form.password,
            name: form.name.trim(),
            invite_code: form.invite_code.trim().toUpperCase(),
          });
          if (profile.user.status === "pending") setPending(true);
          else if (profile.user.must_change_password) window.API.go("list");
          else afterAuth();
        }
      } catch (err) {
        setError(err.message || "操作失败");
      } finally {
        setBusy(false);
      }
    }

    if (pending) {
      return html`<div class="auth-page"><div class="auth-card">
        <${Logo} />
        <div style="text-align:center;margin:18px 0 6px">${icon("clock2", "big-icon")}</div>
        <div class="auth-title" style="font-size:19px;text-align:center">账号正在等待审批</div>
        <div class="auth-sub" style="text-align:center;margin-top:8px">
          已提交注册。请让班长或团支书在「成员」页确认你的身份，通过后即可查看班级截止日。
        </div>
        <div class="hr"></div>
        <${Button} block variant="ghost" onClick=${() => window.API.logout()}>退出，换个账号</${Button}>
      </div></div>`;
    }

    return html`<div class="auth-page">
      <${BackHome} />
      <div class="auth-card">
        <${Logo} />
        <div class="tabs" style="margin-top:20px">
          ${[["login", "登录"], ["register", "注册"]].map(([k, label]) =>
            html`<button type="button" data-on=${mode === k ? "1" : "0"}
              onClick=${() => { setMode(k); setError(null); }}>${label}</button>`)}
        </div>
        <form onSubmit=${submit} autocomplete="on">
          <div class="form-grid">
            <${Field} label="学号" required>
              <input class="input" value=${form.student_no} onInput=${set("student_no")}
                placeholder="例如 20230101" autocomplete="username" inputmode="text" />
            </${Field}>
            ${mode === "register" ? html`<${Field} label="姓名" required>
              <input class="input" value=${form.name} onInput=${set("name")} placeholder="真实姓名" />
            </${Field}>` : null}
            ${mode === "register" ? html`<${Field} label="班级邀请码" required hint="向班长 / 团支书索取，例如 CS2301AB">
              <input class="input" value=${form.invite_code} onInput=${set("invite_code")}
                placeholder="8 位邀请码" autocapitalize="characters" />
            </${Field}>` : null}
            <${Field} label="密码" required>
              <input class="input" type="password" value=${form.password} onInput=${set("password")}
                placeholder=${mode === "register" ? "至少 6 位" : "请输入密码"} autocomplete=${mode === "register" ? "new-password" : "current-password"} />
            </${Field}>
            ${error ? html`<${Note} tone="err">${error}</${Note}>` : null}
            <${Button} type="submit" variant="primary" size="lg" block loading=${busy}>
              ${mode === "login" ? "登录" : "提交注册"}
            </${Button}>
          </div>
        </form>
        <div class="hr"></div>
        <details class="demo-box">
          <summary>演示账号（点开查看）</summary>
          <div class="stack" style="margin-top:8px">
            ${[
              ["20230101", "张明", "班长"],
              ["20230102", "李婷", "团支书"],
              ["20230105", "刘洋", "同学"],
              ["20230100", "系统管理员", "管理员"],
            ].map(([no, name, role]) => html`<div class="spread small">
              <span><b>${no}</b> ${name} · ${role}</span>
              <${CopyBtn} text=${no} label="学号" />
            </div>`)}
            <div class="small muted">密码统一 <code>class123</code>，邀请码 <code>CS2301AB</code></div>
          </div>
        </details>
      </div>
      <div class="small muted" style="text-align:center;margin-top:14px">
        密码仅保存为加盐哈希 · 数据仅本班可见
      </div>
    </div>`;
  }

  function Pending() {
    const S = window.API.useStore();
    return html`<div class="auth-page"><div class="auth-card">
      <${BackHome} />
      <${Logo} />
      <div class="auth-title" style="font-size:19px;margin-top:18px">账号待审批</div>
      <div class="auth-sub" style="margin-top:8px">
        你的账号（${S.me ? S.me.user.student_no : ""} ${S.me ? S.me.user.name : ""}）已提交，
        等班长或团支书审批通过后就能看到班级截止日。
      </div>
      <div class="hr"></div>
      <div class="row-flex">
        <${Button} variant="soft" onClick=${() => window.API.refreshMe()}>刷新状态</${Button}>
        <${Button} variant="ghost" onClick=${() => window.API.logout()}>退出登录</${Button}>
      </div>
    </div></div>`;
  }

  function ChangePassword() {
    const [form, setForm] = useState({ old_password: "", new_password: "", confirm: "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

    async function submit(e) {
      e.preventDefault();
      if (busy) return;
      if (form.new_password.length < 8) { setError("新密码至少 8 位"); return; }
      if (form.new_password !== form.confirm) { setError("两次输入的新密码不一致"); return; }
      setBusy(true);
      setError(null);
      try {
        await window.API.api.post("/api/auth/change-password", {
          old_password: form.old_password,
          new_password: form.new_password,
        });
        window.API.toast("密码已修改，欢迎使用", "ok");
        await window.API.refreshMe();
        afterAuth();
      } catch (err) {
        setError(err.message || "修改失败，请重试");
      } finally {
        setBusy(false);
      }
    }

    return html`<div class="auth-page"><div class="auth-card">
      <${BackHome} />
      <${Logo} />
      <div class="auth-title" style="font-size:19px;margin-top:18px">首次登录，请修改初始密码</div>
      <div class="auth-sub" style="margin-top:8px">
        初始密码只用于第一次登录。请设置一个只有你自己知道的新密码（至少 8 位），
        修改后其它人手里的初始密码就失效了。
      </div>
      <form class="stack" style="margin-top:16px" onSubmit=${submit}>
        <${Field} label="当前密码（初始密码）" required>
          <input class="input" type="password" value=${form.old_password}
            onInput=${set("old_password")} autocomplete="current-password" />
        </${Field}>
        <${Field} label="新密码" required hint="至少 8 位，建议字母 + 数字">
          <input class="input" type="password" value=${form.new_password}
            onInput=${set("new_password")} autocomplete="new-password" />
        </${Field}>
        <${Field} label="确认新密码" required>
          <input class="input" type="password" value=${form.confirm}
            onInput=${set("confirm")} autocomplete="new-password" />
        </${Field}>
        ${error ? html`<${Note} tone="err">${error}</${Note}>` : null}
        <${Button} type="submit" variant="primary" size="lg" block loading=${busy}>保存并进入</${Button}>
      </form>
      <div class="row-flex" style="margin-top:10px;justify-content:center">
        <${Button} variant="ghost" onClick=${() => window.API.logout()}>退出登录</${Button}>
      </div>
    </div></div>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Login = Login;
  window.CDH.views.Pending = Pending;
  window.CDH.views.ChangePassword = ChangePassword;
  window.CDH.views.Logo = Logo;
})();
