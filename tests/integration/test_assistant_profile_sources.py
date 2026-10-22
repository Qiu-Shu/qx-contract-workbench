"""Only independently synthetic messages and DOCX files enter these checks."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from threading import Event
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, service
from cn_contract.assistant.profiles import merge_profile
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation, message, add_matter, add_intake
from test_assistant_attachments import material_workspace


def read(database, actor, patch):
    from cn_contract.assistant.profile_sources import read_profile_sources
    return read_profile_sources(actor, patch, database=database)


def patch(scope, refs=()):
    return d.ProfilePatch(scope=scope, base_profile_revision=0, changes=(d.ProfileProposal(
        field='consultation', value={'kind':'text','value':'合成客户自述，尚待核实。'},
        origin='model_inference', source_refs=refs),) if refs else ())


def msg_ref(value):
    msg = value.messages[0]
    return d.ProfileMessageRef(kind='message', conversation_id=value.scope.conversation_id, message_id=msg.id,
        source_revision=msg.source_revision, start=0, end=len(msg.content), quote=msg.content,
        quote_sha256=hashlib.sha256(msg.content.encode()).hexdigest())


def sent(workspace, **scope):
    database, actors, _, _ = workspace
    value = conversation(workspace, **scope)
    with database.session() as db:
        service.save_message(actors['lawyer'], value.scope.conversation_id, message(value), db)
        return service.read_conversation(actors['lawyer'], value.scope.conversation_id, db)


def parsed_source(material_workspace, *, parser_request=None):
    database, actors, value, request, raw = material_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    receipt = attachments.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    parsed = attachments.parse_attachment(actor, cid, receipt.attachment.id,
        parser_request or d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope),
        database=database).parse
    scope = attachments.read_materials(actor, cid, database=database).scope
    ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=receipt.attachment.id,
        original_sha256=receipt.attachment.sha256, parse_revision=parsed.revision,
        result_sha256=parsed.result_sha256, anchor=parsed.result.anchors[0])
    return patch(scope, (ref,)), parsed


def state(database):
    with database.engine.connect() as db:
        return '\n'.join(db.connection.driver_connection.iterdump())


def denied(database, actor, proposal, code='VERSION_CONFLICT'):
    with pytest.raises(ServiceError) as error:
        read(database, actor, proposal)
    assert error.value.code == code


def test_user_message_sources_merge_without_writes_or_draft_leak(workspace):
    database, actors, _, _ = workspace
    value = sent(workspace)
    with database.session() as db:
        service.save_draft(actors['lawyer'], value.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=value.scope, expected_composer_revision=value.composer_revision,
            content='未发送文本不能作为来源'), db)
    proposal = patch(value.scope, (msg_ref(value), msg_ref(value)))
    before = state(database)
    snapshot = read(database, actors['lawyer'], proposal)
    assert snapshot.messages == value.messages and snapshot.documents == ()
    merged = merge_profile(None, proposal, snapshot, project_intake=True)
    assert merged.projection.consultation == '合成客户自述，尚待核实。'
    assert merged.profile.fields[0].verification == 'unverified'
    assert state(database) == before


def test_sources_are_database_bytes_not_proposal_quote(workspace):
    database, actors, _, _ = workspace
    value = sent(workspace)
    forged = msg_ref(value).model_dump(mode='python')
    forged.update(quote='伪造陈述', end=4, quote_sha256=hashlib.sha256('伪造陈述'.encode()).hexdigest())
    proposal = patch(value.scope, (d.ProfileMessageRef(**forged),))
    snapshot = read(database, actors['lawyer'], proposal)
    assert snapshot.messages == value.messages
    with pytest.raises(ValueError, match='source mismatch'):
        merge_profile(None, proposal, snapshot)


@pytest.mark.parametrize('failure', ['missing', 'other_conversation', 'assistant', 'future'])
def test_only_existing_user_messages_in_this_scope_are_sources(workspace, failure):
    database, actors, _, _ = workspace
    value = sent(workspace)
    ref = msg_ref(value)
    if failure == 'missing':
        ref = ref.model_copy(update={'message_id':uuid4()})
    elif failure == 'other_conversation':
        other = sent(workspace)
        ref = msg_ref(other).model_copy(update={'conversation_id':value.scope.conversation_id})
    else:
        identifier = uuid4()
        with database.session() as db:
            db.execute(text('''INSERT INTO assistant_messages(id,conversation_id,role,content,created_at,source_revision)
                VALUES (:id,:cid,:role,:content,:at,:rev)'''), dict(id=str(identifier),
                cid=str(value.scope.conversation_id), role='assistant' if failure == 'assistant' else 'user',
                content=ref.quote, at=service._at(), rev=2))
        ref = ref.model_copy(update={'message_id':identifier, 'source_revision':2})
    denied(database, actors['lawyer'], patch(value.scope, (ref,)))


@pytest.mark.parametrize('failure', ['owner', 'session', 'role', 'workspace', 'scope', 'archived', 'restore'])
def test_current_authorization_and_live_scope_required_even_for_empty_patch(workspace, failure):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, _ = workspace
    value = conversation(workspace)
    proposal, actor, code = patch(value.scope), actors['lawyer'], 'VERSION_CONFLICT'
    with database.session() as db:
        if failure == 'owner':
            actor, code = actors['reviewer'], 'CROSS_MATTER_DENIED'
        elif failure == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
            code = 'AUTHORIZATION_REQUIRED'
        elif failure == 'role':
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
            code = 'CROSS_MATTER_DENIED'
        elif failure == 'workspace':
            db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
            code = 'CROSS_MATTER_DENIED'
        elif failure == 'scope':
            proposal = proposal.model_copy(update={'scope':value.scope.model_copy(update={'input_revision':1})})
        elif failure == 'archived':
            db.execute(text('UPDATE assistant_conversations SET archived_at=:at'), {'at':service._at()})
        else:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
            code = 'BLOCKED_LIVE'
    denied(database, actor, proposal, code)


def test_document_snapshot_reuses_original_and_exact_selected_parse(material_workspace):
    database, actors, _, _, raw = material_workspace
    proposal, parsed = parsed_source(material_workspace)
    before = state(database)
    snapshot = read(database, actors['lawyer'], proposal)
    assert snapshot.documents[0].result == parsed.result
    assert snapshot.documents[0].original_sha256 == hashlib.sha256(raw).hexdigest()
    assert snapshot.documents[0].parse_revision == parsed.revision
    assert merge_profile(None, proposal, snapshot).changed
    assert state(database) == before
    assert next(database.storage_root.rglob('original.bin')).read_bytes() == raw


@pytest.mark.parametrize('failure', ['unselected', 'different_parse', 'unparsed', 'tampered_original', 'tampered_parse'])
def test_unusable_document_source_fails_closed(material_workspace, failure):
    database, actors, _, _, raw = material_workspace
    proposal, parsed = parsed_source(material_workspace)
    actor, cid = actors['lawyer'], proposal.scope.conversation_id
    ref = proposal.changes[0].source_refs[0]
    if failure in ('unselected','unparsed'):
        values = () if failure == 'unselected' else (d.AssistantMaterialRef(attachment_id=ref.attachment_id, parse_revision=None),)
        attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(request_id=uuid4(),
            expected_scope=proposal.scope,items=values),database=database)
        proposal = proposal.model_copy(update={'scope':attachments.read_materials(actor,cid,database=database).scope})
    elif failure == 'different_parse':
        attachments.parse_attachment(actor,cid,ref.attachment_id,d.AssistantAttachmentParseInput(
            request_id=uuid4(),expected_scope=proposal.scope),database=database)
        proposal = proposal.model_copy(update={'scope':attachments.read_materials(actor,cid,database=database).scope})
    elif failure == 'tampered_original':
        path = next(database.storage_root.rglob('original.bin'))
        path.chmod(0o600)
        path.write_bytes(raw + b'synthetic mutation')
    else:
        with database.session() as db:
            db.execute(text('DROP TRIGGER immutable_assistant_attachment_parses_update'))
            db.execute(text('UPDATE assistant_attachment_parses SET result_sha256=:sha'), {'sha':'0'*64})
    denied(database, actor, proposal)


@pytest.mark.parametrize('change', ['session', 'selection', 'input', 'binding', 'archive', 'restore', 'composer'])
def test_file_io_has_no_open_transaction_and_final_gate_sees_changes(material_workspace, monkeypatch, change):
    from cn_contract.assistant import attachment_files
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, _, _ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    actor, cid = actors['lawyer'], proposal.scope.conversation_id
    entered, resume = Event(), Event()
    original = attachment_files.read_checked
    def slow(*args):
        entered.set()
        assert resume.wait(12)
        return original(*args)
    monkeypatch.setattr(attachment_files, 'read_checked', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(read, database, actor, proposal)
        assert entered.wait(12)
        try:
            with database.session() as db:
                if change == 'session':
                    db.get(SessionRow, str(actor.session_id)).revoked = True
                elif change == 'restore':
                    db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
                elif change == 'archive':
                    db.execute(text('UPDATE assistant_conversations SET archived_at=:at'), {'at':service._at()})
                elif change == 'binding':
                    db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1'))
                elif change == 'input':
                    current = service.read_conversation(actor,cid,db)
                    service.save_message(actor,cid,message(current),db)
                elif change == 'composer':
                    service.save_draft(actor,cid,d.AssistantDraftInput(expected_scope=proposal.scope,
                        expected_composer_revision=0,content='尚未发送新问题'),db)
            if change == 'selection':
                attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(request_id=uuid4(),
                    expected_scope=proposal.scope,items=()),database=database)
        finally:
            resume.set()
        if change == 'composer':
            assert future.result(timeout=15).scope == proposal.scope
        else:
            with pytest.raises(ServiceError) as error:
                future.result(timeout=15)
            assert error.value.code == {'session':'AUTHORIZATION_REQUIRED','restore':'BLOCKED_LIVE'}.get(change,'VERSION_CONFLICT')


@pytest.mark.parametrize('kind', ['matter', 'intake', 'projection'])
def test_linked_matter_membership_is_rechecked(workspace, kind):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    matter = add_matter(database, actor)
    intake = add_intake(database, actor, matter)
    value = conversation(workspace, **({'scope_kind':kind,'scope_ref':matter if kind=='matter' else intake}
        if kind != 'projection' else {}))
    with database.session() as db:
        if kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:id'), {'id':str(intake)})
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter)})
    denied(database, actor, patch(value.scope), 'CROSS_MATTER_DENIED')


def test_nested_model_copy_cannot_bypass_input_validation(workspace):
    database, actors, _, _ = workspace
    value = conversation(workspace)
    proposal = patch(value.scope).model_copy(update={'scope':value.scope.model_copy(update={'input_revision':-1})})
    with pytest.raises(ValidationError):
        read(database, actors['lawyer'], proposal)


def many_refs(scope, refs):
    # The public patch already limits each proposal to 40 references.
    return d.ProfilePatch(scope=scope, base_profile_revision=0, changes=tuple(
        patch(scope, refs[i:i+40]).changes[0] for i in range(0,len(refs),40)))


def test_message_capacity_and_long_history_are_bounded_without_truncation(workspace):
    database, actors, _, _ = workspace
    value = sent(workspace)
    first = msg_ref(value)
    refs = [first]
    with database.session() as db:
        for revision in range(2, 202):
            identifier = uuid4()
            db.execute(text('''INSERT INTO assistant_messages(id,conversation_id,role,content,created_at,source_revision)
                VALUES (:id,:cid,'user',:content,:at,:rev)'''), dict(id=str(identifier),
                cid=str(value.scope.conversation_id),content=first.quote,at=service._at(),rev=revision))
            refs.append(first.model_copy(update={'message_id':identifier,'source_revision':revision}))
        db.execute(text('UPDATE assistant_conversations SET input_revision=201'))
    scope = value.scope.model_copy(update={'input_revision':201})
    subset = read(database, actors['lawyer'], patch(scope,(refs[-1],)))
    assert len(subset.messages) == 1 and subset.messages[0].source_revision == 201
    full = read(database, actors['lawyer'], many_refs(scope,refs[:200]))
    assert len(full.messages) == 200
    denied(database, actors['lawyer'], many_refs(scope,refs), 'FILE_LIMIT')


def test_document_capacity_and_dedup(material_workspace, monkeypatch):
    from cn_contract.assistant import attachment_files
    database, actors, _, request, raw = material_workspace
    proposal, _ = parsed_source(material_workspace)
    refs, scope, actor = [proposal.changes[0].source_refs[0]], proposal.scope, actors['lawyer']
    for index in range(19):
        receipt = attachments.ingest_attachment(actor,scope.conversation_id,request.model_copy(update={
            'request_id':uuid4(),'expected_scope':scope,'original_name':f'合成附件{index}.docx'}),BytesIO(raw),database=database)
        scope = attachments.read_materials(actor,scope.conversation_id,database=database).scope
        parsed = attachments.parse_attachment(actor,scope.conversation_id,receipt.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=scope),database=database).parse
        scope = attachments.read_materials(actor,scope.conversation_id,database=database).scope
        refs.append(d.ProfileDocumentRef(kind='document',conversation_id=scope.conversation_id,
            attachment_id=receipt.attachment.id,original_sha256=receipt.attachment.sha256,
            parse_revision=parsed.revision,result_sha256=parsed.result_sha256,anchor=parsed.result.anchors[0]))
    original, calls = attachment_files.read_checked, []
    def counted(row, database):
        calls.append(row['id'])
        return original(row,database)
    monkeypatch.setattr(attachment_files,'read_checked',counted)
    snapshot = read(database,actor,patch(scope,(*refs,*refs)))
    assert len(snapshot.documents) == len(calls) == len(set(calls)) == 20
    extra = refs[0].model_dump(mode='python')
    extra['attachment_id'] = uuid4()
    extra['anchor']['document_version_id'] = extra['attachment_id']
    denied(database,actor,patch(scope,(*refs,d.ProfileDocumentRef(**extra))), 'FILE_LIMIT')
    assert len(calls) == 20


def test_unreferenced_unparsed_file_does_not_block_source(material_workspace):
    database, actors, _, request, raw = material_workspace
    proposal, _ = parsed_source(material_workspace)
    actor, cid = actors['lawyer'], proposal.scope.conversation_id
    attachments.ingest_attachment(actor,cid,request.model_copy(update={
        'request_id':uuid4(),'expected_scope':proposal.scope}),BytesIO(raw),database=database)
    proposal = proposal.model_copy(update={'scope':attachments.read_materials(actor,cid,database=database).scope})
    assert len(read(database,actor,proposal).documents) == 1


def test_explicit_old_parse_selection_is_not_replaced_with_latest(material_workspace):
    database, actors, _, _, _ = material_workspace
    proposal, original = parsed_source(material_workspace)
    ref, actor, cid = proposal.changes[0].source_refs[0], actors['lawyer'], proposal.scope.conversation_id
    attachments.parse_attachment(actor,cid,ref.attachment_id,d.AssistantAttachmentParseInput(
        request_id=uuid4(),expected_scope=proposal.scope),database=database)
    current = attachments.read_materials(actor,cid,database=database)
    attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(request_id=uuid4(),
        expected_scope=current.scope,items=(d.AssistantMaterialRef(attachment_id=ref.attachment_id,parse_revision=1),)),database=database)
    proposal = proposal.model_copy(update={'scope':attachments.read_materials(actor,cid,database=database).scope})
    snapshot = read(database,actor,proposal)
    assert snapshot.documents[0].parse_revision == 1 and snapshot.documents[0].result == original.result


@pytest.mark.parametrize('status', ['failed','needs_baseline','partial'])
def test_parse_limits_are_preserved_or_rejected(material_workspace, monkeypatch, status):
    database, actors, _, _, _ = material_workspace
    proposal, old = parsed_source(material_workspace)
    ref, actor, cid = proposal.changes[0].source_refs[0], actors['lawyer'], proposal.scope.conversation_id
    if status == 'failed':
        def fail(*args):
            raise ValueError('synthetic parser failure')
        monkeypatch.setattr(attachments,'parse_docx',fail)
    elif status == 'needs_baseline':
        monkeypatch.setattr(attachments,'has_revisions',lambda parts: True)
    else:
        result = old.result.model_copy(update={'unsupported_parts':('synthetic/unread.xml',)})
        monkeypatch.setattr(attachments,'parse_docx',lambda *args:result)
    parsed = attachments.parse_attachment(actor,cid,ref.attachment_id,d.AssistantAttachmentParseInput(
        request_id=uuid4(),expected_scope=proposal.scope),database=database).parse
    assert parsed.reading_status == status
    scope = attachments.read_materials(actor,cid,database=database).scope
    proposal = patch(scope,(ref.model_copy(update={'parse_revision':parsed.revision,
        'result_sha256':parsed.result_sha256 or ref.result_sha256}),))
    if status == 'partial':
        snapshot = read(database,actor,proposal)
        assert snapshot.documents[0].result == parsed.result
        assert snapshot.documents[0].result.unsupported_parts == ('synthetic/unread.xml',)
        assert merge_profile(None,proposal,snapshot).profile.fields[0].verification == 'unverified'
    else:
        denied(database,actor,proposal)


def test_malformed_stored_message_is_redacted_in_error(workspace):
    database, actors, _, _ = workspace
    value = sent(workspace)
    proposal = patch(value.scope,(msg_ref(value),))
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_messages_update'))
        db.execute(text('UPDATE assistant_messages SET content=:content'),{'content':'敏感合成标记'*5000})
    denied(database,actors['lawyer'],proposal)


def test_corrupt_selection_does_not_choose_last_duplicate(material_workspace):
    database, actors, _, _, _ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    ref = proposal.changes[0].source_refs[0]
    values = [{'attachment_id':str(ref.attachment_id),'parse_revision':None},
              {'attachment_id':str(ref.attachment_id),'parse_revision':ref.parse_revision}]
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_material_snapshots_update'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:items WHERE revision=:rev'),
            {'items':json.dumps(values),'rev':proposal.scope.materials_revision})
    denied(database,actors['lawyer'],proposal)


def test_source_module_does_not_import_parser_or_web():
    import subprocess
    import sys
    result = subprocess.run([sys.executable,'-X','utf8','-c',
        'import sys; import cn_contract.assistant.profile_sources; '
        'assert not any(k == "docx" or k.startswith(("cn_contract.web.", "cn_contract.parsers.")) for k in sys.modules)'],
        capture_output=True,text=True,check=False)
    assert result.returncode == 0, result.stderr
