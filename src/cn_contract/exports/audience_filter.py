"""Recipient allowlists applied before writing any new DOCX part."""
from ..security import ServiceError

AUDIENCES={'internal':'内部律师','client':'客户','counterparty':'合同对方'}
DIMENSIONS=('主体身份','签署授权','许可资格','交易性质','标的交付','价格税费','付款账户','期限顺序','验收质保','担保增信','违约损失','免责上限','解除退出','知识产权','保密数据','通知证据','争议解决','整体一致')
STATES={'reviewed_issue':'已发现待复核事项','reviewed_no_issue':'已核对未发现问题','insufficient_material':'材料不足','unsupported':'需专项人工审阅','not_applicable':'不适用'}


def project(run,audience,patches,manual,*,scope=None,internal=None):
    if audience not in AUDIENCES:raise ServiceError('NOT_SUPPORTED',422)
    common={'audience':audience,'title':f'独立虚构合同审查{AUDIENCES[audience]}草案',
        'opening':'本文件仅供核对独立虚构合同的材料范围和模拟修改建议。所有修改须人工复核，不能用作正式法律意见或签发文件。',
        'limitations':['DRAFT MOCK 模拟材料 不构成正式法律意见','QCC未查询 不能确认现实记录不存在或认定无风险',
            '现实法源及法律验收未获批准 所有模拟观察仅供工程验证'],
        'scope':scope if audience!='counterparty' else [],'internal':internal if audience=='internal' else [],
        'coverage':[],'observations':[],'patches':[{'old':p.old_text,'new':p.new_text,'reason':p.reason} for p in patches],
        'manual':manual}
    if audience!='counterparty':
        common['limitations'].extend(run.limitations)
        common['coverage']=[{'dimension':c.coverage_id.value+' '+DIMENSIONS[int(c.coverage_id.value[1:])-1],'status':STATES[c.status.value]} for c in run.coverage]
        for finding in run.findings:
            item={'analysis':finding.analysis,'effect':finding.business_effect,'recommendation':finding.recommendation,
                'severity':finding.severity.value,'evidence':finding.evidence_state.value}
            if audience=='internal':item['fallback']=finding.fallback or '内部备选方案待律师确认'
            common['observations'].append(item)
    else:
        common['opening']='本草案仅列经模拟复核身份明确批准对外范围的模拟修改及说明。请逐项核对文字；未形成正式合同变更或法律意见。'
    return common


def allow_original_copy(audience):
    # Initial outward drafts are wholly new documents. The original package can
    # contain comments/custom props/embeddings/hidden private context that cannot
    # be certified public by merely filtering a report or approving one patch.
    return audience=='internal'
