"""Actual shipped chat entry and side panel, using one synthetic loopback response."""
from playwright.sync_api import expect


def run_profile_ui(page, modal, closing_action, command_native, save, passed, posts, long_text, content):
    page.locator('#send').click(); window=modal()
    expect(window.locator('#approval-profile')).to_be_visible()
    assert window.locator('#approval-content').inner_text()==long_text
    closing_action(window,lambda:window.locator('#approval-cancel').click())
    expect(page.locator('#composer')).to_have_value(long_text)
    assert not posts
    passed('unified_send_uses_profile_confirmation_and_cancel_keeps_draft_zero_calls')

    save(content); expect(page.locator('#send')).to_be_enabled()
    # Lose the acknowledgement after the actual POST. Recovery must GET, never resend.
    def lose_ack(route):
        response=route.fetch(); assert response.status==202
        route.abort('failed')
    page.route('**/profile-generations',lose_ack,times=1)
    page.locator('#send').click(); window=modal()
    expect(window.locator('#approval-profile-intake')).to_contain_text('有可用于接待的字段')
    closing_action(window,lambda:window.locator('#approval-confirm').click())
    expect(page.locator('#recover-generation')).to_be_visible()
    page.locator('#recover-generation').click()
    expect(page.locator('.generation-result')).to_contain_text('档案草稿已更新 · 版本 1',timeout=45000)
    expect(page.locator('.generation-result')).to_contain_text('接待草稿已更新 · 版本 1')
    expect(page.locator('#composer')).to_have_value('')
    assert len(posts)==1
    passed('lost_post_ack_get_recovery_one_model_call_actual_profile_and_intake_save_receipt')

    page.locator('#show-profile').click()
    expect(page.locator('#profile-content')).to_contain_text(content)
    expect(page.locator('#profile-content')).to_contain_text('待核')
    assert page.locator('#profile-content script').count()==0
    for width,height,zoom,name in [(1280,900,1,'profile-ui-100'),(1024,850,1.5,'profile-ui-150'),(800,700,2,'profile-ui-200')]:
        command_native('window',width=width,height=height,zoom=zoom)
        page.wait_for_timeout(80)
        assert page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
        command_native('capture',name=name+'.png')
    command_native('window',width=1280,height=900,zoom=1)
    page.locator('#close-profile-preview').click()
    expect(page.locator('#show-profile')).to_be_focused()
    passed('profile_panel_exact_source_unverified_zoom_and_keyboard_return')

    url=page.url;page.reload()
    expect(page.locator('.generation-result')).to_contain_text('档案草稿已更新 · 版本 1')
    page.locator('#show-profile').click()
    expect(page.locator('#profile-content')).to_contain_text(content)
    page.locator('#close-profile-preview').click()
    page.locator('#new-conversation').click()
    expect(page.locator('#profile-preview')).to_be_hidden()
    assert page.locator('#profile-content').inner_text()==''
    page.goto(url);expect(page.locator('.generation-result')).to_contain_text('档案草稿已更新 · 版本 1')
    assert len(posts)==1
    passed('reload_history_recovers_profile_receipt_and_conversation_switch_clears_panel_without_resend')
