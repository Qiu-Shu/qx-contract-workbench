"""Actual staged client in isolated Chrome, synthetic update states, no downloads/install."""
import json,sys
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'.local/update-checks';out.mkdir(exist_ok=True)
runtime=json.loads((ROOT/'.local/installer-check-updates-0.2.3/.local/runtime.json').read_text(encoding='utf-8'))
script="""
window.__updateState={phase:'idle',version:'0.2.3',availableVersion:null,ready:false,notes:'',progress:0,total:0,transferred:0,error:''};
window.__updateActions=[];window.__updateListeners=[];
window.__setUpdate=patch=>{Object.assign(window.__updateState,patch);for(const f of window.__updateListeners)f({...window.__updateState})};
window.__QX_UPDATES__={read:async()=>({...window.__updateState}),subscribe:f=>{window.__updateListeners.push(f);return()=>{}},act:async action=>{window.__updateActions.push(action);if(action==='download')window.__setUpdate({phase:'downloading',progress:25,total:10485760,transferred:2621440});if(action==='cancel')window.__setUpdate({phase:'available'});return {...window.__updateState}}};
window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}};
"""
report={};errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    context=browser.new_context(viewport={'width':1320,'height':900},locale='zh-CN')
    context.add_init_script(script)
    context.route('**/api/qx-account/balance*',lambda r:r.fulfill(json={'status':'unavailable','balances':[]}))
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(runtime['url'],wait_until='domcontentloaded')
    start=page.get_by_role('button',name='继续',exact=True)
    try:start.click(timeout=5000)
    except Exception:pass
    knowledge=page.get_by_role('button',name='律所知识库',exact=True);expect(knowledge).to_be_visible(timeout=60000)
    expect(page.locator('.qx-upgrade')).to_have_count(0)
    page.evaluate("__setUpdate({phase:'available',availableVersion:'0.2.4',notes:'升级测试说明\\n<img src=x onerror=alert(1)> 仅作为文字显示'})")
    upgrade=page.get_by_role('button',name='升级',exact=True);expect(upgrade).to_be_visible()
    assert upgrade.bounding_box()['y']<knowledge.bounding_box()['y']
    expect(page.locator('.qx-update-panel')).to_have_count(0)
    assert page.evaluate("getComputedStyle(document.querySelector('.qx-upgrade')).backgroundColor")=='rgb(255, 220, 105)'
    report.update(yellowAboveKnowledge=True,noAutomaticPopup=True)
    upgrade.click();panel=page.locator('.qx-update-panel');expect(panel).to_be_visible()
    expect(panel.locator('img')).to_have_count(0)
    page.screenshot(path=str(out/'update-panel.png'))
    page.get_by_role('button',name='下载增量更新',exact=True).click()
    expect(page.get_by_role('progressbar',name='增量下载进度')).to_have_attribute('value','25')
    page.get_by_role('button',name='取消下载',exact=True).click()
    expect(page.get_by_role('button',name='下载增量更新',exact=True)).to_be_visible()
    page.get_by_role('button',name='稍后再说',exact=True).click();expect(panel).to_have_count(0)
    knowledge.click();expect(page.get_by_role('dialog',name='律所知识库')).to_be_visible(timeout=20000)
    report.update(inlineProgressAndCancel=True,notesRenderedAsText=True,knowledgeStillUsable=True,actions=page.evaluate('__updateActions'))
    page.keyboard.press('Escape')
    page.evaluate("__setUpdate({phase:'downloaded',ready:true,progress:100})")
    page.get_by_role('button',name='安装升级',exact=True).click()
    expect(page.get_by_role('button',name='安装并重启',exact=True)).to_be_visible()
    page.keyboard.press('Escape');expect(page.locator('.qx-update-panel')).to_have_count(0)
    report['escapeClosesPanel']=True
    # No bridge: the same client leaves the existing sidebar functional.
    old=browser.new_context(viewport={'width':1320,'height':900},locale='zh-CN')
    old.add_init_script("window.__DSH_LOCALE__={read:async()=>({languages:['zh-CN'],preference:'zh'}),onChange:()=>{}}")
    oldpage=old.new_page();oldpage.goto(runtime['url'],wait_until='domcontentloaded')
    try:oldpage.get_by_role('button',name='继续',exact=True).click(timeout=5000)
    except Exception:pass
    expect(oldpage.get_by_role('button',name='律所知识库',exact=True)).to_be_visible(timeout=30000)
    expect(oldpage.locator('.qx-upgrade')).to_have_count(0);report['noBridgeCompatible']=True
    browser.close()
report['pageErrors']=errors
(out/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert not errors,errors
print(json.dumps(report,ensure_ascii=False))
