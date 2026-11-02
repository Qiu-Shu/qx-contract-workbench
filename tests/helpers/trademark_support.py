"""New independent fiction for structural checks, never a content-quality score."""
from cn_contract.assistant import trademark_triage as method
from tests.helpers.trademark_triage import manifest_for, KINDS

SLOTS = ('issuer', 'speaker', 'actor', 'object', 'event_time', 'report_time', 'record_time')


def manifest():
    base = manifest_for(texts=(
        '虚构记录：纸上印有澄原公司字样，书写者不详，所涉标识未注明。',
        '虚构职员于2025年3月转述澄原公司在2022年使用青禾牌；记录形成时间不明。',
    ))
    return base.model_copy(update={'trademark_triage': method.select_method(
        'case', base.question, method_id='trademark-triage-v6')})


def span(raw, quote_id, text):
    quote = next(q for q in raw['quotes'] if q['id'] == quote_id)
    start = quote['exact_quote'].index(text) + quote['start']
    return dict(quote_id=quote_id, start=start, end=start + len(text))


def draft(manifest):
    quotes = [dict(id=f'q{i}', source_id=s.source_id, start=0,
        end=len(s.reference.anchor.quote), exact_quote=s.reference.anchor.quote)
        for i, s in enumerate(manifest.sources[1:], 1)]
    statements = [dict(id=f's{i}', quote_ids=[q['id']], **dict.fromkeys(SLOTS))
        for i, q in enumerate(quotes, 1)]
    factors = [dict(kind=k, holder=[], respondent=[], neutral=[],
        unresolved=['身份、原件及行为均待核实。']) for k in KINDS]
    factors[0]['neutral'] = [dict(text='第一份记录身份不详；第二份为职员转述，均不能作已证事实。',
        statement_ids=['s1', 's2'], relation='recorded', dependencies=[])]
    value = dict(format_version='trademark-triage-v3', quotes=quotes,
        source_statements=statements, factors=factors, gaps=['补齐原件及陈述者身份。'])
    statements[1].update(speaker=span(value, 'q2', '虚构职员'),
        actor=span(value, 'q2', '澄原公司'), object=span(value, 'q2', '青禾牌'),
        event_time=span(value, 'q2', '2022年'), report_time=span(value, 'q2', '2025年3月'))
    return value
