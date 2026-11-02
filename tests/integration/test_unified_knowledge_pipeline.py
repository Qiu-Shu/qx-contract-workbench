import asyncio
from pathlib import Path
from uuid import uuid4
import pytest
from cn_contract import domain as d
from cn_contract.assistant import material_preparation, material_attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.integrations.skill_registry import SkillRegistry
from cn_contract.exports import material_docx
from cn_contract.security import ServiceError
from tests.helpers.capability_knowledge import knowledge_config
from test_assistant_generation import world
from test_assistant_material_generation import material_world, selection_for, grant, response
from test_assistant_main_provider import config, server, KEY


@pytest.mark.parametrize('workflow',['sales','case'])
def test_automatic_knowledge_is_in_wire_output_export_and_immutable_history(material_world,tmp_path,workflow):
    database,actor,_,_=material_world
    settings=knowledge_config(tmp_path)
    database._capability_registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(settings))
    selection=selection_for(material_world,workflow)
    basis=material_preparation.preview(actor,selection,database,config())
    assert basis.manifest.knowledge.passages
    citation=basis.manifest.knowledge.passages[0].source_id
    with server(response(basis,[citation])) as (url,received,_):
        async def scenario():
            _,lease,approved=grant(material_world,selection,DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url))
            with database.session() as db:attempt=material_attempts.enqueue(actor,selection,approved,db,lease)
            result=await execute_attempt(actor,attempt.id,database,lease)
            assert result.output is not None and result.output.manifest.knowledge==basis.manifest.knowledge
            assert material_docx.build(result.output)
            database._capability_registry=None
            with database.session() as db:validate_model_records(db)
            return result
        asyncio.run(scenario())
        assert len(received)==1 and citation.encode() in received[0]['body']


def test_reference_changed_after_preview_blocks_send(material_world,tmp_path):
    database,actor,_,_=material_world
    settings=knowledge_config(tmp_path)
    database._capability_registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(settings))
    selection=selection_for(material_world)
    basis=material_preparation.preview(actor,selection,database,config())
    with server(response(basis)) as (url,received,_):
        async def scenario():
            _,lease,approved=grant(material_world,selection,DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url))
            path=Path(settings['skills'][1]['root'])/settings['knowledge']['family_files'][0]['path']
            path.write_text('更换后的参考资料',encoding='utf-8')
            with database.session() as db,pytest.raises(ServiceError):
                material_attempts.enqueue(actor,selection,approved,db,lease)
            assert not received
        asyncio.run(scenario())


def test_knowledge_quote_tampering_is_rejected_before_use(tmp_path):
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(knowledge_config(tmp_path)))
    packet=registry.retrieve('case','借款')
    values=packet.model_dump(mode='json');values['passages'][0]['text']='与已登记摘录不符'
    with pytest.raises(ValueError):d.KnowledgePacket.model_validate(values)


def test_court_rounds_keep_only_real_retrieved_cards_and_can_continue(material_world,tmp_path):
    from test_chiheng_capability import install,selection,Provider,run
    database,actor,_,_=material_world
    chiheng=install(database)
    settings=knowledge_config(tmp_path,public=True);settings['chiheng']=chiheng
    database._capability_registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(settings))
    class KnowledgeProvider(Provider):
        async def generate_material(self,request,**kwargs):
            reply=await super().generate_material(request,**kwargs)
            knowledge=next(p for p in request.basis.manifest.knowledge.passages if p.origin=='public_law')
            candidate=reply.output.model_copy(update={'citations':(*reply.output.citations,knowledge.source_id),
                'hearing_turns':tuple(turn.model_copy(update={'knowledge_ids':(knowledge.source_id,)}) for turn in reply.output.hearing_turns)})
            return reply.model_copy(update={'output':candidate})
    async def scenario():
        provider=KnowledgeProvider()
        first=await run(material_world,selection(material_world),provider)
        assert first.output is not None
        cards=first.output.hearing.session.turns[0].source_cards
        assert cards and cards[0].review_state=='unverified_mirror' and not cards[0].applicability_verified
        second=await run(material_world,selection(material_world,'继续模拟法庭。'),provider)
        assert second.output.hearing.session.turns[:3]==first.output.hearing.session.turns
        assert second.output.hearing.session.stage=='evidence' and provider.calls==2
    asyncio.run(scenario())
