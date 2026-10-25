"""Bounded conversation input, preserving the historical v1 contract."""
from uuid import UUID

import pytest
from cn_contract import domain as d
from cn_contract.assistant.providers import profile_codec
from tests.unit.test_assistant_profile_codec import fixture
from tests.integration.test_assistant_main_provider import config


def history():
    return (d.ConversationHistoryMessage(message_id=UUID(int=90),role='user',source_revision=1,
        content='虚构甲借款35000元。'),
        d.ConversationHistoryMessage(message_id=UUID(int=91),role='assistant',source_revision=1,
        content='请补充还款日期。'))


def test_v2_sends_prior_messages_in_order_and_current_text_last():
    _, request=fixture('约定月底还款，继续分析。')
    request=request.model_copy(update={'scope':request.scope.model_copy(update={'input_revision':2}), 'source_revision':2})
    request=d.MainProfileRequest.model_validate(request.model_dump() | {
        'template_version':'profile-text-system-v2', 'conversation_history':history()})
    wire=profile_codec.build_request(request,config())
    assert [item['role'] for item in wire['messages']]==['system','user','assistant','user']
    assert '35000' in wire['messages'][1]['content']
    assert '月底' in wire['messages'][-1]['content']
    assert '当前' in wire['messages'][0]['content']


def test_v1_serialization_and_wire_stay_exactly_history_free():
    _,request=fixture()
    assert 'conversation_history' not in request.model_dump(mode='json')
    wire=profile_codec.build_request(request,config())
    assert len(wire['messages'])==2 and wire['messages'][0]['content']==profile_codec._SYSTEM


def test_version_and_history_cannot_be_mismatched():
    _,request=fixture()
    with pytest.raises(ValueError):
        d.MainProfileRequest.model_validate(request.model_dump() | {'conversation_history':history()})
    with pytest.raises(ValueError):
        d.MainProfileRequest.model_validate(request.model_dump() | {'template_version':'profile-text-system-v2'})


def test_plain_request_never_accepts_history_without_history_authorization():
    _,request=fixture()
    with pytest.raises(ValueError):
        d.MainRequest.model_validate({key:getattr(request,key) for key in d.MainRequest.model_fields} |
                                    {'conversation_history':history()})
