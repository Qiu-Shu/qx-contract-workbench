/* 立丰脱敏 · 规则面板与配置页逻辑
   所有写操作走后端接口，前端不做本地缓存 —— 勾选即落盘，
   避免「界面显示已关闭、实际还在脱」这种致命的不一致。 */
(function () {
  "use strict";

  const API = "";
  const state = { rules: [], groups: [], stats: {}, sel: null, keyword: "", openGroups: {} };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s);

  async function api(path, body, method) {
    const opt = { method: method || (body ? "POST" : "GET") };
    if (body) {
      opt.headers = { "Content-Type": "application/json" };
      opt.body = JSON.stringify(body);
    }
    const r = await fetch(API + path, opt);
    return await r.json();
  }

  /* ---------------- 加载 ---------------- */
  async function load() {
    try {
      const d = await api("/api/rules");
      if (!d.ok) { console.warn("规则加载失败", d.msg); return; }
      state.rules = d.rules || [];
      // 显示层把「主体与位置」提到第一行（2026-11-12 用户要求），其余保持后端原顺序。
      // 只排界面，不动 rules_store.GROUPS / 配置快照 / 规则匹配顺序：那份是共享引擎，
      // 为好几个流程共用，为了一个显示位置去改它不划算。
      // 首位组同时也是默认展开组，打开面板第一眼就是主体字段。
      const _gs = d.groups || [];
      state.groups = _gs.filter((g) => g.id === "entity")
        .concat(_gs.filter((g) => g.id !== "entity"));
      state.stats = d.stats || {};
      // 首次加载默认展开第一组：全收起的面板看着像没加载出来
      if (!state._inited && state.groups.length) {
        state.openGroups[state.groups[0].id] = true;
        state._inited = true;
      }
      if (state.sel && !state.rules.some((r) => r.id === state.sel)) state.sel = null;
      // 没有选中项时默认选第一条：右侧空着会让人以为页面没加载出来
      if (!state.sel && state.rules.length) state.sel = state.rules[0].id;
      renderPanel();
      renderModal();
    } catch (e) {
      console.warn("规则接口不可用", e);
    }
  }

  /* ---------------- 右侧面板 ---------------- */
  function renderPanel() {
    const body = $("rpBody");
    if (!body) return;
    body.innerHTML = "";
    const cnt = $("rpCount");
    if (cnt) cnt.textContent = state.stats.enabled + " / " + state.stats.total;

    state.groups.forEach((g) => {
      const items = state.rules.filter((r) => r.group === g.id);
      if (!items.length) return;

      const wrap = document.createElement("div");
      wrap.className = "rp-group" + (state.openGroups[g.id] ? " open" : "");

      const head = document.createElement("div");
      head.className = "rp-group-head";
      const on = items.filter((r) => r.enabled).length;
      head.innerHTML =
        '<span class="rp-caret">▶</span>' +
        '<span class="rp-gname"></span>' +
        '<span class="rp-gcount' + (on === 0 ? " off" : "") + '"></span>';
      head.querySelector(".rp-gname").textContent = g.name;
      head.querySelector(".rp-gcount").textContent = on + "/" + items.length;
      head.onclick = (e) => {
        if (e.target.type === "checkbox") return;
        state.openGroups[g.id] = !state.openGroups[g.id];
        renderPanel();
      };
      wrap.appendChild(head);

      const box = document.createElement("div");
      box.className = "rp-items";
      items.forEach((r) => {
        const row = document.createElement("label");
        row.className = "rp-item" + (r.enabled ? "" : " off") + (r.engine === "structure" ? " struct" : "");
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!r.enabled;
        cb.onchange = () => onToggle(r, cb.checked, cb);
        const nm = document.createElement("span");
        nm.className = "nm";
        nm.textContent = r.category;
        nm.title = (r.sample ? "示例：" + r.sample + "\n" : "") + (r.note || "");
        row.appendChild(cb);
        row.appendChild(nm);
        if (r.risk === "high") {
          const rk = document.createElement("span");
          rk.className = "rk";
          rk.textContent = "高";
          rk.title = "高风险项：关闭后这类信息会原样出现在成品里";
          row.appendChild(rk);
        }
        box.appendChild(row);
      });
      wrap.appendChild(box);
      body.appendChild(wrap);
    });
  }

  async function onToggle(rule, enabled, cb) {
    if (!enabled && rule.risk === "high") {
      const ok = confirm(
        "「" + rule.category + "」属于高风险项。\n\n" +
        "关闭后，这类信息会原样出现在成品里，不再替换。\n确定关闭吗？"
      );
      if (!ok) { if (cb) cb.checked = true; return; }
    }
    const d = await api("/api/rules/toggle", { target: rule.id, enabled: enabled });
    if (!d.ok) { alert("保存失败：" + d.msg); if (cb) cb.checked = !enabled; return; }
    rule.enabled = enabled;
    load();
  }

  async function bulk(action) {
    if (action === "reset") {
      if (!confirm("恢复默认会删除所有自定义规则，并把内置规则复位。\n确定吗？")) return;
      const d = await api("/api/rules/reset", {});
      alert(d.ok ? "已恢复默认" : "失败：" + d.msg);
      state.sel = null;
      load();
      return;
    }
    const enabled = action === "all";
    if (!enabled) {
      if (!confirm("将关闭全部脱敏字段（包括身份证号、人名等）。\n成品将不含任何脱敏处理，确定吗？")) return;
    }
    for (const g of state.groups) {
      await api("/api/rules/toggle", { target: g.id, enabled: enabled });
    }
    load();
  }

  /* ---------------- 配置页 ---------------- */
  function renderModal() {
    const list = $("rmList");
    if (!list) return;
    list.innerHTML = "";
    const kw = (state.keyword || "").trim();

    state.groups.forEach((g) => {
      const items = state.rules.filter((r) => {
        if (r.group !== g.id) return false;
        if (!kw) return true;
        return (r.category || "").indexOf(kw) >= 0 ||
               (r.note || "").indexOf(kw) >= 0 ||
               (r.sample || "").indexOf(kw) >= 0;
      });
      if (!items.length) return;

      const gh = document.createElement("div");
      gh.className = "rm-g-h";
      gh.textContent = g.name + "（" + items.length + "）";
      list.appendChild(gh);

      items.forEach((r) => {
        const el = document.createElement("div");
        el.className = "rm-i" + (state.sel === r.id ? " sel" : "") + (r.builtin ? "" : " custom");
        const dot = document.createElement("span");
        dot.className = "dot" + (r.enabled ? "" : " off") + (r.builtin ? "" : " cus");
        const n = document.createElement("span");
        n.className = "n";
        n.textContent = r.category;
        el.appendChild(dot);
        el.appendChild(n);
        el.onclick = () => { state.sel = r.id; renderModal(); };
        list.appendChild(el);
      });
    });
    // 「本案词条」：词表不是正则，单独一栏放，独立于 8 个规则分组
    const th = document.createElement("div");
    th.className = "rm-g-h";
    th.textContent = "本案词条";
    list.appendChild(th);
    const te = document.createElement("div");
    te.className = "rm-i" + (state.sel === "__terms__" ? " sel" : "");
    te.innerHTML = '<span class="dot cus"></span><span class="n">词条对照表</span>';
    te.onclick = () => { state.sel = "__terms__"; renderModal(); };
    list.appendChild(te);

    renderEdit();
  }

  function cur() {
    return state.rules.find((r) => r.id === state.sel) || null;
  }

  function renderEdit() {
    const box = $("rmEdit");
    if (!box) return;
    if (state.sel === "__terms__") { renderTerms(box); return; }
    const r = cur();
    if (!r) {
      box.innerHTML = '<div class="rm-hint" style="margin:26px 18px">从左侧选一条规则查看和编辑。</div>';
      return;
    }
    const isStruct = r.engine === "structure";
    box.innerHTML = "";

    // 元信息
    const meta = document.createElement("div");
    meta.className = "rm-meta";
    meta.innerHTML =
      "<span>分组：" + esc(groupName(r.group)) + "</span>" +
      "<span>" + (r.builtin ? "内置规则（内容只读）" : "自定义规则") + "</span>" +
      "<span>" + (isStruct ? "算法识别" : "正则匹配 " + (r.patterns || []).length + " 条") + "</span>" +
      "<span>顺序 " + r.order + "</span>";
    box.appendChild(meta);

    // 名称
    const f1 = document.createElement("div");
    f1.className = "rm-field";
    f1.innerHTML = '<label>名称（也是占位符名，如 [身份证号]）</label>';
    const nm = document.createElement("input");
    nm.type = "text";
    nm.value = r.category;
    nm.readOnly = r.builtin;
    nm.id = "edName";
    f1.appendChild(nm);
    box.appendChild(f1);

    // 正则
    const f2 = document.createElement("div");
    f2.className = "rm-field";
    f2.innerHTML = '<label>正则表达式（多条时每行一条）</label>';
    const ta = document.createElement("textarea");
    ta.id = "edPatterns";
    ta.rows = Math.min(8, Math.max(3, (r.patterns || []).length + 1));
    if (isStruct) {
      ta.value = "（由算法识别，不支持自定义正则）";
      ta.readOnly = true;
    } else {
      ta.value = (r.patterns || []).join("\n");
      ta.readOnly = !!r.builtin;
    }
    f2.appendChild(ta);
    box.appendChild(f2);

    // 示例 + 说明
    const f3 = document.createElement("div");
    f3.className = "rm-field rm-row";
    f3.innerHTML = '<div><label>示例文本</label></div><div><label>说明</label></div>';
    const s1 = document.createElement("input");
    s1.type = "text"; s1.id = "edSample"; s1.value = r.sample || "";
    const s2 = document.createElement("input");
    s2.type = "text"; s2.id = "edNote"; s2.value = r.note || "";
    f3.children[0].appendChild(s1);
    f3.children[1].appendChild(s2);
    box.appendChild(f3);

    if (r.builtin) {
      const h = document.createElement("div");
      h.className = "rm-hint";
      h.textContent = isStruct
        ? "这类字段靠结构识别算法完成，不能写正则。可以停用，停用后不再识别该类信息。"
        : "内置规则的正则已锁定：可以停用，但不能修改内容。需要不同匹配方式时，新建一条自定义规则，它会排在内置规则之后执行。";
      box.appendChild(h);
    }

    // 按钮
    const btns = document.createElement("div");
    btns.className = "rm-btns";
    const bEnable = document.createElement("button");
    bEnable.className = r.enabled ? "" : "primary";
    bEnable.textContent = r.enabled ? "停用此字段" : "启用此字段";
    bEnable.onclick = async () => {
      if (r.enabled && r.risk === "high") {
        if (!confirm("「" + r.category + "」是高风险项，关闭后这类信息会原样出现在成品里。确定？")) return;
      }
      const d = await api("/api/rules/toggle", { target: r.id, enabled: !r.enabled });
      if (!d.ok) { alert("失败：" + d.msg); return; }
      load();
    };
    btns.appendChild(bEnable);

    if (!r.builtin) {
      const bSave = document.createElement("button");
      bSave.className = "primary";
      bSave.textContent = "保存修改";
      bSave.onclick = () => saveCustom(r);
      btns.appendChild(bSave);

      const bDel = document.createElement("button");
      bDel.className = "danger";
      bDel.textContent = "删除";
      bDel.onclick = async () => {
        if (!confirm("删除自定义规则「" + r.category + "」？")) return;
        const d = await api("/api/rules/delete", { id: r.id });
        alert(d.ok ? "已删除" : "失败：" + d.msg);
        state.sel = null;
        load();
      };
      btns.appendChild(bDel);
    } else {
      const bNew = document.createElement("button");
      bNew.textContent = "基于此规则新建自定义规则";
      bNew.onclick = () => newCustom(r);
      btns.appendChild(bNew);
    }

    const sp = document.createElement("span");
    sp.className = "sp";
    btns.appendChild(sp);
    box.appendChild(btns);

    // 测试区内容与选中规则联动
    const t = $("rmTestText");
    if (t && !t.dataset.touched) t.value = r.sample || "";
  }

  function groupName(gid) {
    const g = state.groups.find((x) => x.id === gid);
    return g ? g.name : gid;
  }

  async function saveCustom(r) {
    const category = ($("edName") || {}).value || "";
    const raw = ($("edPatterns") || {}).value || "";
    const patterns = raw.split("\n").map((x) => x.trim()).filter((x) => x);
    if (!category.trim()) { alert("名称不能为空"); return; }
    if (!patterns.length) { alert("至少要有一条正则"); return; }
    const d = await api("/api/rules/save", {
      id: r.builtin ? undefined : r.id,
      category: category.trim(),
      group: r.group,
      patterns: patterns,
      enabled: r.enabled,
      sample: ($("edSample") || {}).value || "",
      note: ($("edNote") || {}).value || "",
    });
    if (!d.ok) { alert("保存失败：" + d.msg); return; }
    alert(d.msg);
    load();
  }

  function newCustom(base) {
    const name = prompt("新规则的名称（将成为占位符，如「内部项目代号」）：",
                        base && !base.builtin ? "" : "");
    if (!name) return;
    const d = api("/api/rules/save", {
      category: name.trim(),
      group: (base && base.group) || "entity",
      patterns: ["在此填写正则"],
      enabled: true,
      sample: "",
      note: "",
    });
    d.then((res) => {
      if (!res.ok) { alert("创建失败：" + res.msg); return; }
      state.sel = "custom-" + name.trim();
      load();
    });
  }

  /* ---------------- 测试器 ---------------- */
  async function runTest() {
    const out = $("rmTestOut");
    const r = cur();
    if (!out) return;
    if (!r) { out.innerHTML = '<span class="none">先选一条规则</span>'; return; }
    if (r.engine === "structure") {
      out.innerHTML = '<span class="none">该字段由算法识别，没有正则可测。可用「质量体检」看扫描件能不能认出来。</span>';
      return;
    }
    const ta = $("edPatterns");
    const patterns = (ta && !ta.readOnly)
      ? ta.value.split("\n").map((x) => x.trim()).filter((x) => x)
      : (r.patterns || []);
    const text = ($("rmTestText") || {}).value || "";
    if (!text.trim()) { out.innerHTML = '<span class="none">先输入一段样例文本</span>'; return; }
    const d = await api("/api/rules/test", {
      patterns: patterns, text: text, category: r.category,
    });
    if (!d.ok) { out.innerHTML = '<span class="err">正则语法错误：' + esc(d.error) + "</span>"; return; }
    if (!d.count) { out.innerHTML = '<span class="none">未命中（这段文本里没有该字段）</span>'; return; }

    // 高亮命中
    let html = "", pos = 0;
    const hits = d.hits;
    hits.forEach((h) => {
      if (h.start > pos) html += esc(text.slice(pos, h.start));
      html += "<mark>" + esc(h.match) + "</mark>";
      pos = h.end;
    });
    if (pos < text.length) html += esc(text.slice(pos));
    out.innerHTML =
      "<div style='margin-bottom:6px;color:var(--muted)'>命中 " + d.count + " 处：" + html + "</div>" +
      "<div><span style='color:var(--muted)'>替换后：</span>" + esc(d.preview) + "</div>";
  }

  /* ---------------- 打开/关闭 ---------------- */
  function openModal() {
    const m = $("rulesModal");
    if (!m) return;
    m.classList.add("show");
    load();
    setTimeout(() => {
      const s = $("rmSearch");
      if (s) s.focus();
    }, 60);
  }
  function closeModal() {
    const m = $("rulesModal");
    if (m) m.classList.remove("show");
    load();
  }

  /* ---------------- 事件绑定 ---------------- */
  function bind() {
    const ob = $("openRules");
    if (ob) ob.onclick = openModal;
    const cb = $("rmClose");
    if (cb) cb.onclick = closeModal;
    const nb = $("rpOpen");
    if (nb) nb.onclick = openModal;

    const s = $("rmSearch");
    if (s) s.oninput = () => { state.keyword = s.value; renderModal(); };

    const t = $("rmTestText");
    if (t) t.oninput = () => { t.dataset.touched = "1"; };
    const tb = $("rmTestBtn");
    if (tb) tb.onclick = runTest;

    document.querySelectorAll("[data-bulk]").forEach((b) => {
      b.onclick = () => bulk(b.getAttribute("data-bulk"));
    });
    document.querySelectorAll("[data-io]").forEach((b) => {
      b.onclick = async () => {
        const act = b.getAttribute("data-io");
        const d = await api("/api/rules/" + act, {});
        alert(d.ok ? (act === "export" ? "已导出到：\n" + d.msg : d.msg) : "失败：" + d.msg);
        load();
      };
    });

    // 面板收起
    const tg = $("rpToggle");
    if (tg) tg.onclick = () => {
      const p = $("rulesPanel");
      if (p) p.classList.toggle("collapsed");
    };

    // Esc 关闭配置页
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const m = $("rulesModal");
        if (m && m.classList.contains("show")) closeModal();
      }
    });
  }

  // 主页面的 poll 每秒跑一次，别抢它的节奏：这里只加载一次，交互时再刷
  document.addEventListener("DOMContentLoaded", () => {
    bind();
    load();
    // 调试/快捷入口：地址栏带 ?rules=1 时直接打开配置页
    if (location.search.indexOf("rules=1") >= 0) setTimeout(openModal, 200);
  });
  if (document.readyState !== "loading") { bind(); load(); }

  /* ---------------- 本案词条 ----------------
     2026-11-06 用户两条要求（原话）：
       「我导入对照表需要基础格式啊，你要支持表格的对照表读取」
       「你要给我一个一键清空的功能，我导进去以后还得自己手动一个个删」

     所以这一版把「导入」从「选个 txt 直接覆盖词表」改成两段式：
       选文件 → 解析 → 给预览（读了几条、认的哪两列、跳过什么）→ 用户点确认才落盘。
     列认错了会一次灌进几百条垃圾，逐条删比重新导还慢，多一次点击是划算的。 */

  // 解析结果暂存：确认前不写盘。
  let termPreview = null;
  // 跨重画留一条提示（清空/导入后要 renderTerms，DOM 重建会把提示冲掉）
  let termTip = null;

  /* 把一份解析结果画成预览卡片。
     单独成函数是为了能脱离「选文件」这一步被单独调用/复测 ——
     选文件要走系统弹窗，落到自动化里就没法验渲染了。 */
  function paintTermPreview(el, r, onMerge, onReplace, onCancel) {
    el.innerHTML = "";
    if (!r) { el.style.display = "none"; return; }
    el.style.display = "";

    const h = document.createElement("div");
    h.className = "tp-h";
    const hb = document.createElement("b");
    hb.textContent = "读到 " + r.total + " 条";
    const hf = document.createElement("span");
    hf.className = "tp-f";
    hf.textContent = (r.file || "") + (r.kind ? " · " + r.kind : "");
    h.appendChild(hb);
    h.appendChild(hf);
    el.appendChild(h);

    const lay = document.createElement("div");
    lay.className = "tp-note";
    lay.textContent = "列识别：" + (r.layout || "—");
    el.appendChild(lay);

    if (r.rows) {
      const n2 = document.createElement("div");
      n2.className = "tp-note";
      let s = "表里共 " + r.rows + " 行";
      if (r.skipped && r.skipped.length) s += "，跳过 " + r.skipped.length + " 条（见下）";
      n2.textContent = s;
      el.appendChild(n2);
    }

    const sm = document.createElement("div");
    sm.className = "tp-list";
    (r.items || []).slice(0, 8).forEach((it) => {
      const row = document.createElement("div");
      row.className = "tp-row";
      const o = document.createElement("span");
      o.className = "o";
      o.textContent = it.orig;
      const eq = document.createElement("span");
      eq.className = "eq";
      eq.textContent = "=";
      const rp = document.createElement("span");
      rp.className = "r";
      rp.textContent = it.repl || "（自动占位符）";
      row.appendChild(o); row.appendChild(eq); row.appendChild(rp);
      sm.appendChild(row);
    });
    if (r.total > 8) {
      const more = document.createElement("div");
      more.className = "tp-more";
      more.textContent = "… 还有 " + (r.total - 8) + " 条";
      sm.appendChild(more);
    }
    el.appendChild(sm);

    if (r.skipped && r.skipped.length) {
      const sk = document.createElement("div");
      sk.className = "tp-skip";
      sk.textContent = "跳过 " + r.skipped.length + " 条：" +
        r.skipped.slice(0, 3).map((s) => "第" + s.row + "行 " + s.why).join("；");
      el.appendChild(sk);
    }

    const acts = document.createElement("div");
    acts.className = "tp-acts";
    const bMerge = document.createElement("button");
    bMerge.className = "primary";
    bMerge.textContent = "合并导入";
    bMerge.title = "保留已有词条，同名的用新值覆盖";
    const bRepl = document.createElement("button");
    bRepl.textContent = "覆盖导入";
    bRepl.title = "先清空整份词表，只留这次导入的";
    const bCancel = document.createElement("button");
    bCancel.className = "ghost";
    bCancel.textContent = "取消";
    bMerge.onclick = onMerge;
    bRepl.onclick = onReplace;
    bCancel.onclick = onCancel;
    acts.appendChild(bMerge);
    acts.appendChild(bRepl);
    acts.appendChild(bCancel);
    el.appendChild(acts);
  }

  async function renderTerms(box) {
    box.innerHTML = '<div class="loading"><span class="spin"></span>读取词条…</div>';
    let items = [];
    try {
      const d = await api("/api/terms/list");
      items = d.items || [];
    } catch (e) {
      box.innerHTML = '<div class="rm-hint">词表读取失败</div>';
      return;
    }

    box.innerHTML = "";
    const meta = document.createElement("div");
    meta.className = "rm-meta";
    meta.innerHTML = "<span>共 " + items.length + " 条</span>" +
                     "<span>规则认不出的具体名称靠它</span>" +
                     "<span>优先于正则执行</span>";
    box.appendChild(meta);

    const hint = document.createElement("div");
    hint.className = "rm-hint";
    hint.textContent = "人名、公司名、项目名没有固定格式，正则识别不了，只能在这里逐个登记。" +
                       "词条优先于正则执行：登记过的名称一定按你写的替换。";
    box.appendChild(hint);

    /* ---- 工具条 ---- */
    const tools = document.createElement("div");
    tools.className = "term-tools";
    const bImp = document.createElement("button");
    bImp.className = "primary";
    bImp.textContent = "导入对照表…";
    bImp.title = "支持 Excel / CSV / 文本 / Word 表格";
    const bTpl = document.createElement("button");
    bTpl.textContent = "下载模板";
    bTpl.title = "生成一份能直接填的基础格式，放到「词表」文件夹并选中";
    const bClr = document.createElement("button");
    bClr.className = "danger";
    bClr.textContent = "清空全部";
    bClr.title = "清空整份词表（清空前自动备份 .bak）";
    tools.appendChild(bImp);
    tools.appendChild(bTpl);
    const tsp = document.createElement("span");
    tsp.className = "sp";
    tools.appendChild(tsp);
    tools.appendChild(bClr);
    box.appendChild(tools);

    const tipEl = document.createElement("div");
    tipEl.className = "term-tip";
    tipEl.style.display = "none";
    box.appendChild(tipEl);
    const setTip = (text, kind) => {
      if (!text) { tipEl.style.display = "none"; return; }
      tipEl.className = "term-tip" + (kind === "warn" ? " warn" : "");
      tipEl.textContent = text;
      tipEl.style.display = "";
    };

    /* ---- 导入预览 ---- */
    const prev = document.createElement("div");
    prev.className = "term-prev";
    prev.style.display = "none";
    box.appendChild(prev);

    const drawPreview = () => {
      paintTermPreview(prev, termPreview,
        () => doImport("merge"),
        () => doImport("replace"),
        () => { termPreview = null; drawPreview(); });
    };

    const doImport = async (mode) => {
      const r = termPreview;
      if (!r) return;
      if (mode === "replace" &&
          !confirm("覆盖导入会先清空现有 " + items.length + " 条词条，只保留这次导入的。\n\n确定？")) return;
      const d = await api("/api/terms/import", { items: r.items, mode: mode });
      if (!d.ok) { setTip("导入失败：" + (d.msg || "未知错误"), "warn"); return; }
      termPreview = null;
      termTip = { text: d.msg || "已导入", kind: "ok" };
      renderTerms(box);
    };

    bImp.onclick = async () => {
      const old = bImp.textContent;
      bImp.disabled = true;
      bImp.textContent = "选择文件…";
      try {
        const d = await api("/api/terms/parse", {});
        if (!d.ok) {
          if (!d.cancel) setTip(d.msg || "读取失败", "warn");
          return;
        }
        termPreview = d;
        setTip("");
        drawPreview();
      } catch (e) {
        setTip("读取失败：" + e.message, "warn");
      } finally {
        bImp.disabled = false;
        bImp.textContent = old;
      }
    };

    bTpl.onclick = async () => {
      bTpl.disabled = true;
      try {
        const d = await api("/api/terms/template", { fmt: "xlsx" });
        setTip(d.ok ? d.msg : ("模板生成失败：" + (d.msg || "")), d.ok ? "ok" : "warn");
      } catch (e) {
        setTip("模板生成失败：" + e.message, "warn");
      } finally {
        bTpl.disabled = false;
      }
    };

    bClr.onclick = async () => {
      if (!items.length) { setTip("词表本来就是空的，不用清", "warn"); return; }
      if (!confirm("清空全部 " + items.length + " 条词条？\n\n" +
                   "清空前会自动备份一份（敏感词表.txt.bak），误点还能捞回来。\n\n确定清空？")) return;
      const d = await api("/api/terms/clear", {});
      if (!d.ok) { setTip("清空失败：" + (d.msg || ""), "warn"); return; }
      termPreview = null;
      termTip = { text: d.msg || "已清空", kind: "ok" };
      renderTerms(box);
    };

    /* ---- 新增单条 ---- */
    const addRow = document.createElement("div");
    addRow.className = "rm-field";
    addRow.innerHTML = '<label>新增词条（原词 = 替换为）</label>';
    const line = document.createElement("div");
    line.className = "term-add";
    line.innerHTML = '<input type="text" id="tOrig" placeholder="原词，如 湖北某某建材有限公司">' +
                     '<span class="eq">=</span>' +
                     '<input type="text" id="tRepl" placeholder="替换为，如 建材公司（留空自动生成）">' +
                     '<button class="btn" id="tAdd">添加</button>';
    addRow.appendChild(line);
    box.appendChild(addRow);

    /* ---- 列表 ---- */
    const wrap = document.createElement("div");
    wrap.className = "term-list";
    if (!items.length) {
      wrap.innerHTML = '<div class="empty">还没有词条。可以点上面的「导入对照表…」批量导入，' +
                       '或手动添加。</div>';
    } else {
      items.forEach((it, idx) => {
        const row = document.createElement("div");
        row.className = "term-row";
        row.innerHTML = '<span class="i">' + (idx + 1) + '</span>' +
                        '<span class="o"></span><span class="eq">=</span><span class="r"></span>' +
                        '<span class="act"></span>';
        row.querySelector(".o").textContent = it.orig;
        row.querySelector(".r").textContent = it.repl || "（自动）";
        const bDel = document.createElement("button");
        bDel.textContent = "删除";
        bDel.onclick = async () => {
          if (!confirm("删除词条「" + it.orig + "」？")) return;
          const d = await api("/api/terms/delete", { orig: it.orig });
          if (!d.ok) { alert("删除失败：" + d.msg); return; }
          renderTerms(box);
        };
        row.querySelector(".act").appendChild(bDel);
        wrap.appendChild(row);
      });
    }
    box.appendChild(wrap);

    // 重画后把上一轮的提示补回来
    if (termTip) { setTip(termTip.text, termTip.kind); termTip = null; }
    // 有预览结果就一起画回来
    drawPreview();

    const btn = $("tAdd");
    if (btn) btn.onclick = async () => {
      const o = ($("tOrig") || {}).value || "";
      const r = ($("tRepl") || {}).value || "";
      if (!o.trim()) { alert("原词不能为空"); return; }
      const d = await api("/api/terms/save", { orig: o.trim(), repl: r.trim() });
      if (!d.ok) { alert("保存失败：" + d.msg); return; }
      renderTerms(box);
    };
  }

  window.RulesUI = { reload: load, open: openModal };
})();
