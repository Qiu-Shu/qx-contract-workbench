"""Shared live/history profile contract uses only current synthetic text."""
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_codec, profile_preparation
from tests.unit.test_assistant_profile_codec import fixture, response
from tests.unit.test_assistant_profile_preparation import basis, saved
from tests.integration.test_assistant_main_provider import config, KEY


def values():
    _, request = fixture()
    prepared = profile_preparation.prepare(*saved(request), basis(request, project_intake=True),
                                           config(), composer_revision=4)
    candidate = profile_codec.decode_response(response(request), request, config(), KEY).output
    return prepared, candidate


def test_fixed_commit_binds_the_same_plan_without_manual_edits():
    prepared, candidate = values()
    build = getattr(profile_preparation, 'commit_request', None)
    assert callable(build), 'profile fixed commit contract is missing'
    request = build(prepared, candidate)
    assert request.request_id == uuid5(NAMESPACE_URL, 'qx-profile.save:1:' + str(prepared.request.run_id))
    assert request.patch == candidate.profile_patch and request.manual_edits == ()
    assert request.project_intake is True
    assert request.expected_intake_id is request.expected_intake_revision is None
    assert build(prepared, candidate) == request


@pytest.mark.parametrize('change', ['scope', 'revision', 'message', 'source_revision',
    'conversation', 'quote', 'position', 'digest', 'document_origin', 'citations', 'received_material'])
def test_candidate_cannot_expand_the_current_text_protocol(change):
    prepared, candidate = values()
    patch = candidate.profile_patch
    proposal = patch.changes[0]
    ref = proposal.source_refs[0]
    if change == 'scope':
        patch = patch.model_copy(update={'scope': patch.scope.model_copy(update={'input_revision': 7})})
    elif change == 'revision':
        patch = patch.model_copy(update={'base_profile_revision': 1})
    elif change == 'document_origin':
        proposal = proposal.model_copy(update={'origin': 'document_statement'})
    elif change == 'citations':
        candidate = candidate.model_copy(update={'citations': (d.MainCitation(
            message_id=prepared.request.message_id, quote_sha256=prepared.request.source_sha256),)})
    elif change == 'received_material':
        proposal = proposal.model_copy(update={'field': 'materials', 'value': d.ProfileMaterialsValue(
            kind='materials', value=(d.IntakeMaterial(name='合成材料', state='received'),))})
    else:
        changes = {'message': {'message_id': UUID(int=999)}, 'source_revision': {'source_revision': 2},
            'conversation': {'conversation_id': UUID(int=999)}, 'quote': {'quote': '乙称借款35000元'},
            'position': {'start': 1, 'end': 11}, 'digest': {'quote_sha256': '0' * 64}}
        proposal = proposal.model_copy(update={'source_refs': (ref.model_copy(update=changes[change]),)})
    if change not in ('scope', 'revision', 'citations'):
        patch = patch.model_copy(update={'changes': (proposal,)})
    candidate = candidate.model_copy(update={'profile_patch': patch})
    with pytest.raises(ValueError):
        profile_preparation.validate_candidate(candidate, prepared.request)


def test_valid_unknown_and_empty_changes_remain_valid():
    prepared, candidate = values()
    for changes in ((), (d.ProfileProposal(field='contact', value=d.NullFactValue(kind='null', value=None),
                                           origin='model_inference'),)):
        revised = candidate.model_copy(update={'profile_patch': candidate.profile_patch.model_copy(
            update={'changes': changes})})
        assert profile_preparation.validate_candidate(revised, prepared.request) == revised
