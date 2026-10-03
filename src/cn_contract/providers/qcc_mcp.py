"""Approved registry adapter, synthetic only until the T08 budget gateway."""
from decimal import Decimal
import json
from uuid import UUID
from ..domain import ProviderConfig, ProviderResult, ToolBinding
from ..security import ServiceError, authorize
from .storage import append, encode
from . import qcc_registry as registry
from .mock_qcc import MockQccTransport


class QccTransport:
    def __init__(self, endpoint_ref, *, actor, matter_id, db, secrets=None):
        self.endpoint_ref = endpoint_ref; self.actor = actor; self.matter_id = matter_id
        self.db = db; self.secrets = secrets; self.dispatch_count = 0

    def _current(self, binding):
        endpoint = registry.read_case_endpoint(self.endpoint_ref, actor=self.actor, matter_id=self.matter_id, db=self.db)
        if not endpoint['synthetic'] or endpoint['live_allowed'] or endpoint['provider'] not in {'synthetic_mock_qcc', 'synthetic_mcp_loopback'}:
            raise ServiceError('BLOCKED_LIVE', 403)
        ref = registry.binding_reference(binding, actor=self.actor, matter_id=self.matter_id, db=self.db)
        current = registry.read_binding(ref, actor=self.actor, matter_id=self.matter_id, db=self.db)
        if not current.enabled or current.endpoint_config_ref != self.endpoint_ref or current != binding:
            raise ServiceError('TOOL_UNBOUND', 403)
        return endpoint

    async def invoke(self, binding, arguments, correlation_id):
        initial_dispatches = self.dispatch_count
        binding = ToolBinding.model_validate(binding.model_dump(mode='python'))
        endpoint = self._current(binding)
        try:
            correlation_id = UUID(str(correlation_id))
        except (ValueError, TypeError, AttributeError):
            raise ServiceError('TOOL_UNBOUND', 422) from None
        if type(arguments) is not dict:
            raise ServiceError('TOOL_UNBOUND', 422)
        registry.validate_schema(binding.input_schema_snapshot)
        try:
            if len(encode(arguments)) > 16384:
                raise ValueError()
            registry.schema_validator(binding.input_schema_snapshot).validate(arguments)
        except Exception:
            raise ServiceError('TOOL_UNBOUND', 422) from None
        status = 'sent_unknown'; raw = None; trace = None; error_code = None; received = False
        def before_dispatch():
            self._current(binding)
            self.dispatch_count += 1
        def on_catalog(catalog):
            registry.accept_discovered_catalog(self.endpoint_ref, catalog, actor=self.actor,
                matter_id=self.matter_id, db=self.db)
        try:
            if endpoint['provider'] == 'synthetic_mock_qcc':
                from .mock_qcc import catalog
                from .storage import latest
                variant = latest('variant', self.endpoint_ref, self.db)
                on_catalog(catalog(json.loads(variant.payload)['variant'] if variant else 'base'))
                before_dispatch()
                raw = await MockQccTransport().invoke(binding.tool_name, arguments, correlation_id)
            else:
                from .mcp_client import invoke
                raw = await invoke(ProviderConfig.model_validate(endpoint['config']), binding, arguments,
                    secrets=self.secrets, before_dispatch=before_dispatch, on_catalog=on_catalog)
            received = True
            self._current(binding)
            if raw.get('is_error'):
                status = 'failed'
            structured = raw.get('structured', raw)
            if type(structured) is dict:
                registry.schema_validator(binding.output_schema_snapshot).validate(structured)
                if structured.get('synthetic') is True and structured.get('state') == 'success' and not raw.get('is_error'):
                    status = 'success'
                candidate = structured.get('trace')
                if isinstance(candidate, str) and len(candidate) <= 64:
                    try:
                        trace = str(UUID(candidate))
                    except ValueError:
                        pass
        except ServiceError as exc:
            if self.dispatch_count == initial_dispatches:
                raise
            # No retry after a dispatch. Preserve receipt without unsafe error/body.
            error_code = exc.code
            if raw is None:
                raw = getattr(exc, '_protected_raw', None)
                received = raw is not None
            if raw is None:
                raw = {'synthetic': True, 'state': 'unknown', 'error_code': exc.code}
            elif 'wire_response' in raw:
                status = 'failed'
        except Exception:
            error_code = 'PROVIDER_ERROR'
            if raw is None:
                raw = {'synthetic': True, 'state': 'unknown', 'error_code': error_code}
            else:
                status = 'failed'
        with self.db.begin_nested():
            row = append('raw', self.endpoint_ref, raw, self.actor.user_id, self.db, matter_id=self.matter_id)
            append('invoke', self.endpoint_ref, {'correlation_id': str(correlation_id), 'status': status,
                'raw_ref': row.ref, 'raw_sha256': row.sha256, 'billing_known': True,
                'charged_credits': '0', 'unit': 'synthetic_credit', 'dispatch_count': self.dispatch_count-initial_dispatches,
                'input_sha256': __import__('hashlib').sha256(encode(arguments).encode()).hexdigest(),
                'synthetic': True, 'error_code': error_code,
                'raw_kind': 'protected_provider_response' if received else 'safe_error_summary'},
                self.actor.user_id, self.db, matter_id=self.matter_id)
        # Never return raw to revoked callers; protected receipt remains server-side.
        self._current(binding)
        return ProviderResult(status=status, trace_id=trace, raw_ref=row.ref, raw_sha256=row.sha256,
            billing_known=True, charged_credits=Decimal('0'))
