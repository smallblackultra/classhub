/* 书签抓取器生成：把学习通 / 雨课堂页面里的作业条目抽成 items，交给本站建草稿。
 * 生成的代码完全在用户浏览器里运行，不经过第三方；服务器只收文本，不收账号。
 */
(function () {
  "use strict";
  window.CDH = window.CDH || {};

  // 在目标页面执行的部分（字符串拼接后作为 javascript: 书签）
  const EXTRACT = [
    "const T=(document.querySelector('main')||document.body).innerText||'';",
    "const L=T.split(/\\n+/).map(s=>s.trim()).filter(Boolean);",
    "const D=/(\\d{4}[-/.]\\d{1,2}[-/.]\\d{1,2}|\\d{1,2}[-/.]\\d{1,2}(?:日)?|(?:今天|明天|后天|本周|下周)[^\\n]{0,12})/;",
    "const near=s=>/截止|提交|完成|due/i.test(s)&&D.test(s);",
    "let buf=[];const items=[];",
    "document.querySelectorAll('li,tr,dd,.item,.list-item,.work-item,.work').forEach(el=>{",
    "const s=(el.innerText||'').trim();if(!s||!near(s))return;",
    "const a=el.querySelector('a[href]');const m=s.match(D);",
    "items.push({title:(buf.slice(-2).join(' ')||s).slice(0,150),due_text:(m?m[0]:''),link:a?a.href:''});",
    "buf=[];});",
    "if(!items.length)items.push({title:(document.title||'未命名页面').slice(0,120),due_text:''});",
  ].join("");

  const PLATFORM = "location.hostname.includes('chaoxing')?'chaoxing':"
    + "(location.hostname.includes('ykt')||location.hostname.includes('yuketang'))?'yuketang':'bookmarklet'";

  window.CDH.buildBookmarklet = function (token, base) {
    // 书签在 chaoxing/yuketang 页面上执行，必须是绝对地址；按当前站点的挂载前缀拼
    const endpoint = new URL("api/ingest/bookmarklet", document.baseURI).toString();
    return "javascript:(()=>{const t=" + JSON.stringify(token) + ",B=" + JSON.stringify(endpoint) + ";"
      + EXTRACT
      + "fetch(B,{method:'POST',"
      + "headers:{'Content-Type':'application/json','X-Classhub-Token':t},"
      + "body:JSON.stringify({platform:" + PLATFORM + ",page_url:location.href,items:items})})"
      + ".then(r=>r.json()).then(d=>alert('已提交 '+(d.created||0)+' 条草稿，去「待审核草稿」确认'))"
      + ".catch(e=>alert('提交失败：'+e));})();";
  };
})();
