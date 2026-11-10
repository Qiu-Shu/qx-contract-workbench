"""Bounded metadata pages for one explicit historical synthetic target."""
from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _owned
from ..ops.storage import require_active
from ..security import ServiceError
from . import accounts, conversation, generation_dispatch


_SOURCES = '''SELECT descriptor.id,poll.next_revision,descriptor.ordinal
    FROM weixin_inbox_descriptors descriptor
    JOIN weixin_poll_receipts poll ON poll.id=descriptor.poll_id
    JOIN weixin_peer_bindings root ON root.id=descriptor.mapping_id
    LEFT JOIN weixin_descriptor_generations target ON target.descriptor_id=descriptor.id
    JOIN task_channel_bindings binding
        ON binding.id=COALESCE(target.task_binding_id,root.task_binding_id)
    LEFT JOIN weixin_dispatch_receipts receipt ON receipt.descriptor_id=descriptor.id
    WHERE descriptor.mapping_id=:mapping AND descriptor.status='accepted_pending_dispatch'
        AND binding.conversation_id=:target'''


def _source(current, identifier, mapping_id, target_cid, db):
    # Reuse the complete immutable-source and current historical-target checks.
    # This deliberately repeats full history validation, even for the lookahead.
    _, _, descriptor, mapping, _, scope, poll, _ = generation_dispatch._source(
        current, identifier, db, active=False)
    if mapping is None or mapping.id != mapping_id or scope.conversation_id != target_cid:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return d.WeixinPendingDescriptorView(descriptor_id=descriptor.id,
        conversation_id=scope.conversation_id, received_at=poll.created_at,
        has_text=bool(descriptor.payload.text), media_count=len(descriptor.payload.media))


def list_pending_descriptors(actor, cid, query, *, database):
    """Read accepted, undispatched sources without advancing any task or poll cursor."""
    query = d.WeixinPendingQuery.model_validate(query.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        current, _, mapping, _, _ = conversation._context(actor, cid, db)
        require_active(db)
        target = _owned(current, query.target_conversation_id, db)
        conversation._active_targets(target, db)
        # Empty pages must still reject damaged parents or an incompatible schema.
        generation_dispatch._validate(db)
        parameters = {'mapping': str(mapping.id) if mapping else None,
                      'target': str(query.target_conversation_id)}
        if (mapping is not None and query.target_conversation_id != mapping.scope.conversation_id
                and not db.scalar(text('''SELECT 1 FROM weixin_peer_generations generation
                    JOIN task_channel_bindings binding ON binding.id=generation.task_binding_id
                    WHERE generation.root_mapping_id=:mapping AND binding.conversation_id=:target'''),
                    parameters)):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        after = ''
        if query.cursor is not None:
            # Do not filter out a cursor that was dispatched between the two GETs.
            anchor = db.execute(text(_SOURCES + ' AND descriptor.id=:cursor'),
                {**parameters, 'cursor': str(query.cursor)}).mappings().first()
            if anchor is None:
                raise ServiceError('CROSS_MATTER_DENIED', 403)
            _source(current, query.cursor, mapping.id, query.target_conversation_id, db)
            parameters.update(revision=anchor['next_revision'], ordinal=anchor['ordinal'])
            after = ''' AND (poll.next_revision>:revision
                OR (poll.next_revision=:revision AND descriptor.ordinal>:ordinal))'''
        rows = db.execute(text(_SOURCES + ' AND receipt.id IS NULL' + after +
            ' ORDER BY poll.next_revision,descriptor.ordinal LIMIT :count'),
            {**parameters, 'count': query.limit + 1}).mappings().all()
        values = tuple(_source(current, row['id'], mapping.id,
            query.target_conversation_id, db) for row in rows)
        items = values[:query.limit]
        result = d.WeixinPendingPage(conversation_id=query.target_conversation_id, items=items,
            next_cursor=items[-1].descriptor_id if len(values) > query.limit else None)
    return result
