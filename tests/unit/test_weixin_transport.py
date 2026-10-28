"""Personal transport boundaries use fictional HTTP fixtures only."""
import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from cn_contract.weixin_transport import PersonalWeixinTransport, ProbeError
from cn_contract.weixin_probe import ConnectionProbe


PLAIN = b'FICTIONAL PDF DOCUMENT\n'
KEY = b'0123456789abcdef'


def test_probe_does_not_gain_general_send_or_document_api():
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('unexpected network'))) as client:
        probe = ConnectionProbe(client=client, expected_file={'name': 'fictional.docx',
            'size': len(PLAIN), 'sha256': hashlib.sha256(PLAIN).hexdigest()})
        assert not hasattr(probe, 'send_text')
        assert not hasattr(probe, 'download_file')


def incoming(**changes):
    return {'message_id': 18446744073709551615, 'from_user_id': 'fictional-peer',
        'to_user_id': 'fictional-bot', 'message_type': 1, 'message_state': 2,
        'context_token': 'private-context',
        'item_list': [{'type': 1, 'text_item': {'text': 'fictional instruction'}}], **changes}


def document(**changes):
    return incoming(item_list=[{'type': 4, 'file_item': {'file_name': 'fictional.pdf',
        'len': str(len(PLAIN)), 'md5': hashlib.md5(PLAIN).hexdigest(),
        'media': {'aes_key': base64.b64encode(KEY).decode(),
                  'encrypt_query_param': 'private-query&safe=1'}, **changes}}])


class Wire:
    def __init__(self):
        self.requests = []
        self.send = {'ret': 0}
        self.updates = b'{"msgs":[],"get_updates_buf":"next-cursor"}'
        self.statuses = [{'status': 'confirmed', 'bot_token': 'private-token',
                         'ilink_bot_id': 'fictional-bot', 'ilink_user_id': 'fictional-peer'}]
        self.display = 'https://ilinkai.weixin.qq.com/qr/display'
        padder = padding.PKCS7(128).padder()
        data = padder.update(PLAIN) + padder.finalize()
        encryptor = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
        self.download = encryptor.update(data) + encryptor.finalize()

    def handle(self, request):
        self.requests.append(request)
        if request.url.path.endswith('/get_bot_qrcode'):
            return httpx.Response(200, json={'qrcode': 'private-qr',
                'qrcode_img_content': self.display})
        if request.url.path.endswith('/get_qrcode_status'):
            return httpx.Response(200, json=self.statuses.pop(0))
        if request.url.path.endswith('/getupdates'):
            return httpx.Response(200, content=self.updates)
        if request.url.path.endswith('/sendmessage'):
            if isinstance(self.send, Exception):
                raise self.send
            return self.send if isinstance(self.send, httpx.Response) else httpx.Response(200, json=self.send)
        if request.url.path.endswith('/download'):
            if isinstance(self.download, Exception):
                raise self.download
            if isinstance(self.download, httpx.Response):
                return self.download
            return httpx.Response(200, content=self.download)
        raise AssertionError('unexpected fixture URL')


@pytest.fixture
def connected():
    wire = Wire()
    with httpx.Client(transport=httpx.MockTransport(wire.handle)) as client:
        value = PersonalWeixinTransport(client=client)
        value.start_qr()
        value.poll_login()
        yield value, wire
        value.close()


def test_fixed_peer_send_uses_claimed_client_id_and_context(connected):
    value, wire = connected
    assert value.send_text(text='fictional result', client_id='durable-claim-1',
                           context_message=incoming()) == 'submitted'
    request = wire.requests[-1]
    assert request.url.path.endswith('/sendmessage')
    assert json.loads(request.content)['msg'] == {'from_user_id': '',
        'to_user_id': 'fictional-peer', 'client_id': 'durable-claim-1',
        'message_type': 2, 'message_state': 2, 'context_token': 'private-context',
        'item_list': [{'type': 1, 'text_item': {'text': 'fictional result'}}]}


def test_document_download_checks_length_md5_and_scope(connected):
    value, wire = connected
    assert value.file_metadata(document(), item_index=0, max_bytes=100) == {
        'name': 'fictional.pdf', 'size': len(PLAIN), 'md5': hashlib.md5(PLAIN).hexdigest()}
    assert value.download_file(document(), item_index=0, max_bytes=100) == PLAIN
    request = wire.requests[-1]
    assert request.url.params['encrypted_query_param'] == 'private-query&safe=1'
    assert 'authorization' not in request.headers


@pytest.mark.parametrize('url', [
    'https://novac2c.cdn.weixin.qq.com/c2c/%2e%2e/download',
    'https://novac2c.cdn.weixin.qq.com/c2c/../download',
    'https://novac2c.cdn.weixin.qq.com/c2c\\download',
    'https://novac2c.cdn.weixin.qq.com.evil.invalid/c2c/download',
    'https://novac2c.cdn.weixin.qq.com@evil.invalid/c2c/download',
    'https://%6eovac2c.cdn.weixin.qq.com/c2c/download',
    'https://novac2c.cdn.weixin.qq.com:444/c2c/download',
    'http://novac2c.cdn.weixin.qq.com/c2c/download',
])
def test_download_url_cannot_bypass_cdn_boundary(connected, url):
    value, wire = connected
    msg = document()
    msg['item_list'][0]['file_item']['media']['full_url'] = url
    with pytest.raises(ProbeError, match='HOST'):
        value.download_file(msg, item_index=0, max_bytes=100)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('md5', [None, '', 'private-invalid-digest', True])
def test_supplied_malformed_digest_is_rejected_before_download(connected, md5):
    value, wire = connected
    with pytest.raises(ProbeError, match='DIGEST'):
        value.download_file(document(md5=md5), item_index=0, max_bytes=100)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('display', [
    'https://ilinkai.weixin.qq.com:private-port/qr',
    'https://[private-invalid-host/qr',
    'https://ilinkai.weixin.qq.com/qr#private-fragment',
    'https://ilinkai.weixin.qq.com/qr\\evil',
])
def test_malformed_qr_display_has_only_fixed_error(display):
    wire = Wire()
    wire.display = display
    with httpx.Client(transport=httpx.MockTransport(wire.handle)) as client:
        value = PersonalWeixinTransport(client=client)
        with pytest.raises(ProbeError, match='^UNSUPPORTED_QR_DISPLAY$'):
            value.start_qr()
        assert value.login_state == 'not_started'


def test_pairing_code_type_is_checked_before_network():
    wire = Wire()
    wire.statuses = [{'status': 'need_verifycode'}]
    with httpx.Client(transport=httpx.MockTransport(wire.handle)) as client:
        value = PersonalWeixinTransport(client=client)
        value.start_qr()
        value.poll_login()
        with pytest.raises(ProbeError, match='^INVALID_PAIRING_CODE$'):
            value.poll_login(123456)
        assert len(wire.requests) == 2


def test_truncated_http_send_response_stays_unknown(connected):
    value, wire = connected
    wire.send = httpx.Response(200, content=b'{"ret":0}', headers={'content-length': '999'})
    assert value.send_text(text='fictional result', client_id='claimed-1',
                           context_message=incoming()) == 'unknown'


@pytest.mark.parametrize('reply,expected', [
    ({'ret': 0}, 'submitted'), ({'ret': 0, 'errcode': 0}, 'submitted'),
    ({'ret': -14}, 'rejected'), ({'ret': 0, 'errcode': -14}, 'rejected'),
    ({}, 'unknown'), ({'errcode': -14}, 'unknown'), ({'ret': '0'}, 'unknown'),
    ({'ret': True}, 'unknown'), ({'ret': 0, 'errcode': '0'}, 'unknown'),
    ({'ret': 0.0}, 'unknown'), ({'ret': 0, 'errcode': True}, 'unknown'),
    ({'ret': 0, 'errcode': False}, 'unknown'),
    ({'ret': -14, 'errcode': True}, 'unknown'),
    (httpx.ReadTimeout('private-context'), 'unknown'),
    (httpx.ReadError('private-context'), 'unknown'),
    (httpx.Response(503, json={'ret': -14}), 'unknown'),
    (httpx.Response(302, headers={'location': 'https://outside.invalid/private'}), 'unknown'),
    (httpx.Response(200, content=b'private-invalid-json'), 'unknown'),
    (httpx.Response(200, content=b'{"ret":0,"ret":-14}'), 'unknown'),
    (httpx.Response(200, content=b'[]'), 'unknown'),
    (httpx.Response(200, content=b'\xff'), 'unknown'),
])
def test_send_receipts_are_conservative_and_never_retry(connected, reply, expected, caplog):
    value, wire = connected
    wire.send = reply
    assert value.send_text(text='fictional result', client_id='durable-claim-2',
                           context_message=incoming()) == expected
    assert len(wire.requests) == 3
    assert 'private' not in caplog.text


@pytest.mark.parametrize('changes', [
    {'from_user_id': 'another-peer'}, {'to_user_id': 'another-bot'},
    {'group_id': 'fictional-group'}, {'delete_time_ms': 1},
    {'message_type': 2}, {'message_state': 1},
    {'message_id': True}, {'message_id': 2**64}, {'message_id': '001'},
    {'item_list': []}, {'item_list': [{'type': 2, 'image_item': {}}]},
    {'item_list': [{'type': 1, 'is_completed': False, 'text_item': {'text': 'partial'}}]},
    {'context_token': ''}, {'context_token': None},
])
def test_send_context_requires_complete_same_peer_private_message(connected, changes):
    value, wire = connected
    with pytest.raises(ProbeError):
        value.send_text(text='fictional result', client_id='claim-3', context_message=incoming(**changes))
    assert len(wire.requests) == 2


@pytest.mark.parametrize('client_id', ['', None, True, 'x' * 129, 'private\r\nvalue', '../other'])
def test_send_rejects_invalid_claim_identifier(connected, client_id):
    value, wire = connected
    with pytest.raises(ProbeError, match='CLIENT_ID'):
        value.send_text(text='fictional result', client_id=client_id, context_message=incoming())
    assert len(wire.requests) == 2


def test_invalid_unicode_text_is_a_fixed_validation_error(connected):
    value, wire = connected
    with pytest.raises(ProbeError, match='^INVALID_RESPONSE$'):
        value.send_text(text='\ud800', client_id='claim-4', context_message=incoming())
    assert len(wire.requests) == 2


@pytest.mark.parametrize('changes', [
    {'file_name': 'fictional.exe'}, {'file_name': '../fictional.docx'},
    {'file_name': 'fictional.pdf.exe'}, {'file_name': 'fictional.doc'},
    {'len': 22}, {'len': True}, {'len': '022'}, {'len': '+22'},
    {'len': '２２'}, {'len': '22 '}, {'len': '0'}, {'len': '-1'},
    {'len': '101'}, {'len': '9' * 100},
])
def test_unsupported_documents_and_noncanonical_lengths_stop_before_network(connected, changes):
    value, wire = connected
    with pytest.raises(ProbeError):
        value.download_file(document(**changes), item_index=0, max_bytes=100)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('max_bytes', [None, True, 0, -1, 21, 2**63])
def test_document_download_requires_explicit_sufficient_byte_limit(connected, max_bytes):
    value, wire = connected
    with pytest.raises(ProbeError):
        value.download_file(document(), item_index=0, max_bytes=max_bytes)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('changes', [
    {'from_user_id': 'another-peer'}, {'to_user_id': 'another-bot'}, {'group_id': 'fictional-group'},
])
def test_other_scope_cannot_download_even_valid_document(connected, changes):
    value, wire = connected
    msg = document()
    msg.update(changes)
    with pytest.raises(ProbeError, match='SCOPE'):
        value.download_file(msg, item_index=0, max_bytes=100)
    assert len(wire.requests) == 2


@pytest.mark.parametrize('flag', ['absent', 0, 1])
@pytest.mark.parametrize('hex_key', [False, True])
def test_document_supports_official_encryption_and_key_encodings(connected, flag, hex_key):
    value, wire = connected
    msg = document(file_name='fictional.DOCX')
    media = msg['item_list'][0]['file_item']['media']
    media['aes_key'] = base64.b64encode(KEY.hex().encode() if hex_key else KEY).decode()
    if flag != 'absent':
        media['encrypt_type'] = flag
    assert value.download_file(msg, item_index=0, max_bytes=len(PLAIN)) == PLAIN


@pytest.mark.parametrize('changes', [
    {'encrypt_type': True}, {'encrypt_type': '0'}, {'encrypt_type': 2},
    {'aes_key': 'private-not-base64'}, {'aes_key': base64.b64encode(b'short').decode()},
])
def test_invalid_document_crypto_metadata_stops_before_download(connected, changes):
    value, wire = connected
    msg = document()
    msg['item_list'][0]['file_item']['media'].update(changes)
    with pytest.raises(ProbeError):
        value.download_file(msg, item_index=0, max_bytes=100)
    assert len(wire.requests) == 2


def test_optional_md5_mismatch_is_detected_and_omitted_md5_is_supported(connected):
    value, wire = connected
    with pytest.raises(ProbeError, match='DIGEST'):
        value.download_file(document(md5='0' * 32), item_index=0, max_bytes=100)
    msg = document()
    del msg['item_list'][0]['file_item']['md5']
    assert value.download_file(msg, item_index=0, max_bytes=100) == PLAIN
    assert value.download_file(document(md5=hashlib.md5(PLAIN).hexdigest().upper()),
                               item_index=0, max_bytes=100) == PLAIN


@pytest.mark.parametrize('download', [
    b'bad-padding', b'x' * 1000,
    httpx.Response(302, headers={'location': 'https://outside.invalid/private'}),
    httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=httpx.ByteStream(b'private')),
    httpx.ReadError('private-query'),
])
def test_download_stream_or_http_failure_exposes_only_fixed_code(connected, download, caplog):
    value, wire = connected
    wire.download = download
    with pytest.raises(ProbeError) as error:
        value.download_file(document(), item_index=0, max_bytes=100)
    assert 'private' not in str(error.value) and 'private' not in caplog.text
    assert len(wire.requests) == 3


def test_declared_plaintext_length_is_checked_after_decryption(connected):
    value, wire = connected
    with pytest.raises(ProbeError, match='DIGEST'):
        value.download_file(document(len=str(len(PLAIN) + 1)), item_index=0, max_bytes=100)


def test_poll_validates_entire_batch_and_preserves_uint64_bytes(connected):
    value, wire = connected
    wire.updates = json.dumps({'msgs': [incoming()], 'get_updates_buf': 'next'}, indent=2).encode()
    assert value.poll_updates('last-durable') == wire.updates
    assert value.validate_message(incoming()) == '18446744073709551615'
    assert value.validate_message(incoming(message_id='18446744073709551615')) == '18446744073709551615'
    wire.updates = json.dumps({'msgs': [incoming(), incoming(from_user_id='another-peer')],
                               'get_updates_buf': 'untrusted-next'}).encode()
    with pytest.raises(ProbeError, match='SCOPE'):
        value.poll_updates('last-durable')
    assert len(wire.requests) == 4


@pytest.mark.parametrize('raw', [b'{}', b'[]', b'{"msgs":[],"msgs":[]}',
    b'{"ret":-14,"msgs":[]}', b'{"msgs":[],"get_updates_buf":123}', b'\xff',
    b'{"msgs":[],"get_updates_buf":"' + b'x' * 16385 + b'"}', b'x' * 262145],
    ids=['missing', 'array', 'duplicate', 'error', 'cursor-type', 'invalid-utf8', 'long-cursor', 'oversized'])
def test_poll_rejects_invalid_or_unbounded_envelopes(connected, raw):
    value, wire = connected
    wire.updates = raw
    with pytest.raises(ProbeError):
        value.poll_updates('last-durable')
    assert len(wire.requests) == 3


def test_close_erases_session_and_blocks_every_public_operation(connected):
    value, wire = connected
    value.close()
    calls = [value.identity, value.start_qr, value.poll_login,
        lambda: value.poll_updates(''), lambda: value.validate_message(incoming()),
        lambda: value.message_context(incoming()),
        lambda: value.file_metadata(document(), item_index=0, max_bytes=100),
        lambda: value.download_file(document(), item_index=0, max_bytes=100),
        lambda: value.send_text(text='fictional result', client_id='claim', context_message=incoming())]
    for call in calls:
        with pytest.raises(ProbeError):
            call()
    assert len(wire.requests) == 2
    assert not any('private' in str(item) for item in vars(value).values())
    assert not value._client.is_closed  # HTTP client belongs to caller.


def test_poll_returns_original_bytes_and_leaves_cursor_to_caller():
    raw = b'{ "msgs": [], "get_updates_buf": "next-private-cursor" }'
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/get_bot_qrcode'):
            return httpx.Response(200, json={'qrcode': 'private-qr',
                'qrcode_img_content': 'https://ilinkai.weixin.qq.com/qr/display'})
        if request.url.path.endswith('/get_qrcode_status'):
            return httpx.Response(200, json={'status': 'confirmed', 'bot_token': 'private-token',
                'ilink_bot_id': 'fictional-bot', 'ilink_user_id': 'fictional-peer'})
        return httpx.Response(200, content=raw)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        transport = PersonalWeixinTransport(client=client)
        transport.start_qr()
        assert transport.poll_login() == 'confirmed'
        assert transport.identity() == ('fictional-bot', 'fictional-peer')
        assert transport.poll_updates('durable-cursor') == raw
        assert transport.poll_updates('durable-cursor') == raw
        assert [json.loads(r.content)['get_updates_buf'] for r in requests[-2:]] == [
            'durable-cursor', 'durable-cursor']
        transport.close()
