"""Recipient allowlists applied before writing any new DOCX part."""
from ..security import ServiceError
from ..review.decisions import resolved, disposition, check_finding_patch_disposition

AUDIENCES={'internal':'内部律师','client':'客户','counterparty':'合同对方'}
DIMENSIONS=('主体身份','签署授权','许可资格','交易性质','标的交付','价格税费','付款账户','期限顺序','验收质保','担保增信','违约损失','免责上限','解除退出','知识产权','保密数据','通知证据','争议解决','整体一致')
STATES={'reviewed_issue':'已发现待复核事项','reviewed_no_issue':'已核对未发现问题','insufficient_material':'材料不足','unsupported':'需专项人工审阅','not_applicable':'不适用'}


def project(run,audience,patches,manual,*,scope=None,internal=None,snapshot=None,decision_history=(),candidate_source=None):
    if audience not in AUDIENCES:raise ServiceError('NOT_SUPPORTED',422)
    findings=snapshot.resolved_findings if snapshot else tuple(resolved(f) for f in run.findings)
    # This pure projection is not an authorization interface. It still must not
    # render selected text that contradicts decisions present on its input.
    for patch in patches:
        check_finding_patch_disposition(next((f for f in findings if f.id==patch.finding_id),None),patch)
    common={'audience':audience,'title':f'独立虚构合同审查{AUDIENCES[audience]}草案',
        'opening':'本文件仅供核对独立虚构合同的材料范围和模拟修改建议。所有修改须人工复核，不能用作正式法律意见或签发文件。',
        'limitations':['DRAFT MOCK 模拟材料 不构成正式法律意见','QCC未查询 不能确认现实记录不存在或认定无风险',
            '现实法源及法律验收未获批准 所有模拟观察仅供工程验证'],
        'scope':scope if audience!='counterparty' else [],'internal':internal if audience=='internal' else [],
        'coverage':[],'observations':[],'patches':[{'old':p.old_text,'new':p.new_text,'reason':p.reason} for p in patches],
        'manual':manual}
    if run.manifest.model_provider=='assisted_manual':
        common['watermark']='DRAFT 离线人工/合成候选 真实模型推理未运行 非正式法律意见'
        common['opening']='本工作稿列明独立虚构合同的离线人工候选及律师处置。待核依据仍待核验；请逐项核对实际文件，不能用作正式法律意见或签发文件。'
        common['limitations'][0]=common['watermark']
        common['limitations'][2]='现实法源及法律验收未获批准 人工候选和处置不构成已核法律结论'
        if candidate_source=='local_plugin_unverified':
            common['watermark']='DRAFT 插件候选 模型来源未核验 非正式法律意见'
            common['opening']='本工作稿列明独立虚构合同的插件候选及律师处置。模型身份与推理来源未核验；待核依据仍须核验，不能用作正式法律意见或签发文件。'
            common['limitations'][0]=common['watermark']
            common['limitations'][2]='现实法源及法律验收未获批准 插件候选和处置不构成已核法律结论'
            common['keywords']='DRAFT PLUGIN-UNVERIFIED'
    if audience!='counterparty':
        common['limitations'].extend(run.limitations)
        common['coverage']=[{'dimension':c.coverage_id.value+' '+DIMENSIONS[int(c.coverage_id.value[1:])-1],'status':STATES[c.status.value]} for c in run.coverage]
        labels={'unreviewed':'待律师处置','accept':'已采纳','edit':'已明确编辑','reject':'已驳回',
            'pending_edit':'待完成编辑','request_info':'待补资料','refer':'待专项复核'}
        for finding in findings:
            state=disposition(finding)
            if audience=='client' and state=='reject':continue
            item={'analysis':finding.analysis,'effect':finding.business_effect,'recommendation':finding.recommendation,
                'severity':finding.severity.value,'evidence':finding.evidence_state.value,'decision_status':labels[state]}
            if audience=='client' and state in {'pending_edit','request_info','refer'}:
                item['analysis']=labels[state]+'：本事项尚未形成有效律师建议。'
                item['recommendation']={'pending_edit':'请律师补齐明确的分析和建议文字后重新确认。',
                    'request_info':'请补充并核对本事项相关材料，再由律师复核。','refer':'请完成相应专项复核，再由律师确认处理意见。'}[state]
            if state=='edit' and finding.replacement_text:item['replacement']=finding.replacement_text
            if audience=='internal':
                original=next(f for f in run.findings if f.id==finding.id)
                item['fallback']=finding.fallback or '内部备选方案待律师确认'
                item['original']='原始分析：'+original.analysis+'\n原始建议：'+original.recommendation
                history=[r.decision for r in decision_history if r.finding_id==finding.id]
                if not history and finding.human_decision:history=[finding.human_decision]
                item['history']='\n'.join('历史处置：'+labels['pending_edit' if d.pending_edit else d.decision.value]+'；理由：'+d.reason+
                    ('；编辑分析：'+d.edited_analysis+'；编辑建议：'+d.edited_recommendation if d.edited_analysis else '')+
                    ('；拟替换文字：'+d.edited_replacement_text if d.edited_replacement_text else '') for d in history)
            common['observations'].append(item)
    else:
        common['opening']='本草案仅列经模拟复核身份明确批准对外范围的模拟修改及说明。请逐项核对文字；未形成正式合同变更或法律意见。'
    return common


def allow_original_copy(audience):
    # Initial outward drafts are wholly new documents. The original package can
    # contain comments/custom props/embeddings/hidden private context that cannot
    # be certified public by merely filtering a report or approving one patch.
    return audience=='internal'
