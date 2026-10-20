"""Independent Spec probes for local context preview only; synthetic data."""
import importlib.util
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.config import canonical_json
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_research_routes import boot
from tests.integration.test_assistant_context_preview_routes import selection


@pytest.mark.parametrize('change,status', [('revoke',401), ('draft',409), ('restore',409)])
def test_authority_is_rechecked_after_body_read(world, tmp_path, library, monkeypatch, change, status):
    from cn_contract.web import assistant_context
    from cn_contract.security import authenticate
    from cn_contract.ops.storage import RestoreFenceRow
    from uuid import uuid4
    with boot(world, tmp_path, library[0]) as http:
        body = selection(http)
        with http.database.session() as db:
            actor = authenticate(http.client.cookies.get('qx_session'), db)
        original = assistant_context.body_input
        async def altered(request, model):
            value = await original(request, model)
            with http.database.session() as db:
                if change == 'revoke':
                    db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
                elif change == 'draft':
                    db.execute(text('UPDATE assistant_conversations SET composer_revision=composer_revision+1 WHERE id=:id'),
                               {'id':str(world[2].scope.conversation_id)})
                else:
                    db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='c'*64, manifest_sha256='d'*64, payload='{}'))
            return value
        monkeypatch.setattr(assistant_context, 'body_input', altered)
        response = http.client.post(http.url+'/context-preview', headers=http.headers, json=body)
        assert response.status_code == status, response.text
        assert world[-1].provider.calls == []
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_corrupt_saved_source_cannot_become_a_clean_preview(world, tmp_path, library):
    with boot(world, tmp_path, library[0]) as http:
        body = selection(http)
        with http.database.session() as db:
            db.execute(text('DROP TRIGGER immutable_assistant_library_citations_update'))
            db.execute(text('UPDATE assistant_library_citations SET citation_sha256=:hash WHERE id=:id'),
                       {'hash':'0'*64, 'id':body['citation_ids'][0]})
        response = http.client.post(http.url+'/context-preview', headers=http.headers, json=body)
        assert response.status_code == 409 and response.json()['code'] == 'LIBRARY_RECORD_INVALID', response.text
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert world[-1].provider.calls == []


def test_old_v1_models_serialize_identically_and_do_not_accept_context():
    path = Path(__file__).with_name('baseline-domain.py')
    spec = importlib.util.spec_from_file_location('cn_contract._context_review_v1', path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    from hashlib import sha256
    from cn_contract.assistant.providers.policy import prepare
    from tests.unit.test_assistant_context_preview import config, scope
    content = '独立审查：仅普通文字。'
    request = d.MainRequest(run_id=UUID(int=21), scope=scope(), message_id=UUID(int=22),
                           content=content, source_sha256=sha256(content.encode()).hexdigest())
    prepared = prepare(request, config())
    approval = d.MainSendApproval(request_id=UUID(int=23), expected_scope=scope(),
                                 expected_composer_revision=2, content_sha256=request.source_sha256)
    for current in (request, prepared, approval):
        previous = getattr(old, type(current).__name__).model_validate(current.model_dump(mode='python'))
        assert canonical_json(current.model_dump(mode='json')) == canonical_json(previous.model_dump(mode='json'))
    with pytest.raises(ValueError):
        d.MainRequest.model_validate(request.model_dump(mode='python') | {'sources':[]})


def test_configuration_preview_does_not_read_secret_or_touch_grants():
    import asyncio
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from cn_contract.assistant.providers.registry import MainModelRegistry
    from cn_contract.assistant.providers.policy import encoded, sha
    from tests.unit.test_assistant_context_preview import config, scope
    configured = config()
    class Provider:
        config = configured
        @property
        def secret(self):
            pytest.fail('preview attempted to read a secret')
        async def generate(self, *a, **kw):
            pytest.fail('preview attempted execution')
    async def run():
        registry = MainModelRegistry()
        provider = Provider()
        registry.configure(provider)
        session = uuid4()
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=scope().workspace_id,
            actor_id=uuid4(), config_sha256=sha(encoded(provider.config)), allowed_content_sha256s=('a'*64,),
            max_total_usd='1', max_calls=1, expires_at=datetime.now(timezone.utc)+timedelta(minutes=1))
        registry.grant(policy, session)
        before = dict(registry._grants)
        assert registry.configuration() == provider.config
        assert registry._grants == before
        registry.configuration().model_copy(update={'enabled':False})
        assert registry.configuration() == provider.config
    asyncio.run(run())
