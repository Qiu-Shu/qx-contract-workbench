"""Real Chromium against the native synthetic generation fixture; no screenshots."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import text

from ui_fixture import ui_fixture


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CHROMIUM = PROJECT/'.local/scrapling/browsers/chromium-1243/chrome-win64/chrome.exe'
INPUTS = [
    'src/cn_contract/web/static/assistant.mjs', 'src/cn_contract/web/static/assistant-state.mjs',
    'src/cn_contract/web/static/assistant-generation.mjs', 'src/cn_contract/web/static/assistant-api.mjs',
    'src/cn_contract/web/static/assistant-render.mjs', 'src/cn_contract/web/static/assistant-composer.mjs',
    'src/cn_contract/web/static/assistant-materials.mjs', 'src/cn_contract/web/templates/assistant.html',
    'src/cn_contract/web/static/assistant.css', 'src/cn_contract/domain.py',
    'src/cn_contract/web/assistant_generation.py', 'src/cn_contract/assistant/providers/history.py',
]


def hashes():
    return {name:hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() for name in INPUTS}


def main():
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=False)
    report = {'scope':'real Chromium + native backend + real adapter + synthetic loopback; no installed app acceptance',
        'checks':[], 'requests':[], 'page_errors':[], 'csp':[], 'real_model_calls':0, 'exit_code':1,
        'source_before':hashes()}
    def checked(name):
        report['checks'].append(name)
        print('PASS '+name, flush=True)

    try:
        with ui_fixture(target) as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(CHROMIUM), headless=True)
            context = browser.new_context(viewport={'width':1366, 'height':768})
            context.expose_binding('__captureCsp', lambda source,uri:report['csp'].append(uri))
            page = context.new_page()
            page.set_default_timeout(12000)
            expect.set_options(timeout=12000)
            page.on('request', lambda request:report['requests'].append({'method':request.method, 'url':request.url}))
            page.on('pageerror', lambda error:report['page_errors'].append(str(error)))
            page.on('dialog', lambda dialog:dialog.accept() if dialog.type == 'beforeunload' else dialog.dismiss())
            page.add_init_script("document.addEventListener('securitypolicyviolation',e=>window.__captureCsp(e.blockedURI));")

            def draft(case):
                page.locator('#composer').fill(fixture.texts[case])
                expect(page.locator('#save-status')).to_have_text('草稿已保存到本机')

            def send(case, *, pause=False, prepared=False):
                if pause:
                    fixture.entered.clear()
                    fixture.release.clear()
                if not prepared:
                    draft(case)
                expect(page.locator('#send')).to_be_enabled()
                page.locator('#send').click()
                if pause:
                    assert fixture.entered.wait(10), 'loopback provider not entered'
                expect(page.locator('#history .message-text').last).to_have_text(fixture.texts[case])

            def new():
                expect(page.locator('#new-conversation')).to_be_enabled()
                page.locator('#new-conversation').click()
                expect(page.locator('#history article')).to_have_count(0)
                expect(page.locator('#composer')).to_have_value('')

            def current_url():
                return fixture.origin+'/api/assistant/conversations/'+page.url.rsplit('/', 1)[-1]

            def settled(url):
                deadline = time.monotonic()+10
                while time.monotonic()<deadline:
                    view = page.request.get(url).json()
                    latest = view['latest_run']
                    value = page.request.get(url+'/generation-history', params={'message_id':latest['message_id']}).json()
                    attempt = value['items'][0]['attempt']
                    if attempt['receipt'] is not None:
                        return attempt
                    page.wait_for_timeout(50)
                raise AssertionError('synthetic generation did not settle')

            try:
                page.goto(fixture.origin+'/login')
                page.get_by_label('用户名').fill(fixture.credentials['username'])
                page.get_by_label('密码').fill(fixture.credentials['password'])
                page.get_by_role('button', name='登录', exact=True).click()
                page.wait_for_url(fixture.origin+'/assistant')
                expect(page.locator('#account-name')).to_have_text(fixture.credentials['username'])
                assert not fixture.received
                checked('native_login_has_no_generation_or_provider_probe')

                draft('first')
                expect(page.locator('#send')).to_be_enabled()
                page.locator('#composer').evaluate('''(input, original) => {
                    input.value=original+'临时编辑';input.dispatchEvent(new Event('input',{bubbles:true}));
                    input.value=original;input.dispatchEvent(new Event('input',{bubbles:true}));
                }''', fixture.texts['first'])
                expect(page.locator('#send')).to_be_enabled()
                expect(page.locator('#composer')).to_have_value(fixture.texts['first'])
                assert not fixture.received
                checked('editing_then_reverting_saved_text_restores_send_without_provider_post')

                page.locator('#skill-cards [data-skill="client_reply"]').evaluate('''button => {
                    button.click();document.getElementById('clear-skill').click();
                }''')
                expect(page.locator('#send')).to_be_enabled()
                expect(page.locator('#clear-skill')).to_be_hidden()
                assert not fixture.received
                assert not any(item['method']=='POST' and item['url'].endswith('/generations') for item in report['requests'])
                checked('rapid_skill_selection_and_cancel_restores_send_without_provider_post')

                send('first', pause=True, prepared=True)
                expect(page.locator('#send')).to_be_disabled()
                draft('edit')
                assert page.request.get(current_url()).json()['draft_input'] == fixture.texts['edit']
                assert len(fixture.received) == 1 and not fixture.release.is_set()
                fixture.release.set()
                expect(page.locator('#history .generation-text')).to_have_count(1)
                expect(page.locator('#composer')).to_have_value(fixture.texts['edit'])
                checked('pending_generation_allows_new_saved_draft_and_preserves_it_on_reply')

                send('second')
                expect(page.locator('#history .generation-text')).to_have_count(2)
                assert len(fixture.received) == 2
                for index,case in enumerate(('first', 'second')):
                    message = page.locator('#history article').nth(index)
                    expect(message.locator('.message-text')).to_have_text(fixture.texts[case])
                    expect(message.locator('.generation-text')).to_have_text(fixture.outputs[case])
                    expect(message.locator('.generation-sources a')).to_have_attribute('href', '#'+message.get_attribute('id'))
                    assert '内部草稿' in message.inner_text() and '待核对' in message.inner_text()
                assert page.locator('#history img').count() == 0
                page.reload()
                expect(page.locator('#history .generation-text')).to_have_count(2)
                assert len(fixture.received) == 2
                checked('two_rounds_and_reload_keep_both_candidates_and_message_citations_without_resend')

                original = {}
                def lose_response(route):
                    original.update(route.request.post_data_json)
                    response = route.fetch()
                    assert response.status == 202
                    route.abort()
                page.route('**/api/assistant/conversations/*/generations', lose_response, times=1)
                draft('unknown')
                expect(page.locator('#send')).to_be_enabled()
                page.locator('#send').click()
                expect(page.locator('#recover-generation')).to_be_visible()
                expect(page.locator('#composer')).to_have_value(fixture.texts['unknown'])
                assert len(fixture.received) == 3
                page.locator('#recover-generation').click()
                expect(page.locator('#history .generation-text')).to_have_count(3)
                assert len(fixture.received) == 3
                assert any('/generations/by-request/'+original['request_id'] in item['url'] for item in report['requests'])
                assert sum(item['method']=='POST' and item['url'].endswith('/generations') for item in report['requests']) == 3
                checked('lost_202_response_recovers_original_request_without_second_provider_post')

                new()
                draft('blocked')
                page.locator('#skill-cards [data-skill="client_reply"]').click()
                expect(page.locator('#send')).to_be_disabled()
                expect(page.locator('#composer')).to_have_value(fixture.texts['blocked'])
                page.locator('#clear-skill').click()
                expect(page.locator('#send')).to_be_enabled()
                page.locator('#add-material').click()
                page.locator('#material-file').set_input_files(str(fixture.attachment))
                page.locator('#material-consent').check()
                page.locator('#upload-material').click()
                expect(page.locator('#material-list strong')).to_have_text(fixture.attachment.name)
                expect(page.locator('#send')).to_be_disabled()
                expect(page.locator('#generation-note')).to_contain_text('DOCX')
                expect(page.locator('#composer')).to_have_value(fixture.texts['blocked'])
                assert len(fixture.received) == 3
                checked('skill_and_selected_local_docx_block_generation_and_keep_draft')

                new()
                send('cancel', pause=True)
                url = current_url()
                expect(page.locator('#cancel-run')).to_be_enabled()
                page.locator('#cancel-run').click()
                expect(page.locator('#run-status')).to_contain_text('取消')
                fixture.release.set()
                result = settled(url)
                assert result['output'] is None and result['receipt'] is not None
                expect(page.locator('#history .generation-text')).to_have_count(0)
                assert len(fixture.received) == 4
                checked('cancel_keeps_receipt_but_never_shows_late_candidate')

                new()
                send('switch', pause=True)
                old_url = current_url()
                new()
                draft('edit')
                new_url = current_url()
                assert old_url != new_url
                fixture.release.set()
                result = settled(old_url)
                assert result['output']['candidate']['text'] == fixture.outputs['switch']
                expect(page.locator('#history .generation-text')).to_have_count(0)
                expect(page.locator('#composer')).to_have_value(fixture.texts['edit'])
                assert len(fixture.received) == 5
                checked('switching_conversation_discards_late_result_from_current_screen')

                new()
                send('revoked', pause=True)
                with fixture.database.session() as db:
                    db.execute(text('UPDATE users SET disabled=1'))
                page.locator('#refresh-run').click()
                expect(page.locator('#save-status')).to_have_text('访问已结束')
                expect(page.locator('#history article')).to_have_count(0)
                expect(page.locator('#composer')).to_have_value('')
                expect(page.locator('#conversation-list')).to_be_empty()
                fixture.release.set()
                assert len(fixture.received) == 6
                checked('observed_revocation_clears_current_text_history_results_and_recent_list')

                external = [item for item in report['requests'] if not item['url'].startswith(fixture.origin+'/')]
                assert not external, external
                assert not report['page_errors'], report['page_errors']
                assert not report['csp'], report['csp']
                assert not fixture.errors, fixture.errors
                checked('zero_external_browser_requests_csp_violations_or_javascript_errors')
                report['exit_code'] = 0
            finally:
                report['upstream_posts'] = len(fixture.received)
                report['upstream_receipts'] = fixture.received
                report['fixture_errors'] = fixture.errors
                report['final_url'] = page.url
                report['final_ui'] = {key:page.locator('#'+key).inner_text() for key in (
                    'save-status', 'generation-note', 'generation-status', 'notice', 'run-status')}
                fixture.release.set()
                browser.close()
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        report['source_after'] = hashes()
        report['source_unchanged'] = report['source_before'] == report['source_after']
        (target/'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'checks':len(report['checks']), 'upstream_posts':report['upstream_posts'],
        'exit_code':report['exit_code'], 'source_unchanged':report['source_unchanged']}), flush=True)


if __name__ == '__main__':
    main()
