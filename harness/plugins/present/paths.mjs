import fs from 'node:fs/promises';
import path from 'node:path';

const producers = new Set([
  'mcp__qx_materials__write_word_draft',
  'mcp__qx_materials__write_review_word',
  'mcp__qx_materials__write_contract_opinion',
  'mcp__qx_materials__generate_document_from_template',
  'mcp__qx_materials__render_custom_word_template',
  'mcp__qx_legal__export_case',
  'mcp__qx_legal__generate_litigation_document',
  'mcp__qx_legal__build_source_bound_litigation',
]);
const key = value => process.platform === 'win32' ? value.toLowerCase() : value;
const same = (a, b) => key(path.resolve(a)) === key(path.resolve(b));
function alias(value) {
  if (typeof value !== 'string' || !value || value.includes('\0') || path.isAbsolute(value)) return;
  const parts = value.replaceAll('\\', '/').split('/');
  if (parts.includes('..') || parts.some(part => part.includes(':'))) return;
  return key(parts.filter(part => part && part !== '.').join('/')) || undefined;
}
function inside(root, file) {
  const relative = path.relative(root, file);
  return relative && !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith('..' + path.sep);
}
function unpack(value) {
  for (let depth = 0; depth < 5; depth++) {
    if (!value || typeof value !== 'object' || value.isError || value.error) return;
    if (value.structuredContent) { value = value.structuredContent; continue; }
    if (!Array.isArray(value.content)) return value;
    try { value = JSON.parse(value.content.filter(item => item.type === 'text').map(item => item.text).join('\n')); }
    catch { return; }
  }
}

export function createDeliveryPaths(ctx, workspace) {
  if (typeof workspace !== 'string' || !path.isAbsolute(workspace)) throw Error('文件交付需要配置当前材料工作区。');
  const root = path.resolve(workspace), sessions = new WeakMap();
  function state(session) {
    let value = sessions.get(session);
    if (!value) { value = {receipts: new Map(), restored: false}; sessions.set(session, value); }
    return value;
  }
  function remember(receipts, name, message) {
    if (!producers.has(name)) return;
    const value = unpack(message);
    if (!value) return;
    const candidates = ['draft', 'partial'].includes(value.status) ? [value, value.html, value.word] : [];
    if (value.delivery?.version === 1 && Array.isArray(value.delivery.documents)) candidates.push(...value.delivery.documents);
    for (const item of candidates) {
      if (!item || typeof item.path !== 'string' || item.path.includes('\0') || !path.isAbsolute(item.path)) continue;
      const target = path.resolve(item.path);
      if (!inside(root, target)) continue;
      const relative = item.relative_path ?? path.relative(root, target);
      const name = alias(relative);
      if (name && same(path.resolve(root, relative), target)) receipts.set(name, target);
    }
  }
  ctx.on('tools/result', (exec, result) => {
    if (exec.agent && producers.has(exec.name)) remember(state(exec.agent.session).receipts, exec.name, result);
  });
  async function restore(session, value, signal) {
    if (value.restored) return;
    if (!value.restoring) value.restoring = (async () => {
      const records = await ctx.sessionQuery.listEvents(session.id), calls = new Map(), history = new Map();
      for (const record of records) {
        signal.throwIfAborted();
        if (record.surface !== 'current' || !['tool/call', 'tool/result'].includes(record.type)) continue;
        const {target} = await ctx.sessionQuery.readEvent({sessionId: session.id, seq: record.seq, before: 0, after: 0}, signal);
        if (target.type === 'tool/call') {
          if (producers.has(target.data.name)) calls.set(target.data.callId, target.data.name);
        } else {
          const message = target.data.message;
          const name = calls.get(message?.toolCallId);
          if (name) remember(history, name, message);
        }
      }
      // A generation may complete during the history read; its live receipt wins.
      for (const [name, target] of history) if (!value.receipts.has(name)) value.receipts.set(name, target);
      value.restored = true;
    })().finally(() => { value.restoring = undefined; });
    await value.restoring;
  }
  return async function resolveFiles(files, exec) {
    if (!exec.agent || !files.some(file => alias(file.path))) return files;
    const session = exec.agent.session, value = state(session);
    await restore(session, value, exec.signal);
    const cwd = await ctx.workingDirectory.ensure(exec.agent, exec.signal), resolved = [];
    for (const file of files) {
      exec.signal.throwIfAborted();
      const target = value.receipts.get(alias(file.path));
      if (!target) { resolved.push(file); continue; }
      // Resolve links at use time: a stale receipt cannot redirect to another directory.
      const [realRoot, realTarget, entry] = await Promise.all([fs.realpath(root), fs.realpath(target), fs.lstat(target)]);
      if (!entry.isFile() || !inside(realRoot, realTarget)) throw Error('生成文件位置已变化，请重新生成或明确选择文件。');
      const local = await ctx.fs.lstat(file.path, {cwd}, exec.signal);
      if (local !== undefined) {
        const localPath = await ctx.fs.resolve(file.path, {cwd, signal: exec.signal});
        if (!same(await fs.realpath(ctx.fs.processPath(localPath)), realTarget)) throw Error('对话目录与生成记录存在同名文件，请使用生成结果中的完整路径明确选择。');
      }
      resolved.push({...file, path: target});
    }
    return resolved;
  };
}
