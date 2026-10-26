import pytest
from cn_contract import domain as d
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import pending
from tests.integration.test_weixin_ingress_atomic import world
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_generation_service import append

@pytest.mark.parametrize('foreign', ['other_peer', 'never_related'])
def test_existing_root_rejects_owned_but_unrelated_target(world, foreign):
    h = setup_history(world)
    append(h)
    target = h['peer_view'] if foreign == 'other_peer' else h['targets'][1][0]
    with pytest.raises(ServiceError) as caught:
        pending.list_pending_descriptors(h['actor'], h['view'].scope.conversation_id,
            d.WeixinPendingQuery(target_conversation_id=target.scope.conversation_id),
            database=h['database'])
    assert caught.value.code == 'CROSS_MATTER_DENIED'
