"""Memory-only, fixed-peer iLink transport; no persistence or business policy.

Protocol adapted from Tencent/openclaw-weixin (MIT), pinned at 874637a0dbc2.
See sources/third-party-notices/weixin-probe/NOTICE.md.
The caller owns the injected HTTP client, durable cursor and send claims.
"""
import base64
import hashlib
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .review.model_adapter import MAX_RAW_BYTES, strict_json

API_BASE = 'https://ilinkai.weixin.qq.com'
CDN_BASE = 'https://novac2c.cdn.weixin.qq.com/c2c'
_BASE_INFO = {'channel_version': '2.4.10', 'bot_agent': 'QXConnectionProbe/0.1'}
_COMMON_HEADERS = {'iLink-App-Id': 'bot', 'iLink-App-ClientVersion': str(0x02040A)}
_LOGIN_STATES = {'wait', 'scaned', 'confirmed', 'expired', 'need_verifycode',
                 'verify_code_blocked', 'scaned_but_redirect', 'binded_redirect'}
_TERMINAL = {'expired', 'verify_code_blocked', 'binded_redirect', 'closed'}


class ProbeError(ValueError):
    """Only fixed, non-sensitive codes cross the transport boundary."""


def _string(value, *, limit=4096):
    if type(value) is not str or not value or len(value) > limit:
        raise ProbeError('INVALID_RESPONSE')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ProbeError('INVALID_RESPONSE') from None
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
                or parsed.fragment or '\\' in value or '%' in parsed.netloc
                or any(ord(char) < 33 for char in value)):
            raise ValueError()
        if not cdn and (parsed.path not in ('', '/') or parsed.query):
            raise ValueError()
        if cdn and parsed.path != '/c2c/download':
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


def _file_metadata(value, *, max_bytes, documents_only=True):
    if type(max_bytes) is not int or not 0 < max_bytes < 2**63:
        raise ProbeError('INVALID_FILE_LIMIT')
    if type(value) is not dict:
        raise ProbeError('INVALID_MEDIA')
    name = value.get('file_name')
    if (type(name) is not str or not re.fullmatch(r'[^/\\:\x00-\x1f]{1,240}', name)
            or (documents_only and not name.lower().endswith(('.docx', '.pdf')))):
        raise ProbeError('UNSUPPORTED_FILE')
    size = value.get('len')
    if (type(size) is not str or not re.fullmatch(r'[1-9][0-9]{0,18}', size)
            or int(size) > max_bytes):
        raise ProbeError('INVALID_FILE_LENGTH')
    md5 = value.get('md5')
    if 'md5' in value and (type(md5) is not str or not re.fullmatch(r'[0-9a-fA-F]{32}', md5)):
        raise ProbeError('INVALID_MEDIA_DIGEST')
    return {'name': name, 'size': int(size), 'md5': md5.lower() if md5 is not None else None}


class _ProtocolSession:
    def __init__(self, *, client):
        self._client = client
        self._base = API_BASE
        self._token = self._bot = self._peer = self._qr = ''
        self.login_state = 'not_started'

    def _connected(self):
        if self.login_state != 'confirmed':
            raise ProbeError('NOT_CONNECTED')

    def identity(self):
        """Confirmed bot/peer only; never exposes token or QR credentials."""
        self._connected()
        return self._bot, self._peer

    def _read(self, method, url, *, headers=None, payload=None, limit=MAX_RAW_BYTES, timeout=20):
        if self.login_state == 'closed':
            raise ProbeError('CLOSED')
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
                if length is not None and (not re.fullmatch(r'0|[1-9][0-9]{0,19}', length)
                                           or int(length) > limit):
                    raise ProbeError('RESPONSE_LIMIT')
                parts, size = [], 0
                for part in response.iter_bytes(chunk_size=16384):
                    size += len(part)
                    if size > limit:
                        raise ProbeError('RESPONSE_LIMIT')
                    if time.monotonic() > deadline:
                        raise ProbeError('NETWORK_TIMEOUT')
                    parts.append(part)
                if length is not None and size != int(length):
                    raise ProbeError('INCOMPLETE_RESPONSE')
                return b''.join(parts)
        except httpx.HTTPError:
            raise ProbeError('NETWORK_ERROR') from None

    def _raw_json(self, method, endpoint, *, payload=None, authenticated=False, timeout=20):
        if self.login_state == 'closed':
            raise ProbeError('CLOSED')
        headers = dict(_COMMON_HEADERS)
        if method == 'POST':
            headers.update({'Content-Type': 'application/json', 'AuthorizationType': 'ilink_bot_token',
                'X-WECHAT-UIN': base64.b64encode(str(secrets.randbits(32)).encode('ascii')).decode('ascii')})
        if authenticated:
            self._connected()
            headers['Authorization'] = 'Bearer ' + self._token
            payload = {**payload, 'base_info': dict(_BASE_INFO)}
        raw = self._read(method, self._base + endpoint, headers=headers, payload=payload, timeout=timeout)
        try:
            return raw, strict_json(raw.decode('utf-8'))
        except (ValueError, UnicodeError):
            raise ProbeError('INVALID_RESPONSE') from None

    def _json(self, method, endpoint, **kwargs):
        return self._raw_json(method, endpoint, **kwargs)[1]

    def _download_file(self, value, *, max_bytes):
        self._connected()
        metadata = _file_metadata(value, max_bytes=max_bytes, documents_only=False)
        media = value.get('media')
        if type(media) is not dict:
            raise ProbeError('INVALID_MEDIA')
        # CDNMedia defaults to 0; both official modes still use the supplied AES key.
        encryption = media.get('encrypt_type', 0)
        if type(encryption) is not int or encryption not in (0, 1):
            raise ProbeError('INVALID_MEDIA')
        key = _key(media.get('aes_key'))
        url = media.get('full_url')
        if not url:
            url = CDN_BASE + '/download?' + urlencode({'encrypted_query_param': _string(media.get('encrypt_query_param'))})
        url = _url(url, cdn=True)
        limit = (metadata['size'] // 16 + 1) * 16
        encrypted = self._read('GET', url, limit=limit)
        try:
            decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            padded = decryptor.update(encrypted) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded) + unpadder.finalize()
        except ValueError:
            raise ProbeError('INVALID_CIPHERTEXT') from None
        if (len(plaintext) != metadata['size'] or (metadata['md5'] is not None
                and hashlib.md5(plaintext).hexdigest() != metadata['md5'])):
            raise ProbeError('FILE_DIGEST_MISMATCH')
        return plaintext

    def _send_text(self, *, text, client_id, context):
        self._connected()
        try:
            value = self._json('POST', '/ilink/bot/sendmessage', authenticated=True, payload={'msg': {
                'from_user_id': '', 'to_user_id': self._peer, 'client_id': client_id,
                'message_type': 2, 'message_state': 2, 'context_token': context,
                'item_list': [{'type': 1, 'text_item': {'text': text}}]}})
        except ProbeError:
            return 'unknown'
        if (type(value.get('ret')) is not int
                or ('errcode' in value and type(value['errcode']) is not int)):
            return 'unknown'
        if value['ret'] != 0 or value.get('errcode', 0) != 0:
            return 'rejected'
        return 'submitted'

    def _updates(self, cursor):
        self._connected()
        if type(cursor) is not str or len(cursor) > 16384:
            raise ProbeError('INVALID_UPDATES')
        if cursor:
            _string(cursor, limit=16384)
        raw, value = self._raw_json('POST', '/ilink/bot/getupdates', authenticated=True,
                                  payload={'get_updates_buf': cursor}, timeout=40)
        _success(value)
        messages = value.get('msgs')
        next_cursor = value.get('get_updates_buf', cursor)
        if (type(messages) is not list or len(messages) > 100
                or type(next_cursor) is not str or len(next_cursor) > 16384):
            raise ProbeError('INVALID_UPDATES')
        for message in messages:
            self._message(message)
        return raw, value

    def start_qr(self):
        if self.login_state != 'not_started':
            raise ProbeError('QR_ALREADY_STARTED')
        value = self._json('POST', '/ilink/bot/get_bot_qrcode?bot_type=3', payload={'local_token_list': []})
        _success(value)
        qr = _string(value.get('qrcode'))
        display = _string(value.get('qrcode_img_content'), limit=16384)
        try:
            parsed = urlsplit(display)
            if (parsed.scheme != 'https' or not parsed.hostname
                    or not parsed.hostname.endswith('.weixin.qq.com')
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in (None, 443) or parsed.fragment
                    or '\\' in display or '%' in parsed.netloc
                    or any(ord(char) < 33 for char in display)):
                raise ValueError()
        except ValueError:
            raise ProbeError('UNSUPPORTED_QR_DISPLAY') from None
        self._qr, self.login_state = qr, 'wait'
        return display

    def poll_login(self, verify_code=None):
        if self.login_state in _TERMINAL or self.login_state in {'not_started', 'confirmed'}:
            raise ProbeError('LOGIN_NOT_PENDING')
        params = {'qrcode': self._qr}
        if verify_code is not None:
            if (self.login_state != 'need_verifycode' or type(verify_code) is not str
                    or not re.fullmatch(r'[0-9]{4,12}', verify_code)):
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
        self._connected()
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

    def close(self):
        """Clear this session; the caller remains responsible for closing its client."""
        self._token = self._bot = self._peer = self._qr = ''
        self.login_state = 'closed'


class PersonalWeixinTransport(_ProtocolSession):
    """Internal fixed-peer transport, never registered as an HTTP contact API."""

    def validate_message(self, message):
        """Validate fixed-peer private text/file scope and return a lossless ID."""
        return self._message(message)

    def message_context(self, message):
        """Private in-memory context; never persist it with the inbox descriptor."""
        self._message(message)
        return _string(message.get('context_token'))

    def _file_item(self, message, item_index):
        self._message(message)
        if (type(item_index) is not int or not 0 <= item_index < len(message['item_list'])
                or message['item_list'][item_index]['type'] != 4):
            raise ProbeError('INVALID_MEDIA')
        return message['item_list'][item_index]['file_item']

    def file_metadata(self, message, *, item_index, max_bytes):
        """Validated document metadata without URL, media key or context credentials."""
        return _file_metadata(self._file_item(message, item_index), max_bytes=max_bytes)

    def download_file(self, message, *, item_index, max_bytes):
        """Return bounded original DOCX/PDF bytes; attachment service computes SHA256."""
        value = self._file_item(message, item_index)
        _file_metadata(value, max_bytes=max_bytes)
        return self._download_file(value, max_bytes=max_bytes)

    def send_text(self, *, text, client_id, context_message):
        """One attempt only. Caller must durably claim client_id before calling.

        The caller owns unknown/replay handling; submitted does not mean delivered.
        Context must come from this confirmed peer, never from model output.
        """
        context = self.message_context(context_message)
        _string(text, limit=20000)
        if type(client_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', client_id):
            raise ProbeError('INVALID_CLIENT_ID')
        return self._send_text(text=text, client_id=client_id, context=context)

    def poll_updates(self, cursor):
        """Return unchanged raw JSON; caller commits a cursor only after durable ingress."""
        return self._updates(cursor)[0]
