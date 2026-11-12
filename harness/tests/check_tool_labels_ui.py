"""Render the unmodified packaged tool cards in Chrome with synthetic records only."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
PAYLOAD = Path(os.environ["QX_TEST_APP"]).resolve()
CLIENT = PAYLOAD / "node_modules/@deepseek-ai/dsh-client-ui-tool/lib/client.js"
LOCALE = PAYLOAD / "node_modules/@deepseek-ai/dsh-client-ui-conversation/lib/client.js"
CASES = [
    ("mcp__qx_materials__read_material", "读取材料正文"),
    ("mcp__qx_legal__calculate_calendar_date", "计算日期"),
    ("mcp__qx_knowledge__search_knowledge", "检索知识库"),
    ("mcp__windows__Snapshot", "读取当前桌面界面"),
    ("mcp__unknown__synthetic_probe", None),
]
# Observe the public module system; import exact shipped modules without rewriting them.
CAPTURE = """(() => {
  let loader;
  Object.defineProperty(window, '__ModuleLoader__', {
    configurable: true, get: () => loader,
    set(value) {
      loader = value;
      const create = value.create;
      value.create = function(options) {
        const modules = create.call(this, options);
        window.__toolQaModules = modules;
        return modules;
      };
    }
  });
})();"""
RENDER = """async ({cases, locale}) => {
  const modules = window.__toolQaModules;
  const [React, dom, toolUi] = await Promise.all([
    modules.import('react'), modules.import('react-dom/client'),
    modules.import('@deepseek-ai/dsh-client-ui-tool')]);
  let Tree;
  toolUi.apply({
    remote: {$host: {home: 'SYNTHETIC_HOME'}}, on() {}, plugin() {},
    slots: {inject(name, factory) {if (name === 'conversation.chat.node') factory();},
      register(options, component) {if (options.key === 'tool-call') Tree = component;}}
  });
  if (!Tree) throw Error('Packaged tool renderer was not registered');
  const t = key => locale[key] ?? key;
  function useDisclosure() {
    const [expanded, setExpanded] = React.useState(false);
    return {expanded, toggle: () => setExpanded(value => !value)};
  }
  const records = cases.map(([name], index) => ({
    kind: 'tool', callId: 'synthetic-call-' + index, subCalls: [],
    call: {name, argsRaw: JSON.stringify({fixture: 'SYNTHETIC_INPUT_' + index, path: '合成材料.txt'})},
    isError: false, content: [{type: 'text', text: 'SYNTHETIC_RESULT_' + index}],
    args: {text: () => undefined, complete: () => false}
  }));
  const before = JSON.stringify(records);
  window.__toolQa = {records, before, inspected: [], dispatch: []};
  const fixture = document.createElement('main'); fixture.id = 'tool-labels-qa';
  fixture.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:white;color:#222;padding:28px;overflow:auto;';
  document.body.append(fixture);
  dom.createRoot(fixture).render(React.createElement(React.Fragment, null,
    React.createElement('h1', null, '包内工具卡片 · 独立合成验收'),
    ...records.map(block => React.createElement(Tree, {
      key: block.callId, node: {data: {root: block}}, cwd: 'SYNTHETIC_WORKSPACE',
      useHostInfo: selector => selector({home: 'SYNTHETIC_HOME'}), useDisclosure, t,
      inspectCall: id => window.__toolQa.inspected.push(id),
      renderSlot(name, owner, options) {
        window.__toolQa.dispatch.push({callId: owner.callId, toolName: owner.toolName, entryKey: options.entryKey});
        return options.fallback;
      }
    }))));
  return {recordCount: records.length, renderer: Tree.name};
}"""


def main():
    assert CLIENT.is_file(), CLIENT
    assert Path(os.environ["QX_TEST_OUTPUT_ROOT"]).is_absolute(), "Use an explicit isolated output directory"
    original_hash = hashlib.sha256(CLIENT.read_bytes()).hexdigest()
    locale_match = re.search(r"\bconst zh = (\{[\s\S]*?\n\t\t\});", LOCALE.read_text(encoding="utf-8"))
    assert locale_match, "Pinned packaged conversation locale is missing"
    locale = {json.loads(key): json.loads(value) for key, value in re.findall(
        r'("(?:[^"\\]|\\.)+"):\s*("(?:[^"\\]|\\.)*")', locale_match.group(1))}
    assert all(key in locale for key in ["row.input", "row.output", "row.inspect", "tool.title.generic"])
    env = {**os.environ, "QX_TEST_PACKAGED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    host = subprocess.Popen(
        [str(PAYLOAD / "runtime/node.exe"), str(ROOT / "contract-compare-smoke.cjs")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        env=env, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    folder = None
    try:
        runtime = json.loads(host.stdout.readline())
        folder = Path(runtime["data"])
        assert runtime["packaged"]
        assert Path(runtime["integration"]).resolve() == (PAYLOAD / "node_modules/@qunxing/desktop-session").resolve()
        report = {"payload": str(PAYLOAD), "clientSha256": original_hash,
                  "realModelRequests": 0, "scope": "Packaged React tool-card browser rendering with synthetic records", "cases": []}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 1350}, locale="zh-CN")
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
                ("http://127.0.0.1:", "data:", "blob:")) else route.abort())
            context.route("**/api/qx-account/balance*", lambda route: route.fulfill(
                json={"status": "unavailable", "balances": []}))
            context.add_init_script(CAPTURE)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(runtime["url"], wait_until="domcontentloaded")
                page.wait_for_function("window.__toolQaModules", timeout=30000)
                report["render"] = page.evaluate(RENDER, {"cases": CASES, "locale": locale})
                for index, (name, label) in enumerate(CASES):
                    card = page.locator(f'#tool-labels-qa [data-tool="{name}"]')
                    expect(card).to_be_visible()
                    expect(card).to_have_attribute("data-state", "ok")
                    row = card.locator('[aria-expanded]').first
                    expect(row).to_have_attribute("aria-expanded", "false")
                    if label:
                        expect(row).to_contain_text(label)
                        assert name not in row.inner_text(), row.inner_text()
                    else:
                        expect(row).to_contain_text(name)
                    row.click()
                    expect(row).to_have_attribute("aria-expanded", "true")
                    expect(card).to_contain_text("SYNTHETIC_INPUT_" + str(index))
                    expect(card).to_contain_text("SYNTHETIC_RESULT_" + str(index))
                    card.get_by_role("button", name=locale["row.inspect"], exact=True).click()
                    report["cases"].append({"toolId": name, "label": label, "expandedInputAndResult": True})
                integrity = page.evaluate("""() => ({unchanged: JSON.stringify(window.__toolQa.records) === window.__toolQa.before,
                    inspected: window.__toolQa.inspected, dispatch: window.__toolQa.dispatch})""")
                assert integrity["unchanged"]
                assert integrity["inspected"] == ["synthetic-call-" + str(index) for index in range(len(CASES))]
                assert all(item["toolName"] == item["entryKey"] and item["toolName"] in dict(CASES) for item in integrity["dispatch"])
                assert not errors, errors
                report.update({"passed": True, "protocolIdentity": integrity, "pageErrors": errors})
                page.locator("#tool-labels-qa").evaluate("element => { element.scrollTop = 0; }")
                page.screenshot(path=str(folder / "tool-labels.png"), full_page=True)
            except Exception:
                page.screenshot(path=str(folder / "tool-labels-failure.png"), full_page=True)
                (folder / "tool-labels-failure.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
                raise
            finally:
                browser.close()
        assert hashlib.sha256(CLIENT.read_bytes()).hexdigest() == original_hash
        (folder / "tool-labels-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": True, "cases": len(CASES), "directory": str(folder)}, ensure_ascii=False))
    finally:
        subprocess.run(["taskkill", "/PID", str(host.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        if folder:
            print("Evidence: " + str(folder))


if __name__ == "__main__":
    main()
