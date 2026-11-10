"""Application gate; production geography/DNS/OS isolation remains unapproved."""
import ipaddress
from urllib.parse import urlsplit
from ..domain import EgressPolicy
from ..security import ServiceError


class SyntheticEndpointRegistry:
    """Trusted server reference to actual T07 registration, not policy labels."""
    def __init__(self, database, actor, matter_id, endpoint_ref):
        self.database, self.actor, self.matter_id, self.endpoint_ref = database, actor, matter_id, endpoint_ref

    def current(self):
        from ..providers.qcc_registry import read_case_endpoint
        from .storage import require_active
        with self.database.session() as db:
            require_active(db)
            return read_case_endpoint(self.endpoint_ref, actor=self.actor, matter_id=self.matter_id, db=db)


def check_egress(destination, policy, *, registry=None, data_type='contract_text', addresses=(), redirect_chain=()):
    try:
        policy = EgressPolicy.model_validate_json(policy.model_dump_json())
        parts = urlsplit(destination)
        if parts.username or parts.password or parts.fragment or parts.query or parts.scheme != 'http':
            raise ValueError()
        if destination not in policy.allowed_endpoints or data_type not in policy.allowed_data_types:
            raise ValueError()
        if type(registry) is not SyntheticEndpointRegistry:
            raise ValueError()
        from ..providers.qcc_registry import allowed_synthetic_endpoint
        current = registry.current()
        if not allowed_synthetic_endpoint(destination) or current['provider'] != 'synthetic_mcp_loopback' or not current['synthetic'] or current['live_allowed'] or current['config']['endpoint'] != destination:
            raise ValueError()
        # Numeric fixed loopback requires no DNS. Caller assertions cannot enable
        # another address or redirect. Actual SDK transport binds this exact URL.
        if redirect_chain or any(ipaddress.ip_address(a) != ipaddress.ip_address('127.0.0.1') for a in addresses):
            raise ValueError()
        return destination
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ServiceError('BLOCKED_LIVE', 403) from None
