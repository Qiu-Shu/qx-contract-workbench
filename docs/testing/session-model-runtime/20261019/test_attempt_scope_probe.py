"""Independent synthetic boundary probe; same assertions before and after wiring."""
from cn_contract.assistant.providers import attempts
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
import pytest


def deny_scope(actor, scope):
    raise ServiceError('BLOCKED_LIVE', 403)


def test_enqueue_obeys_bound_runtime_identity(world):
    database, actor, conversation, request, runtime = world
    runtime.snapshot_for = deny_scope
    with database.session() as db:
        with pytest.raises(ServiceError) as failure:
            attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
        assert failure.value.code == 'BLOCKED_LIVE'


def test_claim_obeys_bound_runtime_identity(world):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        view = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
    runtime.snapshot_for = deny_scope
    with database.session() as db:
        assert attempts.claim(actor, view.id, db, runtime) is None
        result = attempts.read_attempt(actor, view.id, db)
        assert result.state == 'failed_before_send'
        assert result.receipt.cost_status == 'not_sent'
    assert not runtime.provider.calls
