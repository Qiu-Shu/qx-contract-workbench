"""Synthetic task intake never executes a model or drops an inbound attachment."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation
from test_assistant_attachments import material_workspace


def test_task_draft_module_is_available():
    assert importlib.util.find_spec('cn_contract.task_drafts') is not None


@pytest.fixture
def task_workspace(material_workspace):
    from cn_contract.task_drafts import schema, service
    database, actors, value, request, raw = material_workspace
    schema.initialize_storage(database)
    actor, cid = actors['lawyer'], value.scope.conversation_id
    with database.session() as db:
        binding = service.create_binding(actor, cid, db)
    return database, actors, cid, binding, service, request, raw


def receive(env, *events, cursor=None):
    database, actors, _, binding, service, _, _ = env
    with database.session() as db:
        current = service.create_binding(actors['lawyer'], env[2], db)
        index = current.cursor if cursor is None else cursor
        return service.receive_batch(actors['lawyer'], binding.id,
            d.TaskInboxBatchInput(expected_cursor=index, next_cursor=index + 1,
                events=tuple(d.TaskInboxEventInput(**event) for event in events)), db)


def test_intake_aggregates_messages_without_a_run(task_workspace):
    env = task_workspace
    first = receive(env, {'event_id':'instruction', 'text':'审查这份虚构合同'})
    second = receive(env, {'event_id':'file', 'media':[
        {'media_id':'file-1','name':'虚构合同.pdf','mime':'application/pdf','status':'unsupported'},
        {'media_id':'file-2','name':'补充录音.wav','mime':'audio/wav','status':'pending'}]})
    assert first.drafts[0].id == second.drafts[0].id
    draft = second.drafts[0]
    assert draft.instruction == '审查这份虚构合同'
    assert len(draft.events) == 2 and len(draft.events[1].media) == 2
    assert 'media_unsupported' in draft.blockers and 'media_pending' in draft.blockers
    with env[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM matters')) == 0


def test_duplicate_is_replayed_and_changed_payload_is_rejected(task_workspace):
    env = task_workspace
    first = receive(env, {'event_id':'same','text':'原话'})
    again = receive(env, {'event_id':'same','text':'原话'}, cursor=0)
    assert again.drafts[0] == first.drafts[0]
    with pytest.raises(ServiceError) as error:
        receive(env, {'event_id':'same','text':'被改写'}, cursor=0)
    assert error.value.code == 'VERSION_CONFLICT'
    with env[0].session() as db:
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events')) == 1


def test_whole_batch_rolls_back_before_cursor_on_late_failure(task_workspace):
    env = task_workspace
    with env[0].session() as db:
        db.execute(text("CREATE TRIGGER fail_second BEFORE INSERT ON task_inbox_events "
            "WHEN NEW.event_id='second' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"))
    with pytest.raises(Exception, match='synthetic failure'):
        receive(env, {'event_id':'first','text':'一'}, {'event_id':'second','text':'二'})
    with env[0].session() as db:
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM task_drafts')) == 0


def test_ambiguous_assignment_and_explicit_target(task_workspace):
    env = task_workspace
    first = receive(env, {'event_id':'one','text':'任务一','start_new':True}).drafts[0]
    second = receive(env, {'event_id':'two','text':'任务二','start_new':True}).drafts[0]
    third = receive(env, {'event_id':'ambiguous','text':'补充'})
    assert third.events[0].task_id is None and third.events[0].association == 'unassigned'
    selected = receive(env, {'event_id':'explicit','text':'明确归属','task_id':first.id}).drafts[0]
    assert selected.id == first.id and len(selected.events) == 2
    with env[0].session() as db:
        listing = env[4].list_drafts(env[1]['lawyer'],env[2],db)
        assert len(listing.items) == 2 and len(listing.unassigned_events) == 1
        assigned = env[4].update_draft(env[1]['lawyer'],second.id,
            d.TaskDraftUpdateInput(expected_revision=second.revision,action='assign',
                event_ids=(third.events[0].id,)),db)
        assert len(assigned.events) == 2


def test_cross_conversation_explicit_target_fails_without_fallback(task_workspace,workspace):
    env = task_workspace
    own = receive(env, {'event_id':'own','text':'自己任务'}).drafts[0]
    other_cid = conversation(workspace).scope.conversation_id
    with env[0].session() as db:
        other = env[4].create_binding(env[1]['lawyer'],other_cid,db)
        with pytest.raises(ServiceError) as error:
            env[4].receive_batch(env[1]['lawyer'],other.id,d.TaskInboxBatchInput(expected_cursor=0,
                next_cursor=1,events=(d.TaskInboxEventInput(event_id='wrong',text='不能错收',task_id=own.id),)),db)
        assert error.value.code == 'CROSS_MATTER_DENIED'
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings WHERE id=:id'),{'id':str(other.id)}) == 0


@pytest.mark.parametrize('action,state', [('pause','paused'),('cancel','cancelled')])
def test_paused_or_cancelled_requires_resume(task_workspace,action,state):
    env = task_workspace
    draft = receive(env, {'event_id':'initial','text':'虚构任务'}).drafts[0]
    with env[0].session() as db:
        stopped = env[4].update_draft(env[1]['lawyer'],draft.id,
            d.TaskDraftUpdateInput(expected_revision=draft.revision,action=action),db)
        assert stopped.state == state
        restored = env[4].update_draft(env[1]['lawyer'],draft.id,
            d.TaskDraftUpdateInput(expected_revision=stopped.revision,action='resume'),db)
        assert restored.state == 'collecting'
        with pytest.raises(ServiceError):
            env[4].update_draft(env[1]['lawyer'],draft.id,
                d.TaskDraftUpdateInput(expected_revision=draft.revision,action='pause'),db)


def ready_media(env):
    from cn_contract.assistant import attachments as a
    database, actors, cid, _, _, request, raw = env
    uploaded = a.ingest_attachment(actors['lawyer'],cid,request,BytesIO(raw),database=database)
    current = a.read_materials(actors['lawyer'],cid,database=database)
    parsed = a.parse_attachment(actors['lawyer'],cid,uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope),database=database)
    return {'media_id':'ready','name':uploaded.attachment.original_name,'mime':uploaded.attachment.mime,
        'status':'ready','attachment_id':uploaded.attachment.id,'sha256':uploaded.attachment.sha256,
        'parse_revision':parsed.parse.revision}


def test_file_first_freeze_cas_and_late_material_gets_new_draft(task_workspace):
    env = task_workspace
    media = ready_media(env)
    first = receive(env, {'event_id':'file','media':[media]}).drafts[0]
    assert 'instruction_required' in first.blockers
    current = receive(env, {'event_id':'instruction','text':'审查虚构合同'}).drafts[0]
    with env[0].session() as db:
        service, actor = env[4],env[1]['lawyer']
        for rev,sha in ((first.revision,current.manifest_sha256),(current.revision,'0'*64)):
            with pytest.raises(ServiceError) as error:
                service.freeze_draft(actor,current.id,d.TaskFreezeInput(expected_revision=rev,manifest_sha256=sha),db)
            assert error.value.code == 'VERSION_CONFLICT'
        frozen = service.freeze_draft(actor,current.id,d.TaskFreezeInput(
            expected_revision=current.revision,manifest_sha256=current.manifest_sha256),db)
        assert frozen.state == 'prepared' and frozen.manifest.main_attachment_id == media['attachment_id']
        assert frozen.manifest.review_status == 'unverified'
        assert service.freeze_draft(actor,current.id,d.TaskFreezeInput(
            expected_revision=current.revision,manifest_sha256=current.manifest_sha256),db) == frozen
    later = receive(env, {'event_id':'later','text':'后补事实待核','task_id':current.id}).drafts[0]
    assert later.id != current.id and later.parent_draft_id == current.id
    with env[0].session() as db:
        assert env[4].read_execution(env[1]['lawyer'],frozen.id,db) == frozen
        assert env[4].read_draft(env[1]['lawyer'],current.id,db).state == 'frozen'


@pytest.mark.parametrize('kind', ['hash','parse','conversation'])
def test_media_reference_is_rechecked_on_server(task_workspace,workspace,kind):
    env = task_workspace
    media = ready_media(env)
    if kind == 'hash': media['sha256'] = '0'*64
    if kind == 'parse': media['parse_revision'] = 999
    if kind == 'conversation':
        cid = conversation(workspace).scope.conversation_id
        with env[0].session() as db:
            binding = env[4].create_binding(env[1]['lawyer'],cid,db)
        env = (*env[:2],cid,binding,*env[4:])
    with pytest.raises(ServiceError):
        receive(env, {'event_id':'invalid','text':'虚构审查','media':[media]})
    with env[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events')) == 0


def test_unready_media_cannot_freeze(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'pending','text':'审查','media':[
        {'media_id':'pending','name':'待下载.docx','mime':'application/docx','status':'pending'}]}).drafts[0]
    with env[0].session() as db:
        with pytest.raises(ServiceError) as error:
            env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
                expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        assert error.value.code == 'STATE_CONFLICT'
        assert db.scalar(text('SELECT COUNT(*) FROM task_executions')) == 0


def test_execution_transitions_cannot_rewind(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        service, actor = env[4], env[1]['lawyer']
        run = service.freeze_draft(actor,draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        claimed = service.advance_execution(actor,run.id,'creating_matter',db,expected_state='prepared')
        assert claimed.state == 'creating_matter'
        with pytest.raises(ServiceError):
            service.advance_execution(actor,run.id,'prepared',db,expected_state='creating_matter')
        assert service.quarantine_executions(db) == 1
        assert service.read_execution(actor,run.id,db).state == 'blocked'


def test_current_owner_is_required_for_intake_and_reads(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'own','text':'虚构'}).drafts[0]
    with env[0].session() as db:
        with pytest.raises(ServiceError) as error:
            env[4].read_draft(env[1]['reviewer'],draft.id,db)
        assert error.value.code == 'CROSS_MATTER_DENIED'


def test_pending_resolution_and_explicit_exclusion_are_auditable(task_workspace):
    env = task_workspace
    ready = ready_media(env)
    draft = receive(env, {'event_id':'pending','text':'审查','media':[
        {'media_id':'ready','name':'待下载.docx','mime':'application/docx'},
        {'media_id':'audio','name':'录音.wav','mime':'audio/wav','status':'unsupported'}]}).drafts[0]
    with env[0].session() as db:
        changed = env[4].update_draft(env[1]['lawyer'],draft.id,d.TaskDraftUpdateInput(
            expected_revision=draft.revision,media_resolutions=(
                d.TaskMediaResolutionInput(event_id=draft.events[0].id,media_id='ready',action='resolve',replacement=ready),
                d.TaskMediaResolutionInput(event_id=draft.events[0].id,media_id='audio',action='exclude',reason='仅为无关测试录音'))),db)
        assert changed.blockers == () and len(changed.media_resolutions) == 2
        assert changed.events[0].media[0].status == 'pending'
        run = env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=changed.revision,manifest_sha256=changed.manifest_sha256),db)
        assert run.manifest.events[0].media[1].excluded
        assert run.manifest.events[0].media[0].attachment_id == ready['attachment_id']


def test_repeated_resolution_survives_frozen_child_creation(task_workspace):
    env = task_workspace
    media = ready_media(env)
    draft = receive(env, {'event_id':'pending','text':'审查','media':[
        {'media_id':'ready','name':'待下载.docx','mime':'application/docx'}]}).drafts[0]
    with env[0].session() as db:
        for _ in range(2):
            draft = env[4].update_draft(env[1]['lawyer'],draft.id,d.TaskDraftUpdateInput(
                expected_revision=draft.revision,media_resolutions=(d.TaskMediaResolutionInput(
                    event_id=draft.events[0].id,media_id='ready',action='resolve',replacement=media),)),db)
        env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
    child = receive(env, {'event_id':'supplement','text':'后补','task_id':draft.id}).drafts[0]
    assert child.parent_draft_id == draft.id and child.blockers == ()


def test_scope_rebinding_blocks_frozen_execution_and_late_supplement(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        frozen = env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),{'id':str(env[2])})
        with pytest.raises(ServiceError):
            env[4].read_execution(env[1]['lawyer'],frozen.id,db)
    with pytest.raises(ServiceError):
        receive(env, {'event_id':'late','text':'不能借重新绑定重用旧任务','task_id':draft.id})


def test_exact_control_messages_pause_resume_cancel_without_polluting_instruction(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'instruction','text':'审查虚构合同'}).drafts[0]
    paused = receive(env, {'event_id':'pause','text':'先别审','task_id':draft.id}).drafts[0]
    assert paused.state == 'paused' and paused.instruction == '审查虚构合同'
    resumed = receive(env, {'event_id':'resume','text':'继续'}).drafts[0]
    assert resumed.id == draft.id and resumed.state == 'collecting'
    cancelled = receive(env, {'event_id':'cancel','text':'取消','task_id':draft.id}).drafts[0]
    assert cancelled.state == 'cancelled'
    assert len(cancelled.events) == 4 and cancelled.instruction == '审查虚构合同'


def test_frozen_execution_cancellation_does_not_rewrite_manifest(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        frozen = env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        cancelled = env[4].cancel_execution(env[1]['lawyer'],frozen.id,db)
        assert cancelled.state == 'blocked' and cancelled.error == 'TASK_CANCELLED'
        assert cancelled.manifest == frozen.manifest
        assert env[4].cancel_execution(env[1]['lawyer'],frozen.id,db) == cancelled


def test_concurrent_identical_batch_and_freeze_are_exactly_once(task_workspace):
    env = task_workspace
    media = ready_media(env)
    def ingest(_):
        return receive(env, {'event_id':'same','text':'审查','media':[media]},cursor=0).drafts[0]
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(ingest,range(2)))
    assert values[0] == values[1]
    def freeze(_):
        with env[0].session() as db:
            return env[4].freeze_draft(env[1]['lawyer'],values[0].id,d.TaskFreezeInput(
                expected_revision=values[0].revision,manifest_sha256=values[0].manifest_sha256),db)
    with ThreadPoolExecutor(max_workers=2) as executor:
        runs = list(executor.map(freeze,range(2)))
    assert runs[0] == runs[1]


def test_execution_cannot_claim_ready_or_completed_without_saved_evidence(task_workspace):
    env = task_workspace
    draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        run = env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        with pytest.raises(ServiceError):
            env[4].advance_execution(env[1]['lawyer'],run.id,'awaiting_facts',db,expected_state='prepared')
        assert env[4].read_execution(env[1]['lawyer'],run.id,db).state == 'prepared'


def test_original_hash_is_checked_again_when_freezing(task_workspace):
    import stat
    env = task_workspace
    draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    path = next(env[0].storage_root.rglob('original.bin'))
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(path.read_bytes()+b'changed')
    with env[0].session() as db:
        with pytest.raises(ServiceError) as error:
            env[4].freeze_draft(env[1]['lawyer'],draft.id,d.TaskFreezeInput(
                expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert db.scalar(text('SELECT COUNT(*) FROM task_executions')) == 0


def test_full_draft_keeps_new_event_unassigned_and_rejects_explicit_overflow(task_workspace):
    env = task_workspace
    draft = receive(env,*({'event_id':str(index),'text':'虚构'} for index in range(100))).drafts[0]
    assert len(draft.events) == 100
    overflow = receive(env,{'event_id':'overflow','text':'未丢弃'})
    assert overflow.events[0].association == 'unassigned' and overflow.drafts == ()
    with env[0].session() as db:
        with pytest.raises(ServiceError) as error:
            env[4].update_draft(env[1]['lawyer'],draft.id,d.TaskDraftUpdateInput(
                expected_revision=draft.revision,action='assign',event_ids=(overflow.events[0].id,)),db)
        assert error.value.status_code == 413
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events')) == 101
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings')) == 2


def test_list_omits_rebound_execution_but_keeps_current_legal_drafts(task_workspace):
    env = task_workspace
    frozen_draft = receive(env, {'event_id':'ready','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        execution = env[4].freeze_draft(env[1]['lawyer'],frozen_draft.id,d.TaskFreezeInput(
            expected_revision=frozen_draft.revision,manifest_sha256=frozen_draft.manifest_sha256),db)
        db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),{'id':str(env[2])})
    current = receive(env, {'event_id':'fresh','text':'当前合法草稿','start_new':True}).drafts[0]
    with env[0].session() as db:
        listing = env[4].list_drafts(env[1]['lawyer'],env[2],db)
        assert [item.id for item in listing.items] == [current.id]
        with pytest.raises(ServiceError):
            env[4].read_execution(env[1]['lawyer'],execution.id,db)


def test_instruction_at_limit_still_accepts_file_only_followup(task_workspace):
    env = task_workspace
    draft = receive(env,{'event_id':'limit','text':'a'*20000}).drafts[0]
    followup = receive(env,{'event_id':'file','media':[
        {'media_id':'pending','name':'synthetic.docx','mime':'application/docx'}]}).drafts[0]
    assert followup.id == draft.id and len(followup.instruction) == 20000
    assert len(followup.events) == 2


def test_reply_reference_resolves_among_multiple_open_tasks(task_workspace):
    env = task_workspace
    first = receive(env,{'event_id':'first','text':'第一项','start_new':True}).drafts[0]
    second = receive(env,{'event_id':'second','text':'第二项','start_new':True}).drafts[0]
    reply = receive(env,{'event_id':'reply','text':'补充第一项','reply_to_event_id':'first'})
    assert reply.drafts[0].id == first.id
    explicit = receive(env,{'event_id':'explicit','text':'明确改属第二项','task_id':second.id,'reply_to_event_id':'first'})
    assert explicit.drafts[0].id == second.id


def test_unknown_reply_does_not_fall_back_to_only_open_task(task_workspace):
    env = task_workspace
    receive(env,{'event_id':'only','text':'唯一开放任务'})
    reply = receive(env,{'event_id':'reply','text':'回复不存在的来源','reply_to_event_id':'unknown'})
    assert reply.events[0].association == 'unassigned' and reply.drafts == ()


def test_reply_source_is_scoped_to_the_channel_binding(task_workspace,workspace):
    env = task_workspace
    receive(env,{'event_id':'foreign-source','text':'原会话'})
    cid = conversation(workspace).scope.conversation_id
    with env[0].session() as db:
        binding = env[4].create_binding(env[1]['lawyer'],cid,db)
    other = (*env[:2],cid,binding,*env[4:])
    reply = receive(other,{'event_id':'reply','text':'不能跨绑定引用','reply_to_event_id':'foreign-source'})
    assert reply.events[0].association == 'unassigned' and reply.drafts == ()


def test_reply_to_frozen_source_creates_and_reuses_next_draft(task_workspace):
    env = task_workspace
    first = receive(env,{'event_id':'source','text':'审查','media':[ready_media(env)]}).drafts[0]
    with env[0].session() as db:
        env[4].freeze_draft(env[1]['lawyer'],first.id,d.TaskFreezeInput(
            expected_revision=first.revision,manifest_sha256=first.manifest_sha256),db)
    next_draft = receive(env,{'event_id':'reply-one','text':'后补','reply_to_event_id':'source'}).drafts[0]
    repeated = receive(env,{'event_id':'reply-two','text':'再补','reply_to_event_id':'source'}).drafts[0]
    assert next_draft.id != first.id and next_draft.parent_draft_id == first.id
    assert repeated.id == next_draft.id


def test_absent_reply_keeps_legacy_event_digest_bytes():
    from cn_contract.config import canonical_json
    event = d.TaskInboxEventInput(event_id='legacy',text='test')
    assert canonical_json(event.model_dump(mode='json')) == (
        '{"event_id":"legacy","media":[],"start_new":false,"task_id":null,"text":"test"}')


def test_explicit_full_target_keeps_complete_batch_and_cursor(task_workspace):
    env = task_workspace
    full = receive(env,*({'event_id':str(index),'text':'虚构'} for index in range(100))).drafts[0]
    values = (
        {'event_id':'explicit-overflow','task_id':full.id,'text':'保留满额后的完整输入','media':[
            {'media_id':'one','name':'待读取.docx','mime':'application/docx','status':'pending'},
            {'media_id':'two','name':'补充录音.wav','mime':'audio/wav','status':'unsupported'}]},
        {'event_id':'other-task','text':'同批另一项独立任务','start_new':True},
    )
    received = receive(env,*values)
    overflow,other = received.events
    assert received.binding.cursor == 2
    assert overflow.association == 'unassigned' and overflow.task_id is None
    assert [media.media_id for media in overflow.media] == ['one','two']
    assert other.association == 'assigned' and other.task_id != full.id
    assert receive(env,*values,cursor=1) == received
    with env[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events')) == 102
        assert len(env[4].read_draft(env[1]['lawyer'],full.id,db).events) == 100
        payload = db.scalar(text('SELECT payload_json FROM task_inbox_events WHERE id=:id'),{'id':str(overflow.id)})
        assert d.TaskInboxEventInput.model_validate_json(payload).task_id == full.id
        with pytest.raises(ServiceError) as error:
            env[4].update_draft(env[1]['lawyer'],full.id,d.TaskDraftUpdateInput(
                expected_revision=full.revision,action='assign',event_ids=(overflow.id,)),db)
        assert error.value.status_code == 413
        listing = env[4].list_drafts(env[1]['lawyer'],env[2],db)
        assert [event.id for event in listing.unassigned_events] == [overflow.id]
