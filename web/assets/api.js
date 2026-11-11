/* API 客户端 + 全局 store + 路由 + toast */
(function () {
  "use strict";
  const { useState, useEffect } = window.preactHooks;

  // 站点可能挂在 /daily/ 这类子路径下：以当前页面所在目录为根，所有请求都相对它
  const ROOT = (function () {
    const p = location.pathname || "/";
    return p.endsWith("/") ? p : p.replace(/[^/]*$/, "");
  })();

  const state = {
    me: null,          // /api/auth/me 的 profile
    meta: null,        // /api/meta
    ready: false,
    rev: 0,            // 数据版本号，任何写操作后自增，列表据此刷新
    route: { name: "list", id: null, segs: [], query: new URLSearchParams() },
    offline: false,
  };
  const listeners = new Set();
  function notify() { listeners.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } }); }
  function set(patch) { Object.assign(state, patch); notify(); }

  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)cdh_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  class ApiError extends Error {
    constructor(status, code, message, field) {
      super(message || "请求失败");
      this.status = status; this.code = code; this.field = field;
    }
  }

  async function request(method, path, body, opts) {
    opts = opts || {};
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (["POST", "PATCH", "PUT", "DELETE"].includes(method)) headers["X-CSRF"] = csrf();
    let res;
    try {
      res = await fetch(ROOT + String(path).replace(/^\/+/, ""), {
        method, headers, credentials: "same-origin",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (e) {
      if (state.offline !== true) set({ offline: true });
      throw new ApiError(0, "network", "网络连接失败，请确认服务仍在运行");
    }
    const offlineFallback = res.headers.get("X-ClassHub-Offline") === "1";
    if (offlineFallback) {
      if (!state.offline) set({ offline: true });
    } else if (state.offline) {
      set({ offline: false });
    }
    const text = await res.text();
    let data = null;
    if (text) { try { data = JSON.parse(text); } catch (e) { data = null; } }
    if (!res.ok) {
      const err = (data && data.error) || {};
      const error = new ApiError(res.status, err.code || "error",
        err.message || ("请求失败（" + res.status + "）"), err.field);
      if (res.status === 401 && !opts.silentAuth && path !== "/api/auth/login") {
        set({ me: null });
      }
      throw error;
    }
    return data;
  }

  const api = {
    get: (p, o) => request("GET", p, undefined, o),
    post: (p, b, o) => request("POST", p, b === undefined ? {} : b, o),
    patch: (p, b, o) => request("PATCH", p, b, o),
    del: (p, o) => request("DELETE", p, undefined, o),
    request,
  };

  /* ---------------------------------------------------------- 路由 */
  function parseRoute() {
    const raw = (location.hash || "").replace(/^#\/?/, "");
    const [pathPart, queryPart] = raw.split("?");
    const segs = pathPart.split("/").filter(Boolean);
    return { name: segs[0] || "list", id: segs[1] || null, segs, query: new URLSearchParams(queryPart || "") };
  }
  function go(hash, replace) {
    const target = "#/" + String(hash || "").replace(/^#?\/?/, "");
    if (replace) history.replaceState(null, "", target);
    else location.hash = target;
    if (replace) set({ route: parseRoute() });
  }
  window.addEventListener("hashchange", () => set({ route: parseRoute() }));

  /* ---------------------------------------------------------- 会话 */
  async function boot() {
    state.route = parseRoute();
    let me = null;
    try { me = await api.get("/api/auth/me", { silentAuth: true }); } catch (e) { me = null; }
    let meta = null;
    try { meta = await api.get("/api/meta"); } catch (e) { meta = null; }
    set({ me, meta, ready: true });
  }
  async function login(studentNo, password) {
    const profile = await api.post("/api/auth/login", { student_no: studentNo, password });
    set({ me: profile, rev: state.rev + 1 });
    return profile;
  }
  async function register(payload) {
    const profile = await api.post("/api/auth/register", payload);
    set({ me: profile, rev: state.rev + 1 });
    return profile;
  }
  async function logout() {
    try { await api.post("/api/auth/logout", {}); } catch (e) { /* 忽略 */ }
    set({ me: null, rev: state.rev + 1 });
    history.replaceState(null, "", location.pathname);
    set({ route: parseRoute() });
    go("login", true);
  }
  async function refreshMe() {
    try { set({ me: await api.get("/api/auth/me", { silentAuth: true }) }); } catch (e) { set({ me: null }); }
  }
  function bump() { set({ rev: state.rev + 1 }); }

  /* ---------------------------------------------------------- toast */
  function toast(message, kind) {
    const root = document.getElementById("toast-root");
    if (!root) return;
    const el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 220); }, 3200);
  }
  function fail(err) {
    if (err && err.status === 401) return;
    toast((err && err.message) || "操作失败", "err");
  }

  function useStore() {
    const [, force] = useState(0);
    useEffect(() => {
      const fn = () => force((n) => (n + 1) % 1000000);
      listeners.add(fn);
      return () => listeners.delete(fn);
    }, []);
    return state;
  }

  window.API = {
    state, api, boot, login, register, logout, refreshMe, bump, go, toast, fail,
    useStore, ApiError, root: ROOT,
    url(path) { return ROOT + String(path).replace(/^\/+/, ""); },
    get isCommittee() { return !!(state.me && state.me.permissions && state.me.permissions.committee); },
  };
})();
