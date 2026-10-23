"""Profile-only steps for the existing actual Electron acceptance driver.

The profile caller is a test probe, not a shipped chat workflow. It grants then
disables without submitting generation; all materials and credentials are synthetic.
"""
from playwright.sync_api import expect


def run_profile(page, modal, closing_action, command_native, save, settings, passed, posts, long_text):
    def start(project=False):
        page.evaluate("""async(project)=>{
          const id=location.pathname.split('/').pop();
          const view=await(await fetch('/api/assistant/conversations/'+id)).json();
          window.profileProbe=null;
          desktopAssistant.authorizeProfile({conversation_id:id,request_id:crypto.randomUUID(),
            expected_scope:view.scope,expected_composer_revision:view.composer_revision,
            project_intake:project}).then(value=>window.profileProbe=value);
        }""", project)
        return modal()

    window=start()
    expect(window.locator('#approval-profile')).to_be_visible()
    expect(window.locator('#approval-profile-target')).to_contain_text('版本 0')
    expect(window.locator('#approval-profile-intake')).to_contain_text('不同步接待记录')
    expect(window.locator('#approval-judge')).to_be_hidden()
    assert window.locator('#approval-content').inner_text()==long_text
    assert window.locator('script').count()==1
    expect(window.locator('#approval-cancel')).to_be_focused()
    for width,height,zoom,name in [(820,740,1,'profile-100'),(760,760,1.5,'profile-150'),(640,540,2,'profile-200')]:
        command_native('window',target='approval',width=width,height=height,zoom=zoom)
        window.wait_for_timeout(80)
        assert window.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
        window.locator('#approval-profile').scroll_into_view_if_needed()
        command_native('capture',target='approval',name=name+'.png')
        window.locator('#approval-confirm').scroll_into_view_if_needed()
        assert window.locator('#approval-confirm').evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&document.elementFromPoint(r.x+5,r.y+5)===el}')
    window.locator('#approval-cancel').focus()
    closing_action(window,lambda:window.keyboard.press('Enter'))
    page.wait_for_function('()=>window.profileProbe!==null')
    assert page.evaluate('()=>window.profileProbe.ok') is False
    expect(page.locator('#composer')).to_have_value(long_text)
    assert not posts
    passed('profile_native_long_text_application_zoom_100_150_200_keyboard_cancel_zero_send')

    window=start(True)
    expect(window.locator('#approval-profile-intake')).to_contain_text('有可用于接待的字段并形成有效变更时，尝试创建接待草稿')
    changed=page.evaluate("""async()=>{
      const url='/api/assistant/conversations/'+location.pathname.split('/').pop();
      const v=await(await fetch(url)).json();
      const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('qx_csrf=')).split('=')[1]);
      return (await fetch(url+'/draft',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({expected_scope:v.scope,expected_composer_revision:v.composer_revision,
          content:'独立合成资料：确认期间草稿变更，旧计划应失效。'})})).status;
    }""")
    assert changed==200
    closing_action(window,lambda:window.locator('#approval-confirm').click())
    page.wait_for_function('()=>window.profileProbe!==null')
    assert page.evaluate('()=>window.profileProbe.ok') is False
    assert not posts
    passed('profile_native_changed_draft_rejects_stale_plan_before_private_authorization')

    page.reload()
    save(long_text)
    window=start(True)
    expect(window.locator('#approval-profile-note')).to_contain_text('待核草稿')
    command_native('capture',target='approval',name='profile-confirm-plan.png')
    closing_action(window,lambda:window.locator('#approval-confirm').click())
    page.wait_for_function('()=>window.profileProbe!==null')
    assert page.evaluate('()=>window.profileProbe')=={'ok':True,'status':'authorized'}
    expect(page.locator('#composer')).to_have_value(long_text)
    assert not posts
    settings()
    page.locator('#model-disable').click()
    expect(page.locator('#model-runtime-status')).to_contain_text('未配置')
    page.locator('#resume').click()
    passed('profile_native_actual_private_pipe_authorized_status_then_disable_without_generation_or_profile_write')
