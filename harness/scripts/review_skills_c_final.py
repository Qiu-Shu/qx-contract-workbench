"""Finalize C-group synthetic-response judgments; do not mutate any skill."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / 'docs/checks/skills-repair'
INITIAL = json.loads((CHECKS / 'group-c-review-initial.json').read_text(encoding='utf-8'))
RETRY = json.loads((CHECKS / 'group-c-retry-names.json').read_text(encoding='utf-8'))
LIFECYCLE = {row['name']: row for row in json.loads((ROOT / 'config/skill-lifecycle.json').read_text(encoding='utf-8'))['skills']}

JUDGMENTS = {
    'clinic-draft': (
        'pass', '交付仲裁申请书草稿；管辖列待核，法律依据留空，未加导师签字制度。',
        'fail', '正文写“设备实际交付时间我方尚在核对”，输入只有待核；又写“本函不以此作为贵司履行义务的前提”。合同仅约定说明书随设备提供、设备交付待核，草稿却排除该履行前提，改变原约定条件。',
        '新场景把未知状态写成正在执行，并擅自改变说明书随设备提供的履行条件；内部说明不能补救对外正文。'),
    'clinic-plain-language-letters': (
        'pass', '“相关法律期限及对您权利的影响尚待核实”；未再承诺不影响权利，明确草稿尚未发送。',
        'pass', '11月8日为内部补件安排，签收尚未核对，权利影响待核；上层可发送分区未当发送回执。',
        '两类输出已消除内部节点不影响权利的确定承诺；本轮修正了replacement预载与共享上下文，不能把改善全归于此Skill。'),
    'clinic-status': (
        'fail', '内部版写“已完成：无”“尚未接待登记、未联系来访者、未入库”。输入只确定学生尚未联系来访者，未给接待登记/入库的实际状态；缺记录仍被写为未发生。',
        'pass', '清单完成、11月6日计划、签收待核和未联系分别列出；程序/立案/提交状态保留未知。',
        '回归仍将未提供登记记录推成尚未登记，与该技能修复的状态边界相同。'),
    'criminal-bail-application': (
        'pass', '类型及机关待核；措施/是否羁押未知不选程序，不计算羁押，担保承诺待确认。',
        'pass', '申请事项保持中性，不再把未羁押引向羁押必要性审查；母亲退赔说法保留归属，付款待核。',
        '旧新场景的核心措施、羁押、退赔与承诺边界均通过本轮助手判读。'),
    'criminal-compliance-non-prosecution': (
        'pass', '“状态：退赔情况未核实（意愿，非已发生）”；侦查阶段不当然排除启动，差距表当前资料范围均标本次未提供。',
        'pass', '拟复核人和落实记录分开；缺记录不等于未启动；不起诉和个人责任均不作承诺。',
        '两类输出未再断言退赔未发生或单凭侦查排除合规程序；部分表格缺口措辞仍需按其本次材料范围理解。'),
    'criminal-matter-workspace': (
        'pass', '“用户拟定代号：demo-a｜实际case_id：待创建后返回”；家属/委托/授权分开，未建档。',
        'fail', '材料清单写“仅‘家属乙口述案件摘要’”“无书面材料”，又要求“取得摘要的书面化内容”。输入仅称家属给了摘要，未说明口头还是书面，新增来源形态与缺件结论。',
        '原ID问题修复，但新场景仍在工作区事实字段补造材料来源/形态。'),
    'law-student-case-brief': (
        'fail', '先称“整笔交易如何适用追认规则…待补”，后确定“该笔交易对甲不生效”，并回到“裁判要旨（训练模式先行）”；规则缺口仍未在结论一致保留。',
        'fail', '“材料明确为‘未给追认事实’，即既无追认表示，也无拒绝追认表示”。未提供追认信息不等于现实中无追认/拒绝表示，随后又据此写甲未追认。',
        '更换为实务摘要后仍扩大假设规则或把材料缺失转为否定事实，教学旧模式也回流。'),
    'litigation-brief-section-drafter': (
        'pass', '签收是否等同交付待核，未从日期差认定迟延；成文日期待补，T1另列。',
        'fail', '末尾写“本段仅依据…对方口头主张撰写”。输入只说对方称改期，未给表达媒介，仍补造口头这一来源性质。',
        '签收认定已修，但实质段落的来源说明仍补造表达媒介，不能当作忠实案卷摘要。'),
    'litigation-claim-chart': (
        'pass', '合同整体效力待核；不再把“对方称”补成口头；表中签收仅支持记录日期，未证迟延。',
        'fail', '写“履行节点存在日期冲突”；表③把仓库单02-08列在约定02-06的“具体相反材料”栏，表④反向列合同约定。约定日与签收日可同时为真，不能互作相反证据；旁文虽称不同命题仍保留错误映射。',
        '要件表核心的相反证据映射仍混淆不同性质事件，影响补证/论证方向。'),
    'litigation-demand-draft': (
        'fail', '无我方主体映射仍直接写“致：乙方”；输入只有甲乙纠纷和拟主张迟延，没有明确乙为义务人/收函人。',
        'fail', '正文写“我方受丙公司委托”，内部却说“需确认丙公司对本次发函的授权范围…未确认已获授权”。用户只要求给丙致丁函草稿，未报告律师已受委托；正文还落款丙公司，主体叙事不一致。',
        '现版仍在对外正文补造受函主体或已成立委托；内部待核不能补救正文的确定陈述。'),
    'litigation-demand-intake': (
        'fail', '“发函方为甲，收函方为乙”“乙称双方同意延期”。输入未明确甲乙与我方/对方映射，登记补造核心主体。',
        'pass', '丙拟发丁收有本次来源；发函主体与委托人身份分开，权限未知，不补口头或已交涉。',
        '授权分栏修复，但缺角色映射时仍按甲乙模板填定发收函方，核心登记不可靠。'),
    'litigation-matter-intake': (
        'pass', '角色、阶段和权限待核，日历差不等于迟延，利冲/关联未检索。',
        'pass', '11月12日记为计划事项、非实际登记日；未执行建案，未知身份/期限均保留。',
        '计划整理日与实际登记日已区分，旧新场景核心字段未见实质失败。'),
    'litigation-matter-workspace': (
        'pass', '拟定代号与实际case_id分开，ID待创建返回，未建案/跨案读取。',
        'pass', '明确qx-case-work路径，未建档、无建档日，关联未知，工具方案不称执行回执。',
        '两场景代号不再冒充真实case_id，保留明确本案范围；下一步方案的未知字段未填成事实。'),
    'litigation-privilege-log-review': (
        'fail', '“对方主张‘双方同意延期’但未举证”。本次未提供支持材料不证明对方程序中未举证；另把记不清日期写为关联性弱。',
        'fail', '输入仅为合同日期条款截图和记不清日期，未给设备/交付争议；输出默认待证事实“是否发生迟延交付”。此默认是本次Skill修订中加入的过窄示例，导致迁移场景凭空引入争点。',
        '程序提交状态仍被补造；新增默认争点过拟合旧题，无法泛化。停止继续加规则，建议停用该独立入口。'),
    'litigation-subpoena-triage': (
        'pass', '通知未提供；延期说法成立与否待核，不再断言不成立或当通知异议依据。',
        'pass', '通知/送达/范围/期限待核；日期记忆不是无关联异议理由；只给条件式回应与准备。',
        '旧新场景均将材料真实性、证明范围和程序异议条件分开，未见实质失败。'),
}


def loaded_skill_text(name, seen=None):
    seen = set() if seen is None else seen
    assert name not in seen and len(seen) <= 3
    seen.add(name)
    config = ROOT / 'config/skills' / name
    base = config if (config / 'SKILL.md').is_file() else ROOT / 'workspace/.dsh/skills' / name
    text = (base / 'SKILL.md').read_bytes().decode('utf-8')
    method = base / 'references/method.md'
    if method.is_file():
        text += '\n\n' + method.read_bytes().decode('utf-8')
    for resource in ['practice-context.md', 'source-verification.md']:
        file = ROOT / 'workspace/legal-library/workbench' / resource
        if resource in text and file.is_file():
            text += '\n\n' + file.read_bytes().decode('utf-8')
    route = LIFECYCLE.get(name, {})
    if route.get('action') in ('merge', 'replace') and route.get('replacement'):
        text += '\n\n所路由工作台技能：\n' + loaded_skill_text(route['replacement'], seen)
    return text


def response(name, phase, status, evidence):
    prefix = 'legal-smoke-' if phase == 'regression' else 'repair-new-'
    rel = f'docs/checks/skills-quality/model/repair-c-retry-{phase}/{prefix}{name}.json'
    content = (ROOT / rel).read_bytes()
    data = json.loads(content)
    skill_hash = hashlib.sha256((ROOT / 'workspace/.dsh/skills' / name / 'SKILL.md').read_bytes()).hexdigest()
    assert data['skill'] == name and data['response']
    loaded_hash = hashlib.sha256(loaded_skill_text(name).encode('utf-8')).hexdigest()
    assert data['skillSha256'] == loaded_hash, (name, data['skillSha256'], loaded_hash)
    return dict(status=status, evidence=evidence, response_file=rel,
                responseFileSha256=hashlib.sha256(content).hexdigest(), adapterFileSha256=skill_hash,
                loadedInputSha256=loaded_hash)


def run():
    assert {'legal-zh-' + n for n in JUDGMENTS} == set(RETRY)
    final = []
    for old in INITIAL:
        name = old['name']
        item = old.copy()
        if name not in RETRY:
            item['evaluationRound'] = 'initial-retained' if old['finalStatus'] == 'pass' else 'runtime-disable'
            final.append(item)
            continue
        rs, re, ns, ne, reason = JUDGMENTS[name.removeprefix('legal-zh-')]
        item.update(regression=response(name, 'regression', rs, re),
                    generalization=response(name, 'new', ns, ne),
                    finalStatus='disable-recommended' if 'fail' in (rs, ns) else 'pass',
                    reason='助手逐项判读合成输入与输出，不是人工/律师认证。' + reason,
                    evaluationRound='retry-after-one-refinement',
                    contextChange='根代理同时改进共享生命周期/日期口径，并按显式replacement预载实际路由；本轮结果不是纯Skill改动的隔离因果验证。')
        final.append(item)
    assert len(final) == 33
    counts = {s: sum(x['finalStatus'] == s for x in final) for s in ('pass', 'disable-recommended', 'disabled-runtime-verified')}
    (CHECKS / 'group-c-final-review.json').write_text(json.dumps(final, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(reviewed=33, retryResponseHashesVerified=30, finalStatus=counts), ensure_ascii=False))


if __name__ == '__main__':
    run()
