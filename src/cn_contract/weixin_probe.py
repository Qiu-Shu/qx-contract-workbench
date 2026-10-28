"""Bounded, memory-only iLink probe. No business integration or general send API.

Protocol adapted from Tencent/openclaw-weixin (MIT), pinned at 874637a0dbc2.
See sources/third-party-notices/weixin-probe/NOTICE.md.
"""
import base64
import hashlib
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .review.model_adapter import MAX_RAW_BYTES, strict_json

API_BASE = 'https://ilinkai.weixin.qq.com'
CDN_BASE = 'https://novac2c.cdn.weixin.qq.com/c2c'
MAX_FILE_BYTES = 1024 * 1024
REPLY_TEXT = '工作台连接测试已收到。仅用于本人虚构材料通道验证，未执行法律业务。'
_BASE_INFO = {'channel_version': '2.4.10', 'bot_agent': 'QXConnectionProbe/0.1'}
_COMMON_HEADERS = {'iLink-App-Id': 'bot', 'iLink-App-ClientVersion': str(0x02040A)}
_LOGIN_STATES = {'wait', 'scaned', 'confirmed', 'expired', 'need_verifycode',
                 'verify_code_blocked', 'scaned_but_redirect', 'binded_redirect'}
_TERMINAL = {'expired', 'verify_code_blocked', 'binded_redirect', 'closed'}


class ProbeError(ValueError):
    """Only fixed, non-sensitive codes cross the CLI boundary."""


def _string(value, *, limit=4096):
    if type(value) is not str or not value or len(value) > limit:
        raise ProbeError('INVALID_RESPONSE')
    return value


def _url(value, *, cdn=False):
    value = _string(value, limit=16384)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        allowed = host == 'novac2c.cdn.weixin.qq.com' if cdn else bool(
            re.fullmatch(r'ilink[a-z0-9-]*\.weixin\.qq\.com', host))
        if (parsed.scheme != 'https' or not allowed or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or any(ord(char) < 33 for char in value)):
            raise ValueError()
        if not cdn and (parsed.path not in ('', '/') or parsed.query):
            raise ValueError()
    except ValueError:
        raise ProbeError('UNSUPPORTED_HOST') from None
    return value.rstrip('/') if not cdn else value


def _key(value):
    try:
        raw = base64.b64decode(_string(value, limit=128), validate=True)
        if len(raw) == 32 and re.fullmatch(b'[0-9a-fA-F]{32}', raw):
            raw = bytes.fromhex(raw.decode('ascii'))
        if len(raw) != 16:
            raise ValueError()
        return raw
    except ValueError:
        raise ProbeError('INVALID_MEDIA_KEY') from None


def _identifier(value):
    if type(value) is int and 0 <= value < 2**64:
        return str(value)
    if (type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}', value)
            and int(value) < 2**64):
        return value
    raise ProbeError('INVALID_MESSAGE_ID')


def _success(value, *, required=False):
    if required and 'ret' not in value:
        raise ProbeError('INVALID_RESPONSE')
    for key in ('ret', 'errcode'):
        if key in value and (type(value[key]) is not int or value[key] != 0):
            raise ProbeError('REMOTE_REJECTED')


class ConnectionProbe:
    def __init__(self, *, client, expected_file):
        if (type(expected_file) is not dict or set(expected_file) != {'name', 'size', 'sha256'}
                or type(expected_file['size']) is not int
                or not 0 < expected_file['size'] <= MAX_FILE_BYTES
                or type(expected_file['sha256']) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', expected_file['sha256'])
                or type(expected_file['name']) is not str
                or not re.fullmatch(r'[^/\\:\x00-\x1f]{1,240}', expected_file['name'])):
            raise ProbeError('INVALID_EXPECTED_FILE')
        self._client = client
        self._expected = dict(expected_file)
        self._base = API_BASE
        self._token = self._bot = self._peer = self._qr = self._cursor = ''
        self._pending_context = ''
        self._seen = set()
        self._file_verified = False
        self.login_state = 'not_started'
        # A fresh challenge prevents old history from authorizing a new reply.
        self.test_instruction = '工作台连接测试 ' + secrets.token_hex(4)
        self.send_state = 'not_sent'
        self.send_client_id = None

    def _read(self, method, url, *, headers=None, payload=None, limit=MAX_RAW_BYTES, timeout=20):
        deadline = time.monotonic() + timeout
        try:
            with self._client.stream(method, url, headers={'Accept-Encoding': 'identity', **(headers or {})}, json=payload,
                    timeout=httpx.Timeout(timeout, connect=min(10, timeout)),
                    follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ProbeError('HTTP_ERROR')
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise ProbeError('UNSUPPORTED_ENCODING')
                length = response.headers.get('content-length')
                if length is not None and (len(length) > 20 or not length.isdecimal() or int(length) > limit):
                    raise ProbeError('RESPONSE_LIMIT')
                parts, size = [], 0
                for part in response.iter_bytes(chunk_size=16384):
                    size += len(part)
                    if size > limit:
                        raise ProbeError('RESPONSE_LIMIT')
                    if time.monotonic() > deadline:
                        raise ProbeError('NETWORK_TIMEOUT')
                    parts.append(part)
                return b''.join(parts)
        except httpx.HTTPError:
            raise ProbeError('NETWORK_ERROR') from None

    def _json(self, method, endpoint, *, payload=None, authenticated=False, timeout=20):
        headers = dict(_COMMON_HEADERS)
        if method == 'POST':
            headers.update({'Content-Type': 'application/json', 'AuthorizationType': 'ilink_bot_token',
                'X-WECHAT-UIN': base64.b64encode(str(secrets.randbits(32)).encode('ascii')).decode('ascii')})
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self._token
            payload = {**payload, 'base_info': dict(_BASE_INFO)}
        raw = self._read(method, self._base + endpoint, headers=headers, payload=payload, timeout=timeout)
        try:
            return strict_json(raw.decode('utf-8'))
        except (ValueError, UnicodeError):
            raise ProbeError('INVALID_RESPONSE') from None

    def start_qr(self):
        if self.login_state != 'not_started':
            raise ProbeError('QR_ALREADY_STARTED')
        value = self._json('POST', '/ilink/bot/get_bot_qrcode?bot_type=3', payload={'local_token_list': []})
        _success(value)
        qr = _string(value.get('qrcode'))
        display = _string(value.get('qrcode_img_content'), limit=16384)
        parsed = urlsplit(display)
        if (parsed.scheme != 'https' or not parsed.hostname
                or not parsed.hostname.endswith('.weixin.qq.com')
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or any(ord(char) < 33 for char in display)):
            raise ProbeError('UNSUPPORTED_QR_DISPLAY')
        self._qr, self.login_state = qr, 'wait'
        return display

    def poll_login(self, verify_code=None):
        if self.login_state in _TERMINAL or self.login_state in {'not_started', 'confirmed'}:
            raise ProbeError('LOGIN_NOT_PENDING')
        params = {'qrcode': self._qr}
        if verify_code is not None:
            if self.login_state != 'need_verifycode' or not re.fullmatch(r'[0-9]{4,12}', verify_code):
                raise ProbeError('INVALID_PAIRING_CODE')
            params['verify_code'] = verify_code
        value = self._json('GET', '/ilink/bot/get_qrcode_status?' + urlencode(params), timeout=40)
        _success(value)
        state = value.get('status')
        if type(state) is not str or state not in _LOGIN_STATES:
            raise ProbeError('INVALID_LOGIN_STATE')
        if state == 'scaned_but_redirect':
            self._base = _url('https://' + _string(value.get('redirect_host')))
        if state == 'confirmed':
            token = _string(value.get('bot_token'))
            if not re.fullmatch(r'[!-~]+', token):
                raise ProbeError('INVALID_RESPONSE')
            bot = _string(value.get('ilink_bot_id'))
            peer = _string(value.get('ilink_user_id'))
            base = _url(value.get('baseurl', self._base))
            self._token, self._bot, self._peer, self._base = token, bot, peer, base
            self._qr = ''
        self.login_state = state
        if state in _TERMINAL:
            self._qr = ''
        return state

    def _message(self, value):
        if type(value) is not dict:
            raise ProbeError('INVALID_MESSAGE')
        identifier = _identifier(value.get('message_id'))
        if (value.get('from_user_id') != self._peer or value.get('to_user_id') != self._bot
                or value.get('group_id', '') != '' or value.get('delete_time_ms', 0) != 0
                or type(value.get('message_type')) is not int or value['message_type'] != 1
                or type(value.get('message_state')) is not int or value['message_state'] != 2):
            raise ProbeError('PRIVATE_SCOPE_MISMATCH')
        items = value.get('item_list')
        if type(items) is not list or not 1 <= len(items) <= 20:
            raise ProbeError('INVALID_MESSAGE')
        for item in items:
            if type(item) is not dict or type(item.get('type')) is not int or item['type'] not in (1, 4):
                raise ProbeError('UNSUPPORTED_MESSAGE')
            if item.get('is_completed', True) is not True:
                raise ProbeError('INCOMPLETE_MESSAGE')
            body = item.get('text_item' if item['type'] == 1 else 'file_item')
            if type(body) is not dict:
                raise ProbeError('INVALID_MESSAGE')
            if item['type'] == 1:
                _string(body.get('text'), limit=20000)
        return identifier

    def _file(self, value):
        self._file_verified = False
        if value.get('file_name') != self._expected['name'] or value.get('len') != str(self._expected['size']):
            raise ProbeError('UNEXPECTED_FILE')
        media = value.get('media')
        if type(media) is not dict or type(media.get('encrypt_type')) is not int or media['encrypt_type'] != 1:
            raise ProbeError('INVALID_MEDIA')
        key = _key(media.get('aes_key'))
        url = media.get('full_url')
        if not url:
            url = CDN_BASE + '/download?' + urlencode({'encrypted_query_param': _string(media.get('encrypt_query_param'))})
        url = _url(url, cdn=True)
        limit = (self._expected['size'] // 16 + 1) * 16
        encrypted = self._read('GET', url, limit=limit)
        try:
            decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            padded = decryptor.update(encrypted) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
        except ValueError:
            raise ProbeError('INVALID_CIPHERTEXT') from None
        digest = hashlib.sha256(plaintext).hexdigest()
        if len(plaintext) != self._expected['size'] or digest != self._expected['sha256']:
            raise ProbeError('FILE_DIGEST_MISMATCH')
        self._file_verified = True
        return {'kind': 'file_verified', 'size': len(plaintext), 'sha256': digest}

    def _reply(self):
        if self.login_state != 'confirmed' or not self._file_verified or self.send_state != 'not_sent':
            raise ProbeError('REPLY_NOT_READY')
        context = _string(self._pending_context)
        self._pending_context = ''
        self.send_client_id = 'qx-probe-' + str(uuid4())
        # Once transmission begins, cancellation/exception also leaves unknown.
        self.send_state = 'unknown'
        try:
            value = self._json('POST', '/ilink/bot/sendmessage', authenticated=True, payload={'msg': {
                'from_user_id': '', 'to_user_id': self._peer, 'client_id': self.send_client_id,
                'message_type': 2, 'message_state': 2, 'context_token': context,
                'item_list': [{'type': 1, 'text_item': {'text': REPLY_TEXT}}]}})
            if type(value.get('ret')) is not int:
                return
            _success(value, required=True)
        except ProbeError as exc:
            if str(exc) == 'REMOTE_REJECTED':
                self.send_state = 'rejected'
            return
        self.send_state = 'submitted'

    def poll_messages(self):
        if self.login_state != 'confirmed':
            raise ProbeError('NOT_CONNECTED')
        value = self._json('POST', '/ilink/bot/getupdates', authenticated=True,
                           payload={'get_updates_buf': self._cursor}, timeout=40)
        _success(value, required=True)
        messages = value.get('msgs')
        cursor = value.get('get_updates_buf', self._cursor)
        if type(messages) is not list or len(messages) > 100 or type(cursor) is not str or len(cursor) > 16384:
            raise ProbeError('INVALID_UPDATES')
        identified = [(self._message(message), message) for message in messages]
        reports = []
        for identifier, message in identified:
            if identifier in self._seen:
                continue
            for item in message['item_list']:
                if item['type'] == 4:
                    reports.append(self._file(item['file_item']))
                else:
                    text = item['text_item']['text']
                    reports.append({'kind': 'text', 'characters': len(text)})
                    if (text == self.test_instruction and self.send_state == 'not_sent'
                            and not self._pending_context):
                        self._pending_context = _string(message.get('context_token'))
            self._seen.add(identifier)
            if len(self._seen) >= 5000:
                raise ProbeError('SESSION_LIMIT')
        # Validate the complete batch before a reply, including later file items.
        if self._file_verified and self._pending_context and self.send_state == 'not_sent':
            self._reply()
            reports.append({'kind': 'reply', 'state': self.send_state})
        if cursor:
            self._cursor = cursor
        return reports

    def summary(self):
        return {'login': self.login_state, 'file_verified': self._file_verified,
                'reply': self.send_state, 'send_client_id': self.send_client_id}

    def close(self):
        self._token = self._bot = self._peer = self._qr = self._cursor = ''
        self._pending_context = ''
        self._seen.clear()
        self.login_state = 'closed'
