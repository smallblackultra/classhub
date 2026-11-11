/* 班级门户首页交互
   职责：
   1. 解析 #/ 哈希路由，切换首页与模块占位页；
   2. 顶部只展示身份与个人中心链接，登录/头像统一在 /personalcenter/；
   3. 拉取 /api/news，渲染通知公告与我院新闻两栏；
   4. 按上海时区显示日期，并轮换页脚名人名言。 */
(function () {
  "use strict";

  var DATA = window.HOME_DATA || { quotes: [], placeholders: {} };
  var ROUTE_KEYS = {
    home: "home",
    activities: "activities",
    moments: "moments",
    courses: "courses",
    signup: "signup",
    dorm: "dorm",
    news: "news"
  };
  var DEFAULT_TITLE = "微电子学院 · 集成电路设计与集成系统26-1班";
  var ROLE_LABELS = {
    member: "班级成员",
    monitor: "班委",
    secretary: "团支书",
    admin: "管理员",
    superadmin: "超级管理员"
  };

  var homeView = document.querySelector('[data-view="home"]');
  var placeholderView = document.querySelector('[data-view="placeholder"]');
  var placeholderTitle = document.getElementById("placeholder-title");
  var placeholderIcon = document.querySelector("[data-placeholder-icon]");
  var accountModal = document.getElementById("account-modal");
  var guestView = document.getElementById("account-guest");
  var memberView = document.getElementById("account-member");
  var loginForm = document.getElementById("login-form");
  var loginError = document.getElementById("login-error");
  var avatarError = document.getElementById("avatar-error");
  var avatarFile = document.getElementById("avatar-file");
  var hasRendered = false;
  var account = { profile: null, busy: false, lastFocus: null };

  function byId(id) {
    return document.getElementById(id);
  }

  function currentRoute() {
    var hash = window.location.hash || "";
    if (hash.charAt(0) === "#") {
      hash = hash.slice(1);
    }
    var key = hash.replace(/^\/+|\/+$/g, "");
    if (!key) {
      return "home";
    }
    return ROUTE_KEYS[key] || "home";
  }

  function setText(id, value) {
    var node = byId(id);
    if (node) {
      node.textContent = value;
    }
  }

  function setSelectorText(selector, value) {
    var node = document.querySelector(selector);
    if (node) {
      node.textContent = value;
    }
  }

  function updateNav(route) {
    var links = document.querySelectorAll(".nav-link");
    Array.prototype.forEach.call(links, function (link) {
      if (link.getAttribute("data-route") === route) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  function renderPlaceholder(route) {
    var data = (DATA.placeholders && DATA.placeholders[route]) || {
      title: "班级服务",
      icon: "页",
      crumb: "班级服务",
      kicker: "班级服务 · 筹备中",
      summary: "这个模块的入口已经预留，具体功能将在后续版本接入。",
      status: "页面已就位 · 功能筹备中",
      planned: ["需求梳理", "数据接口", "权限与提醒", "页面上线"],
      note: "功能与数据接口将在后续版本接入。"
    };

    setText("placeholder-title", data.title);
    setSelectorText("[data-placeholder-crumb]", data.crumb || data.title);
    setSelectorText("[data-placeholder-kicker]", data.kicker || "班级服务 · 筹备中");
    setSelectorText("[data-placeholder-summary]", data.summary || "");
    setSelectorText("[data-placeholder-status]", data.status || "页面已就位 · 功能筹备中");
    setSelectorText("[data-placeholder-note]", data.note || "功能与数据接口将在后续版本接入。");

    if (placeholderIcon) {
      placeholderIcon.setAttribute("data-icon", route);
      var glyph = placeholderIcon.querySelector(".icon-glyph");
      if (glyph) {
        glyph.textContent = data.icon || "页";
      }
    }

    var list = document.querySelector("[data-placeholder-list]");
    if (list) {
      while (list.firstChild) {
        list.removeChild(list.firstChild);
      }
      (data.planned || []).forEach(function (item) {
        var li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
    }

    if (placeholderTitle) {
      try {
        placeholderTitle.focus({ preventScroll: true });
      } catch (err) {
        placeholderTitle.focus();
      }
    }
  }

  function renderRoute() {
    var route = currentRoute();
    var isHome = route === "home";

    if (homeView) {
      homeView.hidden = !isHome;
    }
    if (placeholderView) {
      placeholderView.hidden = isHome;
    }

    document.body.classList.toggle("portal-home", isHome);
    closeAccount(false);
    updateNav(route);

    if (isHome) {
      document.title = DEFAULT_TITLE;
    } else {
      renderPlaceholder(route);
      var title = DATA.placeholders && DATA.placeholders[route]
        ? DATA.placeholders[route].title
        : "班级服务";
      document.title = title + " · 微电子学院班级门户";
    }

    if (hasRendered) {
      window.scrollTo(0, 0);
    }
  }

  function shanghaiDate() {
    var now = new Date();
    try {
      var formatter = new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long"
      });
      var map = {};
      formatter.formatToParts(now).forEach(function (part) {
        map[part.type] = part.value;
      });
      var year = map.year || String(now.getFullYear());
      var month = map.month || String(now.getMonth() + 1);
      return {
        day: String(map.day || "").replace(/\D/g, "") || String(now.getDate()),
        month: /月$/.test(month) ? month : month + "月",
        year: /年$/.test(year) ? year : year + "年",
        weekday: map.weekday || ""
      };
    } catch (err) {
      var weekdays = "日一二三四五六";
      return {
        day: String(now.getDate()),
        month: (now.getMonth() + 1) + "月",
        year: now.getFullYear() + "年",
        weekday: "星期" + weekdays.charAt(now.getDay())
      };
    }
  }

  function dayOfYear() {
    try {
      var stamp = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      }).format(new Date());
      var matched = /^(\d{4})-(\d{2})-(\d{2})/.exec(stamp);
      if (matched) {
        var start = Date.UTC(Number(matched[1]), 0, 1);
        var today = Date.UTC(Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]));
        return Math.floor((today - start) / 86400000);
      }
    } catch (err) {
      /* 回退到本地日期 */
    }
    var now = new Date();
    return Math.floor((now - new Date(now.getFullYear(), 0, 1)) / 86400000);
  }

  function paintDate() {
    var date = shanghaiDate();
    setText("date-day", date.day);
    setText("date-month-year", date.year + date.month);
    setText("date-weekday", date.weekday);

    var card = document.querySelector(".date-card");
    if (card) {
      card.setAttribute(
        "aria-label",
        "今天的日期：" + date.year + date.month + date.day + "日 " + date.weekday
      );
    }
  }

  function paintQuote() {
    var quotes = DATA.quotes || [];
    if (!quotes.length) {
      return;
    }
    var quote = quotes[dayOfYear() % quotes.length];
    setText("quote-text", quote.text);
    setText("quote-author", quote.author);
  }

  function setAvatarNode(node, avatar, fallback) {
    if (!node) {
      return;
    }
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
    if (avatar) {
      var img = document.createElement("img");
      img.alt = "";
      img.decoding = "async";
      img.src = avatar;
      node.appendChild(img);
    } else {
      node.textContent = String(fallback || "访").trim().charAt(0) || "访";
    }
  }

  function setGuest() {
    var area = document.querySelector(".user-area");
    var name = byId("user-name");
    var avatar = byId("user-avatar");
    var profile = byId("profile-link");
    var chip = byId("user-chip");

    account.profile = null;
    if (area) {
      area.setAttribute("data-auth-state", "guest");
    }
    if (name) {
      name.textContent = "访客";
    }
    setAvatarNode(avatar, "", "访");
    if (profile) {
      profile.setAttribute("href", "/personalcenter/");
      profile.setAttribute("aria-label", "打开个人中心");
    }
    if (chip) {
      chip.setAttribute("aria-label", "当前访客身份，头像仅作展示");
      chip.removeAttribute("title");
    }
  }

  function formatLastLogin(value) {
    if (!value) {
      return "";
    }
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) {
      return "";
    }
    try {
      return new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      }).format(parsed).replace(/\//g, "-");
    } catch (err) {
      return "";
    }
  }

  function paintProfile(payload) {
    if (!payload || !payload.user) {
      setGuest();
      return;
    }

    account.profile = payload;
    var user = payload.user;
    var displayName = user.name || user.student_no || "同学";
    var className = payload.class && payload.class.name ? payload.class.name : "";
    var area = document.querySelector(".user-area");
    var name = byId("user-name");
    var avatar = byId("user-avatar");
    var profile = byId("profile-link");
    var chip = byId("user-chip");
    var state = user.status === "pending" ? "pending" : user.must_change_password ? "password" : "member";
    var hint = displayName;
    if (className) {
      hint += " · " + className;
    }
    if (state === "pending") {
      hint += " · 账号待审批";
    } else if (state === "password") {
      hint += " · 需修改初始密码";
    }

    if (area) {
      area.setAttribute("data-auth-state", state);
    }
    if (name) {
      name.textContent = displayName;
    }
    setAvatarNode(avatar, user.avatar, displayName);
    if (profile) {
      profile.setAttribute("href", "/personalcenter/");
      profile.setAttribute("aria-label", "打开个人中心");
    }
    if (chip) {
      chip.setAttribute("aria-label", displayName + "，" + hint + "（头像仅作展示）");
      chip.title = hint;
    }
  }

  function openAccount() {
    if (!accountModal) {
      return;
    }
    account.lastFocus = document.activeElement;
    if (account.profile) {
      if (guestView) { guestView.hidden = true; }
      if (memberView) { memberView.hidden = false; }
    } else {
      if (guestView) { guestView.hidden = false; }
      if (memberView) { memberView.hidden = true; }
    }
    accountModal.hidden = false;
    document.body.classList.add("modal-open");
    var target = account.profile ? byId("account-close") : byId("login-student");
    if (target) {
      window.setTimeout(function () { target.focus(); }, 30);
    }
  }

  function closeAccount(restoreFocus) {
    if (!accountModal || accountModal.hidden) {
      return;
    }
    accountModal.hidden = true;
    document.body.classList.remove("modal-open");
    hideError(loginError);
    hideError(avatarError);
    if (restoreFocus !== false && account.lastFocus && account.lastFocus.focus) {
      account.lastFocus.focus();
    }
    account.lastFocus = null;
  }

  function hideError(node) {
    if (node) {
      node.hidden = true;
      node.textContent = "";
    }
  }

  function showError(node, message) {
    if (!node) {
      return;
    }
    node.textContent = message;
    node.hidden = false;
  }

  function requestJson(path, options) {
    var opts = options || {};
    var headers = { Accept: "application/json" };
    var init = {
      method: opts.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: headers
    };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    if (opts.csrf) {
      var csrf = readCookie("cdh_csrf");
      if (csrf) {
        headers["X-CSRF"] = csrf;
      }
    }
    return fetch(path, init).then(function (response) {
      return response.text().then(function (text) {
        var payload = null;
        try {
          payload = text ? JSON.parse(text) : null;
        } catch (err) {
          payload = null;
        }
        if (!response.ok) {
          var message = payload && (payload.message || payload.error && payload.error.message);
          throw new Error(message || "请求失败（HTTP " + response.status + "）");
        }
        return payload;
      });
    });
  }

  function readCookie(name) {
    var prefix = name + "=";
    var parts = String(document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i += 1) {
      var part = parts[i].trim();
      if (part.indexOf(prefix) === 0) {
        return decodeURIComponent(part.slice(prefix.length));
      }
    }
    return "";
  }

  function onLogin(event) {
    event.preventDefault();
    if (account.busy) {
      return;
    }
    var student = byId("login-student");
    var password = byId("login-password");
    var submit = byId("login-submit");
    var studentNo = student ? student.value.trim() : "";
    var pass = password ? password.value : "";
    hideError(loginError);

    if (!studentNo) {
      showError(loginError, "请输入学号");
      if (student) { student.focus(); }
      return;
    }
    if (!pass) {
      showError(loginError, "请输入密码");
      if (password) { password.focus(); }
      return;
    }

    account.busy = true;
    if (submit) {
      submit.disabled = true;
      submit.textContent = "登录中…";
    }

    requestJson("/api/auth/login", {
      method: "POST",
      body: { student_no: studentNo, password: pass }
    })
      .then(function (payload) {
        paintProfile(payload);
        if (guestView) { guestView.hidden = true; }
        if (memberView) { memberView.hidden = false; }
        if (password) { password.value = ""; }
        var status = byId("account-status");
        if (status) {
          status.textContent = "登录成功 · " + (status.textContent || "已进入个人中心");
        }
        var close = byId("account-close");
        if (close) { close.focus(); }
      })
      .catch(function (err) {
        showError(loginError, err && err.message ? err.message : "登录失败，请稍后重试");
        if (password) { password.focus(); }
      })
      .then(function () {
        account.busy = false;
        if (submit) {
          submit.disabled = false;
          submit.textContent = "登录";
        }
      });
  }

  function onLogout() {
    if (account.busy) {
      return;
    }
    account.busy = true;
    requestJson("/api/auth/logout", { method: "POST" })
      .catch(function () { /* 即使请求失败，也清理本地状态 */ })
      .then(function () {
        setGuest();
        closeAccount(false);
        account.busy = false;
      });
  }

  function loadImage(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error("无法读取图片")); };
      reader.onload = function () {
        var img = new Image();
        img.onerror = function () { reject(new Error("图片格式无法识别")); };
        img.onload = function () { resolve(img); };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  function cropAvatar(image) {
    var size = 256;
    var canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);
    var side = Math.min(image.naturalWidth || image.width, image.naturalHeight || image.height);
    var sx = ((image.naturalWidth || image.width) - side) / 2;
    var sy = ((image.naturalHeight || image.height) - side) / 2;
    ctx.drawImage(image, sx, sy, side, side, 0, 0, size, size);
    return canvas.toDataURL("image/jpeg", 0.86);
  }

  function onAvatarChange(event) {
    var file = event.target && event.target.files ? event.target.files[0] : null;
    if (!file) {
      return;
    }
    hideError(avatarError);
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
      showError(avatarError, "请选择 PNG、JPEG 或 WebP 图片");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      showError(avatarError, "图片不能超过 8 MB");
      return;
    }
    var button = byId("avatar-choose");
    if (button) {
      button.disabled = true;
      button.textContent = "处理中…";
    }

    loadImage(file)
      .then(function (image) {
        var dataUrl = cropAvatar(image);
        return requestJson("/api/auth/avatar", {
          method: "POST",
          csrf: true,
          body: { avatar: dataUrl }
        }).then(function (result) {
          if (account.profile && account.profile.user) {
            account.profile.user.avatar = result && result.avatar ? result.avatar : dataUrl;
            paintProfile(account.profile);
            setText("account-status", "头像已更新 · 已保存到班级账号");
          }
        });
      })
      .catch(function (err) {
        showError(avatarError, err && err.message ? err.message : "头像上传失败，请稍后重试");
      })
      .then(function () {
        if (button) {
          button.disabled = false;
          button.textContent = "更换头像";
        }
        if (avatarFile) {
          avatarFile.value = "";
        }
      });
  }

  function safeNewsUrl(raw) {
    try {
      var url = new URL(String(raw || ""), window.location.href);
      if (url.protocol !== "https:" || url.hostname.toLowerCase() !== "wdzxy.hfut.edu.cn") {
        return "";
      }
      return url.href;
    } catch (err) {
      return "";
    }
  }

  function newsDate(value) {
    var matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    return matched ? matched[2] + "-" + matched[3] : "";
  }

  function newsUpdated(value) {
    if (!value) {
      return "";
    }
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) {
      return "";
    }
    try {
      return new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      }).format(parsed).replace(/\//g, "-");
    } catch (err) {
      return "";
    }
  }

  function setNewsMessage(list, message) {
    if (!list) {
      return;
    }
    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }
    var note = document.createElement("p");
    note.className = "news-empty";
    note.textContent = message;
    list.appendChild(note);
  }

  function renderNewsColumn(key, items) {
    var list = document.querySelector('[data-news-column="' + key + '"]');
    if (!list) {
      return 0;
    }
    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }
    var rendered = 0;
    (Array.isArray(items) ? items : []).forEach(function (item) {
      if (rendered >= 3) {
        return;
      }
      var url = safeNewsUrl(item && item.url);
      var title = item && item.title ? String(item.title).trim().replace(/\s+/g, " ") : "";
      if (!url || !title) {
        return;
      }
      var article = document.createElement("article");
      article.className = "news-item";

      var meta = document.createElement("div");
      meta.className = "news-meta";
      var time = document.createElement("time");
      var dateText = newsDate(item.published_at);
      if (dateText) {
        time.dateTime = item.published_at;
        time.textContent = dateText;
      } else {
        time.textContent = "学院官网";
      }
      meta.appendChild(time);

      var link = document.createElement("a");
      link.className = "news-title";
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = title;

      article.appendChild(meta);
      article.appendChild(link);
      list.appendChild(article);
      rendered += 1;
    });
    if (!rendered) {
      setNewsMessage(list, "暂无条目");
    }
    return rendered;
  }

  function paintNews(payload) {
    var panel = byId("news-panel");
    var updated = document.querySelector("[data-news-updated]");
    var data = payload && payload.items ? payload.items : {};
    var count = renderNewsColumn("notice", data.notice) + renderNewsColumn("news", data.news);
    var enabled = !payload || payload.enabled !== false;

    if (!enabled) {
      if (panel) { panel.setAttribute("data-news-state", "error"); }
      if (updated) { updated.textContent = "资讯同步未启用"; }
      return;
    }

    if (!count) {
      if (panel) { panel.setAttribute("data-news-state", "error"); }
      if (updated) { updated.textContent = "学院官网暂时无法读取"; }
      return;
    }

    var stale = Boolean(payload.stale);
    if (panel) {
      panel.setAttribute("data-news-state", stale ? "stale" : "ready");
      panel.title = payload.error ? String(payload.error).slice(0, 300) : "";
    }
    if (updated) {
      var stamp = newsUpdated(payload.updated_at);
      updated.textContent = stamp
        ? (stale ? "上次更新 " : "更新于 ") + stamp
        : "来自学院官网";
    }
  }

  function initNews() {
    if (!window.fetch) {
      return;
    }
    fetch("/api/news?limit=3", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" }
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (payload) {
        paintNews(payload);
      })
      .catch(function () {
        paintNews({ enabled: true, items: {}, stale: true });
      });
  }

  function initAuth() {
    if (!window.fetch) {
      return;
    }
    fetch("/api/auth/me", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" }
    })
      .then(function (response) {
        if (!response.ok) {
          return null;
        }
        return response.json();
      })
      .then(function (payload) {
        paintProfile(payload);
      })
      .catch(function () {
        setGuest();
      });
  }

  function initHeader() {
    var header = document.querySelector("[data-header]");
    if (!header) {
      return;
    }
    function onScroll() {
      header.classList.toggle("is-scrolled", window.scrollY > 8);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function initAccount() {
    var profile = byId("profile-link");
    var chip = byId("user-chip");
    var close = byId("account-close");
    var logout = byId("account-logout");
    var choose = byId("avatar-choose");
    if (profile) { profile.addEventListener("click", openAccount); }
    if (chip) { chip.addEventListener("click", openAccount); }
    if (close) { close.addEventListener("click", function () { closeAccount(); }); }
    if (logout) { logout.addEventListener("click", onLogout); }
    if (choose && avatarFile) {
      choose.addEventListener("click", function () { avatarFile.click(); });
      avatarFile.addEventListener("change", onAvatarChange);
    }
    if (loginForm) { loginForm.addEventListener("submit", onLogin); }
    if (accountModal) {
      accountModal.addEventListener("click", function (event) {
        var target = event.target;
        if (target && target.getAttribute && target.getAttribute("data-account-close") !== null) {
          closeAccount();
        }
      });
    }
    document.addEventListener("keydown", function (event) {
      if (!accountModal || accountModal.hidden) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeAccount();
      }
    });
  }

  function init() {
    renderRoute();
    hasRendered = true;
    window.addEventListener("hashchange", renderRoute);
    paintDate();
    paintQuote();
    initHeader();
    initNews();
    initAuth();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
