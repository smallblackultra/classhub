/* 通用组件 */
(function () {
  "use strict";
  const { h, Fragment, html, icon } = window.U;
  const { useState, useEffect, useRef } = window.preactHooks;
  const { render } = window.preact;

  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }

  function Button(props) {
    const cls = cx("btn", props.variant, props.size, props.block && "block");
    return html`<button type=${props.type || "button"} class=${cls}
      disabled=${!!(props.disabled || props.loading)} title=${props.title || ""}
      onClick=${props.onClick}>
      ${props.loading
        ? html`<span class="spinner" style="width:14px;height:14px;border-width:2px"></span>`
        : (props.icon ? icon(props.icon) : null)}
      ${props.children}
    </button>`;
  }

  function IconBtn(props) {
    return html`<button type="button" class="icon-btn" title=${props.title || props.label || ""}
      aria-label=${props.label || props.title || ""} onClick=${props.onClick}>${icon(props.icon)}</button>`;
  }

  function Field(props) {
    return html`<label class="field">
      ${props.label ? html`<span class="field-label">${props.label}${props.required ? html`<i class="req">*</i>` : null}</span>` : null}
      ${props.children}
      ${props.hint ? html`<span class="field-hint">${props.hint}</span>` : null}
      ${props.error ? html`<span class="field-error">${props.error}</span>` : null}
    </label>`;
  }

  function Badge(props) {
    return html`<span class=${cx("badge", props.tone, props.dot && "dot")}>${props.children}</span>`;
  }

  function Chip(props) {
    return html`<button type="button" class="chip" data-on=${props.on ? "1" : "0"} onClick=${props.onClick}>
      ${props.children}${props.count != null ? html`<span class="count">${props.count}</span>` : null}
    </button>`;
  }

  function Seg(props) {
    return html`<div class="seg">${props.items.map((it) =>
      html`<button type="button" data-on=${props.value === it.key ? "1" : "0"}
        onClick=${() => props.onChange(it.key)}>${it.label}</button>`)}</div>`;
  }

  function Tabs(props) {
    return html`<div class="tabs">${props.items.map((it) =>
      html`<button type="button" data-on=${props.value === it.key ? "1" : "0"}
        onClick=${() => props.onChange(it.key)}>${it.label}</button>`)}</div>`;
  }

  function Avatar(props) {
    return html`<span class=${cx("avatar", props.size === "small" && "small")}
      title=${props.name || ""}>${props.avatar
        ? html`<img src=${props.avatar} alt="" loading="lazy" />`
        : window.U.initials(props.name)}</span>`;
  }

  function Stat(props) {
    return html`<div class=${cx("stat", props.tone)} onClick=${props.onClick}
      style=${props.onClick ? "cursor:pointer" : ""}>
      <div class="num">${props.num}</div>
      <div class="lbl">${props.label}</div>
    </div>`;
  }

  function Modal(props) {
    useEffect(() => {
      if (!props.open) return;
      const onKey = (e) => { if (e.key === "Escape") props.onClose && props.onClose(); };
      document.addEventListener("keydown", onKey);
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
    }, [props.open]);
    if (!props.open) return null;
    return html`<div class="overlay" onMouseDown=${(e) => {
        if (e.target === e.currentTarget && props.onClose) props.onClose();
      }}>
      <div class="modal" role="dialog" aria-modal="true"
        style=${props.wide ? "max-width:640px" : ""}>
        <div class="modal-head">
          <div class="modal-title">${props.title || ""}</div>
          <${IconBtn} icon="close" label="关闭" onClick=${props.onClose} />
        </div>
        <div class="modal-body">${props.children}</div>
        ${props.footer ? html`<div class="modal-foot">${props.footer}</div>` : null}
      </div>
    </div>`;
  }

  function DateField(props) {
    const ref = useRef(null);
    const shown = String(props.value || "").replace(/-/g, "/");
    function openPicker() {
      const el = ref.current;
      if (!el) return;
      try {
        if (el.showPicker) el.showPicker();
        else { el.focus(); el.click(); }
      } catch (err) { el.focus(); }
    }
    return html`<div class=${"date-field input" + (props.className ? " " + props.className : "")}
        style=${props.style || ""} role="button" tabindex="0"
        aria-label=${props.label || "选择日期"}
        onClick=${openPicker}
        onKeyDown=${(e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPicker(); }
        }}>
      <span class=${props.value ? "date-text" : "date-text date-ph"}>${props.value ? shown : (props.placeholder || "年/月/日")}</span>
      ${icon("calendar")}
      <input ref=${ref} type="date" tabindex="-1" value=${props.value || ""} aria-hidden="true"
        onInput=${(e) => props.onChange && props.onChange(e.target.value)} />
    </div>`;
  }

  function Empty(props) {
    return html`<div class="empty">
      <div class="empty-icon">${icon(props.icon || "inbox")}</div>
      <div class="empty-title">${props.title || "暂无内容"}</div>
      ${props.hint ? html`<div class="empty-hint">${props.hint}</div>` : null}
      ${props.children}
    </div>`;
  }

  function Note(props) {
    return html`<div class=${cx("note", props.tone)}>
      ${icon(props.icon || (props.tone === "err" ? "alert" : "alert"))}
      <div class="grow">${props.children}</div>
    </div>`;
  }

  function Spinner(props) {
    return html`<span class=${cx("spinner", props.dark && "dark")}></span>`;
  }

  function copyIconSvg() { return html`${icon("copy")}`; }

  function CopyBtn(props) {
    const [done, setDone] = useState(false);
    return html`<button type="button" class=${cx("btn", props.variant || "ghost", props.size || "sm")}
      onClick=${() => {
        window.U.copyText(props.text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        }).catch(() => window.API.toast("复制失败，请手动选择", "err"));
      }}>
      ${done ? icon("check") : icon("copy")}<span>${done ? "已复制" : (props.label || "复制")}</span>
    </button>`;
  }

  function Progress(props) {
    return html`<div class="progress"><i style=${"width:" + Math.max(0, Math.min(100, props.value || 0)) + "%"}></i></div>`;
  }

  function Page(props) {
    return html`<div class="shell"><div class=${"page" + (props.narrow ? " narrow" : "")} key=${props.key || ""}>${props.children}</div></div>`;
  }

  function PageHead(props) {
    return html`<div style="display:flex;align-items:flex-start;gap:10px;margin:10px 0 16px">
      ${props.back ? html`<button type="button" class="icon-btn" style="margin-top:4px"
        aria-label="返回" onClick=${props.back}>${icon("back")}</button>` : null}
      <div class="grow">
        <div style="font-size:21px;font-weight:750;letter-spacing:-.4px;line-height:1.25">${props.title}</div>
        ${props.sub ? html`<div class="small muted" style="margin-top:3px">${props.sub}</div>` : null}
      </div>
      ${props.actions ? html`<div class="row-flex" style="margin-top:2px">${props.actions}</div>` : null}
    </div>`;
  }

  function LoadingList(props) {
    const n = props.rows || 4;
    return html`<div class="stack" aria-busy="true">
      ${Array.from({ length: n }).map(() => html`<div class="skel skel-row"></div>`)}
    </div>`;
  }

  function ErrorView(props) {
    return html`<${Empty} icon="alert" title="加载失败"
      hint=${(props.err && (props.err.message || props.err.code)) || "请稍后重试"}>
      ${props.retry ? html`<${Button} size="sm" variant="soft" onClick=${props.retry}>重试</${Button}>` : null}
    </${Empty}>`;
  }

  /* 通用数据请求 hook：path 变化或 reload() 时重取 */
  function useApi(path, deps) {
    const [state, setState] = useState({ loading: true, data: null, error: null });
    const [nonce, setNonce] = useState(0);
    useEffect(() => {
      if (!path) return;
      let alive = true;
      setState((s) => ({ loading: true, data: s.data, error: null }));
      window.API.api.get(path)
        .then((data) => { if (alive) setState({ loading: false, data, error: null }); })
        .catch((error) => { if (alive) setState({ loading: false, data: null, error }); });
      return () => { alive = false; };
    }, [path, nonce].concat(deps || []));
    return { loading: state.loading, data: state.data, error: state.error,
             reload: () => setNonce((n) => n + 1) };
  }

  /* Promise 化的确认弹窗 */
  function confirmDialog(opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      const host = document.createElement("div");
      document.body.appendChild(host);
      const close = (val) => {
        try { render(null, host); } catch (e) { /* ignore */ }
        host.remove();
        resolve(val);
      };
      const App = () => html`<${Modal} open title=${opts.title || "确认操作"} onClose=${() => close(false)}
        footer=${html`<${Button} variant="ghost" onClick=${() => close(false)}>取消</${Button}>
          <${Button} variant=${opts.danger ? "danger-soft" : "primary"} onClick=${() => close(true)}>
            ${opts.okText || "确定"}</${Button}>`}>
        <div class="muted" style="font-size:14px;line-height:1.6">${opts.body || ""}</div>
      </${Modal}>`;
      render(html`<${App} />`, host);
    });
  }

  window.CDH = window.CDH || {};
  window.CDH.ui = {
    Button, IconBtn, Field, DateField, Badge, Chip, Seg, Tabs, Avatar, Stat, Modal, Empty, Note,
    Spinner, CopyBtn, Progress, Page, PageHead, LoadingList, ErrorView, useApi, confirmDialog,
    copyIconSvg,
  };
})();
