"""Synthetic profile history survives recovery and detects semantic tampering."""
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, service
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, SessionRow
from cn_contract.record_codec import encode, sha
from cn_contract.security import authenticate, login, ServiceError
from tests.helpers.legacy_assistant_backup import USERNAME, PASSWORD, PASSPHRASE
from tests.integration.test_assistant_attachment_backup import corrupt, source


def test_empty_workspace_profile_history_is_valid(source):
    from cn_contract.assistant.profile_integrity import validate_profile_records
    _, database, *_ = source
    with database.session() as db:
        validate_profile_records(db)


def validate(database, *, allowed=True):
    from cn_contract.assistant.profile_integrity import validate_profile_records
    with database.session() as db:
        validate_profile_records(db, allowed=allowed)


def save(database, actor, request):
    from cn_contract.assistant.profile_store import save_profile
    return save_profile(actor, request, database=database)


@pytest.fixture
def chain(source):
    _, database, actor, cid, attachment, parsed, *_ = source
    scope = attachments.read_materials(actor, cid, database=database).scope
    ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=attachment.attachment.id,
        original_sha256=attachment.attachment.sha256, parse_revision=parsed.parse.revision,
        result_sha256=parsed.parse.result_sha256, anchor=parsed.parse.result.anchors[0])
    request = d.ProfileCommitInput(request_id=uuid4(), patch=d.ProfilePatch(scope=scope,
        base_profile_revision=0, changes=(d.ProfileProposal(field='consultation',
            value={'kind':'text', 'value':'仅为合成接待摘要，事实尚待核对。'},
            origin='model_inference', source_refs=(ref,)),)), project_intake=True)
    first = save(database, actor, request)
    repeated = request.model_copy(update={'request_id':uuid4(), 'patch':request.patch.model_copy(
        update={'base_profile_revision':first.profile_revision}),
        'expected_intake_id':first.intake_id, 'expected_intake_revision':first.intake_revision})
    second = save(database, actor, repeated)
    assert first.profile_changed and first.projection_changed
    assert not second.profile_changed and not second.projection_changed
    return source, request, first, repeated, second


def test_history_replays_manual_edits_and_nonprojecting_revisions(chain):
    from cn_contract.intake import service as intake
    source, _, first, repeated, _ = chain
    _, database, actor, cid, *_ = source
    with database.session() as db:
        record = intake.read(first.intake_id, actor, db)
        draft = d.IntakeDraft.model_validate(record.model_dump(include=d.IntakeDraft.model_fields.keys()))
        record = intake.save(first.intake_id, d.IntakeUpdateInput(expected_revision=record.revision,
            draft=draft.model_copy(update={'consultation':'律师更正的合成原话'})), actor, db)
    request = repeated.model_copy(update={'request_id':uuid4(), 'project_intake':False,
        'expected_intake_revision':record.revision, 'manual_edits':(
            d.ProfileEdit(field='principal_amount', value={'kind':'money', 'value':'10.01', 'unit':'CNY'}),)})
    third = save(database, actor, request)
    assert third.profile_changed and not third.projection_changed
    fourth = save(database, actor, request.model_copy(update={'request_id':uuid4(), 'project_intake':True,
        'patch':request.patch.model_copy(update={'base_profile_revision':third.profile_revision})}))
    assert not fourth.profile_changed and not fourth.projection_changed
    validate(database)


def test_history_remains_valid_after_reparse_deselection_and_revocation(chain):
    source, _, first, _, _ = chain
    _, database, actor, cid, attachment, *_ = source
    current = attachments.read_materials(actor, cid, database=database)
    attachments.parse_attachment(actor, cid, attachment.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    attachments.select_materials(actor, cid, d.AssistantMaterialSelectionInput(request_id=uuid4(),
        expected_scope=current.scope, items=()), database=database)
    with database.session() as db:
        db.get(SessionRow, str(actor.session_id)).revoked = True
        db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                   {'id':str(cid), 'at':first.created_at.isoformat()})
    validate(database)


def test_message_sources_and_prior_binding_are_historical(chain):
    source, _, first, *_ = chain
    _, database, actor, cid, *_ = source
    with database.session() as db:
        current = service.read_conversation(actor, cid, db)
        run = service.save_message(actor, cid, d.AssistantMessageInput(request_id=uuid4(),
            expected_scope=current.scope, expected_composer_revision=current.composer_revision,
            content='客户关于合成材料补充的原话'), db)
        service.cancel_run(actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
        current = service.read_conversation(actor, cid, db)
    message = current.messages[-1]
    reference = d.ProfileMessageRef(kind='message', conversation_id=cid, message_id=message.id,
        source_revision=message.source_revision, start=0, end=len(message.content), quote=message.content,
        quote_sha256=hashlib.sha256(message.content.encode()).hexdigest())
    request = d.ProfileCommitInput(request_id=uuid4(), expected_intake_id=first.intake_id,
        expected_intake_revision=first.intake_revision, patch=d.ProfilePatch(scope=current.scope,
        base_profile_revision=first.profile_revision, changes=(d.ProfileProposal(field='title',
            value={'kind':'text','value':'合成补充咨询'}, origin='user_statement', source_refs=(reference,)),)))
    assert save(database, actor, request).profile_changed
    validate(database)
    # No product rebind API exists yet. This synthetic future binding checks
    # that historical validation does not mistake current scope for old proof.
    with database.session() as db:
        db.execute(text("UPDATE assistant_conversations SET binding_revision=2,scope_kind='intake',scope_ref=:iid WHERE id=:cid"),
                   {'cid':str(cid),'iid':str(first.intake_id)})
    validate(database)


def test_noop_before_first_profile_and_first_projection_is_replayable(source):
    _, database, actor, cid, *_ = source
    scope = attachments.read_materials(actor, cid, database=database).scope
    request = d.ProfileCommitInput(request_id=uuid4(), patch=d.ProfilePatch(scope=scope, base_profile_revision=0))
    first = save(database, actor, request)
    assert first.profile_revision == 0 and first.intake_id is None
    next_request = request.model_copy(update={'request_id':uuid4(), 'project_intake':True,
        'manual_edits':(d.ProfileEdit(field='title', value={'kind':'text','value':'律师明确填写的合成标题'}),)})
    second = save(database, actor, next_request)
    assert second.profile_revision == 1 and second.projection_changed
    validate(database)


@pytest.mark.parametrize('edit_body', [False, True])
def test_intake_origin_survives_title_only_edits_but_not_body_change_and_restore(chain, edit_body):
    from cn_contract.intake import service as intake
    source, _, first, repeated, _ = chain
    _, database, actor, *_ = source
    with database.session() as db:
        original = intake.read(first.intake_id, actor, db)
        draft = d.IntakeDraft.model_validate(original.model_dump(include=d.IntakeDraft.model_fields.keys()))
        changed = draft.model_copy(update={'title':'律师只修改标题的合成记录'})
        if edit_body:
            changed = changed.model_copy(update={'consultation':'律师修改的合成正文'})
        current = intake.save(first.intake_id, d.IntakeUpdateInput(expected_revision=1, draft=changed), actor, db)
        if edit_body:
            current = intake.save(first.intake_id, d.IntakeUpdateInput(expected_revision=current.revision,
                draft=draft), actor, db)
    receipt = save(database, actor, repeated.model_copy(update={'request_id':uuid4(), 'project_intake':False,
        'expected_intake_revision':current.revision}))
    assert receipt.consultation_origin == ('user' if edit_body else 'profile_summary')
    validate(database)


@pytest.mark.parametrize('fault', ['request_hash', 'request_json', 'request_scope', 'unselected_parse',
    'profile_hash', 'profile_result', 'profile_json', 'projection_hash', 'projection_result',
    'origin', 'sequence', 'delete_receipt', 'delete_profile', 'orphan_profile', 'wrong_actor',
    'base_revision', 'no_change_lie', 'early_time', 'stale_intake_at_receipt_time'])
def test_semantic_tamper_rejects_backup_before_publish(chain, tmp_path, fault):
    source, request, first, _, _ = chain
    root, database, actor, cid, *_ = source
    receipt_table, revision_table = 'assistant_profile_receipts', 'assistant_profile_revisions'
    if fault in ('request_hash', 'projection_hash', 'origin', 'sequence', 'early_time'):
        column, replacement = {
            'request_hash':('request_sha256','0'*64), 'projection_hash':('intake_sha256','0'*64),
            'origin':('consultation_origin','user'), 'sequence':('sequence',3),
            'early_time':('created_at','2000-01-01T00:00:00+00:00')}[fault]
        seq = 2 if fault == 'sequence' else 1
        corrupt(database, receipt_table, f'UPDATE {receipt_table} SET {column}=? WHERE sequence=?', (replacement,seq))
    elif fault in ('request_json','request_scope','unselected_parse','base_revision'):
        value = request.model_dump(mode='json')
        if fault == 'request_json': raw = encode(value)+' '
        else:
            if fault == 'request_scope': value['patch']['scope']['workspace_id'] = str(uuid4())
            if fault == 'unselected_parse': value['patch']['scope']['materials_revision'] = 1
            if fault == 'base_revision': value['patch']['base_profile_revision'] = 1
            raw = encode(value)
        corrupt(database, receipt_table, f'UPDATE {receipt_table} SET request_json=?,request_sha256=? WHERE sequence=1',
                (raw,hashlib.sha256(raw.encode()).hexdigest()))
    elif fault in ('profile_hash','profile_result','profile_json','orphan_profile'):
        with database.session() as db:
            row = dict(db.execute(text(f'SELECT * FROM {revision_table} WHERE revision=1')).mappings().one())
        value = json.loads(row['profile_json'])
        if fault == 'profile_result': value['fields'][0]['candidates'][0]['value']['value'] = '篡改后的合成摘要'
        if fault == 'orphan_profile': value['revision'] = 2
        raw = encode(value)+(' ' if fault == 'profile_json' else '')
        digest = '0'*64 if fault == 'profile_hash' else hashlib.sha256(raw.encode()).hexdigest()
        if fault == 'orphan_profile':
            with database.session() as db:
                db.execute(text(f'''INSERT INTO {revision_table}
                    (conversation_id,revision,profile_json,profile_sha256,created_at) VALUES (:cid,2,:raw,:hash,:at)'''),
                    {'cid':str(cid),'raw':raw,'hash':digest,'at':row['created_at']})
        else:
            corrupt(database, revision_table, f'UPDATE {revision_table} SET profile_json=?,profile_sha256=?', (raw,digest))
    elif fault == 'projection_result':
        with database.session() as db:
            raw = db.scalar(text('SELECT payload FROM intake_revisions WHERE intake_id=:id'), {'id':str(first.intake_id)})
        value = json.loads(raw); value['consultation'] = '篡改后的接待摘要'
        corrupt(database, 'intake_revisions', 'UPDATE intake_revisions SET payload=?', (encode(value),))
        value.update(client_reply='', internal_notes='')
        corrupt(database, receipt_table, f'UPDATE {receipt_table} SET intake_sha256=?', (sha(value),))
    elif fault.startswith('delete_'):
        table = receipt_table if fault == 'delete_receipt' else revision_table
        column = 'sequence' if fault == 'delete_receipt' else 'revision'
        corrupt(database, table, f'DELETE FROM {table} WHERE {column}=1')
    elif fault == 'wrong_actor':
        from cn_contract.security import provision_user
        with database.session() as db:
            other = provision_user('synthetic-other-profile-owner', PASSWORD, {d.Role.HANDLING_LAWYER}, db,
                                   local_workbench_password=True)
        corrupt(database, receipt_table, f'UPDATE {receipt_table} SET actor_id=?', (str(other),))
    elif fault == 'no_change_lie':
        corrupt(database, receipt_table, f"UPDATE {receipt_table} SET profile_changed=1,event_type='profile.saved' WHERE sequence=2")
    elif fault == 'stale_intake_at_receipt_time':
        from cn_contract.intake import service as intake
        with database.session() as db:
            record = intake.read(first.intake_id, actor, db)
            draft = d.IntakeDraft.model_validate(record.model_dump(include=d.IntakeDraft.model_fields.keys()))
            newer = intake.save(record.id, d.IntakeUpdateInput(expected_revision=record.revision,
                draft=draft.model_copy(update={'title':'律师后来修订的合成标题'})), actor, db)
        corrupt(database, receipt_table, f'UPDATE {receipt_table} SET created_at=? WHERE sequence=2',
                ((newer.saved_at+timedelta(seconds=1)).isoformat(),))
    with pytest.raises(ValueError, match='ASSISTANT_PROFILE_INTEGRITY'):
        validate(database)
    target = tmp_path/'must-not-publish-profile.qxbak'
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
    assert not target.exists()


def test_profile_history_requires_complete_workspace_backup(chain):
    database = chain[0][1]
    with pytest.raises(ValueError, match='ASSISTANT_PROFILES_REQUIRE_QXBAK'):
        validate(database, allowed=False)
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_PROFILES_REQUIRE_QXBAK'):
        backup._collect_files(db)


def test_qxbak_preserves_profile_intake_and_source_history_and_blocks_writes(chain, tmp_path):
    from cn_contract.assistant.profile_store import read_profile, find_receipt
    from cn_contract.intake import service as intake
    source, request, first, repeated, second = chain
    root, database, actor, cid, attachment, parsed, raw, _ = source
    state = read_profile(actor, cid, database=database, revision=first.profile_revision)
    with database.session() as db:
        intake_before = intake.read(first.intake_id, actor, db, revision=first.intake_revision)
    archive = tmp_path/'合成档案完整备份.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored-profile', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings,
                        initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        validate(restored)
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            current = authenticate(token, db)
            assert intake.read(first.intake_id, current, db, revision=first.intake_revision) == intake_before
        assert read_profile(current, cid, database=restored, revision=first.profile_revision) == state
        assert find_receipt(current, cid, request.request_id, database=restored) == first
        assert find_receipt(current, cid, repeated.request_id, database=restored) == second
        assert attachments.read_original(current, cid, attachment.attachment.id, database=restored) == raw
        assert attachments.read_parse(current, cid, attachment.attachment.id, parsed.parse.revision,
                                      database=restored) == parsed.parse
        with pytest.raises(ServiceError) as error:
            save(restored, current, repeated.model_copy(update={'request_id':uuid4()}))
        assert error.value.code == 'BLOCKED_LIVE'
    finally:
        restored.engine.dispose()
