"""Synthetic wire bytes only; no login, network or durable checkpoint."""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
from uuid import UUID

import pytest

from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.security import ServiceError


def adapter_module():
    assert importlib.util.find_spec('cn_contract.weixin_offline') is not None, 'D1 offline adapter missing'
    return importlib.import_module('cn_contract.weixin_offline')


@pytest.fixture
def scope():
    return dict(bot_account_id='bot-A', sender_peer_id='peer-A',
        owner_id=UUID(int=1), session_id=UUID(int=2), binding_id=UUID(int=3),
        expected_scope=d.ScopeSnapshot(workspace_id=UUID(int=4), conversation_id=UUID(int=5),
            binding_revision=1, input_revision=0, materials_revision=0),
        task_cursor=7, upstream_cursor='opaque:之前/==')


def message(identifier='18446744073709551615', **changes):
    value = {'message_id':identifier, 'from_user_id':'peer-A', 'to_user_id':'bot-A',
        'message_type':1, 'message_state':2,
        'item_list':[{'type':1, 'text_item':{'text':'请审查这份虚构合同'}}]}
    value.update(changes)
    return value


def wire(messages=None, **changes):
    value = {'ret':0, 'errcode':0, 'msgs':[message()] if messages is None else messages,
        'get_updates_buf':'opaque:下一页/=='}
    value.update(changes)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def plan(adapter, scope, messages=None, **changes):
    return adapter.translate_response(scope, wire(messages, **changes), load_settings())


def rejected(adapter, scope, raw, code='STATE_CONFLICT', status=422):
    with pytest.raises(ServiceError) as caught:
        adapter.translate_response(scope, raw, load_settings())
    assert (caught.value.code, caught.value.status_code) == (code, status)
    assert str(caught.value) in {'request blocked', 'request not authorized'}


def test_uint64_zero_and_max_preserve_message_identity_and_opaque_cursor(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    result = plan(adapter, scope, [message('0'), message()])
    assert isinstance(result, d.WeixinOfflinePlan)
    assert result.scope == scope
    assert result.next_upstream_cursor == 'opaque:下一页/=='
    assert result.batch.expected_cursor == 7 and result.batch.next_cursor == 8
    assert len(result.batch.events) == 2
    assert result.batch.events[0].event_id != result.batch.events[1].event_id
    assert result.batch.events[1].text == '请审查这份虚构合同'
    assert result.batch.events[1].task_id is None
    assert result.batch.events[1].start_new is False


def test_stable_identity_is_exact_account_peer_and_wire_id():
    adapter = adapter_module()
    expected = hashlib.sha256(b'["bot-A","peer-A","18446744073709551615"]').hexdigest()
    assert adapter.event_id('bot-A', 'peer-A', '18446744073709551615') == 'wx1:' + expected
    assert adapter.event_id('bot-B', 'peer-A', '1') != adapter.event_id('bot-A', 'peer-A', '1')
    assert adapter.event_id('bot-A', 'peer-B', '1') != adapter.event_id('bot-A', 'peer-A', '1')


def test_response_hash_is_raw_bytes_and_each_message_hash_covers_discarded_secrets(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    original = message(context_token='SECRET_CONTEXT')
    raw = wire([original])
    first = adapter.translate_response(scope, raw, load_settings())
    altered = message(context_token='CHANGED_SECRET_CONTEXT')
    second = plan(adapter, scope, [altered])
    assert first.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert first.batch == second.batch
    assert first.event_payload_hashes != second.event_payload_hashes
    assert 'SECRET_CONTEXT' not in first.model_dump_json()
    reordered = dict(reversed(list(original.items())))
    assert plan(adapter, scope, [reordered]).event_payload_hashes == first.event_payload_hashes


@pytest.mark.parametrize('reverse', [False, True])
def test_file_and_text_order_are_preserved_without_media_capabilities(scope, reverse):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    file_item = {'type':4, 'file_item':{'file_name':'独立虚构合同.PDF', 'len':'123',
        'md5':'untrusted', 'media':{'aes_key':'SECRET_AES', 'full_url':'https://secret.invalid/a',
            'encrypt_query_param':'SECRET_QUERY', 'encrypt_type':1}}}
    text_item = {'type':1, 'text_item':{'text':'补充说明'}}
    items = [file_item, text_item] if reverse else [text_item, file_item]
    result = plan(adapter, scope, [message(item_list=items)])
    event = result.batch.events[0]
    assert event.text == '补充说明'
    assert len(event.media) == 1
    media = event.media[0]
    assert media.name == '独立虚构合同.PDF' and media.mime == 'application/pdf'
    assert media.status == 'pending'
    assert media.attachment_id is None and media.sha256 is None and media.parse_revision is None
    serialized = result.model_dump_json()
    assert all(secret not in serialized for secret in ('SECRET_AES', 'secret.invalid', 'SECRET_QUERY', 'untrusted'))


def test_docx_without_declared_length_remains_pending(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    result = plan(adapter, scope, [message(item_list=[{'type':4, 'file_item':{'file_name':'合同.docx'}}])])
    assert result.batch.events[0].media[0].status == 'pending'
    assert result.batch.events[0].media[0].mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def test_text_items_join_with_one_newline_and_preserve_exact_text(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    result = plan(adapter, scope, [message(item_list=[{'type':1, 'text_item':{'text':' 第一段 '}},
        {'type':1, 'text_item':{'text':'第二段'}}])])
    assert result.batch.events[0].text == ' 第一段 \n第二段'


def test_official_boolean_completed_item_and_typed_metadata_are_accepted(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    item = {'type':1, 'is_completed':True, 'msg_id':9007199254740993,
        'create_time_ms':0, 'update_time_ms':10, 'text_item':{'text':'已完成'}}
    result = plan(adapter, scope, [message(item_list=[item], seq=1, create_time_ms=0,
        update_time_ms=10, delete_time_ms=0, client_id='client', session_id='session',
        context_token='SECRET', run_id='run')])
    assert result.batch.events[0].text == '已完成'


def ordinary_message(identifier=18446744073709551615):
    """Fictional values matching only the observed ordinary-message field shape."""
    return message(identifier, seq=1, client_id='fictional-client', session_id='fictional-session',
        create_time_ms=0, update_time_ms=1, delete_time_ms=0, group_id='',
        context_token='FICTIONAL_CONTEXT', root_id=0, parent_id=18446744073709551615,
        item_list=[{'type':1, 'text_item':{'text':'独立虚构普通消息'},
            'create_time_ms':0, 'update_time_ms':1, 'is_completed':True, 'msg_id':str(identifier),
            'button_item_list':[], 'at_bot_username_list':[]}])


@pytest.mark.parametrize('item_id', ['', 'client:fictional-item', '01', '7'])
def test_optional_item_id_is_string_metadata_not_server_message_identity(scope, item_id):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    incoming = ordinary_message()
    baseline = plan(adapter, scope, [incoming])
    incoming['item_list'][0]['msg_id'] = item_id
    changed = plan(adapter, scope, [incoming])
    assert changed.batch == baseline.batch
    assert changed.event_payload_hashes != baseline.event_payload_hashes
    incoming['message_id'] = ''
    rejected(adapter, scope, wire([incoming]))


@pytest.mark.parametrize('item_id', [None, True, False, 1.5, [], {}, -1, 2**64])
def test_optional_item_id_still_requires_string_or_legacy_uint64(scope, item_id):
    adapter = adapter_module()
    incoming = ordinary_message()
    incoming['item_list'][0]['msg_id'] = item_id
    rejected(adapter, d.WeixinOfflineScope(**scope), wire([incoming]))


@pytest.mark.parametrize('reference', [None, '7'])
def test_ordinary_message_metadata_keeps_explicit_reference_and_scope_authoritative(scope, reference):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    value = ordinary_message()
    if reference is not None:
        value['item_list'][0]['ref_msg'] = {'svr_id':reference,
            'message_item':{'type':1, 'msg_id':reference, 'text_item':{'text':'虚构引用'},
                'button_item_list':[], 'at_bot_username_list':[]}}
    event = plan(adapter, scope, [value]).batch.events[0]
    assert event.event_id == adapter.event_id('bot-A', 'peer-A', value['message_id'])
    assert event.text == '独立虚构普通消息'
    assert event.reply_to_event_id == (adapter.event_id('bot-A', 'peer-A', reference)
        if reference is not None else None)
    assert event.task_id is None and event.start_new is False and event.media == ()


@pytest.mark.parametrize('field', ['root_id', 'parent_id'])
@pytest.mark.parametrize('value', [0, 9007199254740993, 18446744073709551615])
def test_ordinary_message_uint64_metadata_is_lossless_but_not_task_data(scope, field, value):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    original = ordinary_message()
    changed = deepcopy(original)
    changed[field] = value
    result = plan(adapter, scope, [changed])
    assert result.batch == plan(adapter, scope, [original]).batch
    expected = hashlib.sha256(json.dumps(changed, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    assert result.event_payload_hashes[result.batch.events[0].event_id] == expected


@pytest.mark.parametrize('field', ['root_id', 'parent_id'])
@pytest.mark.parametrize('value', [True, False, 0.0, 1.5, {}, [], None, '', '0', -1, 2**64])
def test_ordinary_message_root_and_parent_require_exact_nonnegative_uint64_integers(scope, field, value):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    incoming = ordinary_message()
    incoming[field] = value
    rejected(adapter, scope, wire([incoming]))


@pytest.mark.parametrize('quoted', [False, True])
@pytest.mark.parametrize('field', ['button_item_list', 'at_bot_username_list'])
@pytest.mark.parametrize('value,code,status', [
    (None, 'STATE_CONFLICT', 422), (False, 'STATE_CONFLICT', 422),
    (0, 'STATE_CONFLICT', 422), ('', 'STATE_CONFLICT', 422), ({}, 'STATE_CONFLICT', 422),
    (['fictional-control'], 'NOT_SUPPORTED', 409), ([{}], 'NOT_SUPPORTED', 409)])
def test_ordinary_message_and_quoted_controls_remain_empty_only(scope, quoted, field, value, code, status):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    incoming = ordinary_message()
    item = incoming['item_list'][0]
    if quoted:
        item['ref_msg'] = {'svr_id':'7', 'message_item':{'type':1,
            'text_item':{'text':'虚构引用'}, 'button_item_list':[], 'at_bot_username_list':[]}}
        item = item['ref_msg']['message_item']
    item[field] = value
    rejected(adapter, scope, wire([incoming]), code, status)


@pytest.mark.parametrize('location', ['message', 'item', 'quoted'])
def test_ordinary_message_compatibility_keeps_other_unknown_keys_closed(scope, location):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    incoming = ordinary_message()
    target = incoming
    if location != 'message':
        target = incoming['item_list'][0]
    if location == 'quoted':
        target['ref_msg'] = {'svr_id':'7', 'message_item':{'type':1,
            'text_item':{'text':'虚构引用'}, 'button_item_list':[], 'at_bot_username_list':[]}}
        target = target['ref_msg']['message_item']
    target['future_field'] = []
    rejected(adapter, scope, wire([incoming]), 'NOT_SUPPORTED', 409)


@pytest.mark.parametrize('completed,code,status', [(False,'NOT_SUPPORTED',409),
    (1,'STATE_CONFLICT',422), (0,'STATE_CONFLICT',422), ('true','STATE_CONFLICT',422)])
def test_incomplete_or_nonboolean_item_completion_is_rejected(scope, completed, code, status):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    item = {'type':1, 'is_completed':completed, 'text_item':{'text':'x'}}
    rejected(adapter, scope, wire([message(item_list=[item])]), code, status)


@pytest.mark.parametrize('change', [{'seq':True}, {'create_time_ms':1.5}, {'update_time_ms':-1},
    {'client_id':{}}, {'session_id':False}, {'context_token':[]}, {'run_id':1}])
def test_known_message_metadata_keeps_its_declared_type(scope, change):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(**change)]))


@pytest.mark.parametrize('field,value', [('create_time_ms',False), ('update_time_ms',-1)])
def test_item_timestamps_require_local_nonnegative_integers(scope, field, value):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    item = {'type':1, field:value, 'text_item':{'text':'x'}}
    rejected(adapter, scope, wire([message(item_list=[item])]))


def test_reference_uses_scoped_svr_id_and_never_embedded_task_text(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    item = {'type':1, 'text_item':{'text':'补充'},
        'ref_msg':{'svr_id':'9007199254740993', 'title':'ignored',
            'partial_text':'task_id=00000000-0000-0000-0000-000000000099'}}
    event = plan(adapter, scope, [message(item_list=[item])]).batch.events[0]
    assert event.reply_to_event_id == adapter.event_id('bot-A', 'peer-A', '9007199254740993')
    assert event.task_id is None


def test_same_reference_on_multiple_items_is_unambiguous(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    items = [{'type':1, 'text_item':{'text':text}, 'ref_msg':{'svr_id':'1'}} for text in ('一', '二')]
    assert plan(adapter, scope, [message(item_list=items)]).batch.events[0].reply_to_event_id is not None


@pytest.mark.parametrize('changes', [{}, {'get_updates_buf':''}, {'get_updates_buf':'opaque-new'}])
def test_empty_poll_has_no_task_batch_and_never_invents_an_integer_checkpoint(scope, changes):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    payload = {'msgs':[], **changes}
    result = adapter.translate_response(scope, json.dumps(payload).encode(), load_settings())
    assert result.batch is None and result.event_payload_hashes == {}
    assert result.next_upstream_cursor == changes.get('get_updates_buf', scope.upstream_cursor)


@pytest.mark.parametrize('identifier', [True, 1.0, 1e3, -1, 2**64, None, '', '-1', '+1', '01', ' 1', '1 ',
    '1.0', '1e2', '18446744073709551616', '１２'])
def test_message_and_reference_ids_reject_noncanonical_uint64(scope, identifier):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(identifier)]))
    item = {'type':1, 'text_item':{'text':'补充'}, 'ref_msg':{'svr_id':identifier}}
    rejected(adapter, scope, wire([message(item_list=[item])]))


@pytest.mark.parametrize('identifier', [0, 9007199254740993, 18446744073709551615])
def test_numeric_wire_uint64_ids_are_lossless_and_share_string_identity(scope, identifier):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    item = {'type':1, 'text_item':{'text':'补充'}, 'ref_msg':{'svr_id':identifier}}
    result = plan(adapter, scope, [message(identifier, item_list=[item])])
    expected = adapter.event_id('bot-A', 'peer-A', str(identifier))
    assert result.batch.events[0].event_id == expected
    assert result.batch.events[0].reply_to_event_id == expected
    assert adapter.event_id('bot-A', 'peer-A', identifier) == expected


@pytest.mark.parametrize('change', [
    {'from_user_id':'peer-B'}, {'to_user_id':'bot-B'},
])
def test_exact_from_and_to_are_required_for_the_whole_poll(scope, change):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message('1'), message('2', **change)]), 'CROSS_MATTER_DENIED', 403)


@pytest.mark.parametrize('change', [
    {'message_type':2}, {'message_state':0}, {'message_state':1}, {'group_id':'group-A'},
    {'delete_time_ms':1}, {'future_field':True},
])
def test_unsupported_message_semantics_reject_entire_poll(scope, change):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message('1'), message('2', **change)]), 'NOT_SUPPORTED', 409)


@pytest.mark.parametrize('item', [
    {'type':2, 'image_item':{}}, {'type':3}, {'type':5}, {'type':11},
    {'type':1, 'text_item':{'text':'x'}, 'file_item':{'file_name':'x.pdf'}},
    {'type':1, 'text_item':{'text':'x', 'future_field':'SECRET'}},
    {'type':4, 'file_item':{'file_name':'x.exe'}},
])
def test_unknown_items_or_ambiguous_bodies_never_drop_silently(scope, item):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(item_list=[item])]), 'NOT_SUPPORTED', 409)


@pytest.mark.parametrize('change', [
    {'message_id':None}, {'message_type':True}, {'message_state':'2'},
    {'from_user_id':None}, {'item_list':[]}, {'item_list':None},
    {'item_list':[{'type':1, 'text_item':{'text':''}}]},
    {'item_list':[{'type':1, 'text_item':{'text':'   '}}]},
    {'item_list':[{'type':1, 'text_item':{'text':False}}]},
    {'item_list':[{'type':1, 'text_item':{'text':'x'}, 'ref_msg':{'title':'no stable id'}}]},
])
def test_missing_empty_or_mistyped_required_content_is_schema_error(scope, change):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(**change)]))


def test_missing_message_id_and_conflicting_references_reject(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    missing = message()
    del missing['message_id']
    rejected(adapter, scope, wire([missing]))
    items = [{'type':1, 'text_item':{'text':'x'}, 'ref_msg':{'svr_id':id_}} for id_ in ('1', '2')]
    rejected(adapter, scope, wire([message(item_list=items)]))


@pytest.mark.parametrize('name', ['', '../x.pdf', 'a/b.pdf', 'a\\b.pdf', 'C:x.pdf',
    'a\x00.pdf', 'a\n.pdf', '.', '..', 'x'*237+'.pdf'])
def test_file_name_must_be_a_bounded_safe_basename(scope, name):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(item_list=[{'type':4, 'file_item':{'file_name':name}}])]))


@pytest.mark.parametrize('character', ['<', '>', '"', '|', '?', '*'])
def test_file_name_rejects_remaining_windows_reserved_characters(scope, character):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(item_list=[{'type':4,
        'file_item':{'file_name':'虚构'+character+'合同.pdf'}}])]))


@pytest.mark.parametrize('length', [0, True, None, '', '0', '-1', '+1', '01', '1.0', ' 1'])
def test_declared_file_length_requires_a_positive_canonical_decimal_string(scope, length):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire([message(item_list=[{'type':4,
        'file_item':{'file_name':'x.pdf', 'len':length}}])]))


def test_raw_text_message_count_item_count_and_upload_size_have_local_limits(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, b' ' * (256*1024+1), 'FILE_LIMIT', 413)
    rejected(adapter, scope, wire([message(str(i)) for i in range(101)]), 'FILE_LIMIT', 413)
    rejected(adapter, scope, wire([message(item_list=[{'type':1, 'text_item':{'text':'x'}}]*21)]), 'FILE_LIMIT', 413)
    rejected(adapter, scope, wire([message(item_list=[{'type':1, 'text_item':{'text':'x'*20001}}])]), 'FILE_LIMIT', 413)
    limit = load_settings().upload_max_file_mib*1024*1024
    rejected(adapter, scope, wire([message(item_list=[{'type':4,
        'file_item':{'file_name':'x.pdf', 'len':str(limit+1)}}])]), 'FILE_LIMIT', 413)
    result = plan(adapter, scope, [message(item_list=[{'type':4,
        'file_item':{'file_name':'x.pdf', 'len':str(limit)}}])])
    assert result.batch.events[0].media[0].status == 'pending'


@pytest.mark.parametrize('raw', [b'{"msgs":[],"msgs":[]}', b'{"msgs":[],"n":NaN}',
    b'{"msgs":[],"n":1e999}', b'[]', b'\xff', b'not-json', bytearray(b'{"msgs":[]}'),
    '{"msgs":[]}', b'{"msgs":'+b'['*66+b']'*66+b'}'])
def test_strict_json_rejects_duplicates_nonfinite_invalid_depth_and_nonbytes(scope, raw):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, raw)


@pytest.mark.parametrize('changes', [{'ret':-14}, {'errcode':-1}])
def test_upstream_failure_blocks_without_reflecting_errmsg(scope, changes):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire(errmsg='SECRET_FAILURE_BODY', **changes), 'BLOCKED_LIVE', 409)


@pytest.mark.parametrize('code', ['ret', 'errcode'])
def test_upstream_failure_without_a_message_list_still_blocks_live(scope, code):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, json.dumps({code:-14, 'errmsg':'SECRET'}).encode(), 'BLOCKED_LIVE', 409)


@pytest.mark.parametrize('success', [{'ret':0}, {'errcode':0}])
@pytest.mark.parametrize('cursor', [None, 'opaque:next-empty'])
def test_explicit_success_may_omit_msgs_without_inventing_task_cursor(scope, success, cursor):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    payload = dict(success)
    if cursor is not None:
        payload['get_updates_buf'] = cursor
    result = adapter.translate_response(scope, json.dumps(payload).encode(), load_settings())
    assert result.batch is None and result.event_payload_hashes == {}
    assert result.scope.task_cursor == 7
    assert result.next_upstream_cursor == (cursor if cursor is not None else scope.upstream_cursor)


@pytest.mark.parametrize('payload', [{}, {'get_updates_buf':'opaque:unacknowledged'}])
def test_absent_msgs_without_explicit_success_is_rejected(scope, payload):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, json.dumps(payload).encode())


@pytest.mark.parametrize('changes', [{'ret':True}, {'errcode':'0'}, {'get_updates_buf':None}, {'msgs':None}])
def test_response_field_types_are_strict(scope, changes):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire(**changes))


def test_unknown_response_field_and_duplicate_message_id_reject(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope, wire(future_field='SECRET'), 'NOT_SUPPORTED', 409)
    rejected(adapter, scope, wire([message('1'), message('1')]))


def test_scope_and_plan_revalidate_forged_model_copies(scope):
    adapter = adapter_module()
    scope = d.WeixinOfflineScope(**scope)
    rejected(adapter, scope.model_copy(update={'task_cursor':True}), wire())
    with pytest.raises(ValueError):
        d.WeixinOfflineScope.model_validate({**scope.model_dump(), 'bot_account_id':''})
    first = plan(adapter, scope)
    changed = deepcopy(first.model_dump())
    changed['event_payload_hashes'] = {}
    with pytest.raises(ValueError):
        d.WeixinOfflinePlan.model_validate(changed)
