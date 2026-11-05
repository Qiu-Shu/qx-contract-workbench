"""Assistant judgments after the single authorized repair; never edits a Skill."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = {
'chinese-legal-commercial': ('fail', '我方立场：甲方（采购方）。', 'pass', '邮件回复“按新单执行”仅能证明双方意思表示', '邮件与履行证据已分开，但旧题未确认委托立场即定我方为甲方；题干只有甲采购乙，不能等同代理甲。第二轮仍有实质角色补事实，建议停用该总入口，以qx-contract-review明确立场入口替代。'),
'legal-zh-commercial-escalation-flagger': ('pass', '法务负责人是否签字取决于矩阵，不能推定', 'pass', '仅这些明确列举类别不受上限限制', '审批矩阵缺失保持未知；一般责任与例外责任两行分开，已修复悬空指代及自相矛盾。'),
'legal-zh-commercial-review-proposals': ('pass', '有效性及无效后责任适用待核', 'fail', '该等责任本就不能靠约定排除', '新题没有法律来源，仍直接断言故意重大过失责任不能约定排除；后列法律效果待核不能撤销前文确定规则。与首轮未经核验法律效果同类错误重复，建议停用。'),
'legal-zh-commercial-saas-msa-review': ('fail', '导出格式、费用、终止后访问、删除凭证、迁移协助均未约定', 'pass', '不能仅凭未签页认定未生效或仍按旧价', '旧题价格误引已修复，但仍把仅摘要未提供数据退出条款写成合同均未约定，制造实质合同缺失。第二轮来源边界仍不可靠，建议停用专项入口，改由核心合同审查明确已读范围。'),
'legal-zh-commercial-stakeholder-summary': ('pass', '续期时长、通知以发出还是到达为准，均待核', 'pass', '通知生效标准＝待核', '时限四格保留通知发出/到达/收悉未知，续期长度与价款效力未填造，两组通过。'),
'legal-zh-commercial-vendor-agreement-review': ('pass', '建议咨询法务、数据合规岗，但不构成批准要求', 'pass', '基数、累计或每次、时间窗口均【待协商】', '审批角色不再默认，责任上限参数待协商；新题较短通知对采购利益及备选谈判方案方向明确，未把备选天数作为已约定事实。'),
'legal-zh-corporate-board-minutes': ('fail', '签到仅见A、B两名董事，董事身份及来源见E3', 'pass', '董事身份及签到来源待核', '旧题E3只给董事会签到A/B，并未给其董事身份，E1仅给股东身份；本次仍将签到者直接确认为董事并宣称E3支持。此前虚构C/交割条件虽修复，公司记录身份事实仍越界，建议停用。'),
'legal-zh-corporate-integration-management': ('pass', '是否须在触发前取得，待核', 'pass', '暂无。预计交割日2027-02-10仅为目标', '同意取得时点保留待核，不再无依据放在交割后完成；股权收购其他整合动作保留协议或规则触发条件。'),
'legal-zh-corporate-written-consent': ('fail', '签署人核对表**：A、B及第三名董事', 'pass', '本稿不证明任何审议、表决或签署状态', '既定生效条件和未审议事实已修复，但旧题签署表把只见签到/股东身份的A/B直接当董事及签署人，尚缺董事名册与签署资格。第二轮仍生成未核公司身份，建议停用。'),
'legal-zh-employment-expansion-kickoff': ('pass', '上述员工事项与本次扩张是否相关待确认', 'pass', '未提供（非“无制度”）', '既定目标与可选建议分列，仅明确启用日进入目标；当地实体非默认前提，未知制度保留未提供。'),
'legal-zh-employment-handbook-updates': ('pass', '绩效处理 | 未提供', 'pass', '建议，待核是否与既有条款重复', '两组法律程序和数字保持待核，绩效/考核相关条款未提供与缺失分开，个案余额不入制度；旧题新城市办公室行简略“无”未形成明确现有制度缺条结论，不据低风险表述单独判失败。'),
'legal-zh-employment-hiring-review': ('pass', '服务期与何种培训的关系、违约责任限制：规则待核', 'fail', '如另签，须单独书面约定并待核', '旧题服务期未核前提已改为问题；新题仍把竞业另签的单独书面约定作为确定要求，再附待核。未提供法源时预埋程序要求重复，建议停用自动录用专项。'),
'legal-zh-employment-international-expansion': ('pass', '是否有解除计划：材料未给，未知', 'pass', '本事项属境内跨市设点', '境内情境不强加跨境模块；员工个案侧栏不推拟解除，保留国内结构比较与待核规则。'),
'legal-zh-employment-matter-workspace': ('pass', '拟解除日期：未提供', 'pass', '是否拟解除未知', '事件映射明确办公室日期不转填解除，争议阶段、委托立场及保密关联不猜，未声称已执行。'),
'legal-zh-employment-policy-drafting': ('pass', '内部起草说明（非制度正文）', 'pass', '员工Z休假余2天系个案事实，不写入制度', '核心制度与内部个案说明物理分开，适用人员范围及法律规则待核；拟定管理岗位属于草稿方案，非声称已存在机构事实。'),
'legal-zh-employment-termination-review': ('fail', '违法解除赔偿金＝2×经济补偿（适用条件待核）', 'pass', '与解除的关联材料未建立，本次不作计算基准', '旧题再次预埋未取源补偿倍数，且写“新办公室启用日与解除无关联”，与上轮未核法律规则/缺关联推无关同类错误。新题守住不能抵消旧题实质失败，建议停用。'),
'legal-zh-employment-wage-hour-qa': ('pass', '适用性**未知**，不作“不适用”结论', 'pass', '不能以2027-03-15运营点启用日推定', '适用性改为未知，日期不误用、倍率等未填；询问审批属于待补核查而未断言标准工时必需审批，不将该问句单独视为实质失败。'),
}

def main():
    dest = ROOT/'docs/checks/skills-repair'
    reviews = json.loads((dest/'group-b-review.json').read_text(encoding='utf-8'))
    retry = json.loads((dest/'group-b-retry-names.json').read_text(encoding='utf-8'))
    assert set(retry) == set(VERDICTS) and len(retry) == 17
    for folder in ['repair-b-retry-regression','repair-b-retry-new']:
        paths = list((ROOT/'docs/checks/skills-quality/model'/folder).glob('*.json'))
        assert len(paths) == 17, (folder, len(paths))
        assert {json.loads(p.read_text(encoding='utf-8'))['skill'] for p in paths} == set(retry)
    out = []
    for original in reviews:
        name = original['name']
        row = dict(original)
        if name not in VERDICTS:
            assert row['finalStatus'] == 'pass'
            row['reviewRound'] = 'round1-retained'
            out.append(row)
            continue
        rs, re, gs, ge, reason = VERDICTS[name]
        for phase, status, evidence, folder, prefix in [('regression',rs,re,'repair-b-retry-regression','legal-smoke-'),('generalization',gs,ge,'repair-b-retry-new','repair-new-')]:
            path = ROOT/'docs/checks/skills-quality/model'/folder/(prefix+name+'.json')
            data = json.loads(path.read_text(encoding='utf-8'))
            assert data['skill'] == name and data.get('finishReason') == 'stop'
            assert evidence in data['response'], (name, phase, evidence)
            row[phase] = dict(status=status,evidence=evidence,response_file=path.relative_to(ROOT).as_posix(),responseFileSha256=hashlib.sha256(path.read_bytes()).hexdigest())
        row['finalStatus'] = 'pass' if rs == gs == 'pass' else 'disable-recommended'
        row['reason'] = reason
        row['reviewRound'] = 'single-repair-retry'
        row['evaluationScope'] = '助手逐项判读合成材料指令测试；非律师认证，非现行法认证，非真实工具端到端测试。系统含生命周期/日期算术边界，并按replacement预载目标。'
        out.append(row)
    assert len(out) == 27
    (dest/'group-b-final-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    disabled = [x['name'] for x in out if x['finalStatus'] == 'disable-recommended']
    print(json.dumps({'total':27,'pass':27-len(disabled),'disableRecommended':len(disabled),'names':disabled},ensure_ascii=False))

if __name__ == '__main__':
    main()
