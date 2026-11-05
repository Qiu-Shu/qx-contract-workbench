"""Assistant-read judgments of all 54 saved synthetic responses (not legal certification)."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
# Each quote was read in the saved output; judgments cover the material defect, not tool availability.
REVIEWS = {
'chinese-legal-commercial': ('pass', '应先删除全面免责，明确其违约赔偿责任', 'repair-needed', '双方回复“按新单执行”可作合意及实际履行的证据', '新题将邮件同意升级为实际履行证据；题干明确具体履行未给，后文核查并不能修复证据属性。'),
'chinese-legal-renewal-watcher': ('pass', '以届满日为基准倒推30日；因届满日口径未定，暂列算式', 'pass', '2028-04-30 − 45自然日。工具不可用，未计算，待核', '两组正确区分起始与届满，保留续期期限未知；工具不可用时降级不算失败。'),
'legal-zh-commercial-amendment-history': ('pass', '不等于已确认现行有效', 'pass', '亦不能仅因未签即认定仍按8万元', '文本差异与效力分栏，保留签署外效力证据及候选版本。'),
'legal-zh-commercial-escalation-flagger': ('pass', '“高风险”是分析判断，不等于机构自动上报条件', 'repair-needed', '为我方赔偿设金额上限，并写明该等责任不适用上限、仍应承担', '新题未定义例外责任，直接把我方有上限责任又写为不适用上限，替代方向自相矛盾。'),
'legal-zh-commercial-matter-workspace': ('pass', '委托立场待确认', 'pass', '未建档、未保存、未切换', '领域字段保留，未知立场保密关联不猜，未用旧slash或全局配置。'),
'legal-zh-commercial-review': ('pass', '不能据此认定已生效或应按新价支付', 'pass', '验收完成与收票两项条件均满足后，按较晚成就日起算前述20个工作日', '两组责任方向和变更效力保留条件，新题付款补正保留全部前提。'),
'legal-zh-commercial-review-proposals': ('pass', '删除第5条全面免责，明确乙方违约赔偿责任；金额上限另议', 'repair-needed', '避免免责条款被认定无效后责任真空', '新题未经法源与适用分析作免责无效导致责任真空的法律效果判断；不是纯手册管理建议。'),
'legal-zh-commercial-saas-msa-review': ('repair-needed', '价格（E1第5条、E2）', 'pass', '匿名化不等于当然合规，标准待核', '旧题第5条实际为供应商免责，却引用为价格来源；来源定位须与议题逐项绑定。'),
'legal-zh-commercial-stakeholder-summary': ('pass', '续期后持续多久、续几次，条款未写明，待核', 'repair-needed', '不续约通知须在届满前45个自然日发出', '题干只要求通知，未给发出或到达生效规则；将期限确定为发出会改变期限含义。'),
'legal-zh-commercial-vendor-agreement-review': ('repair-needed', '数据训练条款→数据合规负责人；免责与无限赔偿→法务负责人', 'pass', '期限越长，我方须越早决定，与“尽量晚决定”相反', '旧题无矩阵仍确定审批角色，另将累计已付年费写为确定替代上限；新题通知方向正确。'),
'legal-zh-corporate-board-minutes': ('repair-needed', 'C是否缺席无签到证据；属交割条件；需列明全体董事签署', 'pass', '未提供讨论记录，待补', '旧题补造董事C并把合同同意要求定为交割条件，要求全体签署无材料；新题记录型草案守住。'),
'legal-zh-corporate-cold-start-interview': ('pass', '公众公司—适用性未知（无上市信息，不关闭）', 'pass', '转让方及交割后股权结构待补', '公众身份未知、转让方与交割条件待核，配置成果可用。'),
'legal-zh-corporate-diligence-issue-extraction': ('pass', '不能推定由A转让或A退出', 'pass', '40%是否触发、是否已取得同意均待核', '现状与拟转让分开，同意触发条件和资料层级保留。'),
'legal-zh-corporate-entity-compliance': ('pass', '未提供注册地、适用年度及申报规则', 'pass', '完成情况未知', '没有编造年报规则或逾期，现状股权与计划不构造冲突。'),
'legal-zh-corporate-integration-management': ('repair-needed', '交割后：处理E4供应合同控制权变更同意', 'pass', '不设Day-N期限，不认定同意已取得或未接洽', '旧题未核同意时点即建议安排在交割后，可能导致先完成触发事件再补前置同意；需独立未定时点区。'),
'legal-zh-corporate-written-consent': ('repair-needed', '生效条件为E4同意书取得及章程程序完成（待核）', 'repair-needed', '尚未经任何董事审议或表决', '旧题拟稿补造生效条件；新题把未提供审议记录变成尚未审议的事实。'),
'legal-zh-employment-expansion-kickoff': ('pass', '不作为直接用工的默认前提', 'repair-needed', '2026-12前定城市；2027-01前定结构；制度 | 无', '新题将未给的阶段期限直接填入目标时间且未标建议，制度未提供写为无，计划与既定输入混合。'),
'legal-zh-employment-expansion-update': ('pass', '2026-12-01为计划启用日，非解除日', 'pass', '用工结构成立后方可确定', '未知记录不伪造检索，分支依赖有条件，日期不误用。'),
'legal-zh-employment-handbook-updates': ('repair-needed', '无绩效改进条款；无新城市适用条款', 'pass', '员工Z休假余额2天系个案数据，不作为全员制度标准', '旧题仅给E1一句摘要，不足以认定完整制度无上述条款；新题diff和规则占位正确。'),
'legal-zh-employment-hiring-review': ('repair-needed', '服务期须有专项培训证据', 'pass', '工时、竞业、试用期具体规则均待核', '旧题无任何法源仍把服务期专项培训证据作为确定要求写入待补条款，违反仅据材料。'),
'legal-zh-employment-international-expansion': ('repair-needed', '2026-10-25绩效通知后拟解除', 'pass', '本事项属境内跨市设点，不适用跨境用工框架', '旧题虽正确路由境内框架，但补造拟解除状态；须把员工个案完全放在关联未明侧栏。'),
'legal-zh-employment-investigation-memo': ('pass', '无培训、调岗材料，不等于事实上未培训、未调岗', 'pass', '仅据HR摘要（摘要层级，非原件）', '两组保留摘要层级，未造调查开始日或办公室关联结论。'),
'legal-zh-employment-investigation-summary': ('pass', '以下为材料摘要，尚非完整调查结论', 'pass', '以下不是调查结论', '受众摘要保留未知与缺口，没有补法条或保证特权。'),
'legal-zh-employment-matter-workspace': ('repair-needed', '拟解除日 2026-12-01（仅为计划）', 'pass', '是否拟解除未知', '旧题仍将新办公室日期填作拟解除日期并补拟解除阶段，属于核心事实错误。'),
'legal-zh-employment-policy-drafting': ('repair-needed', '三、绩效管理：…现有材料显示员工A于2026-10-25收到绩效不达标通知', 'pass', '适用人员范围【待确认】', '旧题把个案详细事实放进核心制度节选并默认甲公司员工范围；须物理分离制度正文与内部事实说明。'),
'legal-zh-employment-termination-review': ('pass', '不能作为解除日；不计算年限与金额', 'repair-needed', '与解除无关；协商解除：须有双方合意及书面方案，现无', '新题无证据判运营点与解除无关，并将未提供协商材料写现无及断言书面方案必需。'),
'legal-zh-employment-wage-hour-qa': ('repair-needed', '无性别、生育、病假及医疗期材料，不适用或待补', 'pass', '不能以2027-03-15新运营点启用日推定', '旧题缺材料仍给不适用选项，相关适用性须保留未知；核心日期错误已修复。'),
}

def main():
    group = json.loads((ROOT/'docs/checks/skills-repair/group-b.json').read_text(encoding='utf-8-sig'))
    assert len(REVIEWS) == len(group) == 27
    out = []
    for item in group:
        name = item['name']
        rs, re, gs, ge, reason = REVIEWS[name]
        row = {'name': name, 'reason': reason}
        for phase, status, evidence, folder, prefix in [('regression',rs,re,'repair-b-regression','legal-smoke-'),('generalization',gs,ge,'repair-b-new','repair-new-')]:
            path = ROOT/'docs/checks/skills-quality/model'/folder/(prefix+name+'.json')
            data = json.loads(path.read_text(encoding='utf-8'))
            assert data['skill'] == name and data['response']
            row[phase] = dict(status=status,evidence=evidence,response_file=path.relative_to(ROOT).as_posix(),responseFileSha256=hashlib.sha256(path.read_bytes()).hexdigest())
        row['finalStatus'] = 'pass' if rs == gs == 'pass' else 'repair-needed'
        out.append(row)
    dest = ROOT/'docs/checks/skills-repair'
    (dest/'group-b-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    retry = [x['name'] for x in out if x['finalStatus'] != 'pass']
    (dest/'group-b-retry-names.json').write_text(json.dumps(retry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Assistant reviewed 54 responses: {len(out)-len(retry)} skills pass, {len(retry)} need one repair.')

if __name__ == '__main__':
    main()
