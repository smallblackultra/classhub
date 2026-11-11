/* 新建 / 编辑 */
(function () {
  "use strict";
  const { h, html, icon } = window.U;
  const { useState, useMemo } = window.preactHooks;
  const { Button, Page, PageHead, Field, DateField, Note, Seg, Modal, LoadingList, ErrorView, useApi, Empty } = window.CDH.ui;
  const U = window.U;
  const API = window.API;

  function todayPlus(days) {
    const d = new Date(Date.now() + 8 * 3600 * 1000 + days * 86400000);
    return `${d.getUTCFullYear()}-${U.pad(d.getUTCMonth() + 1)}-${U.pad(d.getUTCDate())}`;
  }

  function MemberPicker(props) {
    const { data, loading } = useApi(props.open ? "/api/admin/users?status=active" : "", [props.open]);
    const [kw, setKw] = useState("");
    const people = (data && data.items) || [];
    const filtered = useMemo(() => {
      const k = kw.trim().toLowerCase();
      if (!k) return people;
      return people.filter((p) => (p.name || "").toLowerCase().includes(k) ||
        (p.student_no || "").includes(k));
    }, [people, kw]);
    const chosen = new Set(props.value || []);

    function toggle(id) {
      const next = new Set(chosen);
      if (next.has(id)) next.delete(id); else next.add(id);
      props.onChange(Array.from(next));
    }

    return html`<${Modal} open=${props.open} title="选择参与成员" wide=${true} onClose=${props.onClose}
      footer=${html`<span class="small muted">已选 ${chosen.size} 人</span>
        <${Button} variant="primary" onClick=${props.onClose}>完成</${Button}>`}>
        <div class="row-flex" style="margin-bottom:10px;gap:8px">
          <input class="input grow" placeholder="搜索姓名或学号…" value=${kw}
            onInput=${(e) => setKw(e.target.value)} />
          <button type="button" class="btn sm ghost"
            onClick=${() => props.onChange(filtered.map((p) => p.id))}>全选当前</button>
          <button type="button" class="btn sm ghost" onClick=${() => props.onChange([])}>清空</button>
        </div>
        ${loading ? html`<div class="muted small">加载中…</div>`
        : filtered.length === 0 ? html`<${Empty} icon="users" title="没有匹配的成员" hint="换个关键词试试" />`
        : html`<div class="people-grid">
          ${filtered.map((p) => html`<label class="person ${chosen.has(p.id) ? "" : "missing"}"
            style="cursor:pointer;display:flex;align-items:center;gap:8px">
            <input type="checkbox" checked=${chosen.has(p.id)} onChange=${() => toggle(p.id)} />
            <span style="min-width:0">
              <span style="display:block;font-weight:600">${p.name}</span>
              <span class="small muted mono">${p.student_no}</span>
            </span>
          </label>`)}
        </div>`}
    </${Modal}>`;
  }

  function EditorForm(props) {
    const S = API.useStore();
    const initial = props.initial || {};
    const meta = S.meta || { categories: [], audiences: [], task_subtypes: [], task_levels: [] };
    const local = initial.due_local ? U.parseLocal(initial.due_local) : null;

    const [form, setForm] = useState({
      title: initial.title || "",
      category: initial.category || "homework",
      subtype: initial.subtype || "other",
      task_level: initial.task_level || "class",
      audience: initial.audience || "class",
      due_date: initial.due_date || todayPlus(1),
      due_time: local ? `${U.pad(local.hh)}:${U.pad(local.mm)}` : "23:59",
      all_day: !!initial.all_day,
      course: initial.course || "",
      summary: initial.summary || "",
      location: initial.location || "",
      link: initial.link || "",
      attachments: (initial.attachments || []).slice(),
      as_draft: false,
    });
    const [targets, setTargets] = useState((initial.target_user_ids || []).slice());
    const [targetMode, setTargetMode] = useState((initial.target_user_ids || []).length ? "pick" : "all");
    const [picking, setPicking] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [fieldErr, setFieldErr] = useState({});
    const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
    const hasDue = !!form.due_date;
    const isTask = form.category === "task";

    function quickDue(days) {
      setForm({ ...form, all_day: false, due_date: todayPlus(days), due_time: "23:59" });
    }

    async function submit(e) {
      e.preventDefault();
      if (busy) return;
      setError(null);
      const errs = {};
      if (!form.title.trim()) errs.title = "请填写标题";
      if (!form.due_date && !form.all_day) errs.due_date = "请选择截止日期";
      if (form.audience === "class" && targetMode === "pick" && targets.length === 0) {
        errs.targets = "请选择参与成员，或改回「全班」";
      }
      setFieldErr(errs);
      if (Object.keys(errs).length) return;

      let dueInput = "";
      if (form.due_date) {
        dueInput = form.all_day ? form.due_date : `${form.due_date}T${form.due_time || "23:59"}`;
      }
      const payload = {
        title: form.title.trim(),
        category: form.category,
        subtype: isTask ? form.subtype : null,
        task_level: isTask ? form.task_level : null,
        audience: form.audience,
        target_user_ids: form.audience === "class" && targetMode === "pick" ? targets : [],
        due_at: dueInput,
        all_day: !!form.all_day,
        course: form.course.trim(),
        summary: form.summary.trim(),
        location: form.location.trim(),
        link: form.link.trim(),
        attachments: form.attachments.filter((a) => (a.url || "").trim())
          .map((a) => ({ name: (a.name || "").trim(), url: a.url.trim() })),
      };
      setBusy(true);
      try {
        let res;
        if (props.id) {
          res = await API.api.patch(`/api/deadlines/${props.id}`, payload);
          API.toast("已保存", "ok");
        } else {
          res = await API.api.post("/api/deadlines", { ...payload, as_draft: form.as_draft });
          API.toast(form.as_draft ? "已存为草稿" : "已发布", "ok");
        }
        API.bump();
        API.go("detail/" + res.item.id);
      } catch (err) {
        setError(err.message || "保存失败");
        if (err.field) setFieldErr({ [err.field]: err.message });
        setBusy(false);
      }
    }

    const audiences = meta.audiences && meta.audiences.length
      ? meta.audiences.map((x) => ({ key: x.value, label: x.value === "class" ? "全班" : "仅班委" }))
      : [{ key: "class", label: "全班" }, { key: "committee", label: "仅班委" }];
    const subtypes = (meta.task_subtypes && meta.task_subtypes.length ? meta.task_subtypes
      : [{ value: "form", label: "表格" }, { value: "quiz", label: "答题" }, { value: "study", label: "学习" }, { value: "other", label: "其他" }])
      .map((x) => ({ key: x.value, label: x.label }));
    const levels = (meta.task_levels && meta.task_levels.length ? meta.task_levels
      : [{ value: "college", label: "学院" }, { value: "class", label: "班级" }])
      .map((x) => ({ key: x.value, label: x.label }));

    return html`<${Page} narrow>
      <${PageHead} title=${props.id ? "编辑条目" : "新建事项"}
        sub=${props.id ? "" : "作业、任务（表格/答题/学习）、考试，都可以在这里添加"}
        back=${() => (props.id ? API.go("detail/" + props.id) : API.go("list"))} />

      <form onSubmit=${submit}>
        <div class="card card-pad">
          <div class="form-grid">
            <${Field} label="标题" required error=${fieldErr.title}>
              <input class="input" value=${form.title} onInput=${set("title")}
                placeholder="例如：高数作业第 5 章 / 医保信息收集表" maxlength="120" aria-invalid=${!!fieldErr.title} />
            </${Field}>

            <${Field} label="模块">
              <${Seg} items=${(meta.categories || []).map((x) => ({ key: x.value, label: x.label }))}
                value=${form.category} onChange=${(v) => setForm({ ...form, category: v })} />
            </${Field}>

            ${isTask ? html`<div class="form-grid">
              <${Field} label="任务类型">
                <${Seg} items=${subtypes} value=${form.subtype}
                  onChange=${(v) => setForm({ ...form, subtype: v })} />
              </${Field}>
              <${Field} label="任务层级">
                <${Seg} items=${levels} value=${form.task_level}
                  onChange=${(v) => setForm({ ...form, task_level: v })} />
                <span class="field-hint">学院下发的事项选「学院」，本班自己的选「班级」。</span>
              </${Field}>
            </div>` : null}

            <${Field} label="谁能看到">
              <${Seg} items=${audiences} value=${form.audience}
                onChange=${(v) => setForm({ ...form, audience: v })} />
              <span class="field-hint">
                ${form.audience === "class"
                  ? "全班同学在首页都能看到，适合作业、考试、要全班填的表。"
                  : "只有班长和团支书能看到，适合学院下发给班委的任务。"}
              </span>
            </${Field}>

            ${form.audience === "class" ? html`<${Field} label="参与范围" error=${fieldErr.targets}>
              <${Seg} items=${[{ key: "all", label: "全班" }, { key: "pick", label: "指定成员" }]}
                value=${targetMode}
                onChange=${(v) => { setTargetMode(v); if (v === "all") setTargets([]); }} />
              ${targetMode === "pick" ? html`<div class="row-flex" style="margin-top:8px;gap:8px">
                <${Button} size="sm" variant="soft" icon="users" onClick=${() => setPicking(true)}>
                  选择成员（已选 ${targets.length} 人）
                </${Button}>
                ${targets.length ? html`<button type="button" class="btn sm ghost"
                  onClick=${() => setTargets([])}>清空</button>` : null}
              </div>` : null}
              <span class="field-hint">
                ${targetMode === "all" ? "全班同学都会看到并需要完成。" : "只有被选中的同学能看到这条事项，班委始终可见。"}
              </span>
            </${Field}>` : null}

            <${Field} label="截止时间" error=${fieldErr.due_date}>
              <div class="row-flex wrap">
                <${DateField} value=${form.due_date} onChange=${(v) => setForm({ ...form, due_date: v })} style="flex:1;min-width:150px" />
                ${!form.all_day ? html`<input class="input" type="time" style="width:130px"
                  value=${form.due_time} onInput=${set("due_time")} />` : null}
                <label class="row-flex small muted" style="gap:6px;cursor:pointer">
                  <input type="checkbox" checked=${form.all_day}
                    onChange=${(e) => setForm({ ...form, all_day: e.target.checked })} />全天
                </label>
              </div>
              <div class="row-flex wrap" style="gap:6px;margin-top:2px">
                <button type="button" class="btn sm ghost" onClick=${() => quickDue(0)}>今天 23:59</button>
                <button type="button" class="btn sm ghost" onClick=${() => quickDue(1)}>明天 23:59</button>
                <button type="button" class="btn sm ghost" onClick=${() => quickDue(7)}>一周后</button>
                ${hasDue ? html`<button type="button" class="btn sm ghost"
                  onClick=${() => setForm({ ...form, due_date: "" })}>清除</button>` : null}
              </div>
            </${Field}>

            <div class="form-2">
              <${Field} label="课程 / 来源">
                <input class="input" value=${form.course} onInput=${set("course")} placeholder="例如：高等数学" />
              </${Field}>
              <${Field} label="地点（考试可用）">
                <input class="input" value=${form.location} onInput=${set("location")} placeholder="例如：三教 301" />
              </${Field}>
            </div>

            <${Field} label="说明">
              <textarea class="textarea" value=${form.summary} onInput=${set("summary")}
                placeholder="补充要求、提交方式、注意事项…" maxlength="2000"></textarea>
            </${Field}>

            <${Field} label="相关链接">
              <input class="input" value=${form.link} onInput=${set("link")} placeholder="https://…" />
            </${Field}>

            <${Field} label="附件">
              <div class="stack">
                ${form.attachments.map((a, i) => html`<div class="row-flex">
                  <input class="input" style="flex:1" placeholder="附件名称" value=${a.name || ""}
                    onInput=${(e) => {
                      const next = form.attachments.slice();
                      next[i] = { ...next[i], name: e.target.value };
                      setForm({ ...form, attachments: next });
                    }} />
                  <input class="input" style="flex:1.6" placeholder="https://…" value=${a.url || ""}
                    onInput=${(e) => {
                      const next = form.attachments.slice();
                      next[i] = { ...next[i], url: e.target.value };
                      setForm({ ...form, attachments: next });
                    }} />
                  <button type="button" class="icon-btn" aria-label="移除"
                    onClick=${() => setForm({ ...form, attachments: form.attachments.filter((_, j) => j !== i) })}>
                    ${icon("trash")}
                  </button>
                </div>`)}
                <div>
                  <${Button} size="sm" variant="ghost" icon="plus"
                    onClick=${() => setForm({ ...form, attachments: form.attachments.concat([{ name: "", url: "" }]) })}>
                    添加附件</${Button}>
                </div>
              </div>
            </${Field}>

            ${error ? html`<${Note} tone="err">${error}</${Note}>` : null}
          </div>
        </div>

        <div class="row-flex wrap" style="margin-top:16px">
          <${Button} type="submit" variant="primary" size="lg" loading=${busy}>
            ${props.id ? "保存修改" : (form.as_draft ? "存为草稿" : "发布")}
          </${Button}>
          ${!props.id ? html`
            <label class="row-flex small muted" style="gap:6px;cursor:pointer">
              <input type="checkbox" checked=${form.as_draft}
                onChange=${(e) => setForm({ ...form, as_draft: e.target.checked })} />
              先存草稿（仅班委可见）
            </label>` : null}
          <${Button} variant="ghost" onClick=${() => (props.id ? API.go("detail/" + props.id) : API.go("list"))}>取消</${Button}>
        </div>
      </form>

      <${MemberPicker} open=${picking} value=${targets}
        onChange=${setTargets} onClose=${() => setPicking(false)} />
    </${Page}>`;
  }

  function EditorView(props) {
    if (!props.id) return html`<${EditorForm} />`;
    const { data, loading, error, reload } = useApi(`/api/deadlines/${props.id}`, []);
    if (loading && !data) return html`<${Page}><${LoadingList} rows=${4} /></${Page}>`;
    if (error) {
      return html`<${Page}><${PageHead} title="条目不存在" back=${() => API.go("list")} />
        <${ErrorView} err=${error} retry=${reload} /></${Page}>`;
    }
    return html`<${EditorForm} id=${props.id} initial=${data.item} />`;
  }

  window.CDH = window.CDH || {};
  window.CDH.views = window.CDH.views || {};
  window.CDH.views.Editor = EditorView;
})();


