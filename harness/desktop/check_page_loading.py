"""Exercise the actual preload's blank-page fallback with synthetic content and IPC."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.local/white-screen-20261104'
OUT.mkdir(exist_ok=True)
BRIDGE = """
window.__calls=[];window.__listeners={};
window.process={isMainFrame:true,argv:['--qx-origin='+location.origin]};
window.require=()=>({contextBridge:{exposeInMainWorld:(key,value)=>{window[key]=value}},ipcRenderer:{
 on:(key,fn)=>{__listeners[key]=fn},removeListener:()=>{},
 send:(...args)=>__calls.push(args),
 invoke:async key=>key==='qx:connection-state'?{phase:'connected'}:{ok:false,cancelled:true}
}});
"""
checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':800})
    page.clock.install()
    page.set_content('<html lang="zh-CN"><body><div id="root"></div></body></html>')
    page.evaluate(BRIDGE)
    page.evaluate((ROOT/'desktop/preload.cjs').read_text('utf-8'))
    expect(page.get_by_role('status')).to_contain_text('正在打开工作台',timeout=1000)
    checks.append('empty successful HTML immediately shows loading status')
    page.clock.fast_forward(20000)
    expect(page.get_by_role('status')).to_contain_text('界面尚未加载完成')
    expect(page.get_by_role('button',name='重新连接',exact=True)).to_be_visible()
    assert page.evaluate("__calls.some(x=>x[0]==='qx:page-state'&&x[1]?.phase==='load-timeout')")
    checks.append('stalled blank page shows recovery and records timeout')
    page.screenshot(path=str(OUT/'loading-timeout.png'))
    page.evaluate("document.getElementById('root').innerHTML='<h1>合成工作台</h1><textarea aria-label=草稿>保留的草稿</textarea>'")
    page.clock.fast_forward(1000)
    expect(page.locator('#qx-connection-notice')).to_be_hidden()
    checks.append('late successful render clears the fallback')
    page.evaluate("dispatchEvent(new ErrorEvent('error',{error:new TypeError('PRIVATE CONTENT NEVER LOGGED'),message:'PRIVATE CONTENT NEVER LOGGED',lineno:12,colno:3}))")
    page.clock.fast_forward(1000)
    expect(page.get_by_role('textbox',name='草稿')).to_have_value('保留的草稿')
    expect(page.locator('#qx-connection-notice')).to_be_hidden()
    assert 'PRIVATE CONTENT' not in json.dumps(page.evaluate('__calls'))
    checks.append('nonfatal error preserves visible UI and logs no error content')
    page.evaluate("document.getElementById('root').replaceChildren()")
    page.clock.fast_forward(1000)
    expect(page.get_by_role('status')).to_contain_text('界面显示中断')
    checks.append('root removed after render shows recovery without auto reload')
    assert not page.evaluate("__calls.some(x=>x[0]==='qx:reconnect')")
    for width in [1280,390]:
        page.set_viewport_size({'width':width,'height':800})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        expect(page.get_by_role('button',name='重新连接',exact=True)).to_be_visible()
    checks.append('desktop and narrow view remain readable')
    browser.close()
report={'passed':True,'checks':checks,'model_calls':0,'messages_sent':0}
(OUT/'loading-ui-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
