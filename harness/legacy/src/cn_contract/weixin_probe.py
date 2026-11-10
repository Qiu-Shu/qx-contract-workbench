"""Bounded, memory-only iLink probe with exact fictional-file/challenge gates.

Shared protocol: cn_contract.weixin_transport; Tencent MIT notice at
sources/third-party-notices/weixin-probe/NOTICE.md.
"""
import hashlib
import re
import secrets
from uuid import uuid4

# Retain the historical helper imports for probe/CLI consumers.
from .weixin_transport import (API_BASE, CDN_BASE, _ProtocolSession, ProbeError,
    _identifier, _key, _string, _success, _url)

MAX_FILE_BYTES = 1024 * 1024
REPLY_TEXT = '工作台连接测试已收到。仅用于本人虚构材料通道验证，未执行法律业务。'


class ConnectionProbe(_ProtocolSession):
    def __init__(self, *, client, expected_file):
        if (type(expected_file) is not dict or set(expected_file) != {'name', 'size', 'sha256'}
                or type(expected_file['size']) is not int
                or not 0 < expected_file['size'] <= MAX_FILE_BYTES
                or type(expected_file['sha256']) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', expected_file['sha256'])
                or type(expected_file['name']) is not str
                or not re.fullmatch(r'[^/\\:\x00-\x1f]{1,240}', expected_file['name'])):
            raise ProbeError('INVALID_EXPECTED_FILE')
        super().__init__(client=client)
        self._expected = dict(expected_file)
        self._cursor = ''
        self._pending_context = ''
        self._seen = set()
        self._file_verified = False
        self.login_state = 'not_started'
        # A fresh challenge prevents old history from authorizing a new reply.
        self.test_instruction = '工作台连接测试 ' + secrets.token_hex(4)
        self.send_state = 'not_sent'
        self.send_client_id = None

    def _file(self, value):
        self._file_verified = False
        if value.get('file_name') != self._expected['name'] or value.get('len') != str(self._expected['size']):
            raise ProbeError('UNEXPECTED_FILE')
        plaintext = self._download_file(value, max_bytes=MAX_FILE_BYTES)
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
        self.send_state = self._send_text(text=REPLY_TEXT, client_id=self.send_client_id, context=context)

    def poll_messages(self):
        if self.login_state != 'confirmed':
            raise ProbeError('NOT_CONNECTED')
        _, value = self._updates(self._cursor)
        messages = value['msgs']
        cursor = value.get('get_updates_buf', self._cursor)
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
        super().close()
        self._cursor = ''
        self._pending_context = ''
        self._seen.clear()
        self.login_state = 'closed'
