/* 个人中心：门户与 DDL 共用账号、头像、个人待办与工具入口 */
(function () {
  "use strict";

  var ROLE_LABELS = {
    member: "班级成员",
    monitor: "班委",
    secretary: "团支书",
    admin: "管理员",
    superadmin: "超级管理员"
  };

  var state = {
    me: null,
    todos: [],
    counts: { open: 0, done: 0, total: 0 },
    busy: false
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function showError(node, message) {
    if (!node) {
      return;
    }
    node.textContent = message || "请求失败，请稍后再试。";
    node.hidden = false;
  }

  function clearError(node) {
    if (!node) {
      return;
    }
    node.textContent = "";
    node.hidden = true;
  }

  function setBusy(button, busy, text) {
    if (!button) {
      return;
    }
    if (!button.getAttribute("data-label")) {
      button.setAttribute("data-label", button.textContent);
    }
    button.disabled = Boolean(busy);
    button.textContent = busy ? (text || "处理中…") : button.getAttribute("data-label");
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

  function api(path, options) {
    var opts = options || {};
    var method = opts.method || "GET";
    var headers = { Accept: "application/json" };
    var init = {
      method: method,
      credentials: "same-origin",
      cache: "no-store",
      headers: headers
    };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    if (opts.csrf !== false && method !== "GET") {
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
          var error = new Error(
            (payload && (payload.message || (payload.error && payload.error.message))) ||
            "请求失败（HTTP " + response.status + "）"
          );
          error.status = response.status;
          error.payload = payload;
          throw error;
        }
        return payload;
      });
    });
  }

  function initials(name) {
    var text = String(name || "访").trim();
    return text ? text.charAt(0) : "访";
  }

  function setAvatar(node, avatar, name) {
    if (!node) {
      return;
    }
    if (avatar) {
      var img = document.createElement("img");
      img.src = avatar;
      img.alt = "";
      node.textContent = "";
      node.appendChild(img);
    } else {
      node.textContent = initials(name);
    }
  }

  function lastLoginText(value) {
    if (!value) {
      return "已登录";
    }
    var date = new Date(value);
    if (isNaN(date.getTime())) {
      return "已登录";
    }
    try {
      var text = new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      }).format(date);
      return "上次登录 " + text.replace(/\//g, "-");
    } catch (err) {
      return "已登录";
    }
  }

  function renderGuest(message) {
    state.me = null;
    byId("pc-loading").hidden = true;
    byId("pc-guest").hidden = false;
    byId("pc-account").hidden = true;
    if (message) {
      showError(byId("pc-login-error"), message);
    }
  }

  function renderAccount() {
    var me = state.me;
    if (!me || !me.user) {
      renderGuest();
      return;
    }
    var user = me.user;
    var cls = me.class || {};
    var committee = Boolean(me.permissions && me.permissions.committee);
    var admin = user.role === "admin";
    var pending = user.status === "pending";
    var mustChange = Boolean(user.must_change_password);

    byId("pc-loading").hidden = true;
    byId("pc-guest").hidden = true;
    byId("pc-account").hidden = false;

    byId("pc-name").textContent = user.name || user.student_no || "同学";
    byId("pc-role").textContent = ROLE_LABELS[user.role] || "班级成员";
    var meta = [];
    if (user.student_no) {
      meta.push(user.student_no);
    }
    if (cls.name) {
      meta.push(cls.name);
    }
    byId("pc-meta").textContent = meta.join(" · ") || "班级成员";
    byId("pc-status").textContent = pending
      ? "账号待班委审批"
      : mustChange
        ? "首次登录，请先修改初始密码"
        : lastLoginText(user.last_login_at);

    byId("pc-pending-notice").hidden = !pending;
    byId("pc-password-notice").hidden = !mustChange;
    byId("pc-student-no").textContent = user.student_no || "—";
    byId("pc-class").textContent = cls.name || "—";
    byId("pc-college").textContent = cls.college || "—";
    byId("pc-major").textContent = cls.major || "—";
    byId("pc-grade").textContent = cls.grade || "—";

    var inviteWrap = byId("pc-invite-wrap");
    if (committee && cls.invite_code) {
      inviteWrap.hidden = false;
      byId("pc-invite").textContent = cls.invite_code;
    } else {
      inviteWrap.hidden = true;
    }

    byId("pc-unread").textContent = (me.unread_notifications || 0) + " 条未读";
    byId("pc-drafts").textContent = (me.pending_drafts || 0) + " 份";
    byId("pc-drafts-link").hidden = !committee;
    byId("pc-ingest-link").hidden = !committee;
    byId("pc-reports-link").hidden = !committee;
    byId("pc-admin-link").hidden = !committee;
    byId("pc-global-link").hidden = !admin;

    setAvatar(byId("pc-avatar"), user.avatar || "", user.name);
  }

  function renderTodos() {
    var list = byId("pc-todo-list");
    var count = byId("pc-todo-count");
    list.textContent = "";
    if (count) {
      count.textContent = state.counts.open + " 项未完成";
    }
    if (!state.todos.length) {
      var empty = document.createElement("li");
      empty.className = "pc-empty";
      empty.textContent = "还没有个人待办，先写下一件要做的事。";
      list.appendChild(empty);
      return;
    }
    state.todos.forEach(function (item) {
      var li = document.createElement("li");
      li.className = "pc-todo-item" + (item.done ? " is-done" : "");

      var check = document.createElement("button");
      check.type = "button";
      check.className = "pc-check";
      check.setAttribute("aria-label", item.done ? "标记为未完成" : "标记为已完成");
      check.textContent = item.done ? "✓" : "";
      check.addEventListener("click", function () {
        toggleTodo(item);
      });
      li.appendChild(check);

      var main = document.createElement("div");
      var title = document.createElement("div");
      title.className = "pc-todo-title";
      title.textContent = item.title;
      main.appendChild(title);
      if (item.due_local || item.due_at) {
        var due = document.createElement("div");
        due.className = "pc-todo-due";
        due.textContent = formatDue(item.due_local || item.due_at);
        main.appendChild(due);
      }
      li.appendChild(main);

      var del = document.createElement("button");
      del.type = "button";
      del.className = "pc-del";
      del.setAttribute("aria-label", "删除待办");
      del.textContent = "×";
      del.addEventListener("click", function () {
        deleteTodo(item);
      });
      li.appendChild(del);
      list.appendChild(li);
    });
  }

  function formatDue(value) {
    if (!value) {
      return "";
    }
    var date = new Date(value);
    if (isNaN(date.getTime())) {
      return String(value);
    }
    try {
      return new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      }).format(date).replace(/\//g, "-");
    } catch (err) {
      return String(value);
    }
  }

  function setTodoBusy(busy) {
    state.busy = busy;
    byId("pc-todo-title-input").disabled = busy;
    byId("pc-todo-due").disabled = busy;
    var submit = byId("pc-todo-form").querySelector("button[type=submit]");
    if (submit) {
      submit.disabled = busy;
      submit.textContent = busy ? "保存中…" : "添加";
    }
  }

  function loadTodos() {
    return api("/api/personal?done=all", { csrf: false })
      .then(function (payload) {
        state.todos = (payload && payload.items) || [];
        state.counts = (payload && payload.counts) || { open: 0, done: 0, total: state.todos.length };
        renderTodos();
      })
      .catch(function (error) {
        if (error.status === 401) {
          renderGuest("登录状态已过期，请重新登录。");
          return;
        }
        showError(byId("pc-todo-error"), error.message);
      });
  }

  function toggleTodo(item) {
    if (state.busy) {
      return;
    }
    state.busy = true;
    api("/api/personal/" + item.id, { method: "PATCH", body: { done: !item.done } })
      .then(loadTodos)
      .catch(function (error) {
        showError(byId("pc-todo-error"), error.message);
      })
      .then(function () {
        state.busy = false;
      });
  }

  function deleteTodo(item) {
    if (state.busy) {
      return;
    }
    state.busy = true;
    api("/api/personal/" + item.id, { method: "DELETE" })
      .then(loadTodos)
      .catch(function (error) {
        showError(byId("pc-todo-error"), error.message);
      })
      .then(function () {
        state.busy = false;
      });
  }

  function syncTodoDueState() {
    var input = byId("pc-todo-due");
    if (!input) return;
    input.classList.toggle("has-value", Boolean(input.value));
  }

  function createTodo(event) {
    event.preventDefault();
    clearError(byId("pc-todo-error"));
    var title = byId("pc-todo-title-input").value.trim();
    if (!title) {
      showError(byId("pc-todo-error"), "请填写待办内容。");
      byId("pc-todo-title-input").focus();
      return;
    }
    var dueValue = byId("pc-todo-due").value;
    var body = { title: title };
    if (dueValue) {
      var due = new Date(dueValue);
      if (isNaN(due.getTime())) {
        showError(byId("pc-todo-error"), "截止时间格式不正确。");
        return;
      }
      body.due_at = due.toISOString();
    }
    setTodoBusy(true);
    api("/api/personal", { method: "POST", body: body })
      .then(function () {
        byId("pc-todo-title-input").value = "";
        byId("pc-todo-due").value = "";
        syncTodoDueState();
        return loadTodos();
      })
      .catch(function (error) {
        showError(byId("pc-todo-error"), error.message);
      })
      .then(function () {
        setTodoBusy(false);
      });
  }

  function loadState() {
    byId("pc-loading").hidden = false;
    return api("/api/auth/me", { csrf: false })
      .then(function (payload) {
        state.me = payload;
        renderAccount();
        return loadTodos();
      })
      .catch(function (error) {
        if (error.status === 401) {
          renderGuest();
          return;
        }
        renderGuest(error.message);
      });
  }

  function login(event) {
    event.preventDefault();
    clearError(byId("pc-login-error"));
    var studentNo = byId("pc-student").value.trim();
    var password = byId("pc-password").value;
    if (!studentNo) {
      showError(byId("pc-login-error"), "请输入学号。");
      byId("pc-student").focus();
      return;
    }
    if (!password) {
      showError(byId("pc-login-error"), "请输入密码。");
      byId("pc-password").focus();
      return;
    }
    var button = byId("pc-login-submit");
    setBusy(button, true, "登录中…");
    api("/api/auth/login", {
      method: "POST",
      csrf: false,
      body: { student_no: studentNo, password: password }
    })
      .then(function (profile) {
        state.me = profile;
        byId("pc-password").value = "";
        renderAccount();
        if (profile.user && profile.user.must_change_password) {
          byId("pc-old-password").focus();
        }
        return loadTodos();
      })
      .catch(function (error) {
        showError(byId("pc-login-error"), error.message || "学号或密码不正确。");
      })
      .then(function () {
        setBusy(button, false);
      });
  }

  function logout() {
    var button = byId("pc-logout");
    setBusy(button, true, "退出中…");
    api("/api/auth/logout", { method: "POST", csrf: false })
      .catch(function () {
        /* 即使请求失败，也回到未登录状态，服务端会话会自然过期 */
      })
      .then(function () {
        state.me = null;
        state.todos = [];
        state.counts = { open: 0, done: 0, total: 0 };
        renderGuest();
        setBusy(button, false);
      });
  }

  function paintAvatar(avatar) {
    if (state.me && state.me.user) {
      state.me.user.avatar = avatar || "";
      setAvatar(byId("pc-avatar"), state.me.user.avatar, state.me.user.name);
    }
  }

  function readImage(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error("无法读取图片。")); };
      reader.onload = function () {
        var image = new Image();
        image.onerror = function () { reject(new Error("图片格式无法识别。")); };
        image.onload = function () { resolve(image); };
        image.src = String(reader.result || "");
      };
      reader.readAsDataURL(file);
    });
  }

  function cropAvatar(image) {
    var size = 256;
    var canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    var context = canvas.getContext("2d");
    var sourceWidth = image.naturalWidth || image.width;
    var sourceHeight = image.naturalHeight || image.height;
    var side = Math.min(sourceWidth, sourceHeight);
    var sx = (sourceWidth - side) / 2;
    var sy = (sourceHeight - side) / 2;
    context.drawImage(image, sx, sy, side, side, 0, 0, size, size);
    var quality = 0.86;
    var dataUrl = canvas.toDataURL("image/jpeg", quality);
    while (dataUrl.length > 380000 && quality > 0.5) {
      quality -= 0.08;
      dataUrl = canvas.toDataURL("image/jpeg", quality);
    }
    return dataUrl;
  }

  function avatarChanged(event) {
    var input = event.target;
    var file = input.files && input.files[0];
    input.value = "";
    if (!file) {
      return;
    }
    clearError(byId("pc-avatar-error"));
    if (!/^image\/(png|jpeg|webp)$/i.test(file.type)) {
      showError(byId("pc-avatar-error"), "请选择 PNG、JPEG 或 WebP 图片。");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      showError(byId("pc-avatar-error"), "图片不能超过 8 MB。");
      return;
    }
    var button = byId("pc-avatar-button");
    button.disabled = true;
    readImage(file)
      .then(function (image) {
        return cropAvatar(image);
      })
      .then(function (dataUrl) {
        return api("/api/auth/avatar", { method: "POST", body: { avatar: dataUrl } });
      })
      .then(function (payload) {
        paintAvatar(payload && payload.avatar ? payload.avatar : "");
        byId("pc-status").textContent = "头像已更新";
      })
      .catch(function (error) {
        showError(byId("pc-avatar-error"), error.message);
      })
      .then(function () {
        button.disabled = false;
      });
  }

  function changePassword(event) {
    event.preventDefault();
    clearError(byId("pc-password-error"));
    byId("pc-password-ok").hidden = true;
    var oldPassword = byId("pc-old-password").value;
    var newPassword = byId("pc-new-password").value;
    var confirmPassword = byId("pc-confirm-password").value;
    if (!oldPassword) {
      showError(byId("pc-password-error"), "请输入原密码。");
      return;
    }
    if (newPassword.length < 8) {
      showError(byId("pc-password-error"), "新密码至少 8 位。");
      return;
    }
    if (newPassword !== confirmPassword) {
      showError(byId("pc-password-error"), "两次输入的新密码不一致。");
      return;
    }
    var button = byId("pc-password-form").querySelector("button[type=submit]");
    setBusy(button, true, "保存中…");
    api("/api/auth/change-password", {
      method: "POST",
      body: { old_password: oldPassword, new_password: newPassword }
    })
      .then(function () {
        byId("pc-old-password").value = "";
        byId("pc-new-password").value = "";
        byId("pc-confirm-password").value = "";
        byId("pc-password-ok").hidden = false;
        if (state.me && state.me.user) {
          state.me.user.must_change_password = false;
        }
        byId("pc-password-notice").hidden = true;
        byId("pc-status").textContent = "密码已更新";
      })
      .catch(function (error) {
        showError(byId("pc-password-error"), error.message);
      })
      .then(function () {
        setBusy(button, false);
      });
  }

  function init() {
    byId("pc-login-form").addEventListener("submit", login);
    byId("pc-todo-form").addEventListener("submit", createTodo);
    byId("pc-todo-due").addEventListener("input", syncTodoDueState);
    byId("pc-todo-due").addEventListener("change", syncTodoDueState);
    syncTodoDueState();
    byId("pc-avatar-button").addEventListener("click", function () {
      byId("pc-avatar-file").click();
    });
    byId("pc-avatar-file").addEventListener("change", avatarChanged);
    byId("pc-logout").addEventListener("click", logout);
    byId("pc-password-form").addEventListener("submit", changePassword);

    loadState();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
