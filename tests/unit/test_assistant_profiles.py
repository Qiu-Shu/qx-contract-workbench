"""Synthetic behavior checks at the pure profile merge boundary."""
import hashlib
from decimal import Decimal, localcontext
from uuid import UUID
import pytest

from cn_contract.domain import IntakeDraft, ProfileEdit, ProfilePatch, ProfileSourceSnapshot
from cn_contract.record_codec import sha
from cn_contract.assistant.profiles import merge_profile


def uid(n):
    return UUID(int=n)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def source(text='甲称借款35000元，尚待核实。'):
    return ProfileSourceSnapshot.model_validate({
        'scope': {'workspace_id': uid(1), 'conversation_id': uid(2),
                  'binding_revision': 1, 'input_revision': 1, 'materials_revision': 0},
        'messages': [{'id': uid(3), 'role': 'user', 'content': text,
                      'source_revision': 1, 'created_at': '2026-01-01T00:00:00Z'}],
        'documents': [],
    })


def ref(s, start=0, end=None):
    message = s.messages[0]
    end = len(message.content) if end is None else end
    quote = message.content[start:end]
    return {'kind': 'message', 'conversation_id': s.scope.conversation_id,
            'message_id': message.id, 'source_revision': message.source_revision,
            'start': start, 'end': end, 'quote': quote, 'quote_sha256': digest(quote)}


def change(s, field='consultation', value=None, refs=None):
    return {'field': field, 'value': value or {'kind': 'text', 'value': '甲自述借款，尚待核实。'},
            'origin': 'user_statement', 'source_refs': [ref(s)] if refs is None else refs}


def patch(s, changes, revision=0):
    return ProfilePatch.model_validate({'scope': s.scope, 'base_profile_revision': revision,
                                       'changes': changes})


def test_message_proposal_produces_unverified_projection_with_exact_source():
    s = source()
    result = merge_profile(None, patch(s, [change(s)]), s, project_intake=True)
    assert result.changed is True
    assert result.profile.revision == 1
    assert result.profile.fields[0].verification == 'unverified'
    assert result.profile.fields[0].candidates[0].source_refs[0].quote == s.messages[0].content
    assert result.projection.consultation == '甲自述借款，尚待核实。'
    assert result.projection.status == 'open'
    assert result.projection.internal_notes == result.projection.client_reply == ''


def test_unknown_does_not_erase_known_and_same_role_conflicts_are_parallel():
    s = source()
    p = change(s, 'principal_amount', {'kind': 'money', 'value': '35000.00', 'unit': 'CNY'})
    first = merge_profile(None, patch(s, [p]), s)
    unknown = change(s, 'principal_amount', {'kind': 'null', 'value': None}, [])
    replay = merge_profile(first.profile, patch(s, [p, unknown], 1), s)
    assert not replay.changed
    conflicting = change(s, 'principal_amount', {'kind': 'money', 'value': '36000', 'unit': 'CNY'})
    payment = change(s, 'payment_amount', {'kind': 'money', 'value': '2000', 'unit': 'CNY'})
    result = merge_profile(first.profile, patch(s, [conflicting, payment], 1), s)
    fields = {f.field: f for f in result.profile.fields}
    assert fields['principal_amount'].verification == 'conflicted'
    assert {x.value.value for x in fields['principal_amount'].candidates} == {Decimal('35000'), Decimal('36000')}
    assert fields['payment_amount'].verification == 'unverified'
    assert result.projection is None


def test_invalid_message_location_is_rejected_before_mutating_any_result():
    s = source('同文。同文。')
    wrong = ref(s, 0, 2)
    wrong['start'], wrong['end'] = 1, 3
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, [change(s, refs=[wrong])]), s)


def document_source():
    s = source()
    anchor = {'id': str(uid(4)), 'document_version_id': str(uid(5)), 'part_name': 'word/document.xml',
              'element_id': 'p[1]', 'kind': 'body_paragraph', 'quote': '合成付款2000元',
              'quote_sha256': digest('合成付款2000元'), 'start': 0, 'end': 9,
              'table': None, 'row': None, 'cell': None, 'page': None, 'bbox': None}
    result = {'version_id': str(uid(5)), 'anchors': [anchor], 'pages': [],
              'parts': ['word/document.xml'], 'unsupported_parts': ['synthetic-object'], 'quality_issues': []}
    document = {'conversation_id': uid(2), 'attachment_id': uid(5), 'original_name': '合成凭证.docx',
                'original_sha256': '1' * 64, 'parse_revision': 1, 'result_sha256': sha(result), 'result': result}
    data = s.model_dump(mode='python')
    data['scope']['materials_revision'] = 1
    data['documents'] = [document]
    s = ProfileSourceSnapshot.model_validate(data)
    r = {'kind': 'document', **{k: v for k, v in document.items() if k not in ('result', 'original_name')},
         'anchor': anchor}
    return s, r


def test_document_source_must_match_selected_original_parse_and_exact_anchor():
    s, r = document_source()
    proposal = {**change(s, 'payment_amount', {'kind': 'money', 'value': '2000', 'unit': 'CNY'}, [r]),
                'origin': 'document_statement'}
    result = merge_profile(None, patch(s, [proposal]), s)
    assert result.profile.fields[0].verification == 'unverified'
    for key, wrong in [('parse_revision', 2), ('original_sha256', 'f' * 64),
                       ('result_sha256', 'f' * 64), ('attachment_id', uid(999))]:
        bad = {**proposal, 'source_refs': [{**r, key: wrong}]}
        with pytest.raises(ValueError):
            merge_profile(None, patch(s, [bad]), s)


def test_manual_clear_is_protected_and_new_model_value_only_a_suggestion():
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s, project_intake=True)
    edit = ProfileEdit(field='consultation', value={'kind': 'text', 'value': ''})
    cleared = merge_profile(first.profile, patch(s, [], 1), s,
                            manual_edits=(edit,), project_intake=True)
    assert cleared.projection.consultation == ''
    final = merge_profile(cleared.profile, patch(s, [change(s)], 2), s, project_intake=True)
    assert final.projection.consultation == ''
    assert final.profile.fields[0].protected_value.value == ''
    assert final.profile.fields[0].verification != 'confirmed'
    assert not final.changed


def test_legacy_empty_fields_are_protected_and_human_changes_since_baseline_survive():
    s = source()
    legacy = IntakeDraft(title='人工接待', status='waiting')
    result = merge_profile(None, patch(s, [change(s)]), s, intake_current=legacy, project_intake=True)
    assert result.projection == legacy
    first = merge_profile(None, patch(s, [change(s)]), s, project_intake=True)
    current = first.projection.model_copy(update={'consultation': '', 'status': 'closed'})
    revised = merge_profile(first.profile, patch(s, [change(s)], 1), s, intake_baseline=first.projection,
                            intake_current=current, project_intake=True)
    assert revised.projection.consultation == ''
    assert revised.projection.status == 'closed'


def test_semantic_replay_decimal_spellings_source_order_and_new_source():
    s = source('甲称付款0元。甲称付款0元。')
    one = change(s, 'payment_amount', {'kind': 'money', 'value': '-0.00', 'unit': 'CNY'}, [ref(s, 0, 7)])
    two = change(s, 'payment_amount', {'kind': 'money', 'value': '0', 'unit': 'CNY'}, [ref(s, 0, 7)])
    first = merge_profile(None, patch(s, [one]), s)
    same = merge_profile(first.profile, patch(s, [two], 1), s)
    assert not same.changed
    assert same.profile.fields[0].verification == 'unverified'
    second_ref = ref(s, 7, 14)
    addition = {**two, 'source_refs': [second_ref, ref(s, 0, 7), second_ref]}
    added = merge_profile(same.profile, patch(s, [addition], 1), s)
    assert added.changed and added.profile.revision == 2
    assert len(added.profile.fields[0].candidates[0].source_refs) == 2
    assert merge_profile(None, patch(s, [two, addition]), s) == merge_profile(None, patch(s, [addition, two]), s)


@pytest.mark.parametrize('field,value', [
    ('title', {'kind': 'text', 'value': 'x' * 301}),
    ('consultation', {'kind': 'text', 'value': 'x' * 12001}),
    ('questions', {'kind': 'list', 'value': ['问题'] * 31}),
    ('follow_up_note', {'kind': 'text', 'value': 'x' * 2001}),
    ('follow_up_at', {'kind': 'datetime', 'value': '2026-01-01T12:00:00'}),
    ('follow_up_at', {'kind': 'datetime', 'value': 1700000000}),
    ('principal_amount', {'kind': 'money', 'value': 1.1, 'unit': 'CNY'}),
    ('principal_amount', {'kind': 'money', 'value': '1', 'unit': ''}),
    ('principal_amount', {'kind': 'money', 'value': 'NaN', 'unit': 'CNY'}),
    ('principal_amount', {'kind': 'money', 'value': '-1', 'unit': 'CNY'}),
    ('title', {'kind': 'money', 'value': '1', 'unit': 'CNY'}),
    ('client_reply', {'kind': 'text', 'value': 'bad\x00text'}),
    ('status', {'kind': 'text', 'value': 'closed'}),
    ('client_id', {'kind': 'text', 'value': str(uid(9))}),
])
def test_invalid_fields_types_limits_dates_money_are_rejected(field, value):
    s = source()
    with pytest.raises(ValueError):
        patch(s, [change(s, field, value)])


@pytest.mark.parametrize('forgery', [
    {'origin': 'lawyer_input'}, {'verification': 'confirmed'},
    {'owner': str(uid(6))}, {'confirmed_by': str(uid(6))},
    {'source_refs': []},
])
def test_model_cannot_claim_trusted_metadata_or_unbacked_value(forgery):
    s = source()
    with pytest.raises(ValueError):
        patch(s, [{**change(s), **forgery}])


def test_nested_copy_forgery_of_quote_hash_or_field_type_is_revalidated():
    s = source()
    p = patch(s, [change(s)])
    bad_ref = p.changes[0].source_refs[0].model_copy(update={'quote_sha256': 'f' * 64})
    forged = p.model_copy(update={'changes': (p.changes[0].model_copy(update={'source_refs': (bad_ref,)}),)})
    with pytest.raises(ValueError):
        merge_profile(None, forged, s)
    bad_value = p.changes[0].value.model_copy(update={'value': 'x' * 12001})
    with pytest.raises(ValueError):
        merge_profile(None, p.model_copy(update={'changes': (p.changes[0].model_copy(update={'value': bad_value}),)}), s)


@pytest.mark.parametrize('property,wrong', [('conversation_id', uid(99)), ('source_revision', 2),
                                         ('message_id', uid(99)), ('quote_sha256', 'f' * 64)])
def test_wrong_message_identity_or_version_fails(property, wrong):
    s = source()
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, [change(s, refs=[{**ref(s), property: wrong}])]), s)


def test_stale_patch_and_different_scope_and_future_messages_fail():
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s)
    with pytest.raises(ValueError):
        merge_profile(first.profile, patch(s, []), s)
    changed = s.model_copy(update={'scope': s.scope.model_copy(update={'binding_revision': 2})})
    with pytest.raises(ValueError):
        merge_profile(first.profile, patch(changed, [], 1), changed)
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, []), changed)
    future = s.model_copy(update={'messages': (s.messages[0].model_copy(update={'source_revision': 2}),)})
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, []), future)


def test_document_wrong_anchor_or_corrupt_result_and_cross_conversation_fail():
    s, r = document_source()
    for altered in ({**r['anchor'], 'id': str(uid(99))}, {**r['anchor'], 'element_id': 'p[2]'},
                    {**r['anchor'], 'start': 9, 'end': 18}):
        proposal = {**change(s, refs=[{**r, 'anchor': altered}]), 'origin': 'document_statement'}
        with pytest.raises(ValueError):
            merge_profile(None, patch(s, [proposal]), s)
    for altered in ({'result_sha256': 'f' * 64}, {'conversation_id': uid(99)}, {'parse_revision': 2}):
        invalid = s.model_copy(update={'documents': (s.documents[0].model_copy(update=altered),)})
        with pytest.raises(ValueError):
            merge_profile(None, patch(s, []), invalid)
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, []), s.model_copy(update={'documents': s.documents * 2}))


def test_received_material_is_backed_and_never_marked_checked():
    s, r = document_source()
    value = {'kind': 'materials', 'value': [{'name': '合成凭证.docx', 'state': 'received'}]}
    proposal = {**change(s, 'materials', value, [r]), 'origin': 'document_statement'}
    result = merge_profile(None, patch(s, [proposal]), s, project_intake=True)
    assert result.projection.materials[0].state == 'received'
    for name, state in [('不存在.docx', 'received'), ('合成凭证.docx', 'checked')]:
        with pytest.raises(ValueError):
            bad = {**proposal, 'value': {'kind': 'materials', 'value': [{'name': name, 'state': state}]}}
            merge_profile(None, patch(s, [bad]), s, project_intake=True)


def test_unknown_and_general_writing_have_no_projection_and_audiences_remain_separate():
    s = source()
    assert merge_profile(None, patch(s, []), s, project_intake=True).projection is None
    assert merge_profile(None, patch(s, [change(s, value={'kind': 'null', 'value': None}, refs=[])]),
                         s, project_intake=True).projection is None
    proposals = [change(s, 'client_reply', {'kind': 'text', 'value': '客户可见'}),
                 change(s, 'internal_notes', {'kind': 'text', 'value': '律师内部判断待核'})]
    assert merge_profile(None, patch(s, proposals), s).projection is None
    result = merge_profile(None, patch(s, proposals), s, project_intake=True)
    assert result.projection.client_reply == '客户可见'
    assert result.projection.internal_notes == '律师内部判断待核'


def test_conflicting_projection_never_selects_latest_or_first_and_absence_keeps_value():
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s, project_intake=True)
    preserved = merge_profile(first.profile, patch(s, [], 1), s, project_intake=True)
    assert preserved.projection == first.projection
    second = change(s, value={'kind': 'text', 'value': '另一种未核对陈述'})
    conflicted = merge_profile(first.profile, patch(s, [second], 1), s,
                               intake_current=first.projection, intake_baseline=first.projection,
                               project_intake=True)
    assert conflicted.projection.consultation == ''
    assert len(conflicted.profile.fields[0].candidates) == 2


def test_follow_up_is_explicit_utc_and_manual_null_clear_stays_locked():
    s = source()
    first = merge_profile(None, patch(s, [change(s, 'follow_up_at',
                          {'kind': 'datetime', 'value': '2026-01-01T08:00:00+08:00'})]), s, project_intake=True)
    assert first.projection.follow_up_at.isoformat() == '2026-01-01T00:00:00+00:00'
    cleared = merge_profile(first.profile, patch(s, [], 1), s, project_intake=True,
                            manual_edits=(ProfileEdit(field='follow_up_at', value={'kind': 'null', 'value': None}),))
    assert cleared.projection.follow_up_at is None
    assert cleared.profile.fields[0].protected_value.kind == 'null'


def test_pure_import_does_not_load_persistence_web_document_or_provider_modules():
    import subprocess
    import sys
    probe = '''
import importlib.abc, sys
blocked = ('sqlalchemy', 'sqlite3', 'docx', 'cn_contract.web', 'cn_contract.documents',
           'cn_contract.assistant.providers', 'cn_contract.intake.service')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == x or fullname.startswith(x + '.') for x in blocked):
            raise AssertionError('unexpected dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
from cn_contract.assistant.profiles import merge_profile
assert callable(merge_profile)
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', probe], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_model_contact_requires_trusted_local_or_manual_input_even_with_a_source():
    s = source('没有联系方式的合成借款陈述。')
    for origin in ('user_statement', 'document_statement', 'model_inference'):
        with pytest.raises(ValueError):
            patch(s, [{**change(s, 'contact', {'kind': 'text', 'value': '虚构联系方式'}), 'origin': origin}])
    result = merge_profile(None, patch(s, []), s, project_intake=True,
                           manual_edits=(ProfileEdit(field='contact', value={'kind': 'text', 'value': '律师填写的本地联系渠道'}),))
    assert result.projection.contact == '律师填写的本地联系渠道'
    assert result.profile.fields[0].verification == 'unverified'


def test_previous_derived_verification_cannot_be_forged():
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s)
    forged = first.profile.model_copy(update={'fields': (
        first.profile.fields[0].model_copy(update={'verification': 'unknown'}),)})
    with pytest.raises(ValueError):
        merge_profile(forged, patch(s, [], 1), s)


@pytest.mark.parametrize('bad', [{'conversation_id': uid(999)}, {'source_revision': 2}])
def test_previous_sources_stay_within_historical_scope(bad):
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s)
    field = first.profile.fields[0]
    candidate = field.candidates[0]
    forged = first.profile.model_copy(update={'fields': (field.model_copy(update={
        'candidates': (candidate.model_copy(update={'source_refs': (candidate.source_refs[0].model_copy(update=bad),)}),)
    }),)})
    with pytest.raises(ValueError):
        merge_profile(forged, patch(s, [], 1), s)


@pytest.mark.parametrize('precision', [3, 28, 60])
def test_profile_money_limits_do_not_depend_on_decimal_context(precision):
    from cn_contract.domain import ProfileMoneyValue
    with localcontext() as ctx:
        ctx.prec = precision
        for value in ('1.123456789', '10000000000000000', '1E-1000000', '1E+1000000'):
            with pytest.raises(ValueError):
                ProfileMoneyValue(kind='money', value=value, unit='CNY')
        valid = ProfileMoneyValue(kind='money', value='9999999999999999.99999999', unit='CNY')
        assert valid.value == Decimal('9999999999999999.99999999')
        zero = ProfileMoneyValue(kind='money', value='-0E-1000000', unit='CNY')
        assert str(zero.value) == '0'
