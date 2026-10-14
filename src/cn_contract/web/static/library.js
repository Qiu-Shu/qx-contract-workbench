'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  let page = null, original = null, currentQuery = null, queryEpoch = 0, originalEpoch = 0;
  let queryController = null, originalController = null;
  const csrf = () => decodeURIComponent(document.cookie.split('; ').find((part) => part.startsWith('qx_csrf='))?.slice(8) || '');
  function message(id, text, error = false) {
    $(id).textContent = text;
    $(id).classList.toggle('error', error);
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: 'same-origin', ...options});
    const data = await response.json();
    if (!response.ok) {
      throw new Error(response.status === 401 ? '登录已失效，请重新登录后检索。' : (data.message || '请求未完成，请检查条件后重试。'));
    }
    return data;
  }
  function coverage(data) {
    const c = data.coverage || {};
    $('coverage').textContent = data.state === 'not_ready' ? '索引尚未就绪，收录范围暂不可用。' :
      `当前可检索：${(c.case_csv || 0).toLocaleString()} 条案例 · ${(c.law_markdown || 0).toLocaleString()} 份法规版本`;
  }
  function clearOriginal() {
    originalEpoch += 1;
    originalController?.abort();
    original = null;
    $('original-content').hidden = true;
    $('original-text').replaceChildren();
    $('close-original').disabled = true;
    document.querySelectorAll('.result.selected').forEach((node) => node.classList.remove('selected'));
    message('original-state', '选择一条结果，查看原文、版本和来源。');
  }
  function node(tag, text, className) {
    const result = document.createElement(tag);
    result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function details(label, value) {
    $('source-details').append(node('dt', label), node('dd', value || '未提供'));
  }
  async function showOriginal(hit, element) {
    clearOriginal();
    const epoch = originalEpoch;
    originalController = new AbortController();
    message('original-state', '正在核对来源字节与版本…');
    try {
      const path = hit.fragment_id ? `/api/library/fragments/${hit.fragment_id}` :
        `/api/library/records/${hit.record_id}?version_id=${hit.version_id}`;
      const data = await api(path, {signal: originalController.signal});
      if (epoch !== originalEpoch) return;
      if (data.record.record_id !== hit.record_id || data.record.version_id !== hit.version_id) throw new Error('返回的资料版本不一致，请重新检索。');
      original = data;
      element.classList.add('selected');
      $('source-title').textContent = hit.title;
      $('source-details').replaceChildren();
      details('核验状态', '待核验 · 原文字节已比对，法律效力未确认');
      details('资料版本', data.record.version_id);
      details('本机来源', data.source.aliases.join('\n'));
      details('官方出处', data.record.fields.source_url || '尚未核实官方来源');
      details('定位', data.fragment ? `原文第 ${data.fragment.line_start}—${data.fragment.line_end} 行${data.fragment.ambiguous ? ' · 条号有歧义' : ''}` : `来源第 ${data.record.ordinal} 条记录`);
      $('source-raw').textContent = JSON.stringify({source: data.source, record: data.record, raw_fields: data.raw_fields}, null, 2);
      // Python locations count Unicode code points, not UTF-16 code units.
      const chars = Array.from(data.text);
      const focus = hit.match_start ?? data.fragment?.start ?? 0;
      const start = chars.length > 200000 ? Math.max(0, focus - 10000) : 0;
      const end = chars.length > 200000 ? Math.min(chars.length, start + 50000) : chars.length;
      const text = $('original-text');
      text.replaceChildren();
      if (hit.match_start !== null && hit.match_start >= start && hit.match_end <= end) {
        text.append(document.createTextNode(chars.slice(start, hit.match_start).join('')));
        text.append(node('mark', chars.slice(hit.match_start, hit.match_end).join('')));
        text.append(document.createTextNode(chars.slice(hit.match_end, end).join('')));
      } else text.textContent = chars.slice(start, end).join('');
      $('original-content').hidden = false;
      $('close-original').disabled = false;
      message('original-state', chars.length > 200000 ? `长文当前显示第 ${start + 1}—${end} 字；可导出完整原文与来源。` : '原文已打开；来源与法律结论仍需人工核验。');
      text.querySelector('mark')?.scrollIntoView({block: 'center', behavior: 'instant'});
      $('source-title').focus({preventScroll: true});
    } catch (error) {
      if (epoch === originalEpoch && error.name !== 'AbortError') message('original-state', error.message, true);
    }
  }
  function renderResults(data) {
    $('results').replaceChildren();
    // Group multiple article hits within this page by exact record and version.
    const groups = new Map();
    for (const hit of data.hits) {
      const key = `${hit.record_id}:${hit.version_id}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(hit);
    }
    for (const hits of groups.values()) {
      const hit = hits[0];
      const article = node('article', '', 'result');
      const heading = node('h3', '');
      const title = node('button', hit.title, 'result-button');
      title.type = 'button';
      title.addEventListener('click', () => showOriginal(hit, article));
      heading.append(title);
      const fields = hit.fields;
      const meta = hit.kind === 'case_csv' ? [fields.case_no, fields.court, fields.decision_date] :
        [fields.region_candidate, fields.filename_date_candidate ? `${fields.filename_date_candidate}（文件名日期）` : null];
      article.append(heading, node('p', meta.filter(Boolean).join(' · ') || '来源字段待补核', 'result-meta'),
        node('span', `待核验${hit.body_status === 'catalog_only' ? ' · 仅目录' : ''}`, 'status-label'), node('p', hit.snippet));
      for (const item of hits.filter((h) => h.fragment_id)) {
        const button = node('button', `${item.article || '原文段落'}${item.ambiguous ? '（条号有歧义）' : ''}`, 'secondary fragment-button');
        button.type = 'button';
        button.addEventListener('click', () => showOriginal(item, article));
        article.append(button);
      }
      $('results').append(article);
    }
    const prefix = data.state === 'timeout' ? '检索达到时间上限；当前结果不代表全部匹配，请增加筛选条件。' :
      data.state === 'not_ready' ? '索引尚未就绪，请待收录完成后重试。' :
      data.hits.length ? `本页 ${groups.size} 份资料，${data.hits.length} 个原文位置。` : '当前收录范围内未找到匹配，可减少条件或换用关键词。';
    message('message', prefix, data.state === 'timeout');
    $('next-page').hidden = !data.next_cursor || data.state !== 'ready';
    $('export-results').disabled = !data.hits.length;
  }
  async function runSearch(next = false) {
    queryEpoch += 1;
    const epoch = queryEpoch;
    queryController?.abort();
    queryController = new AbortController();
    clearOriginal();
    const cursor = next ? page?.next_cursor : null;
    if (!next) {
      currentQuery = Object.fromEntries([...new FormData($('search-form')).entries()].filter(([, value]) => value.trim() !== ''));
      currentQuery.limit = 20;
    }
    page = null;
    $('results').replaceChildren();
    $('next-page').hidden = true;
    $('export-results').disabled = true;
    $('search-button').disabled = true;
    $('results').setAttribute('aria-busy', 'true');
    message('message', '正在检索并核对原文…');
    try {
      const data = await api('/api/library/search', {method: 'POST', signal: queryController.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()}, body: JSON.stringify({...currentQuery, cursor})});
      if (epoch !== queryEpoch) return;
      page = data;
      coverage(data);
      renderResults(data);
    } catch (error) {
      if (epoch === queryEpoch && error.name !== 'AbortError') message('message', error.message, true);
    } finally {
      if (epoch === queryEpoch) {
        $('search-button').disabled = false;
        $('results').setAttribute('aria-busy', 'false');
      }
    }
  }
  function download(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('search-form').addEventListener('submit', (event) => {event.preventDefault(); runSearch();});
  $('search-form').addEventListener('reset', () => {
    queryEpoch += 1; queryController?.abort(); clearOriginal(); page = null; currentQuery = null;
    $('results').replaceChildren(); $('results').setAttribute('aria-busy', 'false');
    $('next-page').hidden = true; $('export-results').disabled = true; $('search-button').disabled = false;
    message('message', '条件已清空，可以开始新的检索。'); $('query').focus();
  });
  $('next-page').addEventListener('click', () => runSearch(true));
  $('close-original').addEventListener('click', clearOriginal);
  $('font-size').addEventListener('change', (event) => {$('original-text').className = event.target.value;});
  $('export-results').addEventListener('click', () => {if (page) download({query: currentQuery, page, review_status: 'unverified'}, '群兴资料库-检索本页.json');});
  $('export-original').addEventListener('click', () => {if (original) download(original, '群兴资料库-原文与来源.json');});
  api('/api/library/status').then(coverage).catch((error) => message('coverage', error.message, true));
})();
