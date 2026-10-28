"""Resolve historical descriptor targets without current authorization or replay."""
from sqlalchemy import text

from .. import domain as d
from ..record_codec import sha
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..task_drafts.integrity import _at
from .integrity import _canonical_model, _row_ids


def _fail():
    raise ValueError('WEIXIN_PROVENANCE_INTEGRITY')


def _targets(db):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_descriptor_generations'")):
        return {}
    links={}
    for row in db.execute(text('SELECT * FROM weixin_descriptor_generations')).mappings():
        _row_ids(row,('descriptor_id','generation_id','task_binding_id'))
        links[row['descriptor_id']]=d.WeixinDescriptorGeneration(**row)
    histories={}
    for row in db.execute(text('SELECT * FROM weixin_peer_generations ORDER BY root_mapping_id,generation')).mappings():
        histories.setdefault(row['root_mapping_id'],[]).append(row)
    polls={row['id']:row for row in db.execute(text('SELECT * FROM weixin_poll_receipts')).mappings()}
    mappings={row['id']:row for row in db.execute(text('SELECT * FROM weixin_peer_bindings')).mappings()}
    descriptors=list(db.execute(text('SELECT * FROM weixin_inbox_descriptors')).mappings())
    targets,originals={},{}
    for row in descriptors:
        if row['prior_descriptor_id'] is None and row['source_event_id'] is not None:
            originals[row['source_event_id']]=row
        if row['status']!='accepted_pending_dispatch':continue
        poll=polls[row['poll_id']];latest=None;at=_at(poll['created_at'])
        for candidate in histories.get(row['mapping_id'],()):
            stamp=_at(candidate['created_at'])
            if stamp==at or (stamp<at)!=(candidate['checkpoint_revision']<poll['next_revision']):_fail()
            if stamp<at:latest=candidate
        link=links.get(row['id'])
        if latest is None:
            if link is not None:_fail()
            continue
        if link is None or row['prior_descriptor_id'] is not None:_fail()
        scope=_canonical_model(d.ScopeSnapshot,latest['scope_json'])
        generation=d.WeixinPeerGeneration(**{key:value for key,value in latest.items() if key!='scope_json'},scope=scope)
        mapping=mappings[row['mapping_id']]
        payload=_canonical_model(d.TaskInboxEventInput,row['payload_json'])
        if (mapping['account_id']!=poll['account_id'] or mapping['sender_peer_id']!=row['sender_peer_id']
                or str(generation.root_mapping_id)!=row['mapping_id'] or link.generation_id!=generation.id
                or link.generation_sha256!=generation.generation_sha256 or link.task_binding_id!=generation.task_binding_id
                or link.scope_sha256!=generation.scope_sha256 or link.payload_sha256!=sha(payload.model_dump(mode='json'))):_fail()
        targets[row['id']]=generation
    if set(links)!=set(targets):_fail()
    for row in descriptors:
        if row['status']!='accepted_pending_dispatch':continue
        payload=_canonical_model(d.TaskInboxEventInput,row['payload_json'])
        prior=originals.get(payload.reply_to_event_id)
        if prior is None or prior['status']!='accepted_pending_dispatch':continue
        current=targets.get(row['id']);previous=targets.get(prior['id'])
        if (current.id if current else None)!=(previous.id if previous else None):_fail()
    return targets


def validate_descriptor_generations(db,*,allow_provenance=False):
    """Return no file refs after validating provenance and its complete parent chain."""
    try:
        rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native=any(row[0]=='table' and row[1]=='local_workspace_identity' for row in rows)
        if identify_schema(rows,native=native) not in ('weixin-target-provenance-v1','weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1'):return []
        present=db.scalar(text('SELECT 1 FROM weixin_descriptor_generations LIMIT 1')) is not None
    except (ValueError,TypeError,KeyError,ArithmeticError,RecursionError,ServiceError):_fail()
    if present and not allow_provenance:raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    try:
        if present and (not native or db.scalar(text('SELECT count(*) FROM local_workspace_identity'))!=1):_fail()
        _targets(db)
        from .generation_integrity import validate_peer_generations
        validate_peer_generations(db,allow_generations=True)
    except (ValueError,TypeError,KeyError,ArithmeticError,RecursionError,ServiceError):_fail()
    return []
