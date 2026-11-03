'use strict';
// 产品级前端回归：把生产 knowledge.js 放进最小 DOM 里跑，手动控制响应到达顺序。
//
// 外部审计（review/workbench_citation_repro.cjs）已经用同样的办法证明旧版会出这两个
// 问题；那个脚本是只读的，这里不改它，而是写一份**断言修好之后行为**的回归：
// 迟到响应不许覆盖新选择、版本不一致必须阻断、关闭后不许回填。
//
// 用法：node tests/workbench_ui_check.cjs [源码路径]
// 传一个"旧版本"副本就能看到同一套断言在旧代码上失败。
//
// 响应推进用 setImmediate 打点，不 await openOriginal 返回的 promise：
// 这里要观察的是"用户看到的最终状态"，而不是某个 promise 何时结算。
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');

const sourcePath = process.argv[2]
  || process.env.KB_UI_SOURCE
  || require('node:path').resolve(__dirname, '../../../src/cn_contract/web/static/knowledge.js');
const production = fs.readFileSync(sourcePath, 'utf8');
const digest = text => crypto.createHash('sha256').update(text).digest('hex');
const tick = (rounds = 8) => new Promise(resolve => {
  let left = rounds;
  const step = () => { left -= 1; if (left <= 0) resolve(); else setImmediate(step); };
  setImmediate(step);
});

function setup() {
  const elements = new Map();
  const waiting = [];
  function element() {
    return {
      textContent: '', hidden: false, children: [], id: '',
      classList: {add() {}, remove() {}, toggle() {}},
      append(...nodes) { this.children.push(...nodes); },
      replaceChildren(...nodes) { this.children = nodes; this.textContent = ''; },
      focus() {}, addEventListener() {},
    };
  }
  const at = id => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  const context = {
    AbortController,
    document: {
      getElementById: at, querySelectorAll: () => [],
      createElement: element, createTextNode: text => ({textContent: text}),
    },
    fetch: (url) => {
      if (String(url).endsWith('/status')) {
        return Promise.resolve({ok: true, json: async () => ({assets: {}, rankers: {}}) });
      }
      return new Promise(resolve => waiting.push({url: String(url), resolve}));
    },
    console,
  };
  context.globalThis = context;
  // 只在临时源码里暴露函数，生产文件不动。
  const instrumented = production.replace(/\}\)\(\);\s*$/,
    'globalThis.reviewHooks={openOriginal,clearOriginal};})();');
  vm.runInNewContext(instrumented, context, {filename: sourcePath});

  function take(fragment) {
    const index = waiting.findIndex(item => item.url.includes(fragment));
    assert.notEqual(index, -1, `没有等待中的请求：${fragment}`);
    return waiting.splice(index, 1)[0];
  }
  function reply(entry, {text, sha256, sourceId, ok = true, error = null}) {
    if (!ok) {
      entry.resolve({ok: false, status: 409,
        json: async () => error || {code: 'KNOWLEDGE_SOURCE_STALE', message: '来源版本已变化'}});
      return;
    }
    entry.resolve({
      ok: true,
      json: async () => ({
        source_id: sourceId,
        source_version: {sha256, basis: 'documents.sha256+raw_text_recomputed', verified: 'recomputed'},
        title: 't',
        location: {line_start: 1, line_end: 1, char_start: 0, char_end: text.length, basis: 'line_map'},
        whole_block: {start: 0, end: text.length},
        content: {text, start: 0, end: text.length, truncated: false,
          full_length: text.length, sha256: digest(text)},
        verification: {support: 'unverified', applicability: 'unverified'},
      }),
    });
  }
  const state = () => ({
    title: at('original-title').textContent,
    text: at('original-text').textContent,
    message: at('original-state').textContent,
    bodyHidden: at('original-body').hidden === true,
    panelHidden: at('original-panel').hidden === true,
  });
  return {hooks: context.reviewHooks, element, take, reply, state};
}

const citation = (id, title, sha) => ({
  source_id: id, title, source_version: {sha256: sha},
  snippet: {match_start: null, match_end: null},
});

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({name, passed: true});
  } catch (error) {
    results.push({name, passed: false, detail: error.message});
  }
}

const VERSION = digest('a registered immutable snapshot');
const A = 'case_book:2026年度案例【买卖合同纠纷】#001';
const B = 'case_book:2026年度案例【买卖合同纠纷】#002';

(async () => {
  // 1. A→B，B 先回、A 后回：最终必须是 B 的标题与 B 的正文
  const race = setup();
  race.hooks.openOriginal(citation(A, '引用 A', VERSION), race.element());
  race.hooks.openOriginal(citation(B, '引用 B', VERSION), race.element());
  const entryB = race.take(encodeURIComponent(B));
  const entryA = race.take(encodeURIComponent(A));
  race.reply(entryB, {text: '案例 B 的正文', sha256: VERSION, sourceId: B});
  await tick();
  const afterB = race.state();
  race.reply(entryA, {text: '案例 A 的正文', sha256: VERSION, sourceId: A});
  await tick();
  const afterLateA = race.state();
  check('B 先返回时显示 B 的正文', () => {
    assert.equal(afterB.title, '引用 B');
    assert.equal(afterB.text, '案例 B 的正文');
  });
  check('迟到响应不覆盖后选择的引用', () => {
    assert.equal(afterLateA.title, '引用 B');
    assert.equal(afterLateA.text, '案例 B 的正文');
  });

  // 2. 请求必须带上检索时的版本，服务端才有东西可比
  check('回读请求携带检索时的来源版本', () => {
    assert.ok(entryA.url.includes('version=' + VERSION), `URL 未带版本：${entryA.url}`);
    assert.ok(entryB.url.includes('version=' + VERSION), `URL 未带版本：${entryB.url}`);
  });

  // 3. 检索版本与回读版本不一致：阻断，且不许出现"一致 / 校验通过"
  const mismatch = setup();
  const stale = digest('older registered source text');
  const newer = digest('新版来源正文');
  mismatch.hooks.openOriginal(citation(A, '旧版检索结果', stale), mismatch.element());
  const entryM = mismatch.take(encodeURIComponent(A));
  mismatch.reply(entryM, {text: '新版来源正文', sha256: newer, sourceId: A});
  await tick();
  const afterMismatch = mismatch.state();
  check('版本不一致时阻断显示', () => {
    assert.ok(afterMismatch.bodyHidden, '版本不一致时仍然显示了正文');
    assert.ok(!afterMismatch.message.includes('一致（'), `仍宣称一致：${afterMismatch.message}`);
    assert.ok(/不一致|已阻断|已变化/.test(afterMismatch.message), `提示不明确：${afterMismatch.message}`);
  });

  // 4. 关闭面板后迟到的成功响应不许把内容填回来
  const closed = setup();
  closed.hooks.openOriginal(citation(A, '引用 A', VERSION), closed.element());
  const entryC = closed.take(encodeURIComponent(A));
  closed.hooks.clearOriginal();
  closed.reply(entryC, {text: '案例 A 的正文', sha256: VERSION, sourceId: A});
  await tick();
  const afterClosed = closed.state();
  check('关闭后不回填迟到响应', () => {
    assert.ok(afterClosed.panelHidden, '面板被迟到的响应重新打开了');
    assert.equal(afterClosed.text, '');
  });

  // 5. 迟到的失败不许覆盖已成功的新选择
  const lateError = setup();
  lateError.hooks.openOriginal(citation(A, '引用 A', VERSION), lateError.element());
  lateError.hooks.openOriginal(citation(B, '引用 B', VERSION), lateError.element());
  const entryE2 = lateError.take(encodeURIComponent(B));
  const entryE1 = lateError.take(encodeURIComponent(A));
  lateError.reply(entryE2, {text: '案例 B 的正文', sha256: VERSION, sourceId: B});
  await tick();
  lateError.reply(entryE1, {ok: false, error: {code: 'KB_SERVICE_UNAVAILABLE', message: '不可达'}});
  await tick();
  const afterLateError = lateError.state();
  check('迟到的失败不覆盖已成功的新选择', () => {
    assert.equal(afterLateError.title, '引用 B');
    assert.equal(afterLateError.text, '案例 B 的正文');
    assert.ok(!/不可达/.test(afterLateError.message), `提示被迟到错误覆盖：${afterLateError.message}`);
  });

  const failed = results.filter(item => !item.passed);
  console.log(JSON.stringify({
    checked_at_utc: new Date().toISOString(),
    source_path: sourcePath,
    source_sha256: digest(production),
    method: '生产 knowledge.js 在最小 DOM 与确定性响应顺序下执行；前端行为回归，不是浏览器端到端。',
    checks: results,
    passed: results.length - failed.length,
    failed: failed.length,
  }, null, 2));
  process.exitCode = failed.length ? 1 : 0;
})();
