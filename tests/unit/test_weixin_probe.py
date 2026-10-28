"""Synthetic HTTP only; no live Weixin account, token or file."""
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from cn_contract.weixin_probe import ConnectionProbe, ProbeError, REPLY_TEXT


PLAIN = b'SYNTHETIC DOCUMENT ONLY\n'
KEY = b'0123456789abcdef'
EXPECTED = {'name': 'fictional.docx', 'size': len(PLAIN),
            'sha256': hashlib.sha256(PLAIN).hexdigest()}
CONFIRMED = {'status': 'confirmed', 'bot_token': 'secret-bot-token',
             'ilink_bot_id': 'bot-self', 'ilink_user_id': 'lawyer-self',
             'baseurl': 'https://ilinkai.weixin.qq.com'}


def message(text='ordinary fictional text', **changes):
    return {'message_id': 18446744073709551615, 'from_user_id': 'lawyer-self',
            'to_user_id': 'bot-self', 'message_type': 1, 'message_state': 2,
            'context_token': 'secret-context',
            'item_list': [{'type': 1, 'text_item': {'text': text}}], **changes}


def file_message(*, hex_key=False, **changes):
    media = {'encrypt_type': 1, 'aes_key': base64.b64encode(KEY.hex().encode() if hex_key else KEY).decode(),
             'encrypt_query_param': 'secret-query&x=1',
             'full_url': 'https://novac2c.cdn.weixin.qq.com/c2c/download?full=secret'}
    media.update(changes.pop('media', {}))
    return message(item_list=[{'type': 4, 'file_item': {
        'file_name': EXPECTED['name'], 'len': str(EXPECTED['size']), 'media': media, **changes}}])


def encrypted(data=PLAIN):
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


class Wire:
    def __init__(self):
        self.requests = []
        self.statuses = [CONFIRMED]
        self.messages = []
        self.send = {'ret': 0}
        self.send_status = 200
        self.download = encrypted()
        self.download_status = 200

    def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        if path.endswith('/get_bot_qrcode'):
            return httpx.Response(200, json={'qrcode': 'secret-qr',
                'qrcode_img_content': 'https://ilinkai.weixin.qq.com/qr/display'})
        if path.endswith('/get_qrcode_status'):
            return httpx.Response(200, json=self.statuses.pop(0))
        if path.endswith('/getupdates'):
            return httpx.Response(200, json={'ret': 0, 'get_updates_buf': 'secret-cursor', 'msgs': self.messages})
        if path.endswith('/sendmessage'):
            if isinstance(self.send, Exception):
                raise self.send
            return httpx.Response(self.send_status, json=self.send)
        if path.endswith('/download'):
            return httpx.Response(self.download_status, content=self.download,
                                  headers={'location': 'https://outside.invalid/private'})
        raise AssertionError('unexpected request')

    def calls(self, suffix):
        return [request for request in self.requests if request.url.path.endswith(suffix)]


@pytest.fixture
def probe():
    wire = Wire()
    with httpx.Client(transport=httpx.MockTransport(wire.handle)) as client:
        value = ConnectionProbe(client=client, expected_file=EXPECTED)
        yield value, wire
        value.close()


def connect(value):
    value.start_qr()
    assert value.poll_login() == 'confirmed'


def verify_file(value, wire):
    incoming = file_message()
    incoming['message_id'] = 11
    wire.messages = [incoming]
    value.poll_messages()


@pytest.mark.parametrize('has_message', [False, True])
def test_getupdates_accepts_omitted_success_ret_with_valid_envelope(probe, has_message):
    value, wire = probe
    connect(value)
    wire.messages = [message()] if has_message else []
    original = value._client

    def handler(request):
        response = wire.handle(request)
        if request.url.path.endswith('/getupdates'):
            envelope = response.json()
            del envelope['ret']
            return httpx.Response(200, json=envelope)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        value._client = client
        reports = value.poll_messages()
    value._client = original
    assert reports == ([{'kind': 'text', 'characters': len('ordinary fictional text')}] if has_message else [])
    assert value._cursor == 'secret-cursor'
    assert not wire.calls('/sendmessage')


def test_omitted_ret_does_not_allow_other_sender(probe):
    value, wire = probe
    connect(value)
    original = value._client
    wire.messages = [message(from_user_id='someone-else')]

    def handler(request):
        response = wire.handle(request)
        if request.url.path.endswith('/getupdates'):
            envelope = response.json()
            del envelope['ret']
            return httpx.Response(200, json=envelope)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        value._client = client
        with pytest.raises(ProbeError, match='PRIVATE_SCOPE_MISMATCH'):
            value.poll_messages()
    value._client = original
    assert value._cursor == '' and value.send_state == 'not_sent'
    assert len(wire.calls('/getupdates')) == 1
    assert not wire.calls('/sendmessage') and not wire.calls('/download')


@pytest.mark.parametrize('envelope', [
    {'errcode': -14, 'msgs': [], 'get_updates_buf': 'untrusted-cursor'},
    {'ret': 1, 'msgs': [], 'get_updates_buf': 'untrusted-cursor'},
    {},
])
def test_getupdates_optional_success_still_rejects_error_or_missing_envelope(probe, envelope):
    value, wire = probe
    connect(value)
    original = value._client
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=envelope))) as client:
        value._client = client
        with pytest.raises(ProbeError):
            value.poll_messages()
    value._client = original
    assert value._cursor == '' and value.send_state == 'not_sent'


def test_qr_is_post_bot_type3_and_contains_no_old_token(probe):
    value, wire = probe
    assert value.start_qr() == 'https://ilinkai.weixin.qq.com/qr/display'
    request, = wire.calls('/get_bot_qrcode')
    assert request.method == 'POST'
    assert request.url.params['bot_type'] == '3'
    assert json.loads(request.content) == {'local_token_list': []}
    assert request.headers['AuthorizationType'] == 'ilink_bot_token'
    assert request.headers['iLink-App-Id'] == 'bot'
    assert 'authorization' not in request.headers


def test_pairing_statuses_and_confirmed_identity_stay_in_memory(probe):
    value, wire = probe
    wire.statuses = [{'status': 'need_verifycode'}, {'status': 'scaned'}, CONFIRMED]
    value.start_qr()
    assert value.poll_login() == 'need_verifycode'
    assert value.poll_login('123456') == 'scaned'
    assert value.poll_login() == 'confirmed'
    polls = wire.calls('/get_qrcode_status')
    assert polls[1].url.params['verify_code'] == '123456'
    assert 'verify_code' not in polls[2].url.params
    assert 'authorization' not in polls[1].headers
    assert 'X-WECHAT-UIN' not in polls[1].headers
    assert 'secret' not in repr(value)


@pytest.mark.parametrize('status', ['expired', 'verify_code_blocked', 'binded_redirect'])
def test_terminal_qr_status_cannot_poll_messages(probe, status):
    value, wire = probe
    wire.statuses = [{'status': status}]
    value.start_qr()
    assert value.poll_login() == status
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/getupdates')


@pytest.mark.parametrize('missing', ['bot_token', 'ilink_bot_id', 'ilink_user_id'])
def test_incomplete_confirmed_identity_fails_closed(probe, missing):
    value, wire = probe
    wire.statuses = [{key: val for key, val in CONFIRMED.items() if key != missing}]
    value.start_qr()
    with pytest.raises(ProbeError):
        value.poll_login()
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/getupdates')


def test_official_idc_redirect_and_external_redirect_block(probe):
    value, wire = probe
    wire.statuses = [{'status': 'scaned_but_redirect', 'redirect_host': 'ilinkai2.weixin.qq.com'},
                     {'status': 'scaned_but_redirect', 'redirect_host': 'ilinkai.weixin.qq.com.evil.invalid'}]
    value.start_qr()
    assert value.poll_login() == 'scaned_but_redirect'
    with pytest.raises(ProbeError, match='HOST'):
        value.poll_login()
    assert wire.calls('/get_qrcode_status')[1].url.host == 'ilinkai2.weixin.qq.com'


@pytest.mark.parametrize('changes', [
    {'from_user_id': 'someone-else'}, {'to_user_id': 'another-bot'},
    {'group_id': 'a-group'}, {'message_type': 2}, {'message_state': 1},
    {'delete_time_ms': 1}, {'message_id': True}, {'message_id': 2**64},
])
def test_only_scanning_user_completed_private_messages_are_accepted(probe, changes):
    value, wire = probe
    connect(value)
    wire.messages = [message(value.test_instruction, **changes)]
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/sendmessage')
    assert not wire.calls('/download')


def test_ordinary_text_is_counted_without_reply_or_content_logging(probe):
    value, wire = probe
    connect(value)
    wire.messages = [message()]
    report = value.poll_messages()
    assert report == [{'kind': 'text', 'characters': len('ordinary fictional text')}]
    assert not wire.calls('/sendmessage')
    assert 'fictional' not in json.dumps(report)
    assert value.poll_messages() == []  # large uint64 id is lossless and deduplicated
    assert json.loads(wire.calls('/getupdates')[1].content)['get_updates_buf'] == 'secret-cursor'


def test_reply_is_fixed_same_peer_context_and_once_per_process(probe):
    value, wire = probe
    connect(value)
    verify_file(value, wire)
    wire.messages = [message(value.test_instruction)]
    value.poll_messages()
    value.poll_messages()
    wire.messages = [message(value.test_instruction, message_id=12)]
    value.poll_messages()
    request, = wire.calls('/sendmessage')
    msg = json.loads(request.content)['msg']
    assert msg['to_user_id'] == 'lawyer-self'
    assert msg['context_token'] == 'secret-context'
    assert msg['item_list'] == [{'type': 1, 'text_item': {'text': REPLY_TEXT}}]
    assert value.send_state == 'submitted'


def test_missing_context_prevents_send(probe):
    value, wire = probe
    connect(value)
    wire.messages = [message(value.test_instruction, context_token='')]
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/sendmessage')


@pytest.mark.parametrize('reply', [httpx.ReadTimeout('secret-context'), {}, {'ret': '0'}])
def test_unknown_send_is_retained_and_never_retried(probe, reply):
    value, wire = probe
    connect(value)
    verify_file(value, wire)
    wire.messages = [message(value.test_instruction)]
    wire.send = reply
    value.poll_messages()
    assert value.send_state == 'unknown'
    value.poll_messages()
    wire.messages = [message(value.test_instruction, message_id=13)]
    value.poll_messages()
    assert len(wire.calls('/sendmessage')) == 1
    assert 'secret' not in json.dumps(value.summary())


@pytest.mark.parametrize('hex_key', [False, True])
def test_bounded_file_decrypt_hash_and_full_url_precedence(probe, hex_key):
    value, wire = probe
    connect(value)
    wire.messages = [file_message(hex_key=hex_key)]
    assert value.poll_messages() == [{'kind': 'file_verified', 'size': len(PLAIN), 'sha256': EXPECTED['sha256']}]
    request, = wire.calls('/download')
    assert dict(request.url.params) == {'full': 'secret'}
    assert 'authorization' not in request.headers
    assert 'X-WECHAT-UIN' not in request.headers


@pytest.mark.parametrize('flag', ['omitted', 0, 1])
def test_file_media_accepts_official_default_encryption_flag(probe, flag):
    # Pinned official downloadAndDecryptBuffer uses the AES key for both modes.
    value, wire = probe
    connect(value)
    incoming = file_message(hex_key=True)
    media = incoming['item_list'][0]['file_item']['media']
    if flag == 'omitted':
        del media['encrypt_type']
    else:
        media['encrypt_type'] = flag
    wire.messages = [incoming]
    assert value.poll_messages() == [{'kind': 'file_verified', 'size': len(PLAIN), 'sha256': EXPECTED['sha256']}]
    assert len(wire.calls('/download')) == 1
    assert not wire.calls('/sendmessage')


def test_cdn_query_fallback_is_url_encoded(probe):
    value, wire = probe
    connect(value)
    wire.messages = [file_message(media={'full_url': ''})]
    value.poll_messages()
    assert wire.calls('/download')[0].url.params['encrypted_query_param'] == 'secret-query&x=1'


@pytest.mark.parametrize('changes', [
    {'file_name': '../fictional.docx'}, {'len': '99999999999999999'},
    {'media': {'full_url': 'http://127.0.0.1/download'}},
    {'media': {'full_url': 'https://novac2c.cdn.weixin.qq.com@outside.invalid/download'}},
    {'media': {'aes_key': base64.b64encode(b'bad-key').decode()}},
    *[{'media': {'encrypt_type': flag}} for flag in (None, 2, -1, True, '0')],
])
def test_file_metadata_key_and_url_rejected_before_download(probe, changes):
    value, wire = probe
    connect(value)
    wire.messages = [file_message(**changes)]
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/download')


@pytest.mark.parametrize('body', [encrypted(b'x' * len(PLAIN)), b'x' * 4096, b'broken-padding!!'],
                         ids=['wrong-hash', 'oversized', 'bad-padding'])
def test_bad_hash_oversized_and_invalid_ciphertext_never_verified(probe, body):
    value, wire = probe
    connect(value)
    wire.messages = [file_message()]
    wire.download = body
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert value.summary()['file_verified'] is False


def test_cdn_redirect_is_not_followed(probe):
    value, wire = probe
    connect(value)
    wire.messages = [file_message()]
    wire.download_status = 302
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert len(wire.calls('/download')) == 1


def test_close_clears_credentials_and_stops_network(probe):
    value, wire = probe
    connect(value)
    value.close()
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/getupdates')
    assert not any('secret' in str(item) for item in vars(value).values())


def test_cli_without_live_is_offline():
    script = Path(__file__).resolve().parents[2] / 'scripts/weixin_connection_probe.py'
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0
    assert 'OFFLINE' in result.stdout
    assert '--live' in result.stdout


def test_authenticated_post_has_bearer_and_base_info_only_after_confirmation(probe):
    value, wire = probe
    connect(value)
    value.poll_messages()
    request, = wire.calls('/getupdates')
    assert request.headers['authorization'] == 'Bearer secret-bot-token'
    assert json.loads(request.content) == {'get_updates_buf': '', 'base_info': {
        'channel_version': '2.4.10', 'bot_agent': 'QXConnectionProbe/0.1'}}
    assert request.extensions['timeout']['read'] == 40


@pytest.mark.parametrize('baseurl', ['https://outside.invalid', 'http://ilinkai.weixin.qq.com',
                                  'https://ilinkai.weixin.qq.com/token-path'])
def test_confirmed_untrusted_base_does_not_acquire_a_session(probe, baseurl):
    value, wire = probe
    value.start_qr()
    wire.statuses = [{**CONFIRMED, 'baseurl': baseurl}]
    with pytest.raises(ProbeError, match='HOST'):
        value.poll_login()
    with pytest.raises(ProbeError, match='NOT_CONNECTED'):
        value.poll_messages()
    assert not wire.calls('/getupdates')


@pytest.mark.parametrize('status,body,expected', [(503, {'ret': 0}, 'unknown'),
                                               (200, {'ret': -1}, 'rejected'),
                                               (200, {'ret': 0, 'errcode': -14}, 'rejected')])
def test_send_http_and_application_statuses_preserve_once_only(probe, status, body, expected):
    value, wire = probe
    connect(value)
    verify_file(value, wire)
    wire.messages = [message(value.test_instruction)]
    wire.send_status, wire.send = status, body
    value.poll_messages()
    assert value.send_state == expected
    value.poll_messages()
    assert len(wire.calls('/sendmessage')) == 1


def test_old_generic_test_instruction_cannot_authorize_current_session(probe):
    value, wire = probe
    connect(value)
    wire.messages = [message('工作台连接测试')]
    value.poll_messages()
    assert not wire.calls('/sendmessage')


def test_download_stream_is_bounded_without_content_length(probe):
    value, wire = probe
    connect(value)
    wire.messages = [file_message()]
    read_chunks = []

    class Oversized(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(100):
                read_chunks.append(index)
                yield b'x' * 16384

    original = value._client
    def handler(request):
        if request.url.path.endswith('/download'):
            return httpx.Response(200, stream=Oversized())
        return wire.handle(request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as streaming:
        value._client = streaming
        with pytest.raises(ProbeError, match='LIMIT'):
            value.poll_messages()
    value._client = original
    assert read_chunks == [0]


def test_duplicate_json_cannot_replace_scanner_identity(probe):
    value, wire = probe
    value.start_qr()
    original = value._client
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,
            content=b'{"status":"confirmed","ilink_user_id":"a","ilink_user_id":"b"}'))) as malformed:
        value._client = malformed
        with pytest.raises(ProbeError, match='INVALID_RESPONSE'):
            value.poll_login()
    value._client = original
    assert value.login_state != 'confirmed'


def test_encoded_response_is_rejected_before_unbounded_decompression(probe):
    value, wire = probe
    value.start_qr()
    original = value._client
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,
            headers={'content-encoding': 'gzip'}, stream=httpx.ByteStream(b'invalid-gzip')))) as encoded:
        value._client = encoded
        with pytest.raises(ProbeError, match='ENCODING'):
            value.poll_login()
    value._client = original


def test_bot_token_cannot_be_a_header_injection(probe):
    value, wire = probe
    value.start_qr()
    wire.statuses = [{**CONFIRMED, 'bot_token': 'secret\r\nInjected: value'}]
    with pytest.raises(ProbeError, match='INVALID_RESPONSE'):
        value.poll_login()
    assert value.login_state != 'confirmed'


def test_cli_live_requires_explicit_file_before_network():
    script = Path(__file__).resolve().parents[2] / 'scripts/weixin_connection_probe.py'
    result = subprocess.run([sys.executable, str(script), '--live'], capture_output=True)
    assert result.returncode == 2
    assert b'QR' not in result.stdout


def test_instruction_first_waits_for_verified_file_then_replies_to_original_context(probe):
    value, wire = probe
    connect(value)
    wire.messages = [message(value.test_instruction, context_token='secret-command-context')]
    value.poll_messages()
    assert not wire.calls('/sendmessage')
    assert value.send_state == 'not_sent'
    incoming = file_message()
    incoming.update(message_id=11, context_token='different-file-context')
    wire.messages = [incoming]
    value.poll_messages()
    request, = wire.calls('/sendmessage')
    assert json.loads(request.content)['msg']['context_token'] == 'secret-command-context'
    assert value.summary()['file_verified'] is True
    assert value.send_state == 'submitted'
    value.poll_messages()
    assert len(wire.calls('/sendmessage')) == 1


def test_verified_file_first_waits_for_explicit_instruction(probe):
    value, wire = probe
    connect(value)
    verify_file(value, wire)
    assert not wire.calls('/sendmessage')
    wire.messages = [message(value.test_instruction)]
    value.poll_messages()
    assert value.send_state == 'submitted'
    assert len(wire.calls('/sendmessage')) == 1


@pytest.mark.parametrize('wrong', ['name', 'hash'])
def test_instruction_and_wrong_file_in_same_batch_never_send(probe, wrong):
    value, wire = probe
    connect(value)
    incoming = file_message(file_name='another.docx') if wrong == 'name' else file_message()
    if wrong == 'hash':
        wire.download = encrypted(b'x' * len(PLAIN))
    incoming['message_id'] = 11
    wire.messages = [message(value.test_instruction), incoming]
    with pytest.raises(ProbeError):
        value.poll_messages()
    assert not wire.calls('/sendmessage')
    assert value.send_state == 'not_sent'
    assert value.summary()['file_verified'] is False
    wire.messages = []
    value.poll_messages()
    assert not wire.calls('/sendmessage')


def test_bad_later_file_cannot_use_an_earlier_valid_file_to_send(probe):
    value, wire = probe
    connect(value)
    verify_file(value, wire)
    wrong = file_message(file_name='another.docx')
    wrong['message_id'] = 12
    wire.messages = [message(value.test_instruction), wrong]
    with pytest.raises(ProbeError):
        value.poll_messages()
    wire.messages = []
    value.poll_messages()
    assert not wire.calls('/sendmessage')
    assert value.summary()['file_verified'] is False


def test_close_clears_a_pending_command_context(probe):
    value, wire = probe
    connect(value)
    wire.messages = [message(value.test_instruction)]
    value.poll_messages()
    assert not wire.calls('/sendmessage')
    value.close()
    assert not any('secret' in str(item) for item in vars(value).values())


@pytest.mark.parametrize('length', [len(PLAIN), float(len(PLAIN)), True, '0' + str(len(PLAIN)), str(len(PLAIN)) + ' '])
def test_file_length_uses_pinned_official_decimal_string_contract(probe, length):
    value, wire = probe
    connect(value)
    wire.messages = [file_message(len=length)]
    with pytest.raises(ProbeError, match='UNEXPECTED_FILE'):
        value.poll_messages()
    assert not wire.calls('/download')
