"""Open the already-generated fictional Word artifact in the real desktop UI."""
import json,os,re,socket,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
out=root/'desktop'/'checks'/(time.strftime('%Y%m%d-%H%M%S')+'-output');out.mkdir(parents=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
env.update(QX_DESKTOP_DATA=str(out/'desktop-data'),QX_DESKTOP_HIDDEN='1')
log=(out/'electron.log').open('w',encoding='utf8')
process=subprocess.Popen(['D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe',f'--remote-debugging-port={port}',str(root/'desktop/main.cjs')],cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
report={'status':'running','scope':'Open existing synthetic model output only; no new model call'}
try:
 for _ in range(150):
  try:urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version',timeout=.5).close();break
  except Exception:time.sleep(.2)
 with sync_playwright() as p:
  browser=p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}');page=browser.contexts[0].pages[0]
  try:page.get_by_role('dialog',name='预览版说明').get_by_role('button',name='继续',exact=True).click(timeout=10000)
  except Exception:pass
  shared=page.evaluate("fetch('/qx-wechat/state').then(response=>response.json()).then(state=>state.sessionId)")
  expect(page.locator('html')).to_have_attribute('data-qx-session-id',shared,timeout=30000)
  group=page.get_by_role('treeitem',name='未分组',exact=True)
  if group.count() and group.get_attribute('aria-expanded')!='true':group.click()
  page.get_by_role('treeitem',name=re.compile('群兴合成运行验证 2026-11-03T03-04-24-316Z')).first.click()
  expect(page.locator('html')).to_have_attribute('data-qx-session-id','qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81',timeout=30000)
  page.wait_for_timeout(2500)
  (out/'before.txt').write_text(page.locator('body').inner_text(),encoding='utf8')
  page.screenshot(path=str(out/'1-existing-result.png'))
  filename='qx-smoke-review-2026-11-03T03-04-24-316Z.docx'
  target=page.get_by_text(filename,exact=True)
  if not target.count():
   print(page.locator('body').inner_text()[-5000:])
   raise AssertionError('Word artifact entry not found in existing conversation')
  print(page.get_by_role('button').evaluate_all('(nodes)=>nodes.map(n=>({label:n.getAttribute("aria-label"),title:n.getAttribute("title"),text:n.innerText})).filter(n=>/Word|WPS|打开|下载|保存|docx|应用/.test([n.label,n.title,n.text].join(" ")))'))
  page.get_by_role('button',name='用 WPS Office 打开',exact=True).first.click()
  page.wait_for_timeout(5000)
  command="@(Get-Process -Name wps -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*qx-smoke-review-2026-11-03T03-04-24-316Z*' -or $_.MainWindowTitle -like '*虚构合同审查草稿*' }).Count"
  count=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
  opened=int(count.stdout.strip() or '0')>0
  report.update(status='passed' if opened else 'needs-native-window-check',file=filename,nativeApplication='WPS Office',matchingNativeWindow=opened)
  assert opened,'No matching synthetic Word document window detected'
  browser.close()
except Exception as error:
 report['status']='failed';report['error']=str(error)
 try:
  if page.locator('html').get_attribute('data-qx-session-id')=='qx-smoke-4e02792a-de51-4e60-850d-1ba9ed875e81':page.screenshot(path=str(out/'failure.png'))
 except Exception:pass
 raise
finally:
 process.terminate()
 try:process.wait(timeout=10)
 except subprocess.TimeoutExpired:process.kill()
 log.close();(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'status':report['status'],'report':str(out/'report.json')},ensure_ascii=False))
