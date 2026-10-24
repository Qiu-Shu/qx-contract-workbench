"""The desktop projection exposes bounded same-target authorization state only."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d, 'WeixinConversationAuthorizationView'), 'D2e needs a conversation authorization projection'
    return d.WeixinConversationAuthorizationView


def scope():
    return d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=0, materials_revision=0)


def value(state='unbound', **changes):
    current = scope().model_dump(mode='json')
    authorized = None if state == 'unbound' else dict(current)
    if state == 'refresh_required':
        current['input_revision'] = 1
    if state == 'target_changed':
        current['binding_revision'] = 2
    return {**dict(mode='synthetic', state=state, current_scope=current,
        authorized_scope=authorized, grant_revision=0,
        scope_sha256=sha(authorized) if authorized else None), **changes}


@pytest.mark.parametrize('state', ['unbound', 'current', 'refresh_required', 'target_changed', 'revoked', 'archived', 'restored_blocked'])
def test_projection_roundtrips_all_actual_states_without_account_identifiers(state):
    view = model()(**value(state))
    assert model().model_validate_json(view.model_dump_json()) == view
    assert set(view.model_dump()) == {'mode', 'state', 'current_scope', 'authorized_scope', 'grant_revision', 'scope_sha256'}
    with pytest.raises(ValidationError):
        view.state = 'current'


@pytest.mark.parametrize('change', [
    {'mode':'live'}, {'state':'connected'}, {'grant_revision':True}, {'grant_revision':'1'},
    {'grant_revision':-1}, {'grant_revision':1}, {'scope_sha256':'f'*64},
    {'authorized_scope':scope()}, {'bot_account_id':'forbidden'}, {'mapping_id':str(uuid4())},
    {'reason':'not projected'},
])
def test_unbound_view_rejects_invented_authority_or_identifiers(change):
    with pytest.raises(ValidationError):
        model()(**value(**change))


@pytest.mark.parametrize('damage', ['hash', 'missing_hash', 'missing_scope', 'current_drift', 'refresh_same', 'refresh_target', 'refresh_regression'])
def test_bound_view_requires_matching_hash_and_honest_current_or_refresh_state(damage):
    values = value('current')
    if damage == 'hash':
        values['scope_sha256'] = 'f'*64
    elif damage == 'missing_hash':
        values['scope_sha256'] = None
    elif damage == 'missing_scope':
        values['authorized_scope'] = None
    elif damage == 'current_drift':
        values['current_scope']['input_revision'] = 1
    else:
        values['state'] = 'refresh_required'
        if damage == 'refresh_target':
            values['current_scope']['binding_revision'] = 2
        elif damage == 'refresh_regression':
            values['authorized_scope']['input_revision'] = 2
            values['scope_sha256'] = sha(values['authorized_scope'])
    with pytest.raises(ValidationError):
        model()(**values)


@pytest.mark.parametrize('state', ['archived', 'restored_blocked'])
def test_unbound_blocking_state_keeps_no_authorized_scope(state):
    assert model()(**value(state=state, authorized_scope=None, scope_sha256=None)).grant_revision == 0
