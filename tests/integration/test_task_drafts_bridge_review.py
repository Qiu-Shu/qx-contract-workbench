"""Independent bridge probes: authorization, exact sources and transactional replay."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import stat
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.persistence import read_version
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation
from test_task_drafts_bridge import frozen_task, prepare, review_input


def test_preparation_rechecks_frozen_original_bytes(frozen_task):
    from cn_contract.task_drafts import bridge
    database, actors, cid, execution, matter_id, source_id, raw = frozen_task
    path = database.storage_root / 'assistant' / str(cid) / str(source_id) / 'original.bin'
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(raw+b'changed-after-freezing')
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'],execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(),matter_id=matter_id),db=db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 0
        assert db.scalar(text('SELECT state FROM task_executions')) == 'prepared'


def test_current_synthetic_registry_is_required_again_at_preparation(frozen_task,monkeypatch):
    from cn_contract.ops import backup
    from cn_contract.task_drafts import bridge
    database,actors,_,execution,matter_id,_,_ = frozen_task
    monkeypatch.setattr(backup,'_registered_hashes',lambda: frozenset())
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'],execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(),matter_id=matter_id),db=db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 0


def test_later_assistant_parse_does_not_replace_the_frozen_baseline(frozen_task):
    from cn_contract.assistant import attachments
    database,actors,cid,_,matter_id,source_id,_ = frozen_task
    current = attachments.read_materials(actors['lawyer'],cid,database=database)
    newer = attachments.parse_attachment(actors['lawyer'],cid,source_id,
        d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope,
            baseline_view='accepted_view'),database=database)
    assert newer.parse.revision == 2
    prepared,_ = prepare(frozen_task)
    with database.session() as db:
        copied = read_version(matter_id,prepared.source_versions[source_id],actors['lawyer'],db)
        assert copied.baseline_view == 'original'
    assert prepared.manifest.events[0].media[0].parse_revision == 1


def test_nonempty_target_is_not_merged_implicitly(frozen_task):
    from cn_contract.documents.ingest import ingest,DOCX_MIME
    from cn_contract.task_drafts import bridge,service
    database,actors,_,execution,matter_id,_,raw = frozen_task
    with database.session() as db:
        existing = ingest(BytesIO(raw),d.UploadMeta(matter_id=matter_id,original_name='existing.docx',
            mime=DOCX_MIME,baseline_view='original',supersedes_id=None),actors['lawyer'],db=db)
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'],execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(),matter_id=matter_id),db=db)
        assert error.value.code == 'STATE_CONFLICT'
        assert db.scalars(text('SELECT id FROM document_versions')).all() == [str(existing.id)]
        assert service.read_execution(actors['lawyer'],execution.id,db).state == 'prepared'


def test_cancelled_preparation_does_not_resume_on_review(frozen_task):
    from cn_contract.task_drafts import bridge,service
    database,actors,_,execution,_,_,_ = frozen_task
    prepared,_ = prepare(frozen_task)
    value = review_input(frozen_task,prepared,confirm=True)
    with database.session() as db:
        service.cancel_execution(actors['lawyer'],execution.id,db)
        with pytest.raises(ServiceError) as error:
            bridge.review_execution(actors['lawyer'],execution.id,value,db=db)
        assert error.value.code == 'STATE_CONFLICT'
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 0


def test_concurrent_preparation_has_one_copy_and_one_result(frozen_task):
    from cn_contract.task_drafts import bridge
    database,actors,_,execution,matter_id,_,_ = frozen_task
    value = d.TaskExecutionPrepareInput(request_id=uuid4(),matter_id=matter_id)
    def call(_):
        with database.session() as db:
            return bridge.prepare_execution(actors['lawyer'],execution.id,value,db=db)
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(call,range(2)))
    assert values[0] == values[1]
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM task_executions')) == 1


def test_replayed_result_rejects_different_fact_version(frozen_task):
    from cn_contract.task_drafts import bridge
    database,actors,_,execution,_,_,_ = frozen_task
    prepared,_ = prepare(frozen_task)
    value = review_input(frozen_task,prepared,confirm=True)
    with database.session() as db:
        bridge.review_execution(actors['lawyer'],execution.id,value,db=db)
        changed = d.TaskExecutionReviewInput(request_id=value.request_id,review=d.ReviewStartInput(
            fact_version=value.review.fact_version+1,document_hashes=value.review.document_hashes))
        with pytest.raises(ServiceError) as error:
            bridge.review_execution(actors['lawyer'],execution.id,changed,db=db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 1


def second_attachment(frozen_task, *, local=False):
    from cn_contract.assistant import attachments
    from cn_contract.documents.ingest import DOCX_MIME
    database,actors,cid,_,_,_,raw = frozen_task
    if local:
        database._local_materials_enabled = True
    current = attachments.read_materials(actors['lawyer'],cid,database=database)
    uploaded = attachments.ingest_attachment(actors['lawyer'],cid,d.AssistantAttachmentInput(
        request_id=uuid4(),expected_scope=current.scope,original_name='second-synthetic.docx',mime=DOCX_MIME,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True,material_mode='local' if local else 'synthetic')),
        BytesIO(raw),database=database)
    current = attachments.read_materials(actors['lawyer'],cid,database=database)
    parsed = attachments.parse_attachment(actors['lawyer'],cid,uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope),database=database)
    return d.TaskMediaInput(media_id='second',name=uploaded.attachment.original_name,mime=uploaded.attachment.mime,
        status='ready',attachment_id=uploaded.attachment.id,sha256=uploaded.attachment.sha256,
        parse_revision=parsed.parse.revision)


def additional_frozen_task(frozen_task,media, *, inherit=False):
    from cn_contract.task_drafts import service
    database,actors,cid,original,_,_,_ = frozen_task
    with database.session() as db:
        binding = service.create_binding(actors['lawyer'],cid,db)
        receipt = service.receive_batch(actors['lawyer'],binding.id,
            d.TaskInboxBatchInput(expected_cursor=binding.cursor,next_cursor=binding.cursor+1,events=(
                d.TaskInboxEventInput(event_id='additional',text='新独立虚构审查',media=(media,),
                    task_id=original.draft_id if inherit else None,start_new=not inherit),)),db)
        draft = receipt.drafts[0]
        if inherit:
            draft = service.update_draft(actors['lawyer'],draft.id,d.TaskDraftUpdateInput(
                expected_revision=draft.revision,main_attachment_id=media.attachment_id),db)
        return service.freeze_draft(actors['lawyer'],draft.id,d.TaskFreezeInput(
            expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)


def test_local_policy_is_rejected_even_with_registered_synthetic_bytes(frozen_task):
    from cn_contract.task_drafts import bridge
    database,actors,_,_,matter_id,_,_ = frozen_task
    media = second_attachment(frozen_task,local=True)
    execution = additional_frozen_task(frozen_task,media)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'],execution.id,d.TaskExecutionPrepareInput(
                request_id=uuid4(),matter_id=matter_id),db=db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 0


def test_second_parse_failure_rolls_back_both_new_files(frozen_task,monkeypatch):
    from cn_contract.task_drafts import bridge,service
    from cn_contract.web import services
    database,actors,_,_,matter_id,_,_ = frozen_task
    media = second_attachment(frozen_task)
    execution = additional_frozen_task(frozen_task,media,inherit=True)
    original = services.candidate_parse
    seen = []
    def fail_second(*args,**kwargs):
        seen.append(args[1])
        if len(seen) == 2:
            raise ServiceError('FILE_UNSUPPORTED',400)
        return original(*args,**kwargs)
    monkeypatch.setattr(services,'candidate_parse',fail_second)
    with database.session() as db:
        with pytest.raises(ServiceError):
            bridge.prepare_execution(actors['lawyer'],execution.id,d.TaskExecutionPrepareInput(
                request_id=uuid4(),matter_id=matter_id),db=db)
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM fact_snapshots')) == 0
        assert service.read_execution(actors['lawyer'],execution.id,db).state == 'prepared'
    assert not list((database.storage_root/str(matter_id)).glob('*/original.bin'))


def test_frozen_matter_binding_cannot_target_another_accessible_matter(frozen_task):
    from cn_contract.task_drafts import bridge
    from cn_contract.matters import create_matter
    database,actors,cid,_,matter_id,_,_ = frozen_task
    media = second_attachment(frozen_task)
    with database.session() as db:
        db.execute(text("UPDATE assistant_conversations SET scope_kind='matter',scope_ref=:matter,"
            'binding_revision=binding_revision+1 WHERE id=:cid'),{'matter':str(matter_id),'cid':str(cid)})
        other = create_matter(d.MatterCreateInput(title='另一独立合成案件',contract_type='sales',review_mode='pre_sign',
            position='buyer',objectives=('核对虚构合同',)),actors['lawyer'],db)
    execution = additional_frozen_task(frozen_task,media)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'],execution.id,d.TaskExecutionPrepareInput(
                request_id=uuid4(),matter_id=other.id),db=db)
        assert error.value.code == 'CROSS_MATTER_DENIED'
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 0


@pytest.mark.parametrize('material',['unregistered','local'])
@pytest.mark.parametrize('entry',['candidate_parse','review'])
def test_native_internal_mock_guard_rejects_unapproved_cases(frozen_task,material,entry):
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    from cn_contract.documents.ingest import ingest,DOCX_MIME
    from cn_contract.matters import create_matter
    from cn_contract.review import proposals
    from cn_contract.web import services
    from test_assistant_attachments import sample
    database,actors,_,_,_,_,registered_raw = frozen_task
    proposals.configure(database,'assisted_draft',load_seed_policy())
    database._local_materials_enabled = True
    raw = sample('独立虚构未注册字节：不可沿 native 合成任务进入 Mock。') if material == 'unregistered' else registered_raw
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立拒绝边界',contract_type='sales',review_mode='pre_sign',
            position='buyer',objectives=('核对虚构合同',),material_mode='local' if material == 'local' else 'synthetic'),
            actors['lawyer'],db)
        version = ingest(BytesIO(raw),d.UploadMeta(matter_id=matter.id,original_name='guard-synthetic.docx',
            mime=DOCX_MIME,baseline_view='original',supersedes_id=None),actors['lawyer'],db=db)
        with pytest.raises(ServiceError) as error:
            if entry == 'candidate_parse':
                services.candidate_parse(matter.id,version.id,actors['lawyer'],db,synthetic_task=True)
            else:
                services.review(matter.id,d.ReviewStartInput(fact_version=1,document_hashes={version.id:version.sha256}),
                    actors['lawyer'],db,synthetic_task=True)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        assert proposals.is_assisted(db)
        assert db.scalar(text('SELECT COUNT(*) FROM parse_snapshots')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 0


def test_native_task_permission_does_not_enable_ordinary_assisted_review(frozen_task):
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    from cn_contract.review import proposals
    from cn_contract.web import services
    database,actors,_,_,matter_id,_,_ = frozen_task
    proposals.configure(database,'assisted_draft',load_seed_policy())
    prepared,_ = prepare(frozen_task)
    value = review_input(frozen_task,prepared,confirm=True)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            services.review(matter_id,value.review,actors['lawyer'],db)
        assert error.value.code == 'NOT_SUPPORTED'
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 0
        assert proposals.is_assisted(db)


def test_distinct_sources_with_same_hash_keep_two_version_links(frozen_task):
    from cn_contract.task_drafts import bridge
    database,actors,_,_,matter_id,first_id,_ = frozen_task
    second = second_attachment(frozen_task)
    execution = additional_frozen_task(frozen_task,second,inherit=True)
    request = d.TaskExecutionPrepareInput(request_id=uuid4(),matter_id=matter_id)
    with database.session() as db:
        prepared = bridge.prepare_execution(actors['lawyer'],execution.id,request,db=db)
        assert set(prepared.source_versions) == {first_id,second.attachment_id}
        assert len(set(prepared.source_versions.values())) == 2
        assert set(prepared.document_versions.values()) == {second.sha256}
        assert bridge.prepare_execution(actors['lawyer'],execution.id,request,db=db) == prepared
        assert db.scalar(text('SELECT COUNT(*) FROM document_versions')) == 2


def native_ready(frozen_task):
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    from cn_contract.review import proposals
    proposals.configure(frozen_task[0],'assisted_draft',load_seed_policy())
    prepared,_ = prepare(frozen_task)
    return prepared,review_input(frozen_task,prepared,confirm=True)


@pytest.mark.parametrize('tag',['no_id','malformed_id','unknown_id','not_running','wrong_provider'])
def test_native_manifest_rejects_config_labels_without_execution_permission(frozen_task,tag):
    from cn_contract.review import model_adapter,workflow
    from cn_contract.web import services
    database,actors,_,execution,matter_id,_,_ = frozen_task
    native_ready(frozen_task)
    config = workflow.prompt_configuration(model_adapter.model_configuration(model_adapter.MockProvider()))
    config['synthetic_task'] = True
    if tag != 'no_id':
        config['task_execution_id'] = {'malformed_id':'not-a-uuid','unknown_id':str(uuid4())}.get(tag,str(execution.id))
    if tag == 'wrong_provider':
        config['provider'] = 'untrusted-provider-label'
    with database.session() as db:
        context = services.context(matter_id,actors['lawyer'],db)
        with pytest.raises(ServiceError):
            workflow.current_manifest(context,actors['lawyer'],db,config)
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 0


def complete_native(frozen_task):
    from cn_contract.task_drafts import bridge
    database,actors,_,execution,_,_,_ = frozen_task
    _,value = native_ready(frozen_task)
    with database.session() as db:
        return bridge.review_execution(actors['lawyer'],execution.id,value,db=db)


def test_native_saved_run_reads_recheck_case_permission(frozen_task):
    from cn_contract.review import proposals
    from cn_contract.review.storage import read_run
    from cn_contract.security import remove_membership
    database,actors,_,execution,matter_id,_,_ = frozen_task
    completed = complete_native(frozen_task)
    with database.session() as db:
        saved = read_run(matter_id,completed.review_run_id,actors['lawyer'],db=db,current=True)
        assert saved.status == 'completed' and saved.manifest.model_provider == 'mock'
        assert str(execution.id) in db.scalar(text('SELECT config_json FROM review_runs WHERE id=:id'),
            {'id':str(completed.review_run_id)})
        assert proposals.is_assisted(db)
        remove_membership(matter_id,actors['lawyer'].user_id,db)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            read_run(matter_id,completed.review_run_id,actors['lawyer'],db=db,current=True)
        assert error.value.status_code == 403
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 1


@pytest.mark.parametrize('change',['registry','original'])
def test_native_saved_run_current_read_revalidates_source(frozen_task,monkeypatch,change):
    from cn_contract.ops import backup
    from cn_contract.review.storage import read_run
    database,actors,cid,_,matter_id,source_id,raw = frozen_task
    completed = complete_native(frozen_task)
    if change == 'registry':
        monkeypatch.setattr(backup,'_registered_hashes',lambda: frozenset())
    else:
        original = database.storage_root/'assistant'/str(cid)/str(source_id)/'original.bin'
        original.chmod(stat.S_IREAD | stat.S_IWRITE)
        original.write_bytes(raw+b'changed-after-native-completion')
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            read_run(matter_id,completed.review_run_id,actors['lawyer'],db=db,current=True)
        assert error.value.code == ('DATA_POLICY_UNAPPROVED' if change == 'registry' else 'VERSION_CONFLICT')
        assert db.scalar(text('SELECT COUNT(*) FROM review_runs')) == 1
