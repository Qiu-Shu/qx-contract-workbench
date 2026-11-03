'use strict';
// 只读知识服务前端：检索 -> 分组结果 -> 打开原文并高亮到对应位置。
// 刻意保持无框架、无构建步骤，和既有 library.js 一致的写法，避免为试点引入前端工具链。
(() => {
  const $ = (id) => document.getElementById(id);
  const csrf = () => decodeURIComponent(document.cookie.split('; ')
    .find((part) => part.startsWith('qx_csrf='))?.slice(8) || '');
  let epoch = 0;
  // 打开原文用的是**独立的**请求序号。检索代次只挡"重新检索"这一种情况：
  // 连续点 A、再点 B，两次打开属于同一个代次，代次守卫放行，B 先回、A 后回，
  // 面板就变成"标题写 B、正文是 A、还写着校验通过"。序号必须在每次打开、
  // 每次关闭、每次重新检索时都递增，迟到的响应与错误才无处可写。
  let openSeq = 0;
  let controller = null;
  let current = null;

  const KIND_LABEL = {law: '法条', case: '案例'};

  function message(text, error = false) {
    const node = $('knowledge-message');
    node.textContent = text;
    node.classList.toggle('error', error);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: 'same-origin', ...options});
    let data = {};
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      const error = new Error(data.message || '请求未完成，请稍后重试。');
      error.code = data.code || 'REQUEST_FAILED';
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function badge(text, className) {
    const span = document.createElement('span');
    span.className = `badge ${className || ''}`.trim();
    span.textContent = text;
    return span;
  }

  function renderCard(cite) {
    const card = document.createElement('article');
    card.className = 'card';
    card.dataset.sourceId = cite.source_id;

    const head = document.createElement('div');
    head.className = 'card-head';
    const title = document.createElement('h4');
    title.textContent = cite.title;
    head.append(title, badge('待核验', 'pending'));

    const meta = document.createElement('p');
    meta.className = 'meta';
    const loc = cite.location;
    meta.textContent = `${KIND_LABEL[cite.kind] || cite.kind}｜第 ${loc.line_start}–${loc.line_end} 行｜`
      + `字符 ${loc.char_start}–${loc.char_end}｜版本 ${String(cite.source_version.sha256).slice(0, 12)}`;
    if (cite.heading_path && cite.heading_path.trim()) {
      const path = document.createElement('span');
      path.className = 'path';
      path.textContent = `｜${cite.heading_path}`;
      meta.append(path);
    }

    const quote = document.createElement('blockquote');
    quote.textContent = cite.snippet.text;

    const foot = document.createElement('div');
    foot.className = 'card-foot';
    const basis = document.createElement('span');
    basis.className = 'muted';
    basis.textContent = `排序依据 ${cite.score_basis}`;
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'open-original';
    open.textContent = '打开原文位置';
    open.addEventListener('click', () => openOriginal(cite, card));
    foot.append(basis, open);

    card.append(head, meta, quote, foot);
    return card;
  }

  function clearOriginal() {
    // 作废所有在途的打开请求：面板已经关了，迟到的响应不该再把内容填回来。
    openSeq += 1;
    current = null;
    $('original-panel').hidden = true;
    $('original-body').hidden = true;
    $('original-text').replaceChildren();
    $('original-details').replaceChildren();
    $('original-state').textContent = '';
    $('original-state').classList.remove('error');
    document.querySelectorAll('.card.selected').forEach((node) => node.classList.remove('selected'));
  }

  function detail(label, value) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value || '未提供';
    $('original-details').append(dt, dd);
  }

  async function openOriginal(cite, card) {
    const localEpoch = epoch;
    openSeq += 1;
    const localOpen = openSeq;
    // 本次打开是否是"当前那一次"：检索代次或打开序号任一变化都说明它已经过期。
    const stale = () => localEpoch !== epoch || localOpen !== openSeq;
    const expected = String((cite.source_version && cite.source_version.sha256) || '');

    current = cite.source_id;
    document.querySelectorAll('.card.selected').forEach((node) => node.classList.remove('selected'));
    card.classList.add('selected');
    $('original-panel').hidden = false;
    $('original-body').hidden = true;
    $('original-details').replaceChildren();
    $('original-title').textContent = cite.title;
    $('original-state').classList.remove('error');
    $('original-state').textContent = '正在校验来源版本并回读原文…';

    try {
      // 版本跟请求一起走：服务端据此把"检索时看到的版本"和"这次实际读到的登记版本"比一遍。
      const data = await api(`/api/knowledge/sources/${encodeURIComponent(cite.source_id)}`
        + `?version=${encodeURIComponent(expected)}`);
      if (stale()) return;
      if (data.source_id !== cite.source_id) throw new Error('返回的来源与所选不一致，请重新检索。');
      const returned = String((data.source_version && data.source_version.sha256) || '');
      const verified = String((data.source_version && data.source_version.verified) || '');
      if (!expected || !returned || returned !== expected) {
        const error = new Error('回读到的来源版本与检索时的版本不一致，已阻断显示。');
        error.code = 'KNOWLEDGE_SOURCE_STALE';
        throw error;
      }
      if (verified !== 'recomputed' && verified !== 'anchor_match') {
        const error = new Error('服务端没有声明版本校验方式，不能当作已校验。');
        error.code = 'KNOWLEDGE_UNVERIFIED';
        throw error;
      }
      $('original-state').textContent = data.content.truncated
        ? `已回读原文，版本与原文哈希一致（该块共 ${data.content.full_length} 字，`
          + `本次显示 ${data.content.text.length} 字，已截断）。`
        : `已回读原文，版本与原文哈希一致（${data.content.text.length} 字）。`;
      detail('来源标识', data.source_id);
      detail('版本 sha256', String(data.source_version.sha256).slice(0, 32) + '…');
      detail('版本校验', `${verified}｜${data.source_version.basis || '未声明'}`);
      detail('位置', `第 ${data.location.line_start}–${data.location.line_end} 行｜字符 `
        + `${data.content.start}–${data.content.end}（块 ${data.location.char_start}–${data.location.char_end}）`);
      detail('定位方式', data.location.basis);
      detail('效力状态', '待核验（support / applicability 均未确认）');
      const pre = $('original-text');
      pre.replaceChildren();
      const text = data.content.text;
      const start = cite.snippet.match_start;
      const end = cite.snippet.match_end;
      if (start === null || end === null || start < data.content.start || end > data.content.end) {
        pre.textContent = text;
      } else {
        pre.append(document.createTextNode(text.slice(0, start - data.content.start)));
        const mark = document.createElement('mark');
        mark.id = 'original-mark';
        mark.textContent = text.slice(start - data.content.start, end - data.content.start);
        pre.append(mark, document.createTextNode(text.slice(end - data.content.start)));
      }
      $('original-body').hidden = false;
      $('original-title').focus({preventScroll: true});
    } catch (error) {
      // 迟到的失败同样不许覆盖：可能用户已经点了别的引用，甚至把面板关了。
      if (stale()) return;
      const hints = {
        KNOWLEDGE_SOURCE_STALE: '来源版本已变化（原文哈希不符），已阻断引用。请重新检索。',
        KNOWLEDGE_SOURCE_NOT_FOUND: '未找到这条来源，可能不在已登记范围内。',
        KNOWLEDGE_UNVERIFIED: '服务端未声明版本校验方式，已阻断显示，请重新检索后再引用。',
        KB_SERVICE_UNAVAILABLE: '知识服务不可达或超时，请稍后再试。',
        KB_SERVICE_DEGRADED: '知识服务的数据源故障，本次没有拿到原文；这不等于"没有这条来源"。',
      };
      $('original-body').hidden = true;
      $('original-state').textContent = hints[error.code] || error.message;
      $('original-state').classList.add('error');
    }
  }

  function render(data) {
    for (const kind of ['law', 'case']) {
      const host = $(`${kind}-results`);
      host.replaceChildren();
      const items = data.groups[kind] || [];
      for (const cite of items) host.append(renderCard(cite));
      $(`${kind}-group`).hidden = items.length === 0;
    }
    $('knowledge-notes').textContent = (data.notes || []).join(' ');
    const total = (data.groups.law || []).length + (data.groups.case || []).length;
    if (data.state === 'empty') {
      message('没有命中。检索本身成功，只是没有匹配的来源——这与服务故障不同。');
    } else {
      const degraded = data.degraded || [];
      message(`命中 ${total} 条（法条 ${(data.groups.law || []).length}｜案例 ${(data.groups.case || []).length}）`
        + `${degraded.length ? '；其中一条检索通道未扫完：' + degraded[0].message : ''}`);
    }
  }

  async function submit(event) {
    event.preventDefault();
    const query = $('knowledge-query').value.trim();
    const kinds = [...document.querySelectorAll('input[name="kinds"]:checked')].map((node) => node.value);
    if (!query) { message('请输入关键词。', true); $('knowledge-query').focus(); return; }
    if (!kinds.length) { message('至少选择法条或案例中的一类。', true); return; }
    epoch += 1;
    const localEpoch = epoch;
    controller?.abort();
    controller = new AbortController();
    clearOriginal();
    $('knowledge-submit').disabled = true;
    $('knowledge-groups').setAttribute('aria-busy', 'true');
    message('正在检索并核对来源…');
    try {
      const data = await api('/api/knowledge/search', {
        method: 'POST', signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()},
        body: JSON.stringify({query, kinds, limit: Number($('knowledge-limit').value)}),
      });
      if (localEpoch !== epoch) return;
      render(data);
    } catch (error) {
      if (localEpoch !== epoch || error.name === 'AbortError') return;
      const hints = {
        KB_SERVICE_UNAVAILABLE: '知识服务不可达或超时；输入已保留，服务恢复后可再次检索。',
        KB_SERVICE_DEGRADED: '知识服务的数据源故障，本次没有拿到结果；这不等于"没有命中"，'
          + '输入已保留，服务恢复后可再次检索。',
        KNOWLEDGE_QUERY_INVALID: '检索词不合法：请使用 1–200 字的普通文本。',
        KB_SERVICE_NOT_CONFIGURED: '知识服务未配置，请使用本地资料库或普通对话。',
      };
      message(hints[error.code] || error.message, true);
    } finally {
      if (localEpoch === epoch) {
        $('knowledge-submit').disabled = false;
        $('knowledge-groups').setAttribute('aria-busy', 'false');
      }
    }
  }

  $('knowledge-form').addEventListener('submit', submit);
  $('original-close').addEventListener('click', clearOriginal);

  api('/api/knowledge/status').then((data) => {
    const law = data.assets?.law || {};
    const cases = data.assets?.cases || {};
    $('knowledge-status').textContent =
      `服务就绪｜法条 ${Number(law.units || 0).toLocaleString()} 条/${Number(law.documents || 0).toLocaleString()} 件`
      + `｜案例 ${Number(cases.cases || 0).toLocaleString()} 案｜排序器 ${data.rankers?.case || ''}`
      + `｜线性权重 ${data.rankers?.linear_ranker?.enabled ? '已启用' : '未启用'}`;
  }).catch((error) => {
    $('knowledge-status').textContent = error.code === 'KB_SERVICE_NOT_CONFIGURED'
      ? '知识服务未配置。' : `服务不可用（${error.code || 'UNKNOWN'}）。`;
    $('knowledge-status').classList.add('error');
  });
})();
