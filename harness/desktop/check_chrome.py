"""Check only desktop chrome in an isolated window; no model or user-history inspection."""
import json,os,re,socket,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
out=root/'desktop'/'checks'/(time.strftime('%Y%m%d-%H%M%S')+'-chrome');out.mkdir(parents=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
env.update(QX_DESKTOP_DATA=str(out/'desktop-data'),QX_DESKTOP_HIDDEN='1')
log=(out/'electron.log').open('w',encoding='utf8')
process=subprocess.Popen(['D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe',f'--remote-debugging-port={port}',str(root/'desktop/main.cjs')],cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
report={'status':'running','scope':'Isolated Electron chrome; fixture balance values are not actual account money; no model call','page_errors':[]}
report['host_pid']=json.loads((root/'.local/runtime.json').read_text(encoding='utf-8-sig'))['hostPid']
safe=False
try:
 for _ in range(150):
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
  except Exception:time.sleep(.2)
 with sync_playwright() as p:
  browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}');page=browser.contexts[0].pages[0]
  page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
  try:page.get_by_role('dialog',name='预览版说明').get_by_role('button',name='继续',exact=True).click(timeout=10000)
  except Exception:pass
  page.wait_for_function("Boolean(document.documentElement.dataset.qxSessionId)",timeout=40000)
  group=page.get_by_role('treeitem',name='未分组',exact=True)
  if group.count() and group.get_attribute('aria-expanded')!='true':group.click()
  page.get_by_role('treeitem',name=re.compile('群兴合成运行验证 2026-11-03T03-04-24-316Z')).first.click()
  expect(page.locator('html')).to_have_attribute('data-qx-session-id','qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81',timeout=30000)
  safe=True
  page.screenshot(path=str(out/'0-before-checks.png'))
  report['chrome_buttons']=page.get_by_role('button',name='插件',exact=True).evaluate_all('(nodes)=>nodes.map(node=>node.outerHTML)')
  expect(page.locator('.qx-wordmark')).to_have_text('群兴')
  for name in ['插件','自动化任务','更多']:
   expect(page.get_by_role('button',name=name,exact=True)).to_have_count(0)
  expect(page.get_by_role('button',name='新建会话',exact=True).last).to_be_visible()
  expect(page.get_by_text('群兴工作区',exact=True).first).to_be_visible()
  expect(page.locator('[data-composer-input][contenteditable="true"]')).to_be_visible()
  expect(page.locator('[data-qx-balance]')).to_have_attribute('data-qx-balance','ok',timeout=20000)
  actual=page.locator('.qx-balance-values').inner_text()
  report['actual_balance_currencies']=[currency for currency in ['CNY','USD'] if currency in actual]
  assert report['actual_balance_currencies'],'Actual authenticated balance did not render'
  page.screenshot(path=str(out/'actual-account-sidebar.png'))
  if '--actual-only' in sys.argv:
   assert not report['page_errors'],report['page_errors']
   report.update(status='passed',scope='Isolated Electron; current runtime authentication; real balance, no fixtures and no model call',checks=['群兴 wordmark, focused sidebar, editable composer','Authenticated real balance displayed in returned currencies'])
   browser.close();raise SystemExit(0)
  state={'status':'ok','balances':[{'currency':'CNY','total_balance':'123.4567'}],'updatedAt':'2026-11-03T00:00:00Z'}
  page.route('**/api/qx-account/balance*',lambda route:route.fulfill(status=200,json=state))
  refresh=page.get_by_role('button',name='刷新 DeepSeek 余额',exact=True)
  expect(refresh).to_be_enabled(timeout=20000);refresh.click()
  expect(page.locator('[data-qx-balance]')).to_have_attribute('data-qx-balance','ok')
  expect(page.locator('.qx-balance-values')).to_have_text('123.4567 CNY')
  page.screenshot(path=str(out/'1-focused-sidebar.png'))
  state={'status':'error','balances':[],'error':'合成失败状态'}
  expect(refresh).to_be_enabled();refresh.click()
  expect(page.locator('[data-qx-balance]')).to_have_attribute('data-qx-balance','error')
  expect(page.locator('.qx-balance-values')).to_have_text('123.4567 CNY')
  expect(page.locator('.qx-balance-notice')).to_have_text('更新失败，显示上次余额')
  page.screenshot(path=str(out/'2-balance-failure.png'))
  state={'status':'ok','balances':[{'currency':'USD','total_balance':'0.00'}]}
  expect(refresh).to_be_enabled();refresh.click()
  expect(page.locator('.qx-balance-values')).to_have_text('0.00 USD')
  page.get_by_role('button',name='收起侧边栏',exact=True).click()
  expect(page.locator('.qx-brand-compact')).to_be_visible()
  expect(page.get_by_role('button',name='刷新 DeepSeek 余额',exact=True)).to_be_visible()
  assert not report['page_errors'],report['page_errors']
  report.update(status='passed',checks=['Official sidebar retained; requested global navigation hidden by stable official slot anchors; More launcher omitted','群兴 wordmark; workspace, new session and composer retained','Real authenticated account currencies render before fixtures','Fixture exact amount/currency rendered; refresh failure preserves amount with stale notice; real zero accepted','Collapsed sidebar retains brand and accessible refresh'])
  browser.close()
except Exception as error:
 report.update(status='failed',error=str(error))
 if safe:
  try:page.screenshot(path=str(out/'failure.png'))
  except Exception:pass
 raise
finally:
 process.terminate()
 try:process.wait(timeout=10)
 except subprocess.TimeoutExpired:process.kill()
 log.close();(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'status':report['status'],'report':str(out/'report.json')},ensure_ascii=False))
