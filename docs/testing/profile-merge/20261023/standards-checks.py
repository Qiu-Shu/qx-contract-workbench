"""Independent synthetic checks; no persistence, network, or product mutation."""
import hashlib
import subprocess
import sys
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID

import pytest

from cn_contract import domain as d
from cn_contract.assistant.profiles import merge_profile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'a6d20edf8663222ce6469bae80edfc92c02627b2'


def inputs():
    scope = {'workspace_id': UUID(int=101), 'conversation_id': UUID(int=102),
             'binding_revision': 1, 'input_revision': 1, 'materials_revision': 0}
    text = '合成测试：本金为壹元。'
    sources = d.ProfileSourceSnapshot(scope=scope, messages=[{
        'id': UUID(int=103), 'role': 'user', 'content': text, 'source_revision': 1,
        'created_at': '2026-10-23T00:00:00Z'}])
    ref = {'kind': 'message', 'conversation_id': UUID(int=102), 'message_id': UUID(int=103),
           'source_revision': 1, 'start': 0, 'end': len(text), 'quote': text,
           'quote_sha256': hashlib.sha256(text.encode()).hexdigest()}
    patch = d.ProfilePatch(scope=scope, base_profile_revision=0, changes=[{
        'field': 'principal_amount', 'value': {'kind': 'money', 'value': '1', 'unit': 'CNY'},
        'origin': 'user_statement', 'source_refs': [ref]}])
    return sources, patch


def test_old_domain_unchanged_and_pure_import():
    baseline = subprocess.check_output(['git', 'show', BASE + ':src/cn_contract/domain.py'], cwd=ROOT)
    current = (ROOT / 'src/cn_contract/domain.py').read_bytes()
    assert current.replace(b'\r\n', b'\n').startswith(baseline.replace(b'\r\n', b'\n').rstrip())
    code = '''
import importlib.abc, sys
blocked=('sqlalchemy','sqlite3','docx','httpx','httpx2','cn_contract.web','cn_contract.documents','cn_contract.assistant.providers','cn_contract.intake.service')
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(fullname==n or fullname.startswith(n+'.') for n in blocked): raise AssertionError(fullname)
sys.meta_path.insert(0,Guard())
from cn_contract.assistant.profiles import merge_profile
assert callable(merge_profile)
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_public_merge_rejects_nested_money_forgery_under_low_precision():
    sources, patch = inputs()
    proposal = patch.changes[0]
    forged_money = proposal.value.model_copy(update={'value': Decimal('1.123456789')})
    forged = patch.model_copy(update={'changes': (proposal.model_copy(update={'value': forged_money}),)})
    with localcontext() as ctx:
        ctx.prec = 3
        with pytest.raises(ValueError):
            merge_profile(None, forged, sources)


def test_nested_construct_and_datetime_forgery_rejected():
    sources, patch = inputs()
    proposal = patch.changes[0]
    forged_ref = proposal.source_refs[0].model_construct(**{
        **proposal.source_refs[0].model_dump(), 'quote_sha256': 'f'*64})
    forged = patch.model_construct(**{**patch.model_dump(), 'scope': patch.scope, 'changes': (
        proposal.model_copy(update={'source_refs': (forged_ref,)}),)})
    with pytest.raises(ValueError):
        merge_profile(None, forged, sources)
    result = merge_profile(None, patch, sources)
    field = result.profile.fields[0]
    forged_state = result.profile.model_copy(update={'fields': (
        field.model_copy(update={'protected_value': d.DatetimeFactValue.model_construct(
            kind='datetime', value=datetime(2026,10,23))}),)})
    with pytest.raises(ValueError):
        merge_profile(forged_state, patch.model_copy(update={'base_profile_revision': 1, 'changes': ()}), sources)


def test_all_candidate_container_caps_revalidated():
    sources, patch = inputs()
    proposal = patch.changes[0]
    with pytest.raises(ValueError):
        merge_profile(None, patch.model_copy(update={'changes': (proposal,)*61}), sources)
    with pytest.raises(ValueError):
        merge_profile(None, patch, sources.model_copy(update={'messages': sources.messages*201}))
    forged_refs = proposal.model_copy(update={'source_refs': proposal.source_refs*41})
    with pytest.raises(ValueError):
        merge_profile(None, patch.model_copy(update={'changes': (forged_refs,)}), sources)
    first = merge_profile(None, patch, sources)
    field = first.profile.fields[0].model_copy(update={'candidates': (proposal,)*61})
    with pytest.raises(ValueError):
        merge_profile(first.profile.model_copy(update={'fields': (field,)}),
                      patch.model_copy(update={'base_profile_revision': 1, 'changes': ()}), sources)


def test_utc_normalization_exact_money_and_controls():
    sources, patch = inputs()
    when = d.ProfileProposal(field='follow_up_at', value={'kind':'datetime', 'value':'2026-10-23T08:30:00+08:00'},
        origin='user_statement', source_refs=patch.changes[0].source_refs)
    amount = patch.changes[0].model_copy(update={'value': d.ProfileMoneyValue(
        kind='money', value='1234567890123456.12345678', unit='CNY')})
    updated = patch.model_copy(update={'changes': (when, amount)})
    result = merge_profile(None, updated, sources, project_intake=True)
    assert result.projection.follow_up_at.isoformat() == '2026-10-23T00:30:00+00:00'
    field = next(f for f in result.profile.fields if f.field == 'principal_amount')
    assert field.candidates[0].value.value == Decimal('1234567890123456.12345678')
    assert result.projection.status == 'open'
    for control in (1, 'true', None):
        with pytest.raises(ValueError):
            merge_profile(None, patch, sources, project_intake=control)


def test_source_roles_and_revision_are_not_inferred_or_authorized():
    sources, patch = inputs()
    for update in ({'role': 'assistant'}, {'source_revision': 2}):
        forged = sources.model_copy(update={'messages': (sources.messages[0].model_copy(update=update),)})
        with pytest.raises(ValueError):
            merge_profile(None, patch, forged)
    first = merge_profile(None, patch, sources)
    assert first.profile.fields[0].verification == 'unverified'
    assert first.projection is None


def test_previous_source_cannot_claim_a_different_conversation():
    sources, patch = inputs()
    first = merge_profile(None, patch, sources)
    field = first.profile.fields[0]
    candidate = field.candidates[0]
    wrong_ref = candidate.source_refs[0].model_copy(update={'conversation_id': UUID(int=999)})
    wrong_candidate = candidate.model_copy(update={'source_refs': (wrong_ref,)})
    previous = first.profile.model_copy(update={'fields': (field.model_copy(update={
        'candidates': (wrong_candidate,)}),)})
    with pytest.raises(ValueError):
        merge_profile(previous, patch.model_copy(update={'base_profile_revision': 1, 'changes': ()}), sources)


def test_previous_status_cannot_hide_known_candidate():
    sources, patch = inputs()
    first = merge_profile(None, patch, sources)
    field = first.profile.fields[0].model_copy(update={'verification': 'unknown'})
    forged = first.profile.model_copy(update={'fields': (field,)})
    try:
        result = merge_profile(forged, patch.model_copy(update={'base_profile_revision': 1, 'changes': ()}), sources)
    except ValueError:
        return
    assert result.profile.fields[0].verification == 'unverified'


def test_exact_decimal_extremes_are_bounded_without_context_rounding():
    sources, patch = inputs()
    for text in ('0E-1000000', '0E+1000000', '-0.00000'):
        with localcontext() as ctx:
            ctx.prec = 3
            amount = d.ProfileMoneyValue(kind='money', value=text, unit='CNY')
            assert amount.value.as_tuple().exponent == 0
            updated = patch.model_copy(update={'changes': (patch.changes[0].model_copy(update={'value': amount}),)})
            assert merge_profile(None, updated, sources).profile.fields[0].candidates[0].value.value == Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 3
        amount = d.ProfileMoneyValue(kind='money', value='1234567890123456.12345678', unit='CNY')
        assert amount.value == Decimal('1234567890123456.12345678')
        for text in ('1E-9', '1E16', '0.' + '0'*80, 'NaN', '-1'):
            with pytest.raises(ValueError):
                d.ProfileMoneyValue(kind='money', value=text, unit='CNY')
