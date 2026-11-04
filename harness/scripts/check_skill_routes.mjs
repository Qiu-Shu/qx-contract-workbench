// Offline routing check: explicit commands and named handoffs, not general subject words.
import assert from 'node:assert/strict';
import {readFile, readdir} from 'node:fs/promises';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const escapeRegex = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function disabledCalls(content, disabled, workflows) {
  const aliases = new Map();
  for (const item of workflows) {
    if (!disabled.has(item.name)) continue;
    aliases.set(`/${item.domain}:${item.original_name}`, item.name);
    // Only unique short aliases can identify a disabled target without a domain.
    if (workflows.filter(other => other.original_name === item.original_name).length === 1)
      aliases.set(item.original_name, item.name);
  }
  for (const name of disabled) aliases.set(name, name);
  for (const alias of aliases.keys()) if (!content.includes(alias)) aliases.delete(alias);
  if (!aliases.size) return [];
  const found = [];
  for (const [index, line] of content.split(/\r?\n/).entries()) {
    for (const [alias, target] of aliases) {
      const token = escapeRegex(alias);
      const match = new RegExp(`(?<![a-zA-Z0-9_/:.-])${token}(?![a-zA-Z0-9_/-])`).exec(line);
      if (!match) continue;
      const qualified = alias.startsWith('/') || alias === target;
      const instruction = /加载|调用|运行|传递(?:给|至)|交接|转交|接收来自|\b(?:load|invoke|run|handoff|hand off|route to)\b/i.test(line);
      const directShort = new RegExp('(?:加载|调用|运行|传递给|传递至|\\bload|\\binvoke|\\brun|\\broute to)\\s*(?:`|\\*\\*)' + token + '(?:`|\\*\\*)', 'i').test(line);
      // shortcut: generic names need an immediate verb plus marked name; ordinary prose/options are not calls.
      if ((qualified || directShort || instruction && alias.includes('-')) && !found.some(call => call.line === index + 1 && call.target === target))
        found.push({line: index + 1, alias, target, text: line.trim()});
    }
  }
  return found;
}

async function referenceFiles(folder) {
  const result = [];
  let entries;
  try { entries = await readdir(folder, {withFileTypes: true}); }
  catch (error) { if (error.code === 'ENOENT') return result; throw error; }
  for (const entry of entries) {
    if (entry.isSymbolicLink()) continue;
    const path = join(folder, entry.name);
    if (entry.isDirectory()) result.push(...await referenceFiles(path));
    else if (/\.(?:md|txt|ya?ml|json)$/i.test(entry.name)) result.push(path);
  }
  return result;
}

export async function checkSkillRoutes(projectRoot = root) {
  const spec = JSON.parse(await readFile(join(projectRoot, 'config/skill-lifecycle.json'), 'utf8'));
  const catalog = JSON.parse(await readFile(join(projectRoot, 'workspace/legal-library/skill-catalog.json'), 'utf8'));
  const disabled = new Set(spec.skills.filter(row => row.action === 'disable').map(row => row.name));
  const additions = JSON.parse(await readFile(join(projectRoot, 'config/practice-skill-additions.json'), 'utf8'));
  const withheld = new Set(additions.withheld || []);
  const unavailable = new Set([...disabled, ...withheld]);
  const report = {disabled: disabled.size, withheld: withheld.size, activeSkills: 0, scannedFiles: 0, violations: []};
  for (const location of ['workspace/.dsh/skills', 'config/skills']) {
    const folder = join(projectRoot, location);
    for (const entry of await readdir(folder, {withFileTypes: true})) {
      if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
      const skillPath = join(folder, entry.name, 'SKILL.md');
      const content = await readFile(skillPath, 'utf8');
      const frontmatter = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)?.[1] ?? '';
      const name = frontmatter.match(/^name:\s*(.+)$/m)?.[1]?.trim() ?? entry.name;
      if (disabled.has(name) || /^disable-model-invocation:\s*true\s*$/m.test(frontmatter)) continue;
      report.activeSkills++;
      const files = [skillPath, ...await referenceFiles(join(folder, entry.name, 'references'))];
      for (const path of files) {
        report.scannedFiles++;
        const text = path === skillPath ? content : await readFile(path, 'utf8');
        for (const call of disabledCalls(text, unavailable, catalog.workflows))
          report.violations.push({skill: name, path: relative(projectRoot, path).replaceAll('\\', '/'), ...call});
      }
    }
  }
  return report;
}

export function selfTest() {
  const workflows = [
    {name: 'legal-zh-regulatory-gap-surfacer', domain: 'regulatory-legal', original_name: 'gap-surfacer'},
    {name: 'legal-zh-employment-hiring-review', domain: 'employment-legal', original_name: 'hiring-review'},
    {name: 'legal-zh-commercial-draft', domain: 'commercial-legal', original_name: 'draft'},
    {name: 'legal-zh-regulatory-comments', domain: 'regulatory-legal', original_name: 'comments'},
  ];
  const disabled = new Set(workflows.map(item => item.name));
  for (const sample of ['运行 `/employment-legal:hiring-review`', '加载 **gap-surfacer** 参考技能', '传递至 gap-surfacer：每个差距成为事项。', '`legal-zh-regulatory-gap-surfacer`', 'Load gap-surfacer before working.', '加载 `comments`', '运行 **draft**'])
    assert.equal(disabledCalls(sample, disabled, workflows).length, 1, sample);
  for (const sample of ['普通 draft 文稿、gap-surfacer 方法描述。', '运行 draft 输出文稿。', '调用工具传 `draft` 参数。', '调用 `write_review_word` 不传mode或传 `comments`', 'references/gap-surfacer/template.md', '`legal-zh-regulatory-gap-surfacer-extra`', 'https://example.org/regulatory-legal:gap-surfacer'])
    assert.deepEqual(disabledCalls(sample, disabled, workflows), [], sample);
  const ambiguous = [...workflows, {name: 'other-gap', domain: 'other', original_name: 'gap-surfacer'}];
  assert.deepEqual(disabledCalls('加载 gap-surfacer', disabled, ambiguous), []);
  assert.equal(disabledCalls('调用 /regulatory-legal:gap-surfacer', disabled, ambiguous).length, 1);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  selfTest();
  if (process.argv.includes('--self-test')) console.log('Skill route parser checks passed.');
  else {
    const report = await checkSkillRoutes();
    console.log(JSON.stringify(report, null, 2));
    assert.equal(report.violations.length, 0, 'Active skills still route to disabled targets');
  }
}
