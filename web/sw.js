/* 班级门户根 Service Worker：首页、个人中心、DDL 查询共用一个 PWA 外壳。
 * 接口数据不由 SW 缓存，交给 assets/offline.js 按账号保存，避免串号。
 */
const VERSION = "classhub-shell-v28";
const IS_ROOT = (() => {
  try { return new URL(self.registration.scope).pathname === "/"; }
  catch (e) { return false; }
})();

if (!IS_ROOT) {
  // 旧版 /daliy/sw.js 只覆盖 DDL。它活着会挡住根 SW 接管 /daliy/，
  // 因此旧 scope 的 SW 只负责注销自己；页面重新加载后由 /sw.js 接管。
  self.addEventListener("install", () => self.skipWaiting());
  self.addEventListener("activate", (event) => {
    event.waitUntil(self.registration.unregister().then(() => self.clients.claim()));
  });
} else {
  const SHELL = [
    "/",
    "/personalcenter/",
    "/daliy/",
    "/manifest.webmanifest",
    "/assets/home.css?v=20261111f",
    "/assets/home.js?v=20261111f",
    "/assets/home-data.js?v=20261111f",
    "/assets/offline.js?v=20261112a",
    "/assets/home/campus.jpg?v=20261111f",
    "/assets/home/brand.png",
    "/assets/home/logo.png",
    "/assets/home/favicon.png",
    "/assets/personalcenter.css?v=20261111f",
    "/assets/personalcenter.js?v=20261111f",
    "/assets/icons/icon-192.png",
    "/assets/icons/icon-512.png",
    "/assets/icons/icon-maskable-512.png",
    "/assets/icons/apple-touch-icon.png",
    "/daliy/assets/app.css?v=20261111h",
    "/daliy/assets/util.js?v=20261116",
    "/daliy/assets/offline.js?v=20261112a",
    "/daliy/assets/api.js?v=20261112a",
    "/daliy/assets/components.js?v=20261111a",
    "/daliy/assets/bookmarklet.js?v=20261116",
    "/daliy/assets/app.js?v=20261111j",
    "/daliy/assets/views/login.js?v=20261111j",
    "/daliy/assets/views/list.js?v=20261111f",
    "/daliy/assets/views/detail.js?v=20261116",
    "/daliy/assets/views/editor.js?v=20261116",
    "/daliy/assets/views/drafts.js?v=20261116",
    "/daliy/assets/views/ingest.js?v=20261116",
    "/daliy/assets/views/admin.js?v=20261116",
    "/daliy/assets/views/profile.js?v=20261111a",
    "/daliy/assets/views/notifications.js?v=20261116",
    "/daliy/assets/views/reports.js?v=20261116",
    "/daliy/assets/views/personal.js?v=20261116",
    "/daliy/assets/views/global.js?v=20261116",
    "/daliy/vendor/preact.umd.js?v=20261116",
    "/daliy/vendor/hooks.umd.js?v=20261116",
    "/daliy/vendor/htm.umd.js?v=20261116"
  ];

  self.addEventListener("install", (event) => {
    event.waitUntil((async () => {
      const cache = await caches.open(VERSION);
      await Promise.all(SHELL.map((url) =>
        cache.add(new Request(url, { cache: "reload" })).catch(() => undefined)
      ));
      await self.skipWaiting();
    })());
  });

  self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key)));
      await self.clients.claim();
    })());
  });

  async function navigationFallback(pathname) {
    const cache = await caches.open(VERSION);
    if (pathname.startsWith("/personalcenter")) return (await cache.match("/personalcenter/")) || (await cache.match("/"));
    if (pathname.startsWith("/daliy") || pathname.startsWith("/daily")) return (await cache.match("/daliy/")) || (await cache.match("/"));
    return (await cache.match("/")) || (await cache.match("/daliy/"));
  }

  self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") return;
    const target = new URL(request.url);
    if (target.origin !== self.location.origin) return;

    // 接口交给页面里的离线层处理；SW 不缓存带账号的数据。
    if (target.pathname.includes("/api/")) return;

    if (request.mode === "navigate" || (request.headers.get("accept") || "").includes("text/html")) {
      event.respondWith((async () => {
        try {
          const response = await fetch(request);
          if (response && response.ok) {
            const cache = await caches.open(VERSION);
            cache.put(request, response.clone()).catch(() => undefined);
          }
          return response;
        } catch (e) {
          return (await navigationFallback(target.pathname)) ||
            new Response("<h1>离线</h1><p>这个页面还没有缓存，请联网后打开一次。</p>", {
              status: 200, headers: { "Content-Type": "text/html; charset=utf-8" }
            });
        }
      })());
      return;
    }

    const isStatic = target.pathname.startsWith("/assets/") ||
      target.pathname.startsWith("/daliy/assets/") ||
      target.pathname.startsWith("/daliy/vendor/") ||
      target.pathname === "/manifest.webmanifest";
    if (!isStatic) return;

    event.respondWith((async () => {
      const cache = await caches.open(VERSION);
      // 忽略 ?v= 查询串：页面升级版本号后仍能命中上一版缓存的文件。
      const hit = await cache.match(request, { ignoreSearch: true });
      if (hit) {
        fetch(request).then((response) => {
          if (response && response.ok) cache.put(request, response.clone()).catch(() => undefined);
        }).catch(() => undefined);
        return hit;
      }
      try {
        const response = await fetch(request);
        if (response && response.ok) cache.put(request, response.clone()).catch(() => undefined);
        return response;
      } catch (e) {
        return new Response("", { status: 504, statusText: "Offline" });
      }
    })());
  });

  self.addEventListener("message", (event) => {
    if (event.data === "SKIP_WAITING") self.skipWaiting();
  });
}
