"""T02 foundations; synthetic approval rows are not legal issuance."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import uuid4

import pytest

from cn_contract.domain import Approval, ExportArtifact, Fact, FactSnapshot, ParseResult
from test_versions import meta, world
from io import BytesIO


def need(module, name):
    assert callable(getattr(module, name, None)), f'T02 requires {name} state/snapshot persistence'


def test_legal_transitions_and_formal_approval_blocked(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    need(p, 'transition_matter')
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.transition_matter(matter.id, 'reviewing', actor, db)
        assert error.value.code == 'STATE_CONFLICT'
        for target in ('parsed', 'awaiting_fact_confirmation', 'ready_for_review', 'reviewing', 'awaiting_lawyer'):
            assert p.transition_matter(matter.id, target, actor, db).status == target
        with pytest.raises(s.ServiceError) as error:
            p.transition_matter(matter.id, 'approved', actor, db)
        assert error.value.code == 'NOT_IMPLEMENTED'


def seed_approval(p, db, actor, matter):
    approval = Approval(id=uuid4(), matter_id=matter.id, approver_id=actor.user_id,
                        audience='internal', review_snapshot_sha256='1' * 64,
                        artifact_manifest_sha256='2' * 64, scope=('synthetic',), limitations=(),
                        approved_at=datetime.now(timezone.utc), status='valid', exception_authorization_id=None)
    artifact = ExportArtifact(id=uuid4(), matter_id=matter.id, run_id=uuid4(), audience='internal',
                              type='synthetic', content_sha256='3' * 64, storage_ref='synthetic-only.docx',
                              mode='approved', approval_id=approval.id, created_at=datetime.now(timezone.utc), superseded=False)
    db.add(p.ApprovalRow(id=str(approval.id), matter_id=str(matter.id), approver_id=str(actor.user_id),
                         status='valid', payload=approval.model_dump_json()))
    db.flush()
    db.add(p.ExportRow(id=str(artifact.id), matter_id=str(matter.id), approval_id=str(approval.id),
                       superseded=False, payload=artifact.model_dump_json()))
    db.flush()
    return approval, artifact


def test_position_change_invalidates_approval_and_marks_existing_export(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    need(p, 'set_position')
    with database.session() as db:
        approval, artifact = seed_approval(p, db, actor, matter)
        db.get(p.MatterRow, str(matter.id)).status = 'approved'
    with database.session() as db:
        changed = p.set_position(matter.id, 'seller', actor, db)
        assert changed.position == 'seller'
        assert changed.status == 'awaiting_fact_confirmation'
        assert p.read_approval(matter.id, approval.id, actor, db).status == 'stale'
        assert p.read_export(matter.id, artifact.id, actor, db).superseded is True
        assert db.get(p.ExportRow, str(artifact.id)).payload == artifact.model_dump_json()


def snapshot(matter, *, version=1):
    fact = Fact(id=uuid4(), matter_id=matter.id, version=version, field='synthetic_amount',
                typed_value={'kind': 'decimal', 'value': '10.50'}, unit='CNY', provenance_type='client_statement',
                anchor_ids=(), receipt_ids=(), confirmation_status='unconfirmed', confirmed_by=None, confirmed_at=None)
    payload = json.dumps([fact.model_dump(mode='json')], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return FactSnapshot(version=version, facts=(fact,), sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest())


def test_fact_snapshot_round_trip_and_new_version_stales_approval(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    need(p, 'save_fact_snapshot')
    with database.session() as db:
        first = snapshot(matter)
        p.save_fact_snapshot(matter.id, first, actor, db)
        approval, artifact = seed_approval(p, db, actor, matter)
    with database.session() as db:
        p.save_fact_snapshot(matter.id, snapshot(matter, version=2), actor, db)
        restored = p.get_fact_snapshot(matter.id, 1, actor, db)
        assert restored.facts[0].typed_value.kind == 'decimal'
        assert restored.facts[0].typed_value.value == Decimal('10.50')
        assert restored.facts[0].unit == 'CNY'
        assert p.read_matter(matter.id, actor, db).active_fact_version == 2
        assert p.read_approval(matter.id, approval.id, actor, db).status == 'stale'
        assert p.read_export(matter.id, artifact.id, actor, db).superseded
        with pytest.raises(s.ServiceError) as error:
            p.save_fact_snapshot(matter.id, first, actor, db)
        assert error.value.code == 'VERSION_CONFLICT'


def test_parse_result_is_separate_immutable_snapshot(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    need(p, 'save_parse_result')
    with database.session() as db:
        original = p.create_version(meta(matter.id), actor, db, content=BytesIO(b'synthetic'))
        result = ParseResult(version_id=original.id, anchors=(), pages=(1,), parts=('page:1:read',),
                             unsupported_parts=(), quality_issues=())
        p.save_parse_result(matter.id, result, actor, db)
        assert p.get_parse_result(matter.id, original.id, actor, db) == result
        assert p.read_version(matter.id, original.id, actor, db) == original
        assert original.parse_status == 'pending'


def test_settings_revalidated_and_hash_matches_actual_config(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    from cn_contract.config import canonical_json, load_settings
    from pydantic import ValidationError
    settings = load_settings()
    altered = settings.model_copy(update={'upload_max_matter_files': 1})
    candidate = p.Database(f'sqlite:///{tmp_path / "second.db"}', tmp_path / 'second', altered)
    actual = hashlib.sha256(canonical_json(altered.model_dump(mode='python')).encode('utf-8')).hexdigest()
    assert candidate.settings.config_sha256 == actual
    assert candidate.settings.config_sha256 != settings.config_sha256
    with pytest.raises(ValidationError):
        p.Database(f'sqlite:///{tmp_path / "invalid.db"}', tmp_path / 'invalid',
                   settings.model_copy(update={'qcc_enabled_default': True}))


def test_fact_confirmation_cannot_impersonate_another_confirmer(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    first = snapshot(matter)
    fact = Fact.model_validate({**first.facts[0].model_dump(mode='python'), 'confirmation_status': 'confirmed',
        'confirmed_by': uuid4(), 'confirmed_at': datetime.now(timezone.utc)})
    changed = FactSnapshot(version=1, facts=(fact,), sha256=p.fact_snapshot_sha256((fact,)))
    with database.session() as db:
        with pytest.raises(s.ServiceError) as error:
            p.save_fact_snapshot(matter.id, changed, actor, db)
        assert error.value.status_code == 403
        assert db.query(p.FactSnapshotRow).count() == 0


def test_reused_session_cannot_reopen_case_archived_in_database(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        p.transition_matter(matter.id, 'parsed', actor, db)
    with database.session_factory() as reused:
        cached = reused.get(p.MatterRow, str(matter.id))
        reused.commit()
        with database.session() as db:
            p.transition_matter(matter.id, 'archived', actor, db)
        with pytest.raises(s.ServiceError) as error:
            p.transition_matter(matter.id, 'awaiting_fact_confirmation', actor, reused)
        assert error.value.code == 'STATE_CONFLICT'


def test_reused_session_reads_actual_matter_and_invalidation_flags(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        approval, artifact = seed_approval(p, db, actor, matter)
    with database.session_factory() as reused:
        cached_matter = reused.get(p.MatterRow, str(matter.id))
        cached_approval = reused.get(p.ApprovalRow, str(approval.id))
        cached_export = reused.get(p.ExportRow, str(artifact.id))
        reused.commit()
        with database.session() as db:
            p.set_position(matter.id, 'seller', actor, db)
            p.save_fact_snapshot(matter.id, snapshot(matter), actor, db)
        actual = p.read_matter(matter.id, actor, reused)
        assert actual.position == 'seller'
        assert actual.active_fact_version == 1
        assert actual.status == 'awaiting_fact_confirmation'
        assert p.read_approval(matter.id, approval.id, actor, reused).status == 'stale'
        assert p.read_export(matter.id, artifact.id, actor, reused).superseded
