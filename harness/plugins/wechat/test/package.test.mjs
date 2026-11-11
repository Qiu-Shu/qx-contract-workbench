/**
 * Packaging checks for the private desktop plugin and retained upstream modules.
 *
 * Run: node test/package.test.mjs
 */
import assert from "node:assert/strict";
import { payloadFiles } from "../../../tests/helpers/wechat-payload.mjs";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

/**
 * Every shipped JavaScript module that runs on the host: taken from the real desktop overlay, so
 * a new module cannot be shipped without also being import-checked here. The client
 * half is excluded because it is bundled for the browser, not resolved by node.
 */
function hostModules() {
  return payloadFiles.filter((file) => file.endsWith(".js") && file !== "client.js");
}

let passed = 0;
let failed = 0;
function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`  FAIL ${name}\n       ${error?.message ?? error}`);
  }
}

console.log("packaging");

test("manifest declares what dsh needs", () => {
  assert.equal(pkg.name, "@qunxing/personal-wechat");
  assert.match(pkg.version, /^\d+\.\d+\.\d+$/);
  assert.equal(pkg.type, "module");
  assert.equal(pkg.license, "MIT");
  assert.equal(pkg.private, true);
  assert.equal(pkg.dsh?.bundle?.patch, "./cordis.patch.yml");
  assert.equal(pkg.main, "qx-plugin.js");
});

test("every published file exists", () => {
  for (const file of payloadFiles) {
    assert.ok(existsSync(join(root, file)), `files entry missing on disk: ${file}`);
  }
});

test("exports point at the supported desktop entry and real payload files", () => {
  assert.ok(existsSync(join(root, pkg.main)), `main missing: ${pkg.main}`);
  for (const [key, target] of Object.entries(pkg.exports)) {
    if (key === "./package.json") continue;
    assert.ok(existsSync(join(root, target)), `exports["${key}"] missing: ${target}`);
    assert.ok(payloadFiles.includes(target.replace(/^\.\//, "")), `export missing from desktop payload: ${target}`);
  }
  assert.equal(pkg.exports["."], "./qx-plugin.js");
  for (const file of ["state.js", "credential-files.js", "secrets.js", "qx-panel.html"]) {
    assert.ok(payloadFiles.includes(file), `desktop credential/settings dependency missing: ${file}`);
  }
});

test("the desktop manifest does not activate the unrelated upstream client", () => {
  assert.equal(pkg.dsh.client, undefined);
  assert.equal(pkg.exports["./client"], undefined);
  assert.ok(payloadFiles.includes("qx-panel.html"), "the supported personal-WeChat settings panel ships");
});

test("the client module inject list holds SERVICE names", () => {
  const code = readFileSync(join(root, "client.js"), "utf8");
  const match = /const inject = (\[[^\]]*\]);/.exec(code);
  assert.ok(match, "client.js must declare `const inject = [...]`");
  const services = JSON.parse(match[1].replace(/'/g, '"'));
  assert.ok(services.includes("slots"));
  for (const name of services) {
    assert.ok(!name.startsWith("@"), `service names only, found package: ${name}`);
  }
});

test("the client half keeps its __ModuleLoader__ wrapper", () => {
  const code = readFileSync(join(root, "client.js"), "utf8");
  assert.match(code, /window\.__ModuleLoader__\.load\(\{/);
  assert.match(code, /id: "dsh-wechat-media"/);
  assert.ok(code.trimEnd().endsWith("});"), "the wrapper must close the file");
  assert.match(code, /exports\.apply = apply;/);
});

test("every relative import resolves", () => {
  for (const source of hostModules()) {
    assert.ok(existsSync(join(root, source)), `published source missing: ${source}`);
    const text = readFileSync(join(root, source), "utf8");
    for (const match of text.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
      const target = join(root, dirname(source), match[1]);
      assert.ok(existsSync(target), `${source} imports missing module ${match[1]}`);
    }
  }
});

test("every module a published module imports is published too", () => {
  // Check real staging output: a dependency present only in the checkout still breaks every installed copy.
  const published = new Set(payloadFiles.map((file) => file.replace(/\\/g, "/")));
  for (const source of hostModules()) {
    const text = readFileSync(join(root, source), "utf8");
    for (const match of text.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
      const target = join(dirname(source), match[1]).replace(/\\/g, "/");
      assert.ok(
        published.has(target),
        `${source} imports ${target}, which is missing from the desktop payload`,
      );
    }
  }
  // The SILK encoder is loaded by path at runtime rather than imported by name, so it needs its own line: a missing
  // wasm makes every voice message silently unsendable in an installed copy.
  for (const asset of ["vendor/silk-wasm/index.mjs", "vendor/silk-wasm/silk.wasm"]) {
    assert.ok(published.has(asset), `${asset} must be included by the desktop payload copy`);
    assert.ok(existsSync(join(root, asset)), `${asset} must exist on disk`);
  }
});

test("the host half never statically imports a harness package", () => {
  // A link-installed plugin cannot resolve @deepseek-ai/* from its own directory,
  // so those must go through the loader at runtime instead.
  for (const source of hostModules()) {
    const text = readFileSync(join(root, source), "utf8");
    for (const match of text.matchAll(/^\s*import[^;]*from\s+["'](@deepseek-ai\/[^"']+)["']/gm)) {
      assert.fail(`${source} statically imports ${match[1]}; use ctx.loader.internal.import`);
    }
  }
});

test("every document ships and the README links to it", () => {
  // Check both the desktop payload and the README links.
  const readme = readFileSync(join(root, "README.md"), "utf8");
  for (const doc of ["docs/build-a-knowledge-base.md", "docs/proxy-and-domains.md"]) {
    assert.ok(payloadFiles.includes(doc), `${doc} must be included by the desktop payload copy`);
    assert.ok(existsSync(join(root, doc)), `${doc} must exist on disk`);
    assert.ok(readme.includes(`./${doc}`), `README.md must link to ./${doc}`);
  }
});

test("the proxy preset and the browser routes stay documented together", () => {
  // The doc is the only place that says which domains go through the proxy; if the code's preset and the doc drift,
  // one of them is lying. Both are derived from the same constant here.
  const doc = readFileSync(join(root, "docs/proxy-and-domains.md"), "utf8");
  const browser = readFileSync(join(root, "browser.js"), "utf8");
  const constant = /export const COMMON_PROXY_HOSTS = Object\.freeze\(\[([\s\S]*?)\]\);/.exec(browser);
  assert.ok(constant, "COMMON_PROXY_HOSTS must stay a plain literal so it can be read and compared");
  const hosts = [...constant[1].matchAll(/"([a-z0-9.-]+)"/g)].map((match) => match[1]);
  assert.ok(hosts.length >= 20, `expected a list worth documenting, found ${hosts.length}`);
  for (const host of hosts) assert.ok(doc.includes(`\`${host}\``), `the doc must list ${host}`);
  assert.match(doc, /\/browser hosts preset/, "the doc must name the command that applies it");
  assert.match(doc, /extension/, "and must say that an extension session uses the browser's own proxy");
});

test("the patch inserts exactly one row and carries no secret", () => {
  const yaml = readFileSync(join(root, "cordis.patch.yml"), "utf8");
  const inserts = [...yaml.matchAll(/- id: ([A-Za-z0-9_-]+)/g)].map((m) => m[1]);
  assert.deepEqual(inserts, ["qx-personal-wechat"]);
  assert.match(yaml, /plugins\/wechat\/qx-plugin\.js/);
  assert.ok(!/tvly-|Bearer\s+[A-Za-z0-9]/.test(yaml), "no credential may appear in the patch");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
