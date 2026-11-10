"""Current generation translation only; legacy intake and dispatch stay paused."""
from .. import domain as d
from ..assistant.service import _digest, _snapshot
from .. import weixin_offline as wire
from . import accounts, generations


def preview_generation_response(actor, root_mapping_id, expected_head, raw_response, *, database):
    """Check persistent scope and current authority in one lock, without consuming it."""
    expected_head = d.WeixinGenerationHeadView.model_validate(expected_head.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        current, account, mapping = generations._root(actor, root_mapping_id, db, active=True)
        history = generations._history(mapping, db)
        latest = history[-1] if history else None
        scope = latest.scope if latest else accounts._effective_scope(mapping, db)
        binding, conversation = generations._target(current,
            latest.task_binding_id if latest else mapping.task_binding_id, db, active=True)
        head = d.WeixinGenerationHeadView(generation=len(history),
            generation_sha256=latest.generation_sha256 if latest else None,
            scope=scope, scope_sha256=_digest(scope.model_dump(mode='json')),
            checkpoint_revision=account.checkpoint_revision)
        if head != expected_head or scope != _snapshot(conversation):
            generations._conflict()
        local = d.WeixinOfflineScope(bot_account_id=account.bot_account_id,
            sender_peer_id=mapping.sender_peer_id, owner_id=current.user_id,
            session_id=current.session_id, binding_id=binding.id, expected_scope=scope,
            task_cursor=binding.cursor, upstream_cursor=account.upstream_cursor)
        plan = wire.translate_response(local, raw_response, database.settings)
        return d.WeixinGenerationPreview(head=head, plan=plan)
