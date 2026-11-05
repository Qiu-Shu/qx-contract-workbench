"""Real React/Cytoscape with real local API and in-memory synthetic records; no model calls."""
import json, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/checks/layered-knowledge';OUT.mkdir(parents=True,exist_ok=True)
NODE='C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
child=subprocess.Popen([NODE,str(ROOT/'scripts/knowledge-ui-fixture.mjs')],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
checks=[];errors=[]
try:
 line=child.stdout.readline().strip();assert line.startswith('PORT='),line
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:'+line.split('=')[1]);expect(page.get_by_role('heading',name='知识关系图')).to_be_visible()
  page.wait_for_function("document.querySelectorAll('.canvas canvas').length > 0")
  page.screenshot(path=str(OUT/'01-graph.png'),full_page=True);checks.append('real Cytoscape canvas renders with synthetic project')
  page.get_by_role('button',name='列表',exact=True).click();page.get_by_role('button',name='分阶段交付原则，待律师确认',exact=True).click()
  expect(page.get_by_label('知识条目详情').get_by_text('长期规则 · 待律师确认 · 第 1 版',exact=True)).to_be_visible()
  page.get_by_label('知识内容').fill('经律师确认：必须明确交付验收条件。');page.get_by_role('button',name='保存并确认',exact=True).click()
  expect(page.get_by_text('已保存律师复核结果。',exact=True)).to_be_visible();checks.append('lawyer edits and confirms with real persisted revision')
  page.get_by_role('button',name='追溯原文',exact=True).click();expect(page.get_by_text('合成用户原文：明确交付验收条件，再确认付款时间。',exact=True)).to_be_visible();checks.append('trace reads bounded actual API source')
  page.get_by_role('button',name='查看修改历史',exact=True).click();expect(page.get_by_text('第 1 版 · 待律师确认',exact=False)).to_be_visible();checks.append('prior revision visible after confirmation')
  page.screenshot(path=str(OUT/'02-review.png'),full_page=True)
  page.get_by_text('每周整理与备份',exact=True).click();page.get_by_label('整理星期').select_option('2');page.get_by_role('button',name='保存设置',exact=True).click();expect(page.get_by_text('整理设置已保存。',exact=True)).to_be_visible();checks.append('weekly timezone settings saved')
  page.get_by_role('button',name='立即整理',exact=True).click();page.wait_for_timeout(5200);expect(page.get_by_text('本次已完成',exact=False)).to_be_visible();checks.append('synthetic scheduler completes visibly')
  with page.expect_download() as download:
   page.get_by_role('button',name='导出分层知识备份',exact=True).click()
  backup=OUT/'synthetic-backup.jsonl';download.value.save_as(backup)
  page.locator('input[type=file]').set_input_files(str(backup));expect(page.get_by_text('已分批合并',exact=False)).to_be_visible();checks.append('JSONL download and streamed restore complete')
  page.get_by_text('复用已有案件与资料',exact=True).click();page.get_by_role('button',name='关联资料库中的资料',exact=True).click();page.get_by_role('button',name='关联：合成合同范本',exact=True).click();page.get_by_role('button',name='资料：合成合同范本',exact=True).click();expect(page.get_by_text('虚构范本原文：应明确交付标准。',exact=True)).to_be_visible();checks.append('existing library source linked and paged preview reused')
  page.get_by_role('button',name='选择已有案件',exact=True).click();page.get_by_role('button',name='已建合成案件',exact=True).click();expect(page.get_by_text('已沿用案件编号建立项目索引。原案件和记忆保留。',exact=True)).to_be_visible();checks.append('existing case identity reused and current conversation bound')
  page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='关系图',exact=True).click();page.wait_for_timeout(300)
  assert page.evaluate("document.querySelector('.qx-layered').scrollWidth <= document.querySelector('.qx-layered').clientWidth+1")
  page.screenshot(path=str(OUT/'03-narrow.png'),full_page=True);checks.append('390px no horizontal overflow, graph and list remain accessible')
  assert not errors,errors
  browser.close()
 report={'status':'passed','checks':checks,'pageErrors':errors,'scope':'synthetic in-memory API, real React and Cytoscape; no user data or paid model calls'}
 (OUT/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False))
finally:
 child.terminate()
 try:child.wait(timeout=5)
 except subprocess.TimeoutExpired:child.kill()
