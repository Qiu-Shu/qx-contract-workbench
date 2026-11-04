// Offline, exhaustive Skill loading and resource audit. Does not invoke a model,
// execute bundled scripts, connect external services, or read customer files.
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {access, mkdir, readFile, readdir, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {basename, dirname, extname, isAbsolute, join, relative, resolve, sep} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const slash = value => value.replaceAll('\\', '/');
const sha = value => createHash('sha256').update(value).digest('hex');
const exists = async path => access(path).then(() => true, () => false);
const inside = (path, parent) => { const r = relative(parent, path); return !r.startsWith(`..${sep}`) && r !== '..' && !isAbsolute(r); };
async function walk(path) {
  const files = [];
  for (const entry of await readdir(path, {withFileTypes: true})) {
    if (entry.isSymbolicLink()) continue;
    const full = join(path, entry.name);
    if (entry.isDirectory()) files.push(...await walk(full));
    else if (entry.isFile()) files.push(full);
  }
  return files.sort();
}

// Only explicit local resource paths are errors when absent. Bare filenames,
// output examples, URLs and runtime placeholders are recorded separately.
export function extractReferences(content) {
  const refs = new Map();
  const add = (value, kind, offset) => {
    let raw = value.trim().replace(/^<|>$/g, '').replace(/\s+["'][^"']*["']$/, '');
    if (!raw || /^(?:[a-z][a-z\d+.-]*:|#|\/\/)/i.test(raw)) return;
    try { raw = decodeURIComponent(raw.split('#')[0].split('?')[0]); } catch {}
    if (!raw || /[{}*]|<[^>]+>|\[[^\]]+\]/.test(raw)) return;
    const token = raw.replace(/^<skill(?:-base-dir)?>\//, '').replace(/^\.agents\/skills\/[^/]+\//, '');
    const line = content.slice(0, offset).split('\n').length;
    const key = `${token}:${line}`;
    const context = content.split('\n').slice(Math.max(0, line - 2), line).join('\n');
    const fenced = (content.slice(0, offset).match(/^\s*```/gm) ?? []).length % 2 === 1;
    if (!refs.has(key)) refs.set(key, {path: token, kind, line, context, fenced});
  };
  for (const match of content.matchAll(/\[[^\]\n]*\]\(([^)\n]+)\)/g)) add(match[1], 'markdown-link', match.index);
  for (const match of content.matchAll(/(?:^|[\s`"'(])((?:legal-library\/|(?:\.\.\/|\.\/)*(?:references?|scripts|assets|templates)\/)[^\s`"'()，。；]+?)(?=[\s`"'()，。；]|$)/gm)) {
    add(match[1].replace(/[.,;:]+$/, ''), 'resource-path', match.index);
  }
  return [...refs.values()];
}

export function referenceClassification(reference, source) {
  if (reference.path === 'URL' || reference.path === 'path/to/file') return 'example';
  if (/^legal-library\/en\//.test(reference.path) && /如存在|if (?:it )?exists/i.test(reference.context)) return 'optional-translation';
  if (/(?:缓存到|追踪已驳回|writes.*|records.*|写入|生成|下载到)/i.test(reference.context) && /(?:references\/(?:registry-cache|surfaced)\.json|assets\/credits\.json)$/.test(reference.path)) return 'generated-output';
  if (reference.fenced && reference.path.startsWith('assets/')) return 'example';
  if (reference.path.startsWith('assets/') && /<(?:video|source|img)\b/i.test(reference.context)) return 'example';
  if (/README\.md$/i.test(source) && reference.kind === 'markdown-link' && !reference.path.includes('/')) return 'upstream-documentation';
  return 'required-resource';
}

export function nestedCalls(content, aliases, names) {
  const calls = new Map();
  for (const match of content.matchAll(/\/([a-z][a-z\d-]+):([a-z][a-z\d-]+)/g)) {
    const original = `/${match[1]}:${match[2]}`;
    const resolved = aliases.get(original);
    calls.set(original, {original, resolved: resolved ?? null, status: resolved && names.has(resolved) ? 'resolved' : 'unresolved'});
  }
  for (const match of content.matchAll(/`((?:legal-zh-|chinese-legal-|qx-)[a-z\d-]+)`/g)) {
    const name = match[1];
    calls.set(name, {original: name, resolved: names.has(name) ? name : null, status: names.has(name) ? 'resolved' : 'unresolved'});
  }
  return [...calls.values()].sort((a, b) => a.original.localeCompare(b.original));
}

async function providerLocation(providerEntry) {
  if (providerEntry) return resolve(providerEntry);
  const store = join(root, 'node_modules/.pnpm');
  const packages = (await readdir(store)).filter(name => name.startsWith('@deepseek-ai+dsh-skill-file'));
  if (packages.length !== 1) throw new Error(`Expected one filesystem provider; found ${packages.length}. Pass --provider explicitly.`);
  const packageDir = join(store, packages[0], 'node_modules/@deepseek-ai/dsh-skill-filesystem');
  return createRequire(join(packageDir, 'package.json')).resolve('@deepseek-ai/dsh-skill-filesystem');
}

async function auditWorkspace(label, workspace, Provider, out, labels) {
  const skillRoot = join(workspace, '.dsh/skills');
  const files = await walk(skillRoot);
  const skillFiles = files.filter(path => basename(path).toLowerCase() === 'skill.md');
  const manifestPath = join(workspace, 'legal-library/skill-catalog.json');
  const catalog = await exists(manifestPath) ? JSON.parse(await readFile(manifestPath, 'utf8')) : null;
  const workflows = catalog?.workflows ?? [];
  const entries = catalog?.entries ?? [];
  const catalogByName = new Map([...workflows, ...entries].map(item => [item.name, item]));
  const aliases = new Map(workflows.map(item => [`/${item.domain}:${item.original_name}`, item.name]));
  const warnings = [], controller = new AbortController();
  const provider = new Provider({get: () => undefined, logger: {warn: message => warnings.push(String(message))}},
    {signal: controller.signal, invalidate() {}},
    {watch: false, dshHome: join(out, 'isolated/dsh'), agentsHome: join(out, 'isolated/agents'), bundledSkillDir: join(out, 'isolated/bundled')});
  const rows = [], errors = [];
  try {
    const observation = await provider.list({cwd: workspace});
    const candidates = Array.isArray(observation) ? observation : observation.candidates;
    const names = new Set(candidates.map(candidate => candidate.name));
    const discovered = new Set(candidates.map(candidate => resolve(candidate.path).toLowerCase()));
    for (const path of skillFiles) {
      if (!discovered.has(resolve(path).toLowerCase())) errors.push({type: 'not-discovered', path: slash(relative(workspace, path))});
    }
    for (const name of names) {
      if (candidates.filter(candidate => candidate.name === name).length > 1) errors.push({type: 'duplicate-name', name});
    }
    for (const candidate of candidates) {
      const row = {name: candidate.name, chineseName: labels[candidate.name] ?? null, description: candidate.description, path: slash(relative(workspace, candidate.path)), issues: [], advisories: [], dependencies: [], calls: [], references: [], scripts: []};
      rows.push(row);
      try {
        const loaded = await provider.get(candidate, {cwd: workspace});
        row.loaded = true;
        row.modelInvocable = loaded.invocation?.modelInvocable === true;
        row.characters = loaded.content.length;
        row.resourceBase = slash(relative(workspace, loaded.resourceBase.path));
        if (!row.modelInvocable) row.issues.push({type: 'model-invocation-disabled'});
        if (!loaded.content.trim()) row.issues.push({type: 'empty-body'});
        const bundleRoot = loaded.resourceBase.path;
        const bundleFiles = files.filter(path => inside(path, bundleRoot));
        const hashes = [];
        for (const path of bundleFiles) hashes.push([slash(relative(bundleRoot, path)), sha(await readFile(path))]);
        row.fileCount = hashes.length;
        row.bundleSha256 = sha(JSON.stringify(hashes));
        row.fileHashes = Object.fromEntries(hashes);
        const info = catalogByName.get(row.name);
        if (info) {
          for (const sourcePath of [info.source, info.context, ...Object.values(info.resources ?? {})].filter(Boolean)) {
            const target = resolve(workspace, sourcePath);
            if (!inside(target, workspace)) row.issues.push({type: 'catalog-outside-workspace', path: sourcePath});
            else if (!await exists(target)) row.issues.push({type: 'missing-catalog-source', path: sourcePath});
          }
          for (const [target, source] of Object.entries(info.resources ?? {})) {
            const targetPath = resolve(bundleRoot, target);
            if (!inside(targetPath, bundleRoot)) row.issues.push({type: 'resource-outside-bundle', path: target});
            else if (!await exists(targetPath)) row.issues.push({type: 'missing-catalog-resource', path: target, source});
          }
        }
        for (const file of bundleFiles.filter(path => extname(path).toLowerCase() === '.md')) {
          const content = await readFile(file, 'utf8');
          const source = slash(relative(bundleRoot, file));
          for (const reference of extractReferences(content)) {
            const ref = {...reference, source, classification: referenceClassification(reference, source)};
            // references/... in secondary documents denotes the bundle root;
            // ordinary Markdown relative links denote that document's folder.
            const explicitWorkspace = ref.path.startsWith('legal-library/');
            const direct = resolve(explicitWorkspace ? workspace : dirname(file), ref.path);
            const rootRelative = resolve(bundleRoot, ref.path);
            const candidates = explicitWorkspace ? [direct] : [direct, rootRelative];
            const target = (await Promise.all(candidates.map(async path => inside(path, workspace) && await exists(path) ? path : null))).find(Boolean);
            ref.status = target ? 'exists' : 'missing';
            if (target) ref.resolved = slash(relative(workspace, target));
            row.references.push(ref);
            if (!target) (ref.classification === 'required-resource' ? row.issues : row.advisories).push({type: 'missing-local-reference', ...ref});
          }
          row.calls.push(...nestedCalls(content, aliases, names).map(call => ({...call, source})));
        }
        for (const call of row.calls.filter(call => call.status === 'unresolved')) {
          const destination = /README\.md$/i.test(call.source) ? row.advisories : row.issues;
          destination.push({type: 'unresolved-skill-call', ...call});
        }
        const dependencies = {
          browser: /bb-browser|浏览器.*(?:连接|授权|登录)/i,
          network: /联网|web.?search|https?:\/\//i,
          'external-service-mentions': /\b(?:Slack|Notion|SharePoint|CoCounsel|iManage|NetDocuments|CLM|DMS|Gmail|Outlook|Ironclad|DocuSign|Salesforce|Carta|Juro)\b/i,
          'local-qx-legal-tools': /mcp__qx_legal__|qx_legal\./,
          'local-qx-materials-tools': /qx_materials/,
          'scheduled-runtime': /(?:定时|自动监控|周期(?:性|任务))/,
        };
        for (const [dependency, pattern] of Object.entries(dependencies)) if (pattern.test(loaded.content)) row.dependencies.push(dependency);
        row.externalServiceMentions = [...new Set((loaded.content.match(/\b(?:Slack|Notion|SharePoint|CoCounsel|iManage|NetDocuments|CLM|DMS|Gmail|Outlook|Ironclad|DocuSign|Salesforce|Carta|Juro)\b/gi) ?? []).map(value => value.toLowerCase()))].sort();
        for (const file of bundleFiles.filter(path => /(?:^|[\\/])scripts[\\/]/.test(path))) {
          if (/\.(?:py|mjs|cjs|js|sh|cmd|ps1|exe)$/.test(file) || !extname(file)) {
            const script = {path: slash(relative(bundleRoot, file)), exists: true, executed: false, localImports: []};
            row.scripts.push(script);
            if (/\.(?:mjs|cjs|js)$/.test(file)) {
              const content = await readFile(file, 'utf8');
              for (const match of content.matchAll(/(?:from\s*|import\s*\(|require\s*\()\s*['"](\.[^'"]+)['"]/g)) {
                const target = resolve(dirname(file), match[1]);
                const present = inside(target, bundleRoot) && await exists(target);
                script.localImports.push({path: match[1], exists: present});
                if (!present) row.issues.push({type: 'missing-script-import', source: script.path, path: match[1]});
              }
            }
          }
        }
        row.status = row.issues.length ? 'needs-review' : 'load-and-resources-ok';
      } catch (error) {
        row.loaded = false;
        row.status = 'load-failed';
        row.issues.push({type: 'load-error', message: String(error)});
      }
    }
    return {label, workspace, complete: Array.isArray(observation) || observation.complete, catalogExpected: catalog?.discoverable_count ?? null,
      discovered: candidates.length, diskSkillFiles: skillFiles.length, loaded: rows.filter(row => row.loaded).length,
      modelInvocable: rows.filter(row => row.modelInvocable).length, warnings, errors, rows: rows.sort((a, b) => a.name.localeCompare(b.name))};
  } finally {
    controller.abort();
    await provider.dispose();
  }
}

export function compareWorkspaces(source, target) {
  const first = new Map(source.rows.map(row => [row.name, row]));
  const second = new Map(target.rows.map(row => [row.name, row]));
  const differences = [];
  for (const [name, row] of first) {
    const other = second.get(name);
    if (!other) differences.push({name, type: 'missing-skill'});
    else if (row.bundleSha256 !== other.bundleSha256) {
      const paths = new Set([...Object.keys(row.fileHashes ?? {}), ...Object.keys(other.fileHashes ?? {})]);
      differences.push({name, type: 'different-bundle', files: [...paths].filter(path => row.fileHashes[path] !== other.fileHashes[path])});
    }
  }
  for (const name of second.keys()) if (!first.has(name)) differences.push({name, type: 'extra-skill'});
  return {source: source.label, target: target.label, differences};
}

function selfTest() {
  const refs = extractReferences('[Needed](references/missing.md)\n[Web](https://example.com/a.md)\n`assets/scenes/demo/<id>.html`\n[Example](URL)\n将索引缓存到本地（`references/registry-cache.json`）。\n英文对应版本（如存在）在 `legal-library/en/foo/SKILL.md`。');
  assert.ok(refs.some(ref => ref.path === 'references/missing.md'));
  assert.ok(!refs.some(ref => ref.path.includes('https:') || ref.path.includes('<id>')));
  assert.equal(referenceClassification(refs.find(ref => ref.path === 'references/missing.md'), 'SKILL.md'), 'required-resource');
  assert.equal(referenceClassification(refs.find(ref => ref.path === 'URL'), 'SKILL.md'), 'example');
  assert.equal(referenceClassification(refs.find(ref => ref.path === 'references/registry-cache.json'), 'SKILL.md'), 'generated-output');
  assert.equal(referenceClassification(refs.find(ref => ref.path.startsWith('legal-library/en/')), 'SKILL.md'), 'optional-translation');
  const names = new Set(['legal-zh-privacy-dpa-review', 'qx-contract-review']);
  const calls = nestedCalls('/privacy-legal:dpa-review /unknown-legal:missing `qx-contract-review`', new Map([['/privacy-legal:dpa-review', 'legal-zh-privacy-dpa-review']]), names);
  assert.equal(calls.find(call => call.original === '/privacy-legal:dpa-review').status, 'resolved');
  assert.equal(calls.find(call => call.original === '/unknown-legal:missing').status, 'unresolved');
  assert.equal(calls.find(call => call.original === 'qx-contract-review').status, 'resolved');
  console.log('Skill audit parser checks passed: required resource, example, dynamic path, generated cache, optional translation, cross-domain and unknown aliases.');
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 1 && argv[0] === '--self-test') return selfTest();
  let workspace = join(root, 'workspace'), out = join(root, '.local/skill-audit'), providerEntry;
  const comparisons = [];
  while (argv.length) {
    const option = argv.shift(), value = argv.shift();
    if (!value) throw new Error(`Missing value for ${option}`);
    if (option === '--workspace') workspace = resolve(value);
    else if (option === '--out') out = resolve(value);
    else if (option === '--provider') providerEntry = value;
    else if (option === '--compare') {
      const index = value.indexOf('=');
      if (index < 1) throw new Error('--compare requires label=workspace-path');
      comparisons.push([value.slice(0, index), resolve(value.slice(index + 1))]);
    } else throw new Error(`Unknown option ${option}`);
  }
  await mkdir(out, {recursive: true});
  providerEntry = await providerLocation(providerEntry);
  const {FileSystemSkillProvider} = await import(pathToFileURL(providerEntry).href);
  const labelsPath = join(root, 'config/skill-labels.zh-CN.json');
  const labels = await exists(labelsPath) ? JSON.parse(await readFile(labelsPath, 'utf8')).labels ?? {} : {};
  const workspaces = [];
  for (const [label, path] of [['source', workspace], ...comparisons]) workspaces.push(await auditWorkspace(label, path, FileSystemSkillProvider, out, labels));
  const comparison = workspaces.slice(1).map(target => compareWorkspaces(workspaces[0], target));
  const report = {generatedAt: new Date().toISOString(), providerEntry,
    scope: 'Every Skill is listed and loaded through the official filesystem provider. Static bundled references, catalog resources and qualified nested Skill names are checked. Bundled scripts and external services are not executed; model reasoning and legal output quality are not tested. Bare input/output filenames and dynamic paths are not classified as broken resources.',
    workspaces, comparison};
  await writeFile(join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  const lines = ['# Skill 逐项可调用性与资源审计', '', report.scope, ''];
  for (const item of workspaces) {
    lines.push(`## ${item.label}`, '', `路径：${item.workspace}`, '', `发现 ${item.discovered}；实际加载 ${item.loaded}；允许模型调用 ${item.modelInvocable}；加载警告 ${item.warnings.length}。`, '',
      '| 中文名 | Skill ID | 加载 | 资源与嵌套调用 | 外部/运行条件 |', '|---|---|---|---|---|');
    for (const row of item.rows) lines.push(`| ${row.chineseName ?? '未标注'} | ${row.name} | ${row.loaded ? '通过' : '失败'} | ${row.issues.length ? `${row.issues.length} 项待核对` : '通过'} | ${row.dependencies.join('、') || '无静态标记'} |`);
    lines.push('', '逐条引用、调用映射和问题详情见同目录 report.json。', '');
  }
  for (const item of comparison) lines.push(`## ${item.source} → ${item.target}`, '', `${item.differences.length} 个 Skill 副本不同。`, '', ...item.differences.map(diff => `- ${diff.name}: ${diff.type}${diff.files ? ` (${diff.files.join(', ')})` : ''}`), '');
  await writeFile(join(out, 'report.md'), lines.join('\n'));
  console.log(JSON.stringify({out, workspaces: workspaces.map(item => ({label: item.label, discovered: item.discovered, loaded: item.loaded, modelInvocable: item.modelInvocable, warnings: item.warnings, errors: item.errors, skillsNeedingReview: item.rows.filter(row => row.issues.length).length, issueCount: item.rows.reduce((sum, row) => sum + row.issues.length, 0)})), comparison}, null, 2));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
