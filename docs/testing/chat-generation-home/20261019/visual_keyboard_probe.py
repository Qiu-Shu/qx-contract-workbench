"""One batched visual and keyboard review using independent synthetic inputs."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright, expect
from ui_fixture import ui_fixture
from browser_probe import CHROMIUM, hashes

target=Path(sys.argv[1]).resolve()
target.mkdir(parents=True,exist_ok=False)
report={'checks':[], 'screens':[], 'errors':[], 'source_before':hashes(), 'exit_code':1,
        'physical_ime_tested':False, 'physical_os_scaling_tested':False}
try:
    with ui_fixture(target) as f, sync_playwright() as p:
        f.outputs['second']='独立合成长回复，仅用于可读性检查。\n\n'+('一、客户陈述仍待核对。应保留每一项材料的版本、来源和审核状态。\n'
            '二、律师更正优先保留，未知事实不补写，冲突意见分别列示。\n\n'*80)+'极长字符串：'+'A'*500
        browser=p.chromium.launch(executable_path=str(CHROMIUM),headless=True)
        page=browser.new_page(viewport={'width':1366,'height':900})
        page.set_default_timeout(12000)
        expect.set_options(timeout=12000)
        page.on('pageerror',lambda e:report['errors'].append(str(e)))
        page.on('dialog',lambda d:d.accept() if d.type=='beforeunload' else d.dismiss())
        def shot(name):
            page.screenshot(path=str(target/(name+'.png')))
            report['screens'].append(name+'.png')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name+' horizontal overflow'
        page.goto(f.origin+'/login')
        page.get_by_label('用户名').fill(f.credentials['username'])
        page.get_by_label('密码').fill(f.credentials['password'])
        page.get_by_role('button',name='登录',exact=True).click()
        page.wait_for_url(f.origin+'/assistant')
        expect(page.locator('#account-name')).to_have_text(f.credentials['username'])
        shot('desktop-empty')
        box=page.locator('#composer')
        box.fill(f.texts['first'])
        box.press('Shift+Enter')
        expect(box).to_have_value(f.texts['first']+'\n')
        assert len(f.received)==0
        box.fill(f.texts['first'])
        box.dispatch_event('compositionstart')
        box.dispatch_event('keydown',{'key':'Enter','isComposing':True,'keyCode':229})
        assert len(f.received)==0
        box.dispatch_event('compositionend')
        box.dispatch_event('keydown',{'key':'Enter'})
        page.wait_for_timeout(300)
        assert len(f.received)==0
        report['checks'].append('shift_enter_and_synthetic_composition_enter_do_not_send')
        expect(page.locator('#send')).to_be_enabled()
        box.press('Enter')
        expect(page.locator('.generation-text')).to_have_count(1)
        assert len(f.received)==1
        report['checks'].append('enter_sends_exactly_once')
        page.locator('.generation-sources a').click()
        assert page.url.rsplit('#',1)[-1].startswith('message-')
        shot('desktop-result')
        box.fill(f.texts['second'])
        expect(page.locator('#send')).to_be_enabled()
        box.press('Enter')
        expect(page.locator('.generation-text')).to_have_count(2)
        expect(page.locator('.generation-text').last).to_have_text(f.outputs['second'])
        page.locator('.generation-text').last.scroll_into_view_if_needed()
        shot('desktop-long')
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate('scrollTo(0,0)')
        shot('narrow-top')
        page.evaluate('scrollTo(0,document.documentElement.scrollHeight)')
        shot('narrow-bottom')
        page.set_viewport_size({'width':800,'height':600})
        page.locator('#body-size').select_option('20')
        page.evaluate('scrollTo(0,document.documentElement.scrollHeight)')
        shot('large-font-bottom')
        assert len(f.received)==2 and not f.errors and not report['errors']
        report['checks'].append('long_chinese_and_unbroken_string_wrap_at_desktop_narrow_and_large_font')
        report['checks'].append('citation_targets_original_input')
        report['loopback_posts']=len(f.received)
        report['fixture_errors']=f.errors
        report['exit_code']=0
        browser.close()
finally:
    report['source_after']=hashes()
    report['source_unchanged']=report['source_before']==report['source_after']
    (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({k:report[k] for k in ['checks','screens','errors','exit_code','source_unchanged']},ensure_ascii=False))
