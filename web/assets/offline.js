/* 班级门户：离线缓存、离线个人计划、PWA 注册。
 *
 * 原则：
 * 1. 静态外壳交给根路径 Service Worker（/sw.js）缓存；
 * 2. API GET 成功响应缓存在 localStorage，断网时按最近登录账号回放；
 * 3. 个人待办/计划允许离线新增、修改、完成、删除，联网后自动同步；
 * 4. 班级 DDL、成绩、通知等只读，不伪造任何写操作。
 */
(function () {
  "use strict";

  const PREFIX = "cdh.offline.v1.";
  const nativeFetch = window.fetch.bind(window);
  let offline = false;
  let syncing = false;
  let banner = null;

  function read(key, fallback) {
    try {
      const raw = localStorage.getItem(PREFIX + key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function write(key, value) {
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch (e) {
      /* 存储已满或被禁用时，在线功能继续可用 */
    }
  }
  function remove(key) {
    try { localStorage.removeItem(PREFIX + key); } catch (e) { /* ignore */ }
  }
  function clearAll() {
    try {
      Object.keys(localStorage)
        .filter((k) => k.startsWith(PREFIX))
        .forEach((k) => localStorage.removeItem(k));
    } catch (e) { /* ignore */ }
    updateBanner();
  }

  function lastProfile() {
    const profile = read("profile", null);
    return profile && profile.user ? profile : null;
  }
  function studentKey() {
    const profile = lastProfile();
    return profile && profile.user ? String(profile.user.student_no || profile.user.id || "user") : "anon";
  }
  function cacheName(path) {
    return "data." + studentKey() + "." + path;
  }

  function normalizeApiPath(input) {
    let parsed;
    try {
      parsed = new URL(typeof input === "string" ? input : input.url, location.href);
    } catch (e) {
      return null;
    }
    if (parsed.origin !== location.origin) return null;
    let path = parsed.pathname;
    path = path.replace(/^\/(?:daliy|daily)(?=\/api\/)/, "");
    if (!path.startsWith("/api/")) return null;
    return path + parsed.search;
  }

  function jsonResponse(data) {
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json; charset=utf-8", "X-ClassHub-Offline": "1" }
    });
  }

  function getCookie(name) {
    const hit = document.cookie.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"));
    return hit ? decodeURIComponent(hit[1]) : "";
  }

  function writeHeaders() {
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    const csrf = getCookie("cdh_csrf");
    if (csrf) headers["X-CSRF"] = csrf;
    return headers;
  }

  function bodyObject(init) {
    const raw = init && init.body;
    if (typeof raw === "string") {
      try { return JSON.parse(raw); } catch (e) { return {}; }
    }
    return raw && typeof raw === "object" ? raw : {};
  }

  function isoLocal(iso) {
    if (!iso) return null;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    try {
      return new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Asia/Shanghai",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hour12: false
      }).format(date).replace(" ", "T");
    } catch (e) {
      return iso;
    }
  }

  /* ------------------------------------------------------ 通用 GET 缓存 */
  function remember(path, data) {
    if (!data || typeof data !== "object") return;
    write(cacheName(path), { at: Date.now(), data });
    if (/^\/api\/auth\/me$/.test(path) && data.user) {
      write("profile", data);
      updateBanner();
    }
  }
  function recall(path) {
    const hit = read(cacheName(path), null);
    return hit && hit.data ? hit.data : null;
  }

  async function cacheNetworkResponse(path, response) {
    try {
      const data = await response.clone().json();
      remember(path, data);
    } catch (e) {
      /* 非 JSON 响应不缓存 */
    }
  }

  async function networkGet(request, path) {
    let response;
    try {
      response = await nativeFetch(request);
    } catch (error) {
      markOffline();
      const cached = path === "/api/auth/me" ? lastProfile() : recall(path);
      if (cached) return jsonResponse(cached);
      throw error;
    }
    if (response.ok) {
      if (path !== "/api/auth/me" || response.status === 200) {
        cacheNetworkResponse(path, response);
      }
      clearOffline();
    }
    return response;
  }

  /* ------------------------------------------------------ 个人计划离线队列 */
  function emptyPersonal() {
    return { server: [], local: [], patches: {}, deletes: [] };
  }
  function personalKey() {
    return "personal." + studentKey();
  }
  function personalState() {
    const state = read(personalKey(), null);
    if (!state || typeof state !== "object") return emptyPersonal();
    return {
      server: Array.isArray(state.server) ? state.server : [],
      local: Array.isArray(state.local) ? state.local : [],
      patches: state.patches && typeof state.patches === "object" ? state.patches : {},
      deletes: Array.isArray(state.deletes) ? state.deletes : []
    };
  }
  function savePersonal(state) {
    write(personalKey(), state);
    updateBanner();
  }
  function mergeItem(base, patch) {
    const next = Object.assign({}, base, patch || {});
    if (patch && Object.prototype.hasOwnProperty.call(patch, "due_at")) {
      next.due_local = patch.due_at ? isoLocal(patch.due_at) : null;
    }
    if (patch && Object.prototype.hasOwnProperty.call(patch, "done")) {
      next.done = !!patch.done;
    }
    return next;
  }
  function personalPayload(path) {
    const state = personalState();
    const query = new URLSearchParams(path.split("?")[1] || "");
    const done = query.get("done") || "all";
    const items = [];
    state.server.forEach((item) => {
      if (state.deletes.indexOf(item.id) !== -1) return;
      items.push(state.patches[item.id] ? mergeItem(item, state.patches[item.id]) : item);
    });
    state.local.forEach((item) => {
      if (state.deletes.indexOf(item.id) === -1) items.push(item);
    });
    const filtered = items.filter((item) => done === "all" || (done === "done" ? item.done : !item.done));
    filtered.sort((a, b) => {
      if (!!a.done !== !!b.done) return a.done ? 1 : -1;
      if (!a.due_at && !b.due_at) return Number(b.id) - Number(a.id);
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;
      return String(a.due_at).localeCompare(String(b.due_at));
    });
    return {
      items: filtered,
      counts: {
        total: filtered.length,
        open: filtered.filter((item) => !item.done).length,
        done: filtered.filter((item) => item.done).length
      },
      offline: true
    };
  }

  function newClientKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return "offline-" + window.crypto.randomUUID();
    }
    return "offline-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  function localItem(body) {
    const due = body.due_at || null;
    const now = new Date().toISOString();
    return {
      id: "local-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
      client_key: newClientKey(),
      title: String(body.title || "").trim(),
      note: String(body.note || ""),
      due_at: due,
      due_local: due ? isoLocal(due) : null,
      done: false,
      created_at: now,
      updated_at: now,
      local: true
    };
  }

  function offlinePersonalWrite(method, path, init) {
    const state = personalState();
    const body = bodyObject(init);
    const match = path.match(/^\/api\/personal\/([^/?]+)/);
    const itemId = match ? decodeURIComponent(match[1]) : null;
    if (method === "POST" && path === "/api/personal") {
      const item = localItem(body);
      state.local.push(item);
      savePersonal(state);
      return jsonResponse({ item: item });
    }
    if (itemId && itemId.indexOf("local-") === 0) {
      const item = state.local.find((row) => row.id === itemId);
      if (!item) return jsonResponse({ ok: true });
      if (method === "PATCH") {
        Object.assign(item, body, { updated_at: new Date().toISOString() });
        if (Object.prototype.hasOwnProperty.call(body, "due_at")) {
          item.due_local = body.due_at ? isoLocal(body.due_at) : null;
        }
        if (Object.prototype.hasOwnProperty.call(body, "done")) item.done = !!body.done;
        savePersonal(state);
        return jsonResponse({ item: item });
      }
      if (method === "DELETE") {
        state.local = state.local.filter((row) => row.id !== itemId);
        savePersonal(state);
        return jsonResponse({ ok: true });
      }
    }
    if (itemId && method === "PATCH") {
      state.patches[itemId] = Object.assign({}, state.patches[itemId] || {}, body);
      state.server = state.server.map((item) => item.id == itemId ? mergeItem(item, body) : item);
      savePersonal(state);
      return jsonResponse({ item: state.server.find((item) => item.id == itemId) || body });
    }
    if (itemId && method === "DELETE") {
      if (state.deletes.indexOf(itemId) === -1) state.deletes.push(itemId);
      delete state.patches[itemId];
      state.server = state.server.filter((item) => item.id != itemId);
      savePersonal(state);
      return jsonResponse({ ok: true });
    }
    return null;
  }

  function restoreLocalItem(item) {
    const state = personalState();
    if (!state.local.some((row) => row.id === item.id)) {
      state.local.push(item);
      savePersonal(state);
    }
  }

  async function syncPersonal() {
    if (syncing || !navigator.onLine) return false;
    syncing = true;
    try {
      let state = personalState();
      for (const snapshot of state.local.slice()) {
        state = personalState();
        const item = state.local.find((row) => row.id === snapshot.id);
        if (!item) continue;
        // 先摘除本地项，避免在线事件与显式同步并发时重复创建。
        state.local = state.local.filter((row) => row.id !== item.id);
        savePersonal(state);
        let response;
        try {
          response = await nativeFetch("/api/personal", {
            method: "POST", credentials: "same-origin",
            headers: writeHeaders(),
            body: JSON.stringify({
              title: item.title,
              note: item.note || "",
              due_at: item.due_at || null,
              client_key: item.client_key || item.id
            })
          });
        } catch (e) {
          restoreLocalItem(item);
          throw e;
        }
        if (!response.ok) {
          restoreLocalItem(item);
          throw new Error("sync create failed");
        }
        const created = (await response.json()).item;
        if (item.done) {
          await nativeFetch("/api/personal/" + created.id, {
            method: "PATCH", credentials: "same-origin", headers: writeHeaders(),
            body: JSON.stringify({ done: true })
          });
          created.done = true;
        }
        state = personalState();
        state.server = state.server.filter((row) => row.id != created.id).concat(created);
        savePersonal(state);
      }
      state = personalState();
      for (const [id, patch] of Object.entries(state.patches)) {
        const response = await nativeFetch("/api/personal/" + id, {
          method: "PATCH", credentials: "same-origin", headers: writeHeaders(),
          body: JSON.stringify(patch)
        });
        if (!response.ok) throw new Error("sync patch failed");
        state = personalState();
        delete state.patches[id];
        savePersonal(state);
      }
      for (const id of state.deletes.slice()) {
        const response = await nativeFetch("/api/personal/" + id, {
          method: "DELETE", credentials: "same-origin", headers: writeHeaders()
        });
        if (!response.ok && response.status !== 404) throw new Error("sync delete failed");
        state = personalState();
        state.deletes = state.deletes.filter((row) => row !== id);
        savePersonal(state);
      }
      return true;
    } catch (e) {
      return false;
    } finally {
      syncing = false;
      updateBanner();
    }
  }

  async function personalGet(request, path) {
    if (navigator.onLine) {
      await syncPersonal();
      try {
        const response = await nativeFetch(request);
        if (response.ok) {
          const data = await response.clone().json();
          if (Array.isArray(data.items)) {
            const state = personalState();
            state.server = data.items;
            savePersonal(state);
            const pending = state.local.length || Object.keys(state.patches).length || state.deletes.length;
            if (pending) return jsonResponse(personalPayload(path));
          }
        }
        return response;
      } catch (e) {
        markOffline();
        return jsonResponse(personalPayload(path));
      }
    }
    markOffline();
    return jsonResponse(personalPayload(path));
  }

  function isPersonalPath(path) {
    return path === "/api/personal" || path.indexOf("/api/personal/") === 0 ||
      path.indexOf("/api/personal?") === 0;
  }

  async function offlineFetch(input, init) {
    const request = new Request(input, init);
    const path = normalizeApiPath(request.url);
    if (!path) return nativeFetch(input, init);
    const method = request.method.toUpperCase();

    if (method === "GET" && path === "/api/auth/me" && !navigator.onLine) {
      const profile = lastProfile();
      if (profile) { markOffline(); return jsonResponse(profile); }
    }
    if (method === "GET" && isPersonalPath(path)) return personalGet(request, path);
    if (method === "GET") return networkGet(request, path);

    if (path === "/api/auth/login" && method === "POST") {
      try {
        const response = await nativeFetch(request);
        if (response.ok) {
          response.clone().json().then((data) => {
            if (data && data.user) { write("profile", data); updateBanner(); }
          }).catch(() => undefined);
          clearOffline();
        }
        return response;
      } catch (e) { markOffline(); throw e; }
    }
    if (path === "/api/auth/logout" && method === "POST") {
      try {
        const response = await nativeFetch(request);
        if (response.ok) clearAll();
        return response;
      } catch (e) { markOffline(); throw e; }
    }
    if (isPersonalPath(path) && ["POST", "PATCH", "DELETE"].includes(method)) {
      try {
        const response = await nativeFetch(request);
        if (response.ok) clearOffline();
        return response;
      } catch (e) {
        const queued = offlinePersonalWrite(method, path, init);
        if (queued) { markOffline(); return queued; }
        throw e;
      }
    }
    return nativeFetch(request);
  }

  /* ------------------------------------------------------ 离线状态提示 */
  let bannerStyle = null;
  function ensureBanner() {
    if (!bannerStyle && document.head) {
      bannerStyle = document.createElement("style");
      // DDL 自己已经有顶部离线提示，避免同屏出现两条横幅。
      bannerStyle.textContent = "body:has(.offline-bar) #cdh-offline-banner{display:none!important}";
      document.head.appendChild(bannerStyle);
    }
    if (banner || !document.body) return banner;
    banner = document.createElement("div");
    banner.id = "cdh-offline-banner";
    banner.setAttribute("role", "status");
    banner.style.cssText = [
      "position:fixed", "left:50%", "bottom:calc(78px + env(safe-area-inset-bottom))",
      "transform:translateX(-50%)", "z-index:9999", "max-width:min(92vw,460px)",
      "padding:8px 14px", "border-radius:999px", "font:500 12px/1.4 system-ui,sans-serif",
      "color:#fff8ed", "background:rgba(75,21,29,.94)", "border:1px solid rgba(210,173,108,.55)",
      "box-shadow:0 8px 28px rgba(0,0,0,.22)", "display:none", "text-align:center",
      "pointer-events:none", "white-space:nowrap"
    ].join(";");
    document.body.appendChild(banner);
    return banner;
  }
  function updateBanner() {
    const node = ensureBanner();
    if (!node) return;
    if (!offline) { node.style.display = "none"; return; }
    const pending = personalState().local.length;
    node.textContent = pending > 0
      ? "离线模式 · 已缓存数据 · " + pending + " 条计划待同步"
      : "离线模式 · 显示上次缓存的数据";
    node.style.display = "block";
  }
  function markOffline() {
    if (!offline) {
      offline = true;
      window.CDH_OFFLINE = true;
      document.documentElement.setAttribute("data-offline", "1");
      window.dispatchEvent(new CustomEvent("cdh-offline", { detail: { offline: true } }));
    }
    updateBanner();
  }
  function clearOffline() {
    if (offline) {
      offline = false;
      window.CDH_OFFLINE = false;
      document.documentElement.removeAttribute("data-offline");
      window.dispatchEvent(new CustomEvent("cdh-offline", { detail: { offline: false } }));
    }
    updateBanner();
  }

  /* ------------------------------------------------------ Service Worker */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        const stale = registrations.filter((reg) => {
          try { return new URL(reg.scope).pathname !== "/"; } catch (e) { return true; }
        });
        return Promise.all(stale.map((reg) => reg.unregister().catch(() => undefined)));
      }).then(() => navigator.serviceWorker.register("/sw.js", { scope: "/" }))
        .catch(() => undefined);
    });
  }

  window.addEventListener("online", () => {
    syncPersonal().then((ok) => { if (ok) clearOffline(); else updateBanner(); });
  });
  window.addEventListener("offline", markOffline);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { updateBanner(); });
  } else {
    updateBanner();
  }
  if (!navigator.onLine) markOffline();

  window.addEventListener("cdh-offline-sync", updateBanner);
  window.CDH_OFFLINE = offline;
  window.CDH_OFFLINE_SYNC = syncPersonal;
  window.fetch = function (input, init) { return offlineFetch(input, init); };
  window.CDH_OFFLINE_STATE = { isOffline: () => offline, clear: clearAll, sync: syncPersonal };
})();
