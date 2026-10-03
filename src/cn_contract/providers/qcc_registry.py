"""Server-owned catalog, prices and approval history. No live authorization."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from urllib.parse import urlsplit
from uuid import UUID
from sqlalchemy import select
from ..domain import BindingInput, ProviderConfig, ToolBinding, ToolCatalog, ToolDefinition, Role
from ..persistence import UserRow, SessionRow, MembershipRow
from ..security import _principal, authorize, ServiceError
from .storage import initialize_storage, append, latest, by_ref, encode, require_storage, ProviderRecordRow
from .mock_qcc import catalog as mock_catalog


def allowed_synthetic_endpoint(endpoint):
    try:
        url = urlsplit(endpoint)
        return bool(url.scheme == 'http' and url.hostname == '127.0.0.1' and url.port and 1 <= url.port <= 65535
            and url.netloc == f'127.0.0.1:{url.port}' and url.path == '/mcp' and not url.query and not url.fragment)
    except (ValueError, TypeError):
        return False


def provision_binding_manager(user_id, *, db):
    """Trusted server provisioning; never implied by actor DTO or exposed via HTTP."""
    require_storage(db)
    user = db.get(UserRow, str(user_id), populate_existing=True)
    if not user or user.disabled or 'admin' not in json.loads(user.roles):
        raise ServiceError('TOOL_UNBOUND', 403)
    append('grant', user_id, {'enabled': True}, user_id, db)


def revoke_binding_manager(user_id, *, db):
    append('grant', user_id, {'enabled': False}, user_id, db)


def manager_valid(user_id, db):
    user = db.get(UserRow, str(user_id), populate_existing=True)
    grant = latest('grant', user_id, db)
    return bool(user and not user.disabled and 'admin' in json.loads(user.roles) and grant
                and json.loads(grant.payload)['enabled'])


def authorize_manager(actor, db):
    db.flush()
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if not principal:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    if not manager_valid(principal.user_id, db):
        raise ServiceError('TOOL_UNBOUND', 403)


def register_endpoint(config, *, actor, db):
    authorize_manager(actor, db)
    config = ProviderConfig.model_validate(config.model_dump(mode='python'))
    if config.approved_by or config.approved_at:
        raise ServiceError('BLOCKED_LIVE', 403)
    if config.transport == 'mock' and config.endpoint == 'mock://synthetic-t07' and not config.secret_ref:
        provider = 'synthetic_mock_qcc'
    else:
        # Only explicit server provision_synthetic_endpoint may authorize loopback.
        raise ServiceError('BLOCKED_LIVE', 403)
    return append('endpoint', '', {'config': config.model_dump(mode='json'), 'provider': provider,
        'synthetic': True, 'live_allowed': False}, actor.user_id, db).ref


def provision_synthetic_endpoint(config, *, actor, db):
    """Explicit trusted local-test registration, absent from HTTP/config ingestion.

    Numeric loopback and exact /mcp are mandatory; never authorizes real QCC.
    """
    authorize_manager(actor, db)
    config = ProviderConfig.model_validate(config.model_dump(mode='python'))
    if (config.transport != 'streamable_http' or not allowed_synthetic_endpoint(config.endpoint)
            or config.approved_by or config.approved_at):
        raise ServiceError('BLOCKED_LIVE', 403)
    return append('endpoint', '', {'config': config.model_dump(mode='json'), 'provider': 'synthetic_mcp_loopback',
        'synthetic': True, 'live_allowed': False}, actor.user_id, db).ref


def read_endpoint(ref, *, actor, db):
    authorize_manager(actor, db)
    return _endpoint(ref, db)


def _endpoint(ref, db):
    row = by_ref(ref, 'endpoint', db)
    if not row or not manager_valid(UUID(row.actor_id), db):
        raise ServiceError('TOOL_UNBOUND', 403)
    return json.loads(row.payload)


def authorize_case(actor, matter_id, db):
    """Recheck without rolling back a previously dispatched technical receipt."""
    db.flush()
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if not principal:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    member = db.get(MembershipRow, (str(matter_id), str(actor.user_id)), populate_existing=True)
    if not member or not principal.roles & {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER, Role.ASSISTANT}:
        raise ServiceError('CROSS_MATTER_DENIED', 403)


def read_case_endpoint(ref, *, actor, matter_id, db):
    """Server-only endpoint projection for T08; never a frontend response."""
    authorize_case(actor, matter_id, db)
    return _endpoint(ref, db)


def schema_hash(tool):
    tool = ToolDefinition.model_validate(tool.model_dump(mode='python'))
    return hashlib.sha256(encode({'name': tool.name, 'input': tool.input_schema_snapshot,
        'output': tool.output_schema_snapshot}).encode()).hexdigest()


def validate_schema(schema):
    from jsonschema import Draft202012Validator
    stack = [(schema, 0)]
    count = 0
    while stack:
        value, depth = stack.pop(); count += 1
        if depth > 32 or count > 10000:
            raise ServiceError('TOOL_UNBOUND', 422)
        if isinstance(value, dict):
            for keyword in ('$ref', '$dynamicRef', '$recursiveRef', '$id'):
                if keyword in value and (not isinstance(value[keyword], str) or not value[keyword].startswith('#')):
                    raise ServiceError('TOOL_UNBOUND', 422)
            if '$schema' in value and value['$schema'] != 'https://json-schema.org/draft/2020-12/schema':
                raise ServiceError('TOOL_UNBOUND', 422)
            stack.extend((v, depth+1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth+1) for v in value)
    try:
        if len(encode(schema)) > 65536:
            raise ValueError()
        Draft202012Validator.check_schema(schema)
    except Exception:
        raise ServiceError('TOOL_UNBOUND', 422) from None


def schema_validator(schema):
    """Defense in depth: no implicit remote retrieve even after preflight."""
    from jsonschema import Draft202012Validator
    from referencing import Registry
    validate_schema(schema)
    return Draft202012Validator(schema, registry=Registry())


async def discover_tools(endpoint_ref, *, actor, matter_id, db, secrets=None):
    if isinstance(endpoint_ref, ProviderConfig):
        # Spec DTO compatibility is a lookup, never authority to register/send.
        authorize_manager(actor, db)
        claimed = ProviderConfig.model_validate(endpoint_ref.model_dump(mode='python')).model_dump(mode='json')
        rows = db.scalars(select(ProviderRecordRow).where(ProviderRecordRow.kind == 'endpoint').order_by(ProviderRecordRow.sequence.desc()))
        endpoint_ref = next((row.ref for row in rows if json.loads(row.payload)['config'] == claimed), None)
        if endpoint_ref is None:
            raise ServiceError('BLOCKED_LIVE', 403)
    endpoint = read_endpoint(endpoint_ref, actor=actor, db=db)
    authorize(actor, matter_id, 'read', db)
    from ..ops.storage import require_active
    require_active(db)
    if endpoint['provider'] == 'synthetic_mock_qcc':
        variant = latest('variant', endpoint_ref, db)
        catalog = mock_catalog(json.loads(variant.payload)['variant'] if variant else 'base')
    elif endpoint['provider'] == 'synthetic_mcp_loopback':
        from .mcp_client import discover
        catalog = await discover(ProviderConfig.model_validate(endpoint['config']), secrets=secrets)
    else:
        raise ServiceError('BLOCKED_LIVE', 403)
    accept_discovered_catalog(endpoint_ref, catalog, actor=actor, matter_id=matter_id, db=db)
    return catalog


def accept_discovered_catalog(endpoint_ref, catalog, *, actor, matter_id, db):
    """Internal trusted SDK/mock projection; not a client catalog registration API."""
    endpoint = read_case_endpoint(endpoint_ref, actor=actor, matter_id=matter_id, db=db)
    if catalog.provider != endpoint['provider'] or len(catalog.tools) > 128 or len({t.name for t in catalog.tools}) != len(catalog.tools):
        raise ServiceError('TOOL_UNBOUND', 422)
    for tool in catalog.tools:
        validate_schema(tool.input_schema_snapshot); validate_schema(tool.output_schema_snapshot)
    # End check before accepting changed catalog from a request in flight.
    authorize_case(actor, matter_id, db)
    payload = catalog.model_dump(mode='json')
    current = latest('catalog', endpoint_ref, db)
    if current is None or json.loads(current.payload) != payload:
        append('catalog', endpoint_ref, payload, actor.user_id, db)


def register_mock_catalog_variant(ref, variant, *, actor, db):
    endpoint = read_endpoint(ref, actor=actor, db=db)
    if endpoint['provider'] != 'synthetic_mock_qcc':
        raise ServiceError('TOOL_UNBOUND', 403)
    mock_catalog(variant)
    append('variant', ref, {'variant': variant}, actor.user_id, db)


def register_synthetic_price(endpoint_ref, *, actor, db):
    read_endpoint(endpoint_ref, actor=actor, db=db)
    return UUID(append('price', endpoint_ref, {'unit_price': '0', 'unit': 'synthetic_credit/call',
        'synthetic': True, 'production_approval': None}, actor.user_id, db).ref)


def read_current_price(endpoint_ref, *, actor, db, matter_id=None):
    if matter_id is None:
        read_endpoint(endpoint_ref, actor=actor, db=db)
    else:
        read_case_endpoint(endpoint_ref, actor=actor, matter_id=matter_id, db=db)
    row = latest('price', endpoint_ref, db)
    if not row:
        raise ServiceError('PRICE_UNKNOWN', 403)
    return {'id': row.ref, **json.loads(row.payload)}


def _current_tool(endpoint_ref, name, db):
    row = latest('catalog', endpoint_ref, db)
    if row:
        tools = ToolCatalog.model_validate_json(row.payload).tools
        for tool in tools:
            if tool.name == name:
                return tool
    raise ServiceError('TOOL_UNBOUND', 403)


def bind_capability_record(value, *, actor, db):
    authorize_manager(actor, db)
    value = BindingInput.model_validate(value.model_dump(mode='python'))
    endpoint = read_endpoint(value.endpoint_config_ref, actor=actor, db=db)
    tool = _current_tool(value.endpoint_config_ref, value.tool_name, db)
    price = read_current_price(value.endpoint_config_ref, actor=actor, db=db)
    if (value.approved_by or value.approved_at or value.provider != endpoint['provider']
            or value.input_schema_snapshot != tool.input_schema_snapshot or value.output_schema_snapshot != tool.output_schema_snapshot
            or value.schema_hash != schema_hash(tool) or str(value.price_snapshot_id) != price['id']
            or value.unit_price != Decimal(price['unit_price']) or value.price_unit != price['unit']):
        raise ServiceError('TOOL_UNBOUND', 403)
    binding = ToolBinding(**value.model_dump(exclude={'unit_price', 'price_unit'}), enabled=False)
    return append('binding', value.endpoint_config_ref, binding.model_dump(mode='json'), actor.user_id, db).ref


def bind_capability(value, actor=None, *, db):
    """Specification-compatible pending DTO; technical immutable ref is separate."""
    ref = bind_capability_record(value, actor=actor, db=db)
    return read_binding(ref, actor=actor, db=db)


def read_approval(binding_ref, *, actor, db):
    authorize_manager(actor, db)
    row = latest('approval', binding_ref, db)
    return {'ref': row.ref, 'actor_id': row.actor_id, 'timestamp': row.timestamp.isoformat(),
            **json.loads(row.payload)} if row else None


def read_binding(binding_ref, *, actor, db, matter_id=None):
    if matter_id is None:
        authorize_manager(actor, db)
    else:
        authorize_case(actor, matter_id, db)
    row = by_ref(binding_ref, 'binding', db)
    if not row:
        raise ServiceError('TOOL_UNBOUND', 403)
    binding = ToolBinding.model_validate_json(row.payload)
    if matter_id is None:
        read_endpoint(binding.endpoint_config_ref, actor=actor, db=db)
    else:
        read_case_endpoint(binding.endpoint_config_ref, actor=actor, matter_id=matter_id, db=db)
    tool = _current_tool(binding.endpoint_config_ref, binding.tool_name, db)
    price = read_current_price(binding.endpoint_config_ref, actor=actor, db=db, matter_id=matter_id)
    approval = latest('approval', binding_ref, db)
    enabled = bool(approval and json.loads(approval.payload)['approved'] and manager_valid(UUID(approval.actor_id), db)
        and manager_valid(UUID(row.actor_id), db) and schema_hash(tool) == binding.schema_hash
        and price['id'] == str(binding.price_snapshot_id))
    return binding.model_copy(update={'enabled': enabled, 'approved_by': UUID(approval.actor_id) if approval else None,
        'approved_at': approval.timestamp if approval else None})


def approve_binding(binding_ref, *, actor, db):
    binding = read_binding(binding_ref, actor=actor, db=db)
    tool = _current_tool(binding.endpoint_config_ref, binding.tool_name, db)
    price = read_current_price(binding.endpoint_config_ref, actor=actor, db=db)
    if schema_hash(tool) != binding.schema_hash or price['id'] != str(binding.price_snapshot_id):
        raise ServiceError('TOOL_UNBOUND', 403)
    append('approval', binding_ref, {'approved': True, 'synthetic': True, 'production_approval': None}, actor.user_id, db)
    return read_binding(binding_ref, actor=actor, db=db)


def revoke_binding(binding_ref, *, actor, db):
    read_binding(binding_ref, actor=actor, db=db)
    append('approval', binding_ref, {'approved': False}, actor.user_id, db)


def binding_reference(binding, *, actor, db, matter_id=None):
    if matter_id is None:
        authorize_manager(actor, db)
    else:
        authorize_case(actor, matter_id, db)
    for row in db.scalars(select(ProviderRecordRow).where(ProviderRecordRow.kind == 'binding').order_by(ProviderRecordRow.sequence.desc())):
        stored = ToolBinding.model_validate_json(row.payload)
        if stored.endpoint_config_ref != binding.endpoint_config_ref or stored.tool_name != binding.tool_name:
            continue
        if read_binding(row.ref, actor=actor, db=db, matter_id=matter_id) == binding:
            return row.ref
    raise ServiceError('TOOL_UNBOUND', 403)


def read_raw(ref, *, actor, matter_id, db):
    authorize(actor, matter_id, 'read', db)
    row = by_ref(ref, 'raw', db)
    if not row or row.matter_id != str(matter_id):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return json.loads(row.payload)
