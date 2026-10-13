"""Current server snapshots, exact patch approvals and frozen draft bundles."""
import hashlib,json,re
from io import BytesIO
from uuid import UUID,uuid4
from sqlalchemy import select
from ..domain import Patch,ArtifactBundle,ExportArtifact
from ..persistence import ExportRow,configured_database,read_version
from ..security import ServiceError
from ..documents import local_materials
from ..review.storage import read_run,ReviewRunRow
from . import storage as s
from . import redline_adapter as redline
from .audience_filter import project,allow_original_copy,AUDIENCES
from .report_docx import build
from ..review.decisions import read_snapshot,read_history,finding_fingerprint,check_patch_disposition


def approve_patch(matter_id,run_id,patch,actor,*,db,audiences=('internal',),exception_authorization_id=None):
    s.authorize(actor,matter_id,db,write=True)
    from ..ops.storage import require_active
    require_active(db)
    run=read_run(matter_id,run_id,actor,db=db,current=True)
    if run.status!='completed':raise ServiceError('VERSION_CONFLICT',409)
    try:patch=Patch.model_validate_json(patch.model_dump_json())
    except Exception:raise ServiceError('VERSION_CONFLICT',409) from None
    if patch.status!='proposed' or patch.approved_by is not None or not audiences or len(set(audiences))!=len(audiences) or not set(audiences)<=set(AUDIENCES):
        raise ServiceError('VERSION_CONFLICT',409)
    if exception_authorization_id is not None:raise ServiceError('AUTHORIZATION_REQUIRED',403)
    finding=next((f for f in run.findings if f.id==patch.finding_id),None)
    if finding is None or patch.anchor_id not in (*finding.anchor_ids,*finding.cross_anchor_ids) or patch.document_version_id not in run.manifest.document_hashes:
        raise ServiceError('VERSION_CONFLICT',409)
    snapshot=read_snapshot(matter_id,run_id,actor,db=db)
    check_patch_disposition(snapshot,patch)
    run_row=db.get(ReviewRunRow,str(run.id))
    if finding.severity=='high':
        if run_row.actor_id==str(actor.user_id):raise ServiceError('UNRESOLVED_HARD_GATE',403)
        s.authorize(actor,matter_id,db,review=True)
    version=read_version(matter_id,patch.document_version_id,actor,db)
    if version.sha256!=run.manifest.document_hashes[version.id]:raise ServiceError('VERSION_CONFLICT',409)
    from ..persistence import read_original
    from ..documents.ingest import _parse
    parsed=_parse(read_original(matter_id,version.id,actor,db),version,configured_database(db).settings)
    if not any(anchor.id==patch.anchor_id and anchor.document_version_id==version.id for anchor in parsed.anchors):
        raise ServiceError('VERSION_CONFLICT',409)
    approved=Patch.model_validate({**patch.model_dump(mode='python'),'status':'approved','approved_by':actor.user_id})
    with db.begin_nested():
        if s.latest('patch_approval',patch.id,db):raise ServiceError('VERSION_CONFLICT',409)
        record=s.append('patch_approval',patch.id,{'run_id':str(run.id),'run_sha256':s.sha(run.model_dump(mode='json')),
            'patch':approved.model_dump(mode='json'),'audiences':list(audiences),'approval_session_id':str(actor.session_id),
            'finding_decision_sha256':finding_fingerprint(snapshot,patch.finding_id),'synthetic':not local_materials.is_local(matter_id,db)},actor,matter_id,db)
        s.audit(actor,matter_id,'patch_approved','EXACT_DRAFT_PATCH_APPROVAL',db,entity_id=patch.id,after_hash=record.sha256)
    return approved


def revoke_patch(matter_id,patch_id,actor,*,db):
    s.authorize(actor,matter_id,db,write=True)
    row=s.latest('patch_approval',patch_id,db)
    if not row or row.matter_id!=str(matter_id):raise ServiceError('CROSS_MATTER_DENIED',403)
    with db.begin_nested():
        record=s.append('patch_revocation',row.ref,{'revoked':True},actor,matter_id,db)
        s.audit(actor,matter_id,'patch_revoked','DRAFT_PATCH_REVOKED',db,entity_id=patch_id,after_hash=record.sha256)


def _artifact(raw,kind,run,audience,actor,db):
    identifier=uuid4();digest=hashlib.sha256(raw).hexdigest();path=s.store_bytes(raw,identifier,db)
    artifact=ExportArtifact(id=identifier,matter_id=run.matter_id,run_id=run.id,audience=audience,type=kind,
        content_sha256=digest,storage_ref=path,mode='draft',approval_id=None,created_at=s.now(),superseded=False)
    db.add(ExportRow(id=str(identifier),matter_id=str(run.matter_id),approval_id=None,superseded=False,payload=artifact.model_dump_json()))
    db.flush();return artifact


def _manual(anchor,patch,reason):
    return {'location':anchor.part_name+':'+anchor.element_id,'status':'manual_required','reason':reason,
            'old':patch.old_text,'new':patch.new_text,'explanation':patch.reason}


def _page_ranges(pages):
    ranges=[]
    for page in sorted(set(pages)):
        if ranges and page==ranges[-1][1]+1:ranges[-1][1]=page
        else:ranges.append([page,page])
    return '、'.join(str(start) if start==end else f'{start}–{end}' for start,end in ranges)


def _client_scope_labels(values):
    # Display known inventories only; unknown diagnostics remain verbatim.
    patterns=(
        (r'page:([1-9][0-9]*)', '第{}页'),
        (r'page:([1-9][0-9]*):read', '已提取文字：第{}页'),
        (r'page:([1-9][0-9]*):manual', '需人工核对：第{}页'),
        (r'page:([1-9][0-9]*):unsupported', '自动解析未取得可用文字：第{}页'),
        (r'OCR_NOT_DEPLOYED:page:([1-9][0-9]*)', '自动解析未取得文字：第{}页（按页识别和人工来源核对另行记录）'),
    )
    groups={};items=[]
    for value in values:
        for pattern,label in patterns:
            match=re.fullmatch(pattern,value)
            if match:
                if label not in groups:
                    groups[label]=[];items.append((label,True))
                groups[label].append(int(match[1]))
                break
        else:items.append((value,False))
    return '；'.join(label.format(_page_ranges(groups[label])) if grouped else label for label,grouped in items)


def _scope(run,actor,db,*,audience='internal'):
    from ..persistence import read_matter,read_original
    from ..documents.ingest import _parse
    matter=read_matter(run.matter_id,actor,db)
    plugin_source=False
    if run.manifest.model_provider=='assisted_manual':
        from ..review.proposals import read_proposal
        plugin_source=read_proposal(run.matter_id,run.id,actor,db).execution_receipt.source=='local_plugin_unverified'
    scope=['本次审查记录：'+str(run.id)+'；完成时间（UTC）：'+str(run.finished_at),
        '事实快照：'+run.manifest.fact_snapshot_sha256,'法律规则快照：'+run.manifest.rules_sha256,
        '客户政策快照：'+run.manifest.policy_sha256,
        ('本次采用本机人工候选；真实模型未运行，真实模型调用0；' if local_materials.is_local(run.matter_id,db) else
         '本次采用本机插件候选；模型身份与推理来源未核验，工作台远程模型调用0；' if plugin_source else
         '本次采用离线人工/合成候选；真实模型推理NOT_RUN，真实模型调用0；' if run.manifest.model_provider=='assisted_manual'
         else '本次仅采用本地模拟模型；')+'未关联企业查询收据，未采用任何原始企业查询材料。未查询不能解释为无风险。']
    if audience=='client':scope=[scope[0],scope[-1]]
    labels=_client_scope_labels if audience=='client' else '、'.join
    for identifier,digest in run.manifest.document_hashes.items():
        version=read_version(run.matter_id,identifier,actor,db)
        parsed=_parse(read_original(run.matter_id,identifier,actor,db),version,configured_database(db).settings)
        scope.extend(['读取文件：'+version.original_name+'；SHA256：'+digest+'；基线：'+version.baseline_view.value,
          '读取部件：'+(labels(parsed.parts) or '无可读部件')+'；结构锚点：'+str(len(parsed.anchors)),
          '页码范围：'+((_page_ranges(parsed.pages) if audience=='client' else '、'.join(map(str,parsed.pages))) if parsed.pages else 'DOCX未进行分页定位，页码须原生Word复核'),
          '未支持或未读项：'+(labels(parsed.unsupported_parts) or '结构解析未报告未支持部件；这不代表所有材料均获法律核验'),
          '解析质量限制：'+(labels(parsed.quality_issues) or '未报告结构质量问题')])
    internal=['本案确认立场：'+(matter.position.value if matter.position else '待确认'),
        *['本案内部目标与底线：'+item for item in matter.objectives],
        '复核任务：核对保证附件、补充材料及全部未完成维度；模拟建议尚未成为合同变更。']
    from ..rules.loader import read_policy,policy_is_approved
    if matter.active_policy_version:
        policy=read_policy(matter.active_policy_version,actor,matter_id=matter.id,db=db)
        if policy_is_approved(policy,matter.id,db):internal.extend('已批准内部客户政策：'+item for item in policy.preferences)
    return scope,internal


def prepare_exports(run,audience,patches,actor,*,db):
    run=s.load_run(run,actor,db)
    candidate_source=None
    if run.manifest.model_provider=='assisted_manual':
        from ..review.proposals import read_proposal
        candidate_source=read_proposal(run.matter_id,run.id,actor,db).execution_receipt.source
    snapshot=read_snapshot(run.matter_id,run.id,actor,db=db)
    _,history=read_history(run.matter_id,run.id,actor,db=db)
    if audience not in AUDIENCES:raise ServiceError('NOT_SUPPORTED',422)
    if len({p.id for p in patches})!=len(patches) or len({(p.document_version_id,p.anchor_id) for p in patches})!=len(patches):
        raise ServiceError('VERSION_CONFLICT',409)
    patches=list(patches);manual=[];changes={};baseline={};approvals=[]
    for patch in patches:
        checked,patch_run,row=s.load_patch(run.matter_id,patch,actor,db,audience=audience)
        if patch_run.id!=run.id:raise ServiceError('VERSION_CONFLICT',409)
        version=read_version(run.matter_id,patch.document_version_id,actor,db)
        data,anchor,reason=redline.preconditions(version,patch,actor,db,audience=audience)
        approvals.append({'ref':row.ref,'sha256':row.sha256,'patch_id':str(patch.id)})
        if reason:manual.append(_manual(anchor,patch,reason))
        elif not allow_original_copy(audience):
            manual.append(_manual(anchor,patch,'对外草案仅生成新文件 原件全包内容尚无独立对外范围核验 请按已批准文字人工修改'))
        else:
            baseline[version.id]=data;changes.setdefault(version.id,[]).append((checked,anchor))
    scope,internal=_scope(run,actor,db,audience=audience)
    with db.begin_nested():
        artifacts=[];applied={}
        for version_id,values in changes.items():
            try:raw=redline.build_redline(baseline[version_id],values,configured_database(db).settings,local_material=candidate_source=='manual_local')
            except ServiceError as error:
                if error.code!='NOT_SUPPORTED':raise
                manual.extend(_manual(anchor,patch,'已有页眉页脚需要人工保真处理') for patch,anchor in values)
            else:
                artifact=_artifact(raw,'redline_contract_docx',run,audience,actor,db)
                artifacts.append(artifact);applied[version_id]=(artifact,{p.id for p,a in values})
        report=_artifact(build(project(run,audience,patches,manual,scope=scope,internal=internal,
            snapshot=snapshot,decision_history=history,candidate_source=candidate_source)),'review_report_docx',run,audience,actor,db)
        artifacts.insert(0,report)
        identifier=uuid4()
        metadata={'run_sha256':s.sha(run.model_dump(mode='json')),'patch_set_sha256':s.sha(approvals),
            'patch_approvals':approvals,'manual':manual,'synthetic':candidate_source!='manual_local','mode':'draft',
            'decision_snapshot_sha256':snapshot.sha256,'decision_snapshot_version':snapshot.version,
            'projection_version':2}
        bundle=ArtifactBundle(id=identifier,matter_id=run.matter_id,run_id=run.id,audience=audience,artifacts=tuple(artifacts),manifest_sha256='0'*64)
        digest=s.sha({'bundle':bundle.model_dump(mode='json',exclude={'manifest_sha256'}),'metadata':metadata})
        bundle=bundle.model_copy(update={'manifest_sha256':digest})
        s.append('decision_snapshot',identifier,snapshot.model_dump(mode='json'),actor,run.matter_id,db)
        s.append('bundle',identifier,{'bundle':bundle.model_dump(mode='json'),'metadata':metadata},actor,run.matter_id,db)
        from .effective_text import save_effective_text
        save_effective_text(bundle,run,snapshot,patches,applied,manual,actor,db)
        s.audit(actor,run.matter_id,'export_prepared','DRAFT_EXPORT_PREPARED',db,entity_id=identifier,after_hash=bundle.manifest_sha256)
        # End check before any generated bytes can become committed candidate.
        s.load_run(run,actor,db)
        if read_snapshot(run.matter_id,run.id,actor,db=db).sha256!=snapshot.sha256:
            raise ServiceError('APPROVAL_STALE',409)
        for patch in patches:s.load_patch(run.matter_id,patch,actor,db,audience=audience)
    return bundle


def _bundle(bundle_id,actor,db):
    row=s.latest('bundle',bundle_id,db)
    if not row:raise ServiceError('CROSS_MATTER_DENIED',403)
    s.authorize(actor,UUID(row.matter_id),db)
    from ..ops.storage import require_active
    require_active(db)
    value=json.loads(row.payload);bundle=ArtifactBundle.model_validate(value['bundle'])
    digest=s.sha({'bundle':bundle.model_dump(mode='json',exclude={'manifest_sha256'}),'metadata':value['metadata']})
    if digest!=bundle.manifest_sha256:raise ServiceError('VERSION_CONFLICT',409)
    actual=read_run(bundle.matter_id,bundle.run_id,actor,db=db,current=True)
    if s.sha(actual.model_dump(mode='json'))!=value['metadata']['run_sha256']:raise ServiceError('APPROVAL_STALE',409)
    snapshot=read_snapshot(bundle.matter_id,bundle.run_id,actor,db=db)
    saved_hash=value['metadata'].get('decision_snapshot_sha256')
    if (saved_hash is None and snapshot.version!=0) or (saved_hash is not None and saved_hash!=snapshot.sha256):
        raise ServiceError('APPROVAL_STALE',409)
    if saved_hash is not None:
        frozen=s.latest('decision_snapshot',bundle_id,db)
        from ..domain import ReviewDecisionSnapshot
        if not frozen or frozen.matter_id!=str(bundle.matter_id):raise ServiceError('APPROVAL_STALE',409)
        try:stored=ReviewDecisionSnapshot.model_validate_json(frozen.payload)
        except ValueError:raise ServiceError('APPROVAL_STALE',409) from None
        if stored!=snapshot:raise ServiceError('APPROVAL_STALE',409)
    for approval in value['metadata']['patch_approvals']:
        patch_row=s.latest('patch_approval',approval['patch_id'],db)
        if not patch_row or patch_row.ref!=approval['ref'] or patch_row.sha256!=approval['sha256']:
            raise ServiceError('APPROVAL_STALE',409)
        patch=Patch.model_validate(json.loads(patch_row.payload)['patch'])
        s.load_patch(bundle.matter_id,patch,actor,db,audience=bundle.audience,write=False)
    for artifact in bundle.artifacts:s.checked_bytes(artifact.storage_ref,artifact.content_sha256,db)
    return bundle,actual


def read_bundle(bundle_id,actor,*,db):
    from ..ops.storage import require_active
    require_active(db)
    return _bundle(bundle_id,actor,db)[0]


def approve_bundle(bundle_id,expected_hash,actor,*,db,exception_authorization_id=None):
    bundle,run=_bundle(bundle_id,actor,db)
    s.authorize(actor,bundle.matter_id,db,sign=True)
    if expected_hash!=bundle.manifest_sha256:raise ServiceError('VERSION_CONFLICT',409)
    if exception_authorization_id is not None:raise ServiceError('AUTHORIZATION_REQUIRED',403)
    # No real non-mock provider/data-policy/law-source approval exists in T09.
    # Changing a DTO/provider string or seeding an Approval cannot satisfy it.
    error=ServiceError('BLOCKED_LIVE',403)
    s.audit(actor,bundle.matter_id,'authorization_denied',error.code,db,correlation=error.correlation_id)
    raise error


def require_current_artifact(artifact,db):
    """Call only after _bundle authorization/content checks in the same transaction."""
    row=db.get(ExportRow,str(artifact.id),populate_existing=True)
    if (not row or row.matter_id!=str(artifact.matter_id) or row.superseded or row.approval_id is not None
            or artifact.mode!='draft' or ExportArtifact.model_validate_json(row.payload)!=artifact):
        raise ServiceError('APPROVAL_STALE',409)


def download_artifact(artifact_id,actor,*,db):
    s.require_storage(db)
    row=db.get(ExportRow,str(artifact_id),populate_existing=True)
    if not row:raise ServiceError('CROSS_MATTER_DENIED',403)
    s.authorize(actor,UUID(row.matter_id),db)
    actual=ExportArtifact.model_validate_json(row.payload)
    bundle_row=None
    for record in db.scalars(select(s.ExportRecordRow).where(s.ExportRecordRow.kind=='bundle',s.ExportRecordRow.matter_id==row.matter_id)):
        data=json.loads(record.payload)
        if str(artifact_id) in {a['id'] for a in data['bundle']['artifacts']}:
            bundle_row=record;break
    if bundle_row is None:raise ServiceError('CROSS_MATTER_DENIED',403)
    bundle,_=_bundle(UUID(bundle_row.parent),actor,db)
    stored=next(a for a in bundle.artifacts if a.id==actual.id)
    require_current_artifact(stored,db)
    return BytesIO(s.checked_bytes(actual.storage_ref,actual.content_sha256,db))
