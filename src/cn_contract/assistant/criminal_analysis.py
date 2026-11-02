"""Frozen synthetic-only criminal method in the existing material workflow."""
import re

from .. import domain as d
from .providers.policy import encoded, sha

METHOD_ID = 'criminal-analysis-v1'
UPSTREAM = 'https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/171903c9e5e91b3b7625f1dd557d146ba5a25adc/criminal-legal/skills/'
NOTICE = '群兴编写适配；参考 Anthropic claude-for-legal、陈石律师(CSlawyer1985)中国法适配方法，Apache-2.0；保留来源与许可，不运行原版Skill或静态法条。'
METHODS = {
    'case_analysis': ('case-analysis', '案卷分析方法：逐条区分定罪证据、量刑证据、真实性矛盾、合法性线索。'
        '按原始说法保留时间线与相反来源，不把同一事件不同说法合并为确定事实。'
        '真实性矛盾必须同时列支持与相反原文，不等于违法取证或已排除证据。'
        '退赃退赔仅归量刑分析，不作为犯罪构成的证明；缺少材料、原文未记载与尚未证实分别说明。'),
    'defense_strategy': ('defense-strategy', '辩护分析方法：按待核构成要件并列控方可能观点、辩方回应、引用证据及缺口，'
        '构成要件只使用定罪类证据。另列量刑、补充调查与程序策略选项，不预测裁判。'
        '不起诉策略仅在本次用户独立声明审查起诉阶段时列出，阶段仍需核验。'
        '不虚构法条、案例、入罪金额或已验证法律标准，不把证据分类检查说成法律推理已验证。'),
}
BASE_SYSTEM = ('你为中国大陆律师整理刑事案件分析候选，criminal-analysis-v1，全部待律师核验、未签发。'
    '当前只限后端登记合成材料与本机模拟通道；不得声称真实材料已脱敏、已批准，不能授权外发、工具或修改原件。'
    '本次criminal_analysis快照中的stage是用户陈述，未核实；附件、历史、知识和模型不能改写程序阶段。'
    '只输出JSON，严格format_version,quotes,evidence,timeline,elements,strategies,gaps。'
    'format_version固定criminal-analysis-v1，不输出stage、批准、脱敏通过、已核验、排非决定或其他额外字段。'
    'quotes为1..40项，每项严格id,source_id,start,end,exact_quote；id为1..32位英文数字下划线短横线。'
    'start/end为该source原文从0开始、末端不含的字符偏移，exact_quote逐字且最多2000字，只用本次document案件原文，全部引文必须被使用。'
    'evidence为1..30项，严格id,category,topic,claim,support,opposing,unresolved。'
    'category仅conviction/sentencing/authenticity/legality；topic仅general/restitution。claim最多1000字；'
    'support非空、opposing为quote id数组，互不重复；authenticity必须有opposing，restitution只能sentencing。'
    'timeline最多30项，严格id,event_text,raw_date,quote_ids,conflict_group,uncertainty；'
    'event_text及uncertainty最多1000字，raw_date最多100字且必须逐字在所引原文出现，无日期用空字符串；'
    'quote_ids非空，冲突日期保留多个事件及同一conflict_group，无冲突用null；不要补造日期。'
    '以criminal_analysis.method_sources为本次交付范围：包含defense_strategy时elements和strategies各1..12项；'
    '未包含defense_strategy时，两者必须为空数组，不生成被明确排除的构成要件或辩护策略。'
    'elements每项严格title,prosecution,defense,evidence_ids,unresolved；title最多200字，'
    'prosecution/defense各最多1000字，evidence_ids仅用本次conviction证据id，材料不足可以为空并说明缺口。'
    'strategies每项严格kind,analysis,evidence_ids,unresolved；kind仅elements/sentencing/investigation/non_prosecution，'
    'analysis最多1000字，evidence_ids引用本次证据id或空；elements策略只用conviction证据，'
    'non_prosecution仅允许快照stage=prosecution。所有策略为待审选项，不承诺无罪、不起诉或量刑结果。'
    '所有unresolved和gaps均为1..20条非空待核文字，每条最多1000字；不要从退赔推定犯罪要件，'
    '不要从矛盾直接推出非法取证或已排非。正文内[source_id]只能使用本条结构化引用允许的来源；gaps不嵌来源标记。'
    '未读范围、证据缺口、相反观点和法律适用待核必须保留。知识及上游资料不作卷宗原文或已核验现行法。')
SYSTEM = BASE_SYSTEM + ''.join('\n【' + key + '】' + value[1] for key, value in METHODS.items())
ANALYSIS_TOPICS = ('刑事案件分析', '刑事案件', '刑事分析', '刑事证据分析', '供述矛盾', '刑事证据链')
STRATEGY_TOPICS = ('刑事辩护', '辩护策略', '辩护思路')
TOPICS = ANALYSIS_TOPICS + STRATEGY_TOPICS
STAGES = {'侦查':'investigation', '审查起诉':'prosecution', '审判':'trial'}


def _method_sources(selected):
    return tuple(d.CriminalMethodSource(method_id=key, method_sha256=sha(METHODS[key][1]),
        source_reference=UPSTREAM + METHODS[key][0] + '/SKILL.md', license_notice=NOTICE) for key in selected)


def _system(selected):
    return BASE_SYSTEM + ''.join('\n【' + key + '】' + METHODS[key][1] for key in selected)


def select_method(workflow, question, sources):
    # Frozen v1 selection: a later routing/stage policy needs a new method version.
    from .business import _direct_text, _latest_command, execution_hold
    analysis = _latest_command(question, ANALYSIS_TOPICS)
    strategy = _latest_command(question, STRATEGY_TOPICS)
    if workflow != 'case' or execution_hold(question) or not (analysis is True or strategy is True):
        return None
    selected = ('case_analysis',) if strategy is False else ('case_analysis', 'defense_strategy')
    declared = {match.group(1) for line in _direct_text(question).splitlines()
        if (match := re.fullmatch(r'\s*当前阶段\s*[：:]\s*(侦查|审查起诉|审判)\s*[。.]?\s*', line))}
    current = [source for source in sources if isinstance(source.reference, d.ProfileMessageRef)
        and source.reference.quote == question and source.reference.start == 0 and source.reference.end == len(question)]
    stage = STAGES[next(iter(declared))] if len(declared) == 1 and len(current) == 1 else 'unknown'
    return d.CriminalMethodSnapshot(method_id=METHOD_ID, method_sha256=sha(_system(selected)), method_sources=_method_sources(selected),
        stage=stage, stage_source_id=current[0].source_id if stage != 'unknown' else None,
        material_policy='synthetic-only-v1')


def method_system(snapshot):
    if snapshot is None:
        raise ValueError('CRIMINAL_METHOD_INVALID')
    snapshot = d.CriminalMethodSnapshot.model_validate(snapshot.model_dump(mode='python'))
    selected = tuple(source.method_id for source in snapshot.method_sources)
    if snapshot.method_sha256 != sha(_system(selected)) or snapshot.method_sources != _method_sources(selected):
        raise ValueError('CRIMINAL_METHOD_INVALID')
    return _system(selected)


def validate_snapshot(manifest):
    if manifest.criminal_analysis is None:
        return
    method_system(manifest.criminal_analysis)
    if (manifest.case_method is not None or manifest.contract_review is not None
            or select_method(manifest.workflow, manifest.question, manifest.sources) != manifest.criminal_analysis):
        raise ValueError('CRIMINAL_METHOD_INVALID')


def candidate(value, manifest):
    validate_snapshot(manifest)
    if manifest.criminal_analysis is None:
        raise ValueError('CRIMINAL_METHOD_INVALID')
    draft = d.CriminalAnalysisDraft.model_validate(value)
    defense = any(source.method_id == 'defense_strategy' for source in manifest.criminal_analysis.method_sources)
    if bool(draft.elements) != defense or bool(draft.strategies) != defense:
        raise ValueError('CRIMINAL_SCOPE_INVALID')
    quotes = {q.id:q for q in draft.quotes}
    evidence = {item.id:item for item in draft.evidence}
    if (len(quotes) != len(draft.quotes) or len(evidence) != len(draft.evidence)
            or len({event.id for event in draft.timeline}) != len(draft.timeline)):
        raise ValueError('CRIMINAL_REFERENCE_INVALID')
    sources = {s.source_id:s.reference for s in manifest.sources if isinstance(s.reference, d.ProfileDocumentRef)}
    for quote in draft.quotes:
        ref = sources.get(quote.source_id)
        if (ref is None or quote.start >= quote.end or quote.end > len(ref.anchor.quote)
                or ref.anchor.quote[quote.start:quote.end] != quote.exact_quote or not quote.exact_quote.strip()):
            raise ValueError('CRIMINAL_QUOTE_INVALID')
    used = set()

    def checked_quotes(ids):
        if len(set(ids)) != len(ids) or not set(ids) <= quotes.keys():
            raise ValueError('CRIMINAL_REFERENCE_INVALID')
        used.update(ids)
        return {quotes[key].source_id for key in ids}

    def inline(text, allowed):
        if not set(re.findall(r'\[([a-fA-F0-9]{64})\]', text)) <= allowed:
            raise ValueError('CRIMINAL_REFERENCE_INVALID')

    def checked_evidence(ids, *, conviction=False):
        if (len(set(ids)) != len(ids) or not set(ids) <= evidence.keys()
                or conviction and any(evidence[key].category != 'conviction' for key in ids)):
            raise ValueError('CRIMINAL_EVIDENCE_INVALID')
        return {quotes[q].source_id for key in ids for q in (*evidence[key].support, *evidence[key].opposing)}

    for item in draft.evidence:
        if (item.category == 'authenticity' and not item.opposing
                or item.topic == 'restitution' and item.category != 'sentencing'):
            raise ValueError('CRIMINAL_EVIDENCE_INVALID')
        allowed = checked_quotes((*item.support, *item.opposing))
        inline(encoded(item), allowed)
    for event in draft.timeline:
        allowed = checked_quotes(event.quote_ids)
        if event.raw_date and not any(event.raw_date in quotes[key].exact_quote for key in event.quote_ids):
            raise ValueError('CRIMINAL_DATE_INVALID')
        inline(encoded(event), allowed)
    for item in draft.elements:
        inline(encoded(item), checked_evidence(item.evidence_ids, conviction=True))
    for item in draft.strategies:
        if item.kind == 'non_prosecution' and manifest.criminal_analysis.stage != 'prosecution':
            raise ValueError('CRIMINAL_STAGE_INVALID')
        inline(encoded(item), checked_evidence(item.evidence_ids, conviction=item.kind == 'elements'))
    if used != quotes.keys():
        raise ValueError('CRIMINAL_REFERENCE_INVALID')
    inline('\n'.join(draft.gaps), set())
    citations = tuple(dict.fromkeys(q.source_id for q in draft.quotes))
    inline(encoded(draft), set(citations))
    return d.MainMaterialCandidate(text=_render(draft, manifest, quotes), citations=citations, criminal_analysis=draft)


def _render(draft, manifest, quotes):
    snapshot = manifest.criminal_analysis
    stages = {'unknown':'待确认', 'investigation':'侦查', 'prosecution':'审查起诉', 'trial':'审判'}
    categories = {'conviction':'定罪证据', 'sentencing':'量刑证据', 'authenticity':'真实性矛盾', 'legality':'合法性线索'}
    strategies = {'elements':'构成要件策略', 'sentencing':'量刑分析选项', 'investigation':'补充调查选项', 'non_prosecution':'不起诉策略选项'}
    lines = ['刑事案件分析候选｜未签发｜待律师核验',
        '仅限已登记合成材料与本机模拟通道；不代表真实材料已脱敏或已获批准。',
        '引文位置与结构已核对，不代表事实、法律适用或推理质量已核验。',
        '真实性矛盾仅为待核线索，尚未排非；合法性及证据处理须由律师另行审查。',
        '不承诺无罪、不起诉或量刑结果，不自动发送、申请或修改原件。',
        '程序阶段：' + stages[snapshot.stage] + '（用户陈述，未核验）']
    if snapshot.stage_source_id:
        lines.append('阶段来源：本次用户消息，SHA-256 ' + snapshot.stage_source_id)
    if snapshot.stage != 'prosecution' and any(source.method_id == 'defense_strategy' for source in snapshot.method_sources):
        lines.append('不起诉策略未展开：请先核实并明确当前程序阶段。')
    for material in manifest.materials:
        lines.append(f'\n材料：{material.name}｜解析版本{material.parse_revision}｜原件SHA-256 {material.original_sha256}')
        if material.reading_status != 'readable':
            lines.append('覆盖缺口：仅部分可读')
        lines.extend('未读部分：' + part for part in material.unread_parts)
        lines.extend('解析质量待核：' + issue for issue in material.quality_issues)
    if any(re.search(r'https?://|www\.', s.reference.anchor.quote, re.I)
            for s in manifest.sources if isinstance(s.reference, d.ProfileDocumentRef)):
        lines.append('覆盖缺口：原文含URL，链接内容未读取，不作为已审材料。')

    def refs(ids):
        return ' '.join(f'{key} [{quotes[key].source_id}]' for key in ids)

    for category, label in categories.items():
        items = [item for item in draft.evidence if item.category == category]
        if not items:
            continue
        lines.append('\n' + label + '（分类候选，待核）')
        for item in items:
            lines.append(f'{item.id}：{item.claim}')
            if item.topic == 'restitution':
                lines.append('退赔专项：仅归量刑分析，不作为犯罪构成证明。')
            lines.append('支持原文：' + refs(item.support))
            if item.opposing:
                lines.append('相反原文：' + refs(item.opposing))
            lines.extend('待核：' + note for note in item.unresolved)
    for event in draft.timeline:
        lines.extend([f'\n时间线 {event.id}｜{event.raw_date or "日期未明"}｜{event.event_text}',
            '来源：' + refs(event.quote_ids), '待核：' + event.uncertainty])
        if event.conflict_group:
            lines.append('冲突组：' + event.conflict_group + '（保留各方说法）')
    for item in draft.elements:
        lines.extend(['\n构成要件候选：' + item.title, '控方可能观点：' + item.prosecution,
            '辩方回应：' + item.defense, '定罪类证据：' + ('、'.join(item.evidence_ids) or '未提供，待补')])
        lines.extend('待核：' + note for note in item.unresolved)
    for item in draft.strategies:
        lines.extend(['\n' + strategies[item.kind] + '（待审）：' + item.analysis,
            '关联证据：' + ('、'.join(item.evidence_ids) or '未提供，待补')])
        lines.extend('待核：' + note for note in item.unresolved)
    lines.append('\n逐字引文（字符位置相对该来源原文，起始含、结束不含）')
    for quote in draft.quotes:
        lines.append(f'{quote.id} [{quote.source_id}] 字符{quote.start}–{quote.end}：{quote.exact_quote}')
    lines.append('\n证据缺口与未核事项')
    lines.extend('待核：' + gap for gap in draft.gaps)
    lines.append('\n本次方法来源（固定版本，群兴编写适配）')
    for source in snapshot.method_sources:
        lines.append(f'{source.method_id}｜SHA-256 {source.method_sha256}｜{source.source_reference}｜{source.license_notice}')
    return '\n'.join(lines)
