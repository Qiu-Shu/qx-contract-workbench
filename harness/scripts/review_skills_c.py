"""Record source-linked assistant judgments of the synthetic C-group responses."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / 'docs/checks/skills-repair'
CHANGES = json.loads((CHECKS / 'group-c-changes.json').read_text(encoding='utf-8'))

# These are manual assistant judgments after reading the complete response, not keyword scores.
REVIEW = {
    'clinic-client-comms-log': ('pass', '未提供已发生沟通；导师审阅与T1均在待办，未保存未外发。', 'pass', '尚未联系、无发生记录，11月7日与9日作为计划而非历史；补件负责人尚应进一步明确。'),
    'clinic-deadlines': ('pass', '基准日11月4日；T1距6天列未来7天；导师具体日期待核不计数。', 'pass', '未来7天确定未完成1项A；C日期过2天但完成未知独列；D有完成记录被排除。'),
    'clinic-draft': ('repair-needed', '未给管辖规则且仅允许材料仍写“劳动合同履行地或用人单位所在地仲裁委员会”；实质草稿及无签字制度正确。', 'pass', '给催交说明书连贯正文，11月8日为希望收到，设备交付待核，无虚构签字制度。'),
    'clinic-plain-language-letters': ('repair-needed', '正文写内部节点“也不影响您的任何权利”，法律期限仍未知，末尾待核不能补救。', 'pass', '法定期限未知并另查，未声称不影响权利；“可发送回复”仅上层分区标签，不计虚构发送。'),
    'clinic-research-start': ('pass', 'E1/E2未提供全文且未读取；交付待查问题和检索线索，无伪造已检索结果。', 'pass', '手册仅线索，尚未核实/读取；全部计划检索，不造匹配或法条结果。'),
    'clinic-status': ('repair-needed', '内部版编“咨询阶段，未立案、未对外提交”“已完成：登记”；这些不是输入事实。', 'pass', '三页清单已整理、签收待核、尚未联系、11月6日拟办均分开；无虚构完成或无需行动承诺。'),
    'clinic-supervisor-review-queue': ('pass', '启用状态未确认；待审条目草稿未入队；决定栏空白，未代批。', 'pass', '启用未知，D-02/v3拟审，11月5日为计划，无等待时长、审批或入队虚构。'),
    'criminal-bail-application': ('pass', '措施、是否羁押、起算均待核；担保与到案承诺待确认；无羁押算术。', 'repair-needed', '申请事项写“如经核实尚未羁押…调整为羁押必要性审查”，程序分支错误；开头说不选类型又在正文选择。'),
    'criminal-case-analysis': ('pass', '缺付款凭证仅记退赔情况未核实；无笔录不能比较，不把意愿当退赔结果。', 'pass', 'P1称已付与P2正在核账可并存，P3记不清不作反证；范围限三段，不评全卷。'),
    'criminal-compliance-non-prosecution': ('repair-needed', '“无付款凭证，退赔未发生”把缺件直接转为否定事实；程序不排除已修。', 'pass', '整改建议与落实分开；侦查不足断言启动资格，个人责任与企业整改分开。'),
    'criminal-matter-workspace': ('repair-needed', '把拟定代号demo-a写成“明确case_id=demo-a”，没有真实建案ID。', 'repair-needed', '委托关系未确认却写“未签委托合同”；未建案仍填建档日期11月4日。'),
    'law-student-case-brief': ('repair-needed', '先写“10台部分在授权内；超出5台须追认”，再称不得当然拆分，结论自相矛盾。', 'pass', '对12箱一笔交易不给8/4效力切分，规则限制和假设性质明确，直接给摘要。'),
    'litigation-brief-section-drafter': ('pass', '约定日、物流签收、日期差与迟延认定分开；不否定延期，不借T1落款。', 'repair-needed', '写签收环节“并非设备实际交付完成的时间”，原材料只能支持二者是否相同待核，不能确定排除相同。'),
    'litigation-claim-chart': ('repair-needed', '表格额外写“对方口头主张”，输入未给媒介；核心合同片段与证言范围已有正确限制。', 'pass', '局部条款不证完整合同；日期记忆不否定全部证言；履行与签收分开。'),
    'litigation-demand-draft': ('repair-needed', '把本次未提供转为“截至本函发出，我方未收到相关书面材料”，扩大渠道与时间范围。', 'pass', '12月2日原样，未认定迟延；内部建议日不冒充法定，未发送保存。'),
    'litigation-demand-intake': ('pass', '延期仅对方主张，不补口头约定或双方确认；主体、权限、原文待核，未入库。', 'repair-needed', '表格“发函方（委托人）丙 已知”，与权限/委托关系未知不一致；发函主体不等于委托关系已成立。'),
    'litigation-demand-received': ('pass', '来函未提供，纠纷预分析；我方迟延主张与对方延期抗辩分栏，不倒置。', 'pass', '明确无来函，丙被我方主张迟延与丙抗辩分开；不认定迟延或建议不回复。'),
    'litigation-deposition-prep': ('pass', '身份关系亲历均未知，开放问询，不补物流经办人、中立身份或不在场。', 'pass', '恰好三个开放问题，关系、亲历来源、日期核对，无角色或答案预设。'),
    'litigation-matter-intake': ('pass', '我方地位待补，日历差不能作迟延，利冲/关联未检索，内部节点无转法定。', 'repair-needed', '“登记整理日2026年11月12日…已记”把未来内部计划写成实际登记日期。'),
    'litigation-matter-workspace': ('repair-needed', '拟建方案最小字段直接“case_id=demo-a”，把代号冒充真实ID。', 'pass', '明确create_case返回ID后填写，不沿用最近案；关联未知，实际操作均未执行。'),
    'litigation-portfolio-status': ('pass', '没有台账只做单案，不填组合零数；基准11月4日T1未来6天。', 'pass', '范围三案，未结2；A未来4天；B完成未知不算确定逾期；风险/陈旧未知。'),
    'litigation-privilege-log-review': ('repair-needed', '待证事实自行填“乙是否迟延交货”，输入未明谁负交付义务；部分证言关联性仍混同证明限制。', 'pass', '原件来源方式未知，可采性待核；记不清非整体否定；没有提交记录不推未举证。'),
    'litigation-subpoena-triage': ('repair-needed', '对延期主张写“属单方陈述，不成立”，将缺支持材料变成主张不成立。', 'pass', '无通知原文则类型范围送达期限均待核；记不清非无关联异议，不建议直接拒绝。'),
}


def response_review(name, phase, status, evidence):
    prefix = 'legal-smoke-' if phase == 'regression' else 'repair-new-'
    relative = f'docs/checks/skills-quality/model/repair-c-{phase}/{prefix}{name}.json'
    path = ROOT / relative
    data = path.read_bytes()
    parsed = json.loads(data)
    assert parsed.get('response') and parsed['skill'] == name
    return dict(status=status, evidence=evidence, response_file=relative,
                responseFileSha256=hashlib.sha256(data).hexdigest())


def run():
    results = []
    retries = []
    for item in CHANGES:
        name = item['name']
        if item['action'] == 'disable':
            check = dict(status='disabled-runtime-verified', evidence='根代理报告已通过官方Harness验证拒绝调用并从自动目录移除；本组只核对双禁用字段，不将其视为模型行为通过。', response_file=None, responseFileSha256=None)
            results.append(dict(name=name, regression=check, generalization=check.copy(), finalStatus='disabled-runtime-verified', reason='不适合当前律所工作台；原参考保留。'))
            continue
        rstatus, revidence, nstatus, nevidence = REVIEW[name.removeprefix('legal-zh-')]
        final = 'repair-needed' if 'repair-needed' in (rstatus, nstatus) else 'pass'
        if final == 'repair-needed':
            retries.append(name)
        results.append(dict(name=name, regression=response_review(name, 'regression', rstatus, revidence),
                            generalization=response_review(name, 'new', nstatus, nevidence), finalStatus=final,
                            reason='助手逐项判读合成输入与产出的一致性；非人工/律师认证。' + ('已做最小修，待重测。' if final == 'repair-needed' else '本轮两类输出未发现影响核心任务的实质失败。')))
    assert len(results) == 33
    (CHECKS / 'group-c-review-initial.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (CHECKS / 'group-c-review.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (CHECKS / 'group-c-retry-names.json').write_text(json.dumps(retries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'reviewed': 33, 'active': 23, 'retry': len(retries), 'disabled': 10}))


if __name__ == '__main__':
    run()
