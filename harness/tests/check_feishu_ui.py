"""Synthetic browser acceptance of the resident Feishu settings; no real network/model."""
import json,os,subprocess,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
host=subprocess.Popen(['node',str(ROOT/'contract-compare-smoke.cjs')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
try:
 runtime=json.loads(host.stdout.readline()); folder=Path(runtime['data']); actions=[]; errors=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
  context=browser.new_context(viewport={'width':1440,'height':900},locale='zh-CN')
  context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:','data:','blob:')) else r.abort())
  context.route('**/api/qx-account/balance*',lambda r:r.fulfill(json={'status':'unavailable','balances':[]}))
  state={'configured':False,'appId':'','connected':False,'paused':True,'owner':None,'sessionId':'','lastError':'','pairing':None,'batching':{'active':False,'pendingMessages':0},'forwarded':0}
  sessions=[]
  def api(route):
   if route.request.url.endswith('/state'):return route.fulfill(json=state)
   if route.request.url.endswith('/settings'):return route.fulfill(json={'csrf':'synthetic-csrf','sessions':sessions})
   data=route.request.post_data_json;assert route.request.headers.get('x-qx-token')=='synthetic-csrf';actions.append(data)
   if data['action']=='connect':
    state.update(configured=True,appId=data['appId'],connected=True,paused=False,sessionId=data['sessionId'],pairing={'code':'192837','expiresAt':int(time.time()*1000)+300000})
   elif data['action']=='pause':state.update(connected=False,paused=True)
   elif data['action']=='resume':state.update(connected=True,paused=False)
   elif data['action']=='session':state['sessionId']=data['sessionId']
   elif data['action']=='clear':state.update(configured=False,appId='',owner=None,pairing=None,connected=False,paused=True)
   return route.fulfill(json={'ok':True,'sessionId':state['sessionId']})
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(runtime['url'],wait_until='domcontentloaded')
  try:page.get_by_role('button',name='开始使用',exact=True).click(timeout=15000)
  except Exception:pass
  page.get_by_role('button',name='新建客户接待对话',exact=True).click(timeout=60000)
  page.wait_for_function('document.documentElement.dataset.qxSessionId')
  session=page.evaluate('document.documentElement.dataset.qxSessionId');assert session
  actual=page.evaluate("async()=>({state:await (await fetch('/qx-feishu/state')).json(),settings:await (await fetch('/qx-feishu/settings')).json()})")
  assert actual['state']['configured'] is False
  assert actual['settings']['csrf'] and any(row['id']==session for row in actual['settings']['sessions'])
  context.route('**/qx-feishu/*',api)
  sessions.extend([{'id':session,'title':'当前虚构对话'},{'id':'synthetic-other','title':'另一虚构对话'}])
  page.get_by_role('button',name='飞书连接',exact=True).click(timeout=10000)
  dialog=page.get_by_role('dialog',name='飞书连接');expect(dialog).to_be_visible()
  expect(page.get_by_label('飞书使用的会话',exact=True)).to_have_value(session)
  page.get_by_label('App ID',exact=True).fill('cli_synthetic')
  page.get_by_label('App Secret',exact=True).fill('synthetic-secret-only')
  page.get_by_role('button',name='保存并连接',exact=True).click()
  expect(dialog).to_contain_text('连接 192837');expect(page.get_by_label('App Secret',exact=True)).to_have_value('')
  assert len(actions)==1 and actions[0]['sessionId']==session
  state.update(owner='ou_synthetic',pairing=None)
  expect(dialog).to_contain_text('已绑定本人',timeout=10000)
  page.get_by_label('飞书使用的会话',exact=True).select_option('synthetic-other')
  expect(dialog).to_contain_text('已切换会话')
  assert actions[-1]=={'action':'session','sessionId':'synthetic-other'}
  state['sessionId']=session
  expect(page.get_by_label('飞书使用的会话',exact=True)).to_have_value(session,timeout=10000)
  page.get_by_role('button',name='暂停接收',exact=True).click();expect(dialog).to_contain_text('接收已暂停')
  page.get_by_role('button',name='恢复连接',exact=True).click();expect(dialog).to_contain_text('飞书已连接')
  for width in [1440,768,390]:
   page.set_viewport_size({'width':width,'height':860});expect(dialog).to_be_visible()
   assert dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
   page.screenshot(path=str(folder/f'feishu-{width}.png'))
  page.keyboard.press('Escape');expect(dialog).to_have_count(0)
  expect(page.get_by_role('button',name='飞书连接',exact=True)).to_be_focused()
  assert not errors,errors
  report={'passed':True,'uiTransport':'synthetic Feishu API responses; real resident Harness and Chrome','actions':[a['action'] for a in actions],'pageErrors':errors,'realHostUnconfiguredApi':True,'realModels':0,'realFeishuAccounts':0,'viewports':[1440,768,390]}
  (folder/'feishu-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'evidence':str(folder),**report},ensure_ascii=False));browser.close()
finally:
 host.terminate()
 try:host.wait(timeout=15)
 except subprocess.TimeoutExpired:host.kill()
