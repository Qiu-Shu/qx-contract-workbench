"""Bounded iLink wire preview. No networking, media capability or inbox writes."""
import hashlib
from pathlib import PureWindowsPath
import re
import unicodedata

from . import domain as d
from .assistant import service as assistant
from .config import canonical_json
from .persistence import configured_database
from .review.model_adapter import MAX_RAW_BYTES, strict_json
from .security import ServiceError
from .task_drafts import service as tasks

_UINT64 = '18446744073709551615'
_DECIMAL = re.compile(r'(?:0|[1-9][0-9]*)\Z')
_RESPONSE = {'ret', 'errcode', 'errmsg', 'msgs', 'get_updates_buf',
             'longpolling_timeout_ms', 'sync_buf'}
_MESSAGE = {'message_id', 'from_user_id', 'to_user_id', 'client_id', 'session_id',
            'group_id', 'seq', 'create_time_ms', 'update_time_ms', 'delete_time_ms',
            'message_type', 'message_state', 'item_list', 'context_token', 'run_id'}
_ITEM = {'type', 'create_time_ms', 'update_time_ms', 'is_completed', 'msg_id',
         'text_item', 'file_item', 'ref_msg'}
_MIME = {'.pdf':'application/pdf',
         '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}


def _fail(code='STATE_CONFLICT', status=422):
    raise ServiceError(code, status)


def _keys(value, allowed, required=()):
    if type(value) is not dict or not set(required) <= value.keys():
        _fail()
    if value.keys() - allowed:
        _fail('NOT_SUPPORTED', 409)
    return value


def _string(value):
    if type(value) is not str:
        _fail()
    return value


def _integer(value):
    if type(value) is not int:
        _fail()
    return value


def _metadata(value, *, numbers=(), strings=()):
    for key in numbers:
        if key in value and _integer(value[key]) < 0:
            _fail()
    for key in strings:
        if key in value:
            _string(value[key])


def _message_id(value):
    if type(value) is int:
        if 0 <= value <= 2**64-1:
            return str(value)
        _fail()
    if (type(value) is not str or _DECIMAL.fullmatch(value) is None
            or len(value) > 20 or len(value) == 20 and value > _UINT64):
        _fail()
    return value


def _hash(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _scope(value):
    if not isinstance(value, d.WeixinOfflineScope):
        _fail()
    return d.WeixinOfflineScope.model_validate(value.model_dump(mode='python'))


def event_id(bot_account_id, sender_peer_id, message_id):
    """Exact source namespace, with lossless wire uint64 IDs canonicalized as strings."""
    return 'wx1:' + _hash([_string(bot_account_id), _string(sender_peer_id), _message_id(message_id)])


def create_offline_scope(actor, binding_id, *, bot_account_id, sender_peer_id, upstream_cursor, db):
    current = assistant._current(actor, db)
    binding = tasks.read_binding(current, binding_id, db)
    conversation = tasks._write(current, binding.conversation_id, db)
    try:
        return d.WeixinOfflineScope(bot_account_id=bot_account_id, sender_peer_id=sender_peer_id,
            owner_id=current.user_id, session_id=current.session_id, binding_id=binding.id,
            expected_scope=assistant._snapshot(conversation), task_cursor=binding.cursor,
            upstream_cursor=upstream_cursor)
    except (ValueError, TypeError):
        _fail()


def _reference(item, scope):
    if 'ref_msg' not in item:
        return None
    reference = _keys(item['ref_msg'], {'svr_id', 'message_item', 'title', 'partial_text'}, {'svr_id'})
    identifier = _message_id(reference['svr_id'])
    for key in ('title', 'partial_text'):
        if key in reference:
            _string(reference[key])
    if 'message_item' in reference:
        quoted = _keys(reference['message_item'], _ITEM)
        if 'msg_id' in quoted and _message_id(quoted['msg_id']) != identifier:
            _fail()
    return event_id(scope.bot_account_id, scope.sender_peer_id, identifier)


def _file(item, identifier, ordinal, settings):
    value = _keys(item['file_item'], {'file_name', 'md5', 'len', 'media'}, {'file_name'})
    name = _string(value['file_name'])
    if (not 1 <= len(name) <= 240 or name in {'.', '..'}
            or any(character in '/\\:<>"|?*' or unicodedata.category(character).startswith('C') for character in name)
            or name[-1:] in {' ', '.'} or PureWindowsPath(name).is_reserved()):
        _fail()
    suffix = PureWindowsPath(name).suffix.lower()
    if suffix not in _MIME:
        _fail('NOT_SUPPORTED', 409)
    if 'len' in value:
        length = _string(value['len'])
        if _DECIMAL.fullmatch(length) is None or length == '0':
            _fail()
        limit = str(settings.upload_max_file_mib * 1024 * 1024)
        if len(length) > len(limit) or len(length) == len(limit) and length > limit:
            _fail('FILE_LIMIT', 413)
    if 'md5' in value:
        _string(value['md5'])
    if 'media' in value:
        media = _keys(value['media'], {'encrypt_query_param', 'aes_key', 'encrypt_type', 'full_url'})
        for key in media:
            (_integer if key == 'encrypt_type' else _string)(media[key])
    return d.TaskMediaInput(media_id=identifier + ':' + str(ordinal), name=name,
        mime=_MIME[suffix], status='pending')


def _event(message, scope, settings):
    message = _keys(message, _MESSAGE, {'message_id', 'from_user_id', 'to_user_id',
        'message_type', 'message_state', 'item_list'})
    identifier = event_id(scope.bot_account_id, scope.sender_peer_id, message['message_id'])
    if (_string(message['from_user_id']) != scope.sender_peer_id
            or _string(message['to_user_id']) != scope.bot_account_id):
        _fail('CROSS_MATTER_DENIED', 403)
    if (_integer(message['message_type']) != 1 or _integer(message['message_state']) != 2):
        _fail('NOT_SUPPORTED', 409)
    _metadata(message, numbers=('seq', 'create_time_ms', 'update_time_ms', 'delete_time_ms'),
        strings=('client_id', 'session_id', 'context_token', 'run_id'))
    if 'group_id' in message and _string(message['group_id']):
        _fail('NOT_SUPPORTED', 409)
    if 'delete_time_ms' in message and _integer(message['delete_time_ms']) != 0:
        _fail('NOT_SUPPORTED', 409)
    items = message['item_list']
    if type(items) is not list or not items:
        _fail()
    if len(items) > 20:
        _fail('FILE_LIMIT', 413)
    texts, media, references = [], [], set()
    for ordinal, item in enumerate(items):
        item = _keys(item, _ITEM, {'type'})
        kind = _integer(item['type'])
        if kind not in (1, 4):
            _fail('NOT_SUPPORTED', 409)
        body = 'text_item' if kind == 1 else 'file_item'
        if body not in item:
            _fail()
        if ('file_item' if kind == 1 else 'text_item') in item:
            _fail('NOT_SUPPORTED', 409)
        _metadata(item, numbers=('create_time_ms', 'update_time_ms'))
        if 'is_completed' in item:
            if type(item['is_completed']) is not bool:
                _fail()
            if not item['is_completed']:
                _fail('NOT_SUPPORTED', 409)
        if 'msg_id' in item:
            _message_id(item['msg_id'])
        reference = _reference(item, scope)
        if reference:
            references.add(reference)
        if kind == 1:
            value = _keys(item['text_item'], {'text'}, {'text'})
            content = _string(value['text'])
            if not content.strip():
                _fail()
            texts.append(content)
        else:
            media.append(_file(item, identifier, ordinal, settings))
    if len(references) > 1:
        _fail()
    text = '\n'.join(texts)
    if len(text) > 20000:
        _fail('FILE_LIMIT', 413)
    return d.TaskInboxEventInput(event_id=identifier, text=text, media=tuple(media),
        reply_to_event_id=next(iter(references), None))


def translate_response(scope, raw_response, settings):
    """Plan one account response; accepting the plan never confirms its upstream cursor."""
    try:
        scope = _scope(scope)
        if type(raw_response) is not bytes:
            _fail()
        if len(raw_response) > MAX_RAW_BYTES:
            _fail('FILE_LIMIT', 413)
        value = _keys(strict_json(raw_response.decode('utf-8')), _RESPONSE)
        for key in ('ret', 'errcode'):
            if key in value and _integer(value[key]) != 0:
                _fail('BLOCKED_LIVE', 409)
        if 'msgs' not in value and not ({'ret', 'errcode'} & value.keys()):
            _fail()
        if 'errmsg' in value:
            _string(value['errmsg'])
        _metadata(value, numbers=('longpolling_timeout_ms',))
        if 'sync_buf' in value:
            _string(value['sync_buf'])
        cursor = _string(value['get_updates_buf']) if 'get_updates_buf' in value else scope.upstream_cursor
        messages = value.get('msgs', [])
        if type(messages) is not list:
            _fail()
        if len(messages) > 100:
            _fail('FILE_LIMIT', 413)
        events, hashes = [], {}
        for message in messages:
            event = _event(message, scope, settings)
            if event.event_id in hashes:
                _fail()
            hashes[event.event_id] = _hash(message)
            events.append(event)
        batch = d.TaskInboxBatchInput(expected_cursor=scope.task_cursor,
            next_cursor=scope.task_cursor+1, events=tuple(events)) if events else None
        return d.WeixinOfflinePlan(scope=scope, response_sha256=hashlib.sha256(raw_response).hexdigest(),
            next_upstream_cursor=cursor, batch=batch, event_payload_hashes=hashes)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail()


def preview_response(actor, scope, raw_response, *, db):
    try:
        scope = _scope(scope)
    except (ValueError, TypeError):
        _fail()
    current = create_offline_scope(actor, scope.binding_id, bot_account_id=scope.bot_account_id,
        sender_peer_id=scope.sender_peer_id, upstream_cursor=scope.upstream_cursor, db=db)
    if current != scope:
        _fail('VERSION_CONFLICT', 409)
    return translate_response(scope, raw_response, configured_database(db).settings)
