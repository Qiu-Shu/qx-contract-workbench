"""Exercise the real preload with a synthetic IPC bridge; no model or personal data."""
import json,sys
from pathlib import Path
sys.path.append('C:/Users/Lenovo/.codex/tools/scrapling/venv/Lib/site-packages')
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
out=root/'.local/recovery-checks';out.mkdir(exist_ok=True)
bridge="""
window.__calls=[];window.__listeners={};window.__state={phase:'connected',attempt:0};
window.process={isMainFrame:true,argv:['--qx-origin='+location.origin]};
window.require=()=>({contextBridge:{exposeInMainWorld:(key,value)=>{window[key]=value}},ipcRenderer:{
 on:(key,fn)=>{__listeners[key]=fn},removeListener:()=>{},send:()=>{},
 invoke:async(key)=>{__calls.push(key);return key==='qx:connection-state'?__state:{ok:false,cancelled:true}}
}});
window.__stateChange=phase=>{__state={phase,attempt:1};__listeners['qx:connection-state']?.({},__state)};
"""
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1320,'height':900})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.set_content('<html lang="zh-CN"><body><h1>AI师兄法律助手平台</h1><textarea aria-label="未发送内容">这是一段尚未发送的草稿</textarea></body></html>')
    page.evaluate(bridge);page.evaluate((root/'desktop/preload.cjs').read_text(encoding='utf-8'))
    page.evaluate("__stateChange('recovering')")
    expect(page.get_by_role('status')).to_contain_text('正在恢复')
    draft=page.get_by_role('textbox',name='未发送内容');expect(draft).to_have_value('这是一段尚未发送的草稿')
    assert page.evaluate("__calls.filter(x=>x==='qx:reconnect').length")==0
    page.evaluate("__stateChange('ready')")
    expect(page.get_by_role('status')).to_contain_text('后台已恢复')
    expect(draft).to_have_value('这是一段尚未发送的草稿')
    page.screenshot(path=str(out/'connection-ready.png'))
    for width in [800,390]:
        page.set_viewport_size({'width':width,'height':700})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        button=page.get_by_role('button',name='重新连接',exact=True)
        expect(button).to_be_visible();assert button.bounding_box()['height']>=40
    page.get_by_role('button',name='重新连接',exact=True).click()
    assert page.evaluate("__calls.filter(x=>x==='qx:reconnect').length")==1
    expect(draft).to_have_value('这是一段尚未发送的草稿')
    page.evaluate("__stateChange('failed')")
    expect(page.get_by_role('button',name='重试恢复',exact=True)).to_be_visible()
    expect(page.get_by_role('status')).to_contain_text('未能恢复')
    page.evaluate("__stateChange('stopped')")
    expect(page.get_by_role('status')).to_contain_text('已停止')
    page.evaluate("__stateChange('connected')")
    expect(page.locator('#qx-connection-notice')).to_be_hidden()
    assert not errors,errors
    browser.close()
report={'draftPreserved':True,'noAutomaticReconnect':True,'manualReconnect':True,'states':True,'smallViewport':True,'pageErrors':errors}
(out/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
