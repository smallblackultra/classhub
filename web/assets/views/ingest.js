/* 消息导入：粘贴 / 书签 / QQ 机器人 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState } = window.preactHooks;
  const { Button, Page, PageHead, Field, Tabs, Note, CopyBtn, Badge, Empty } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  const SAMPLE = `@班级小助手 学院通知：请各班班长于本周五（11月7日）17:00 前，将《心理健康普查表》收齐后交到学院 305 办公室，电子版发至 xlzx@example.edu.cn。`;

  function PasteTab() {
    const S = API.useStore();
    const meta = S.meta || {};
    const [form, setForm] = useState({
      content: "",
      sender_name: "辅导员",
      chat_name: "计科2301班委群",
      use_ai: !!(meta.ai_enabled),
    });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [result, setResult] = useState(null);

    async function submit(e) {
      e.preventDefault();
      if (busy) return;
      if (!form.content.trim()) return setError("请粘贴消息内容");
      setBusy(true); setError(null); setResult(null);
      try {
        const r = await API.api.post("/api/ingest/paste", {
          content: form.content.trim(),
          sender_name: form.sender_name.trim(),
          chat_name: form.chat_name.trim(),
          use_ai: !!form.use_ai,
        });
        setResult(r);
        API.bump();
        API.toast("已生成 " + (r.drafts || []).length + " 条草稿", "ok");
      } catch (err) {
        setError(err.message || "抽取失败");
      } finally {
        setBusy(false);
      }
    }

    return html`<div>
      <${Note} tone="info" icon="sparkles">
        ${meta.ai_enabled
          ? "已配置大模型：会先尝试 AI 抽取，失败时自动回退到规则解析。"
          : "当前未配置大模型（设置 CDH_AI_API_KEY 即可启用），先用规则解析：识别日期、关键词与可见范围。"}
        结果一律进入<b>草稿箱</b>，不会直接发布。
      </${Note}>

      <form onSubmit=${submit} style="margin-top:14px">
        <div class="card card-pad">
          <div class="form-grid">
            <${Field} label="消息原文" required hint="从 QQ 群复制整条消息，包含 @ 与通知正文">
              <textarea class="textarea" style="min-height:150px" value=${form.content}
                onInput=${(e) => setForm({ ...form, content: e.target.value })}
                placeholder=${SAMPLE}></textarea>
            </${Field}>
            <div class="form-2">
              <${Field} label="发送人">
                <input class="input" value=${form.sender_name}
                  onInput=${(e) => setForm({ ...form, sender_name: e.target.value })} />
              </${Field}>
              <${Field} label="群名称">
                <input class="input" value=${form.chat_name}
                  onInput=${(e) => setForm({ ...form, chat_name: e.target.value })} />
              </${Field}>
            </div>
            <label class="row-flex small muted" style="gap:6px;cursor:pointer">
              <input type="checkbox" checked=${form.use_ai} disabled=${!meta.ai_enabled}
                onChange=${(e) => setForm({ ...form, use_ai: e.target.checked })} />
              使用 AI 抽取${meta.ai_enabled ? "" : "（未配置密钥）"}
            </label>
            ${error ? html`<${Note} tone="err">${error}</${Note}>` : null}
          </div>
        </div>
        <div class="row-flex" style="margin-top:14px">
          <${Button} type="submit" variant="primary" size="lg" icon="sparkles" loading=${busy}>
            抽取为草稿</${Button}>
          <${Button} variant="ghost" onClick=${() => setForm({ ...form, content: SAMPLE })}>填入示例</${Button}>
        </div>
      </form>

      ${result ? html`<div class="section">
        <div class="section-head"><div class="section-title">抽取结果</div>
          <button type="button" class="section-more" onClick=${() => API.go("drafts")}>去审核 →</button></div>
        <div class="card card-pad">
          <div class="small muted" style="margin-bottom:10px">
            来源：${result.raw ? (result.raw.sender_name || "未知") + " · " + (result.raw.chat_name || "QQ 群") : "—"}
            ${result.job ? " · 方式：" + (result.job.engine === "ai" ? "大模型" : "规则解析") : ""}
          </div>
          <div class="stack">
            ${(result.drafts || []).map((d) => html`<button type="button" class="item" data-tone="violet"
              style="width:100%;text-align:left" onClick=${() => API.go("drafts")}>
              <div class="item-main">
                <div class="item-title">${d.title}
                  <${Badge} tone="amber">草稿</${Badge}>
                  ${d.needs_review ? html`<${Badge} tone="red">待核对</${Badge}>` : null}
                </div>
                <div class="item-sub">
                  <span>${U.CATEGORY[d.category] ? U.CATEGORY[d.category].label : d.category}</span>
                  <span class="dot"></span><span>${d.audience === "class" ? "全班" : "仅班委"}</span>
                  ${d.confidence != null ? html`<span class="dot"></span><span>置信度 ${Math.round(d.confidence * 100)}%</span>` : null}
                </div>
              </div>
              <div class="item-side"><div class="due-main">${U.dueShort(d)}</div></div>
            </button>`)}
          </div>
          <div class="row-flex" style="margin-top:14px">
            <${Button} variant="primary" onClick=${() => API.go("drafts")}>去草稿箱审核</${Button}>
          </div>
        </div>
      </div>` : null}
    </div>`;
  }

  function BookmarkletTab() {
    const S = API.useStore();
    const [token, setToken] = useState("");
    const [copied, setCopied] = useState(false);
    const base = location.origin;

    const code = token.trim() ? window.CDH.buildBookmarklet(token.trim(), base) : "";

    return html`<div>
      <${Note} tone="info" icon="link">
        学习通、雨课堂没有公开的作业接口。最稳妥的方式：<b>你在自己已登录的浏览器里点一下书签</b>，
        把当前页面的文本交给网站解析。服务器不保存你的平台账号密码。
      </${Note}>

      <div class="card card-pad" style="margin-top:14px">
        <div class="form-grid">
          <${Field} label="数据源令牌" hint="在「班委后台 → 数据源」里创建 bookmarklet 类型后生成的令牌">
            <input class="input" value=${token} onInput=${(e) => setToken(e.target.value)}
              placeholder="bookmarklet_1_…" />
          </${Field}>
          ${code ? html`<div>
            <div class="field-label">书签代码</div>
            <div class="code-box" style="max-height:150px;overflow:auto"><code style="white-space:pre-wrap;word-break:break-all;font-size:11.5px">${code}</code></div>
            <div class="row-flex" style="margin-top:8px">
              <${CopyBtn} text=${code} label="复制书签代码" />
            </div>
          </div>` : null}
        </div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">怎么用</div></div>
        <div class="card card-pad">
          <div class="stack" style="gap:10px">
            ${[
              "在班委后台创建「浏览器书签抓取」数据源，复制令牌。",
              "把令牌填到上面，复制生成的 javascript: 代码。",
              "浏览器书签栏新建书签，名称随意，地址粘贴这段代码。",
              "打开学习通「作业」或雨课堂「作业」页面，点一下这个书签。",
              "回到「待审核草稿」，逐条确认后发布。",
            ].map((t, i) => html`<div class="row-flex" style="align-items:flex-start;gap:10px">
              <span class="badge violet" style="flex:none">${i + 1}</span>
              <span class="small" style="padding-top:2px">${t}</span></div>`)}
          </div>
        </div>
      </div>
    </div>`;
  }

  function QqTab() {
    const S = API.useStore();
    const base = location.origin;
    return html`<div>
      <${Note} tone="info" icon="users">
        QQ 群机器人用 <b>NapCat / LLOneBot</b> 这类 OneBot v11 实现。机器人被 @ 时，
        把消息转发到本站，自动落草稿。整个链路只在本机或你的服务器上运行。
      </${Note}>

      <div class="card card-pad" style="margin-top:14px">
        <div class="section-title" style="margin-bottom:10px">接入步骤</div>
        <div class="stack" style="gap:10px">
          ${[
            "在「班委后台 → 数据源」创建「QQ 群机器人」数据源，复制令牌（qq_ 开头）。",
            "在一台能长期开机的电脑上安装 NapCat，登录一个 QQ 小号并加入班级群。",
            "NapCat 设置 → 网络 → HTTP 上报（HTTP POST），地址填 http://服务器:8090/onebot。",
            "启动桥接程序：python bot/onebot_bridge.py，环境变量见下。",
            "在群里 @小助手 发一条通知，几秒后「待审核草稿」里就会出现。",
          ].map((t, i) => html`<div class="row-flex" style="align-items:flex-start;gap:10px">
            <span class="badge violet" style="flex:none">${i + 1}</span>
            <span class="small" style="padding-top:2px">${t}</span></div>`)}
        </div>
        <div class="hr"></div>
        <div class="small muted" style="margin-bottom:6px">桥接程序环境变量（PowerShell）</div>
        <div class="code-box"><code>$env:CDH_SITE = "${base}"
$env:CDH_TOKEN = "qq_1_…"
$env:CDH_LISTEN = "0.0.0.0:8090"
python bot\onebot_bridge.py</code></div>
        <div class="row-flex" style="margin-top:10px">
          <${CopyBtn} text=${`$env:CDH_SITE = "${base}"` + "\n" + `$env:CDH_TOKEN = "qq_1_…"` + "\n" + `$env:CDH_LISTEN = "0.0.0.0:8090"` + "\n" + "python bot\\onebot_bridge.py"} label="复制命令" />
        </div>
      </div>

      <div class="section">
        <div class="section-head"><div class="section-title">机器人识别规则</div></div>
        <div class="card card-pad small">
          <div>· 只在 <b>群消息</b>里触发，且消息中必须有 @机器人。</div>
          <div>· 同一群同一条消息只会处理一次（按 message_id 去重）。</div>
          <div>· 抽取不出截止时间 → 仍然生成草稿，标记「待人工核对」。</div>
          <div>· 消息里出现「班长 / 团支书 / 班委」→ 默认可见范围「仅班委」。</div>
        </div>
      </div>
    </div>`;
  }

  function IngestView() {
    const S = API.useStore();
    const [tab, setTab] = useState("paste");
    if (!(S.me && S.me.permissions && S.me.permissions.committee)) {
      return html`<${Page}><${PageHead} title="无权访问" back=${() => API.go("list")} />
        <${Empty} icon="shield" title="只有班委可以使用消息导入" /></${Page}>`;
    }
    return html`<${Page}>
      <${PageHead} title="从消息导入" sub="QQ 群 / 学习通 / 雨课堂 → 草稿箱"
        back=${() => API.go("list")} />
      <${Tabs} items=${[
        { key: "paste", label: "粘贴消息" },
        { key: "bookmarklet", label: "书签抓取" },
        { key: "qq", label: "QQ 机器人" },
      ]} value=${tab} onChange=${setTab} />
      ${tab === "paste" ? html`<${PasteTab} />`
      : tab === "bookmarklet" ? html`<${BookmarkletTab} />`
      : html`<${QqTab} />`}
      <div style="height:40px"></div>
    </${Page}>`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Ingest = IngestView;
})();
