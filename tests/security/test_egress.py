"""T12 guarded destinations, independently fictional values, zero external send."""
import pytest
from cn_contract.domain import EgressPolicy
from cn_contract.security import ServiceError
from tests.helpers.synthetic_operations import feature


@pytest.mark.parametrize('destination', ['https://foreign.invalid/upload', 'http://127.0.0.1:9876/mock',
    'https://approved.cn@127.0.0.1/metadata', 'https://169.254.169.254/latest'])
def test_unapproved_endpoint_labels_cannot_enable_egress(destination):
    check = feature('egress', 'check_egress')
    policy = EgressPolicy(allowed_endpoints=(destination,), allowed_regions=('CN-mainland',),
        allowed_data_types=('contract_text',))
    with pytest.raises(ServiceError):
        check(destination, policy)


def test_actual_backend_fixed_loopback_registration_and_revocation(tmp_path):
    import asyncio
    from tests.helpers.synthetic_qcc import setup, ready, sdk_server
    from cn_contract.ops.egress import SyntheticEndpointRegistry
    from cn_contract.providers.qcc_registry import revoke_binding_manager
    database, owner, matter, registry_api = setup(tmp_path)
    with sdk_server() as (cfg, counts, _):
        ref, _, _, _ = asyncio.run(ready(database, owner, matter, registry_api, cfg=cfg))
        policy = EgressPolicy(allowed_endpoints=(cfg.endpoint,), allowed_regions=(), allowed_data_types=('contract_text',))
        registry = SyntheticEndpointRegistry(database, owner, matter.id, ref)
        assert feature('egress', 'check_egress')(cfg.endpoint, policy, registry=registry, addresses=('127.0.0.1',)) == cfg.endpoint
        with pytest.raises(ServiceError): feature('egress', 'check_egress')(cfg.endpoint, policy, registry=registry, addresses=('169.254.169.254',))
        with database.session() as db: revoke_binding_manager(owner.user_id, db=db)
        with pytest.raises(ServiceError): feature('egress', 'check_egress')(cfg.endpoint, policy, registry=registry)
        assert counts['call'] == 0
