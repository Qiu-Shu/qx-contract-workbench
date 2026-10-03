"""Current server evidence -> bounded operations -> immutable engineering run."""
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID,uuid4
from sqlalchemy import select

from ..config import PROJECT_ROOT
from ..domain import (CoverageId,CoverageItem,Finding,ModelRequest,ModelUsageLimit,ReviewContext,
    ReviewRun,RunManifest,FactSnapshot,SafeExpression,VariableExpression,BinaryExpression,CalculationInput,RoundingSpec)
from ..persistence import (DocumentRow,configured_database,read_matter,read_version,get_parse_result,
    get_fact_snapshot,fact_snapshot_sha256,review_status_changed)
from ..security import authorize,ServiceError
from ..facts.storage import trusted_parse
from ..facts.extract import build_fact_candidates
from ..facts.calculate import calculate_expression
from ..rules.loader import read_rule_snapshot,read_policy,policy_runtime_sha256
from ..rules.evaluator import select_rules,confirmed_field
from ..authorities.registry import read_authority
from .model_adapter import (require_provider,model_configuration,dispatch,last_attempt,RawOutputError,candidates)
from .storage import require_storage,_save,_save_operation_record

SCOPE=tuple(CoverageId)
LIMITATIONS=('虚构演示，非正式意见','mock不能正式签发；QCC关闭，外部调用为0',
    'BLOCKED_RULE_APPROVAL：现实法律规则及法源尚未批准，法律样本验收/真实试点/生产均未完成',
    '仅材料缺口、数学关系和义务方向观察；其他维度须律师补充材料与专项审阅')


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def prompt_configuration(model_config):
    return {**model_config,'prompts':{name:hashlib.sha256((PROJECT_ROOT/'prompts'/name).read_bytes()).hexdigest()
        for name in ('intake.md','review_system.md','cross_clause.md')},'chunk_anchors':32,'engine':'T06-limited-v1'}


def current_manifest(context,actor,db,config,*,allow_finished=False):
    authorize(actor,context.matter.id,'review' if not allow_finished else 'read',db)
    context=ReviewContext.model_validate_json(context.model_dump_json())
    matter=read_matter(context.matter.id,actor,db)
    statuses={'ready_for_review','awaiting_lawyer','failed'} if allow_finished else {'ready_for_review'}
    if matter.status not in statuses: raise ServiceError('STATE_CONFLICT',409)
    if context.matter.model_dump(exclude={'status'})!=matter.model_dump(exclude={'status'}):
        raise ServiceError('VERSION_CONFLICT',409)
    if not allow_finished and context.matter.status!=matter.status: raise ServiceError('VERSION_CONFLICT',409)
    if context.allowed_scope!=SCOPE: raise ServiceError('VERSION_CONFLICT',409)
    if config.get('prompts')!=prompt_configuration(config)['prompts']:
        raise ServiceError('VERSION_CONFLICT',409)
    current_ids=set(db.scalars(select(DocumentRow.id).where(DocumentRow.matter_id==str(matter.id))))
    superseded=set(db.scalars(select(DocumentRow.supersedes_id).where(DocumentRow.matter_id==str(matter.id),DocumentRow.supersedes_id.is_not(None))))
    current_ids-=superseded
    if not current_ids or {str(v.id) for v in context.document_versions}!=current_ids or len(current_ids)!=len(context.document_versions):
        raise ServiceError('VERSION_CONFLICT',409)
    anchors={};parses=[]
    for supplied in context.document_versions:
        actual=read_version(matter.id,supplied.id,actor,db)
        if supplied!=actual: raise ServiceError('VERSION_CONFLICT',409)
        parsed=get_parse_result(matter.id,actual.id,actor,db)
        if parsed is None: raise ServiceError('FACTS_UNCONFIRMED',409)
        parsed=trusted_parse(matter.id,actual.id,actor,db,parsed)
        parses.append(parsed)
        anchors.update({a.id:a for a in parsed.anchors})
    if matter.active_fact_version is None: raise ServiceError('FACTS_UNCONFIRMED',409)
    facts=get_fact_snapshot(matter.id,matter.active_fact_version,actor,db)
    if facts!=context.fact_snapshot or facts.sha256!=fact_snapshot_sha256(facts.facts): raise ServiceError('VERSION_CONFLICT',409)
    if not facts.facts or any(f.confirmation_status not in ('confirmed','corrected','rejected') for f in facts.facts):
        raise ServiceError('FACTS_UNCONFIRMED',409)
    for f in facts.facts:
        if f.confirmation_status=='rejected': continue
        if f.confirmed_at>datetime.now(timezone.utc): raise ServiceError('FACTS_UNCONFIRMED',409)
        if f.provenance_type=='external' or f.receipt_ids: raise ServiceError('NOT_SUPPORTED',409)
        if not set(f.anchor_ids).issubset(anchors) or f.provenance_type=='document' and not f.anchor_ids:
            raise ServiceError('VERSION_CONFLICT',409)
    snapshot=read_rule_snapshot(actor,matter_id=matter.id,db=db)
    policy=read_policy(matter.active_policy_version,actor,matter_id=matter.id,db=db)
    actual_context=ReviewContext(**{**context.model_dump(mode='python'),'matter':matter})
    selection=select_rules(actual_context,snapshot,actor=actor,db=db)
    policy_hash=policy_runtime_sha256(policy,actor,matter_id=matter.id,db=db)
    manifest=RunManifest(contract_type=matter.contract_type,document_hashes={v.id:v.sha256 for v in context.document_versions},
        fact_snapshot_sha256=facts.sha256,rules_sha256=snapshot.sha256,policy_sha256=policy_hash,
        model_config_sha256=_hash(config),config_sha256=configured_database(db).settings.config_sha256,model_provider='mock')
    return manifest,anchors,tuple(parses),selection,actual_context


def _project(context,selection):
    # Draft rules and their authority IDs never enter a model context.
    rules=selection.applied
    return ReviewContext(**{**context.model_dump(mode='python'),'rules':rules,
        'authority_ids':tuple(dict.fromkeys(a for r in rules for a in r.authority_ids))})


def _package(anchors):
    return {'anchors':[{'id':str(a.id),'document_version_id':str(a.document_version_id),
        'part_name':a.part_name,'element_id':a.element_id,'quote':a.quote,'quote_sha256':a.quote_sha256} for a in anchors]}


def _request(operation,context,package,limit,repair):
    # x-input is a technical, immutable structural bundle; not a business DTO.
    prompt_name={'extract_facts':'intake.md','review_chunk':'review_system.md','review_cross_clauses':'cross_clause.md'}[operation]
    schema={'type':'object','additionalProperties':False,'required':['examined_anchor_ids','facts','observations'],
        'properties':{'examined_anchor_ids':{'type':'array'},'facts':{'type':'array'},'observations':{'type':'array'}},
        'x-input':package,'x-repair':repair,'x-system':(PROJECT_ROOT/'prompts'/prompt_name).read_text(encoding='utf-8')}
    return ModelRequest(operation=operation,context=context,schema=schema,budget_approval_id=None,usage_limit=limit)


def _payload(payload,package,operation):
    expected={'examined_anchor_ids':[a['id'] for a in package['anchors']],
        'facts':candidates(package) if operation=='extract_facts' else [],'observations':[]}
    # Local mock proposes only a fixed controlled envelope. Arbitrary prose,
    # approvals, IDs or legal claims are rejected rather than certified by IDs.
    if dict(payload)!=expected: raise ValueError('unsupported model payload')
    return expected


def _operation(operation,context,package,model,limit,usages,attempts):
    for repair in (False,True):
        request=_request(operation,context,package,limit,repair)
        input_count=len(request.model_dump_json().encode())
        if (sum(u.input_tokens for u in usages)+input_count>limit.max_input_tokens
            or sum(u.output_tokens for u in usages)>=limit.max_output_tokens
            or sum((u.cost for u in usages),Decimal('0'))>limit.max_cost):
            return None,'BUDGET_EXCEEDED'
        invalid=False
        try:
            response=dispatch(model,request)
        except RawOutputError:
            invalid=True;response=None
        raw,usage,status=last_attempt(model)
        usages.append(usage)
        attempts.append({'raw_ref':str(uuid4()),'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'operation':operation,'repair':repair,'input_sha256':hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
            'anchor_ids':[a['id'] for a in package['anchors']],'usage':usage.model_dump(mode='json'),
            'status':status,'valid':False,'_raw':raw})
        if status=='sent_unknown': return None,'QUERY_STATE_UNKNOWN'
        if status!='success': return None,'MODEL_OUTPUT_INVALID'
        if (sum(u.output_tokens for u in usages)>limit.max_output_tokens
            or sum((u.cost for u in usages),Decimal('0'))>limit.max_cost): return None,'BUDGET_EXCEEDED'
        if not invalid:
            try:
                payload=_payload(response.payload,package,operation)
                attempts[-1]['valid']=True
                return payload,None
            except ValueError:
                pass
    return None,'MODEL_OUTPUT_INVALID'


def _suggestion(context):
    position=context.position.value
    if context.matter.review_mode=='post_sign':
        return f'当前客户立场：{position}；核查履行与已发生事项，保存证据；必要时协商补充措施，未经双方确认不能改变已签合同。'
    if any('无谈判空间' in objective or '不得建议修改' in objective for objective in context.matter.objectives):
        return f'当前客户立场：{position}；在现有条款下核对履行可行性、接受或拒绝风险及可取得的补充证据；由律师决定，不自动认定安全可签。'
    direction={
        'buyer':'核对付款条件与对方交付证据','seller':'核对自身交付义务与对方付款安排',
        'customer':'核对服务验收、可用性与付款条件','provider':'核对服务边界、自身履行条件与收款安排',
        'lessor':'核对交付条件、对方使用义务与租金证据','lessee':'核对场地交付、持续使用条件与支付证据',
        'discloser':'核对接收方用途约束与披露授权','recipient':'核对接收用途、保密和返还证据',
        'mutual':'分别核对双方披露、接收与保密义务'}
    action=direction.get(position,'分别核对双方义务及客户目标')
    return f'当前客户立场：{position}；{action}，协商明确条款；由律师复核后决定谈判修改方案。'


def controlled_findings(context,anchors,processed,run_id,*,actor=None,db=None):
    findings=[]
    chosen=[a for a in anchors.values() if a.id in processed]
    def add(kind,dims,refs,analysis,effect,state='unconfirmed',severity='info'):
        refs=tuple(dict.fromkeys(refs))
        if not refs: return
        findings.append(Finding(id=uuid4(),run_id=run_id,coverage_ids=dims,issue_type=kind,severity=severity,
            evidence_state=state,anchor_ids=refs[:1],cross_anchor_ids=refs[1:],rule_ids=(),authority_ids=(),
            analysis=analysis,business_effect=effect,recommendation=_suggestion(context),
            replacement_text=None,fallback='需律师核实，工程观察不构成效力结论。',human_decision=None))
    names=[Path(v.original_name).stem for v in context.document_versions]
    for a in chosen:
        if re.search(r'忽略.{0,8}规则|执行\s*shell|API\s*Key|上传其他案件',a.quote,re.I):
            add('untrusted_instruction',('C18',),(a.id,),'原文包含要求越权操作的文字，已作为不可信数据处理。','不改变审查权限、预算或案件范围。')
        refs=re.findall(r'附件《([^》]+)》',a.quote)
        missing=[name for name in refs if name not in names]
        if not refs: missing.extend(re.findall(r'\bSOW\b|\bDPA\b|报价单|技术附件',a.quote))
        if missing:
            add('missing_appendix',('C05','C06','C09','C15','C18'),(a.id,),
                '缺件清单：'+ '、'.join(dict.fromkeys(missing))+'；尚无可核对的对应原件，范围、金额与附件优先级待确认。','无法核验附件中的交付、价格、验收或数据安排。','missing','medium')
        for clause in re.split(r'[；。;\n]',a.quote):
            for match in re.finditer(r'不续约|涨价|安全事件|工作小时|退出费',clause):
                action=match.group()
                if action in ('不续约','涨价'):
                    # Only a narrow explicit subject immediately governing the
                    # action licenses attribution; keywords alone do not.
                    prefix=clause[:match.start()].strip()
                    subject_match=re.fullmatch(r'(客户|供应商)(?:决定|有权|应|须|需|拟|选择|将|可|可以)?',prefix)
                    subject=subject_match.group(1) if subject_match else None
                    statement=(f'原文明示{subject}{action}，通知属于{subject}义务；提前期对客户的影响须结合立场和履行安排判断。'
                        if subject else f'原文涉及{action}，义务主体待确认；不能按事项关键词推定客户或供应商承担通知义务。')
                    periods=re.findall(r'[0-9]+\s*(?:个)?(?:工作小时|自然小时|小时|天|日|月|年)',clause[match.end():])
                    if periods: statement+=' 原文期间：'+ '、'.join(periods)+'；起算方式待核实。'
                elif action=='工作小时': statement='原文使用工作小时，不能换成自然小时；通知对象和起算方式待核实。'
                elif action=='退出费': statement='原文涉及退出费用，解除权与通知和费用需一并核对，不能仅因此声称没有解除权。'
                else: statement='安全事件通知对象、起算方式和时点待核实，不能推导未批准的法定期限。'
                add('obligation_direction',('C13','C16'),(a.id,),statement+' 当前客户立场：'+context.position.value+'。','仅描述义务方向及执行安排，风险等级和法律效力待律师判断。')
        if '保证' in a.quote:
            add('guarantee_material',('C10',),(a.id,),'原文存在保证表述；保证方式、主体与签署证据待核实。','无法仅据用词确认保证责任或默认连带方式。')
    facts=context.fact_snapshot.facts
    ratios=[f for f in facts if f.field.startswith('payment_ratio_') and f.confirmation_status in ('confirmed','corrected')]
    if ratios and all(f.typed_value.kind=='decimal' and f.unit=='percent' for f in ratios):
        refs=[a for f in ratios for a in f.anchor_ids]
        if set(refs).issubset(processed):
            try:
                if len(ratios)>32: raise ValueError('bounded ratio AST depth')
                if len({f.field for f in ratios})!=len(ratios): raise ValueError('ambiguous ratio facts')
                ast=VariableExpression(kind='variable',name='v0')
                for i in range(1,len(ratios)):
                    ast=BinaryExpression(kind='binary',operator='add',left=ast,right=VariableExpression(kind='variable',name='v'+str(i)))
                quantum=Decimal((0,(1,),min(f.typed_value.value.as_tuple().exponent for f in ratios)))
                calculation=calculate_expression(SafeExpression(ast=ast,unit='percent'),
                    {'v'+str(i):f.typed_value.value for i,f in enumerate(ratios)},
                    inputs=tuple(CalculationInput(name='v'+str(i),value=f.typed_value.value,unit='percent',fact_ids=(f.id,)) for i,f in enumerate(ratios)),
                    rounding=RoundingSpec(mode='ROUND_HALF_EVEN',quantum=quantum),matter_id=context.matter.id,
                    fact_version=context.fact_snapshot.version,actor=actor,db=db)
                total=calculation.value
                if total!=Decimal('100'):
                    add('payment_ratio_sum',('C06','C18'),refs,f'已确认付款比例合计{total}%，与100%不一致。',
                        '需核对重复付款、遗漏阶段与总价口径；此为数学观察。','conflicting','medium')
            except ValueError:
                add('payment_math_insufficient',('C06','C18'),refs,'付款比例存在数值资源或事实冲突边界，数学证据不足；请人工核验。',
                    '未计算或未确认精确合计，不能据此认定100%。','missing','medium')
    first=confirmed_field(facts,'total_price');second=confirmed_field(facts,'addendum_price')
    if first and second and first.typed_value.kind==second.typed_value.kind=='decimal' and first.unit==second.unit=='CNY':
        refs=(*first.anchor_ids,*second.anchor_ids)
        if first.typed_value.value!=second.typed_value.value and set(refs).issubset(processed):
            add('amount_conflict',('C06','C18'),refs,'已确认正文与附件金额不同，适用优先级待确认。','付款与履行金额口径冲突。','conflicting','medium')
    for kind,terms,dims,text in (
        ('confidentiality_training',('保密','训练'),('C15','C18'),'原文同时存在保密义务与训练授权；须核对授权范围与保密义务的关系。'),
        ('license_termination',('成果','许可','终止'),('C13','C14','C18'),'原文同时涉及成果许可与终止；已付款成果继续使用、迁移与交接安排待核实。')):
        matches=[a for a in chosen if any(term in a.quote for term in terms)]
        if all(any(term in a.quote for a in matches) for term in terms):
            add(kind,dims,[a.id for a in matches],text,'关系观察需结合完整证据和客户目标由律师判断。')
    merged={}
    for finding in findings:
        key=(finding.issue_type,finding.coverage_ids,finding.analysis,finding.business_effect,
            finding.recommendation,finding.evidence_state,finding.severity)
        if key not in merged:
            merged[key]=finding
        else:
            previous=merged[key]
            refs=tuple(dict.fromkeys((*previous.anchor_ids,*previous.cross_anchor_ids,*finding.anchor_ids,*finding.cross_anchor_ids)))
            merged[key]=Finding(**{**previous.model_dump(mode='python'),'anchor_ids':refs[:1],'cross_anchor_ids':refs[1:]})
    return tuple(merged.values())


def coverage_for(context,findings,processed,parses,*,failed=False):
    out=[]
    specialist=context.matter.contract_type=='unknown' or context.matter.jurisdiction!='CN-mainland'
    labor=confirmed_field(context.fact_snapshot.facts,'labor_relationship')
    labor=bool(labor and labor.typed_value.kind=='bool' and labor.typed_value.value)
    gaps=any(p.unsupported_parts or p.quality_issues for p in parses)
    for dimension in SCOPE:
        linked=[f for f in findings if dimension in f.coverage_ids]
        status='insufficient_material'
        reason='没有获批法律规则及足够核验材料；不得据此认定无风险。'
        if specialist or labor and dimension in ('C11','C12','C13'):
            status='unsupported';reason='类型/法域或劳动专项须转交专项审阅。'
        elif linked and not failed and not gaps:
            status='insufficient_material' if any(f.evidence_state=='missing' for f in linked) else 'reviewed_issue'
            reason='仅工程观察或明确缺件；不构成法律效力结论。'
        if gaps: reason='存在未读部件或解析质量缺口，不能声明全文已审查。'
        if failed: reason='受控模型步骤失败或预算不足；仅记录实际已处理位置。'
        out.append(CoverageItem(coverage_id=dimension,status=status,examined_anchor_ids=tuple(processed),
            rule_ids=(),rationale=reason,finding_ids=tuple(f.id for f in linked)))
    return tuple(out)


def run_review(context,model,*,actor,db,usage_limit=None,require_legal_rules=False):
    require_storage(db);require_provider(model)
    config=prompt_configuration(model_configuration(model))
    manifest,anchors,parses,selection,actual=current_manifest(context,actor,db,config)
    projected=_project(actual,selection)
    for aid in projected.authority_ids: read_authority(aid,actor,matter_id=actual.matter.id,db=db)
    limit=usage_limit or ModelUsageLimit(max_input_tokens=10000000,max_output_tokens=10000000,max_cost='0',unit='mock_credit')
    limit=ModelUsageLimit.model_validate_json(limit.model_dump_json())
    if limit.unit!='mock_credit': raise ServiceError('PRICE_UNKNOWN',409)
    started=datetime.now(timezone.utc);usages=[];attempts=[];processed=[];error=None
    if require_legal_rules: error='RULE_UNAPPROVED'
    all_anchors=list(anchors.values())
    if not error:
        for start in range(0,len(all_anchors),32):
            chunk=all_anchors[start:start+32]
            package=_package(chunk)
            for operation in ('extract_facts','review_chunk'):
                _,error=_operation(operation,projected,package,model,limit,usages,attempts)
                if error: break
            if error: break
            processed.extend(a.id for a in chunk)
        if not error:
            _,error=_operation('review_cross_clauses',projected,_package(all_anchors),model,limit,usages,attempts)
    # Independent end re-read includes sessions, rule/source approvals and full parses.
    try:
        end_manifest,_,_,_,_=current_manifest(context,actor,db,config)
        if end_manifest!=manifest: raise ServiceError('VERSION_CONFLICT',409)
    except ServiceError as exc:
        _save_operation_record(actual.matter.id,actor,'review_rejected',attempts,exc.code,config,db)
        raise
    run_id=uuid4()
    findings=controlled_findings(actual,anchors,set(processed),run_id,actor=actor,db=db)
    limitations=list(LIMITATIONS)
    if any(p.unsupported_parts or p.quality_issues for p in parses): limitations.append('存在未读部件/质量问题；全文已审查=false')
    if actual.matter.contract_type=='unknown' or actual.matter.jurisdiction!='CN-mainland': limitations.append('须转专项；不能声明大陆四类完整法律审查。')
    if selection.applied: limitations.append('已选批准规则仅登记引用依赖；mock不生成任意法律结论，仍需律师判断。')
    run=ReviewRun(id=run_id,matter_id=actual.matter.id,manifest=manifest,status='failed' if error else 'completed',
        coverage=coverage_for(actual,findings,processed,parses,failed=bool(error)),findings=findings,
        limitations=tuple(limitations),model_usage=tuple(usages),started_at=started,
        finished_at=datetime.now(timezone.utc),error_code=error)
    with db.begin_nested():
        _save(run,actual,config,processed,attempts,actor,db)
        review_status_changed(actual.matter.id,actor,db,success=error is None)
    return run


def extract_document_candidates(parsed,model,*,matter_id,actor,db):
    """Explicit intake before confirmation; real raw parsing and T04 candidates."""
    authorize(actor,matter_id,'candidate_facts',db);require_provider(model);require_storage(db)
    stored=get_parse_result(matter_id,parsed.version_id,actor,db)
    if parsed!=stored: raise ServiceError('VERSION_CONFLICT',409)
    trusted_parse(matter_id,parsed.version_id,actor,db,stored)
    matter=read_matter(matter_id,actor,db)
    snapshot=read_rule_snapshot(actor,matter_id=matter_id,db=db)
    policy=read_policy(matter.active_policy_version,actor,matter_id=matter_id,db=db)
    if policy.preferences: raise ServiceError('RULE_UNAPPROVED',409)
    empty=FactSnapshot(version=(matter.active_fact_version or 0)+1,facts=(),sha256=fact_snapshot_sha256(()))
    ctx=ReviewContext(matter=matter,document_versions=(read_version(matter_id,parsed.version_id,actor,db),),
        fact_snapshot=empty,position=matter.position,rules=(),policy=policy,authority_ids=(),allowed_scope=SCOPE)
    limit=ModelUsageLimit(max_input_tokens=10000000,max_output_tokens=10000000,max_cost='0',unit='mock_credit')
    usages=[];attempts=[];extracted=[];error=None
    for start in range(0,len(parsed.anchors),32):
        payload,error=_operation('extract_facts',ctx,_package(parsed.anchors[start:start+32]),model,limit,usages,attempts)
        if error: break
        extracted.extend(payload['facts'])
    if not error:
        try:
            result=build_fact_candidates(parsed,{'facts':extracted},matter_id=matter_id,version=empty.version,actor=actor,db=db)
        except ServiceError as exc:
            error=exc.code
    _save_operation_record(matter_id,actor,'intake',attempts,error,prompt_configuration(model_configuration(model)),db)
    if error: raise ServiceError(error,409)
    return result
