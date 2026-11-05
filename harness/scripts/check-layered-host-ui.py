"""Use the explicitly isolated, loopback-model QA host; never the installed user instance."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'.local/layered-host-qa/data'
runtime=json.loads((DATA/'.local/runtime.json').read_text(encoding='utf8'))
OUT=ROOT/'docs/checks/layered-knowledge'
errors=[];report={'scope':'real Harness isolated QA host; synthetic data and loopback model only','checks':[]}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000},locale='zh-CN')
 page.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
 page.on('pageerror',lambda e:errors.append(str(e)))
 try:
  page.goto(runtime['url'],wait_until='domcontentloaded')
  page.get_by_role('button',name='律所知识库',exact=True).click(timeout=60000)
  page.get_by_role('button',name='关系图与三层知识',exact=True).click()
  expect(page.get_by_role('heading',name='知识关系图',exact=True)).to_be_visible(timeout=30000)
  page.get_by_text('项目与对话归属',exact=True).click()
  page.get_by_label('新项目名称',exact=True).fill('隔离工作台知识验证')
  page.get_by_label('项目目标',exact=True).fill('合成场景，验证项目隔离和来源追溯')
  page.get_by_role('button',name='新建项目',exact=True).click()
  expect(page.get_by_label('当前知识项目')).to_contain_text('隔离工作台知识验证')
  report['checks'].append('native sidebar library entry opens new graph and authenticates real project API')
  page.get_by_text('每周整理与备份',exact=True).click()
  page.get_by_label('自动整理',exact=True).uncheck();page.get_by_role('button',name='保存设置',exact=True).click()
  expect(page.get_by_text('整理设置已保存。',exact=True)).to_be_visible()
  report['checks'].append('weekly settings accepted through real Harness original-Host carrier')
  value=page.evaluate("async()=>{const r=await fetch('/api/qx-layered/state',{headers:{'x-qx-layered':'1'}});return {status:r.status,body:await r.json()};}")
  assert value['status']==200 and len(value['body']['sessions'])>0
  report['checks'].append('real persisted synthetic workbench conversations enumerated')
  page.screenshot(path=str(OUT/'04-native-host.png'),full_page=True)
  started=time.time();page.get_by_role('button',name='关闭知识关系图',exact=True).click()
  editor=page.locator('[data-conversation-content] [contenteditable=true][role=textbox]').first
  editor.fill('合成验证：请核对付款条件。');editor.press('Enter')
  found=False
  for _ in range(40):
   for file in DATA.glob('mock-*.json'):
    if file.stat().st_mtime>=started and 'knowledge_start' in file.read_text(encoding='utf8'):found=True;break
   if found:break
   page.wait_for_timeout(500)
  assert found,'Real model request did not include scoped knowledge-start instruction'
  report['checks'].append('scoped project index and knowledge_start instruction reach actual Harness model request')
  assert not errors,errors
  report['status']='passed'
 except Exception as e:
  report.update(status='failed',error=str(e));page.screenshot(path=str(OUT/'native-host-failure.png'),full_page=True);raise
 finally:
  report['pageErrors']=errors;(OUT/'native-host-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');browser.close()
print(json.dumps(report,ensure_ascii=False))
