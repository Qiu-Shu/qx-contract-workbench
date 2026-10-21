"""Native one-time authorization for source-bound answers; synthetic loopback only."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.context_preview import assemble_context
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import backup
from cn_contract.security import authenticate, login
from tests.integration.test_assistant_context_provider import envelope
from tests.integration.test_assistant_context_send import context_world
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_main_provider import raw, server
from tests.integration.test_native_model_control import denied

SECRET = 'SYNTHETIC_NATIVE_CONTEXT_NOT_A_REAL_KEY_67890'


@pytest.fixture
def native_context(context_world):
    """Real saved citations plus a draft, behind the private control service."""
    database, _, view, submission, basis, runtime = context_world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        row = service._owned(actor, view.scope.conversation_id, db)
        scope, manifest, _ = assemble_context(actor, row, submission.citation_ids, db,
                                              question=submission.content)
    endpoint = []
    providers = []
    def factory(config, resolver):
        provider = DeepSeekProvider.for_synthetic_loopback(config, resolver, endpoint[0])
        providers.append(provider)
        return provider
    registry = MainModelRegistry()
    return SimpleNamespace(database=database, actor=actor, token=token, view=view,
        submission=submission, basis=basis, scope=scope, manifest=manifest,
        config=runtime.provider.config, registry=registry, providers=providers,
        control=NativeModelControl(database, registry, provider_factory=factory),
        endpoint=endpoint)


def configure(n):
    result = n.control.configure({'config': n.config.model_dump(mode='json'), 'secret': SECRET})
    assert result['status'] == 'configured'
    return {'session_token': n.token, 'basis': n.basis.model_dump(mode='json'),
        'max_total_usd': '1', 'valid_for_seconds': 120,
        'expected_config_version': result['config_version']}


def test_native_context_authorization_executes_one_exact_loopback_send(native_context):
    n = native_context
    async def scenario():
        with server(raw(envelope(SimpleNamespace(manifest=n.manifest)))) as (url, received, _):
            n.endpoint.append(url)
            payload = configure(n)
            assert n.control.authorize_context(payload) == {'status': 'authorized'}
            lease = n.registry.resolve(n.actor, n.scope)
            assert lease.snapshot()[1].max_calls == 1
            # Identical confirmation is an idempotent replay, never a second grant.
            assert n.control.authorize_context(payload) == {'status': 'authorized'}
            with n.database.session() as db:
                attempt = attempts.enqueue_context(n.actor, n.scope.conversation_id,
                                                   n.submission, db, lease)
            completed = await execute_attempt(n.actor, attempt.id, n.database, lease)
            assert type(completed) is d.MainContextAttemptView and completed.state == 'received'
            assert completed.receipt.cost_status == 'estimated'
            assert (completed.output.candidate.citations[0].saved_citation_id
                    == n.basis.source_bindings[0].saved_citation_id)
            assert len(received) == 1
            with n.database.session() as db:
                row = db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
                                 {'id': str(attempt.id)}).mappings().one()
                prepared = attempts._input(row)
                # The bytes on the wire equal the immutable registered input exactly.
                assert received[0]['body'] == prepared.wire_payload_json.encode('utf-8')
                assert backup._file_references(db) == []
            # A sent intent is a tombstone; re-authorization never regrants.
            assert n.control.authorize_context(payload) == {'status': 'existing'}
            with n.database.session() as db:
                assert attempts.enqueue_context(n.actor, n.scope.conversation_id,
                                                n.submission, db, lease) == completed
            assert len(received) == 1
    asyncio.run(scenario())


def test_authorize_context_v2_requires_the_explicit_matching_rounds_shape(native_context):
    from cn_contract.assistant.providers.rounds_codec import build_basis_rounds
    n = native_context
    async def scenario():
        n.endpoint.append('http://127.0.0.1:9/chat/completions')
        with n.database.session() as db:
            row = service._owned(n.actor, n.scope.conversation_id, db)
            scope, manifest, records = assemble_context(n.actor, row, n.submission.citation_ids, db,
                                                        question=n.submission.content)
            v2 = build_basis_rounds(n.submission.request_id, manifest, scope,
                                    n.submission.expected_composer_revision, n.config, records)
        payload = configure(n)
        payload['basis'] = v2.model_dump(mode='json')
        payload['max_rounds'] = 2
        assert n.control.authorize_context(payload) == {'status': 'authorized'}
        lease = n.registry.resolve(n.actor, n.scope)
        assert lease.snapshot()[1].max_calls == 2
        # The default shape stays single-round; mismatched pairs never grant.
        for basis, rounds in ((n.basis.model_copy(update={'request_id': uuid4()}), 2),
                              (v2.model_copy(update={'request_id': uuid4()}), 1)):
            with denied():
                n.control.authorize_context({'session_token': n.token,
                    'basis': basis.model_dump(mode='json'), 'max_total_usd': '1',
                    'valid_for_seconds': 120, 'max_rounds': rounds,
                    'expected_config_version': payload['expected_config_version']})
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
    asyncio.run(scenario())


def test_native_context_grant_never_covers_plain_text_or_another_context(native_context):
    n = native_context
    async def scenario():
        # No server: a denied path must not even resolve the secret or connect.
        n.endpoint.append('http://127.0.0.1:9/chat/completions')
        payload = configure(n)
        n.control.authorize_context(payload)
        lease = n.registry.resolve(n.actor, n.scope)
        plain = d.AssistantMessageInput(request_id=uuid4(), expected_scope=n.submission.expected_scope,
            expected_composer_revision=n.submission.expected_composer_revision,
            content=n.submission.content)
        other = n.submission.model_copy(update={'request_id': uuid4()})
        with n.database.session() as db:
            with denied():
                attempts.enqueue_generation(n.actor, n.scope.conversation_id, plain, db, lease)
            with denied():
                attempts.enqueue_context(n.actor, n.scope.conversation_id, other, db, lease)
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_input_citations')) == 0
        with denied():
            lease.check_execution(n.actor, other.request_id, None)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['version', 'wire', 'binding', 'budget', 'draft'])
def test_authorize_context_denies_without_grant_or_send(native_context, change):
    n = native_context
    async def scenario():
        n.endpoint.append('http://127.0.0.1:9/chat/completions')
        payload = configure(n)
        if change == 'version':
            payload['expected_config_version'] = str(uuid4())
        elif change == 'wire':
            payload['basis'] = {**payload['basis'], 'wire_sha256': '0'*64}
        elif change == 'binding':
            binding = dict(payload['basis']['source_bindings'][0])
            binding['citation_sha256'] = '1'*64
            payload['basis'] = {**payload['basis'], 'source_bindings': [binding]}
        elif change == 'budget':
            payload['max_total_usd'] = '0.000000000001'
        else:
            with n.database.session() as db:
                current = service.read_conversation(n.actor, n.scope.conversation_id, db)
                service.save_draft(n.actor, n.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=current.scope,
                    expected_composer_revision=current.composer_revision,
                    content='授权前改过的合成草稿'), db)
        with denied():
            n.control.authorize_context(payload)
        lease = n.registry.resolve(n.actor, n.scope)
        assert lease.snapshot()[1] is None
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
    asyncio.run(scenario())
