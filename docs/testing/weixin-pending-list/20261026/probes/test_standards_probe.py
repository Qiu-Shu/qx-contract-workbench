"""Independent synthetic empty-page archive probes; no network or real materials."""
from uuid import uuid4
import pytest
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.matters import create_matter
from cn_contract.persistence import MatterRow
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import pending
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_generation_service import append
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_generation_dispatch import state

@pytest.mark.parametrize('position', ['root', 'target'])
def test_archived_linked_case_denies_empty_pending_without_writes(world, position):
    h = setup_history(world)
    generation = append(h)
    cid = h['view'].scope.conversation_id if position == 'root' else generation.scope.conversation_id
    with h['database'].session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立合成归档空列表探针', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('当前案件归档守卫',)), h['actor'], db)
        intake = uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''), dict(id=str(intake),owner=str(h['actor'].user_id),
            request=str(uuid4()),sha='a'*64,matter=str(matter.id)))
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:cid'),
            dict(intake=str(intake),cid=str(cid)))
        db.get(MatterRow,str(matter.id)).status = 'archived'
    before = state(h['database'])
    with pytest.raises(ServiceError) as caught:
        pending.list_pending_descriptors(h['actor'],h['view'].scope.conversation_id,
            d.WeixinPendingQuery(target_conversation_id=generation.scope.conversation_id),database=h['database'])
    assert caught.value.code == 'CROSS_MATTER_DENIED'
    assert caught.value.status_code == 403
    assert state(h['database']) == before
