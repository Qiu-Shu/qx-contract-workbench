"""Over-limit renders keep the disclaimer head, the caveat block and the method sources."""
import importlib

from cn_contract import domain as d
from cn_contract.assistant.render_budget import (
    HEAD_KEEP_LINES,
    MAX_RENDER_CHARS,
    NOTICE_CAVEATS,
    NOTICE_MIDDLE,
    NOTICE_SOURCES,
    bounded,
)
from tests.helpers.contract_review import draft_for
from tests.unit.test_contract_live_method import sample

HEAD = '\n'.join([
    '合同组合审查草稿｜未签发｜待律师核实',
    '红色：建议升级律师处理',
    '聊天材料流程未接入经核验的律师批准标准，绿色关闭；以下标准立场均为候选。',
    '引文位置已校验，不代表分析正确、法律有效或可签署。',
    '我方角色：供应方',
    '立场来源：[' + 'a' * 64 + ']',
])
CAVEAT_MARKER = '\n覆盖缺口与待核事项'
SOURCES_MARKER = '\n本次已载入方法来源（固定版本）'
SOURCES = SOURCES_MARKER + '\n合同组合｜SHA-256 ' + 'b' * 64 + '｜示例来源｜许可：CC-BY-4.0'


def _caveats(items):
    """Build a contract-shaped caveat block from ``items``."""
    return CAVEAT_MARKER + ''.join('\n待核：' + item for item in items)


def _gaps(count, width=1000):
    """Build ``count`` distinct gap strings of exactly ``width`` characters."""
    gaps = []
    for number in range(count):
        label = '待核事项' + str(number) + '：'
        filler = ('虚构独立待核事项。' * width)[:width - len(label)]
        gaps.append(label + filler)
    return gaps


def _head_of(text):
    """Return the first ``HEAD_KEEP_LINES`` lines of ``text``."""
    return '\n'.join(text.split('\n')[:HEAD_KEEP_LINES])


def _middle_section(text):
    """Return the part of ``text`` that sits between the head and the caveats."""
    start = 0
    for _ in range(HEAD_KEEP_LINES):
        found = text.find('\n', start)
        if found < 0:
            return ''
        start = found + 1
    ends = [index for index in (text.find(CAVEAT_MARKER), text.find(NOTICE_MIDDLE),
        text.find(SOURCES_MARKER)) if index >= 0]
    return text[start:min(ends)] if ends else text[start:]


def _visible_gaps(text):
    """Return the gap lines still shown in the caveat block of ``text``."""
    start = text.find(CAVEAT_MARKER)
    if start < 0:
        return 0
    end = text.find(SOURCES_MARKER, start)
    block = text[start:] if end < 0 else text[start:end]
    return block.count('\n待核：')


def test_text_within_the_limit_is_returned_as_the_same_object():
    text = '案件整理候选｜待律师核实\n' + '短正文。' * 10
    assert bounded(text) is text
    exact = '正' * MAX_RENDER_CHARS
    assert bounded(exact) is exact


def test_over_limit_result_stays_within_the_budget():
    text = HEAD + _caveats(_gaps(20)) + SOURCES
    assert len(text) > MAX_RENDER_CHARS
    assert len(bounded(text)) <= MAX_RENDER_CHARS


def test_disclaimer_head_survives_verbatim():
    text = HEAD + '\n' + '\n'.join('条目' + str(number) + '：' + '虚构正文。' * 40
        for number in range(400)) + _caveats(_gaps(20)) + SOURCES
    result = bounded(text)
    assert len(result) <= MAX_RENDER_CHARS
    assert _head_of(result) == HEAD
    assert '引文位置已校验，不代表分析正确' in result
    assert '我方角色：供应方' in result


def test_method_sources_survive_verbatim_at_the_end():
    text = HEAD + '\n' + '\n'.join('条目' + str(number) + '：' + '虚构正文。' * 40
        for number in range(400)) + _caveats(_gaps(20)) + SOURCES
    result = bounded(text)
    assert result.endswith(SOURCES)
    assert SOURCES in result[result.find(CAVEAT_MARKER):]


def test_caveat_notice_reports_the_real_number_of_hidden_items():
    total = 20
    body = '\n'.join('条目' + str(number) + '：' + '虚构正文。' * 40 for number in range(400))
    text = HEAD + '\n' + body + _caveats(_gaps(total)) + SOURCES
    assert len(text) > MAX_RENDER_CHARS
    result = bounded(text)
    shown = _visible_gaps(result)
    assert 0 < shown < total, 'the caveat block must be cut by whole items'
    assert NOTICE_CAVEATS.format(count=total - shown) in result
    assert NOTICE_CAVEATS.format(count=total - shown + 1) not in result
    assert '\n待核：待核事项0：' in result, 'the first gap stays visible, in order'


def test_middle_notice_appears_when_the_body_is_cut():
    body = '\n'.join('条目' + str(number) + '：' + '虚构正文。' * 40 for number in range(400))
    text = HEAD + '\n' + body + _caveats(['待核一']) + SOURCES
    result = bounded(text)
    assert NOTICE_MIDDLE in result
    assert len(result) <= MAX_RENDER_CHARS


def test_a_body_longer_than_the_budget_keeps_every_kept_line_whole():
    dropped = '乙' * 300
    lines = ['甲' * 200] * 40 + [dropped] + ['丙' * 200] * 80
    text = HEAD + '\n' + '\n'.join(lines) + _caveats(['待核一']) + SOURCES
    result = bounded(text)
    kept = [line for line in _middle_section(result).split('\n') if line]
    assert 0 < len(kept) < len(lines), 'the body must actually be cut'
    assert all(line in set(lines) for line in kept), 'no kept line may be a partial line'


def test_a_single_line_longer_than_the_budget_is_dropped_whole():
    text = HEAD + '\n' + '乙' * 25000 + _caveats(['待核一']) + SOURCES
    result = bounded(text)
    assert len(result) <= MAX_RENDER_CHARS
    assert '乙' not in result, 'a line that cannot fit is dropped whole, never halved'
    assert NOTICE_MIDDLE in result
    assert result.endswith(SOURCES)


def test_bounding_is_idempotent():
    text = HEAD + _caveats(_gaps(20)) + SOURCES
    once = bounded(text)
    twice = bounded(once)
    assert twice == once
    assert twice is once


def test_text_without_any_closing_marker_is_still_bounded():
    text = HEAD + '\n' + '\n'.join('行' + str(number) + '：' + '无标记正文。' * 20
        for number in range(400))
    result = bounded(text)
    assert len(result) <= MAX_RENDER_CHARS
    assert _head_of(result) == HEAD
    assert NOTICE_MIDDLE in result


def test_oversized_method_sources_keep_their_newest_whole_lines():
    licences = ['许可：CC-BY-4.0 第' + str(number) + '行 ' + '丁' * 100 for number in range(200)]
    sources = SOURCES_MARKER + '\n' + '\n'.join(licences)
    text = HEAD + '\n' + '正文行。' * 2000 + _caveats(_gaps(5)) + sources
    assert len(HEAD) + len(sources) > MAX_RENDER_CHARS
    result = bounded(text)
    assert len(result) <= MAX_RENDER_CHARS
    assert NOTICE_SOURCES in result
    assert result.startswith(HEAD)
    assert result.endswith(licences[-1]), 'the newest license lines are the ones kept'


def test_oversized_single_line_method_sources_never_raise():
    sources = SOURCES_MARKER + '\n' + '丁' * 25000
    text = HEAD + '\n' + '正文行。' * 2000 + _caveats(_gaps(5)) + sources
    result = bounded(text)
    assert len(result) <= MAX_RENDER_CHARS
    assert NOTICE_SOURCES in result
    assert '丁' not in result, 'a source block with no line boundary cannot be kept'
    assert result.startswith(HEAD)


def test_contract_builder_keeps_a_schema_legal_over_limit_draft_readable():
    """The reported bug: 20 gaps of 1000 characters is legal input, yet it exceeded the limit."""
    builder = importlib.import_module('cn_contract.assistant.contract_review')
    manifest, _, _ = sample()
    manifest = manifest.model_copy(update={'contract_review': builder.select_method(
        manifest.workflow, manifest.materials, manifest.sources)})
    value = draft_for(manifest)
    value['gaps'] = _gaps(20)
    draft = d.ContractReviewDraft.model_validate(value)
    assert all(len(gap) <= 1000 for gap in draft.gaps)
    raw = builder._render(draft, manifest, {quote.id: quote for quote in draft.quotes})
    assert len(raw) > MAX_RENDER_CHARS
    candidate = builder.candidate(value, manifest)
    text = candidate.text
    assert len(text) <= MAX_RENDER_CHARS
    assert _head_of(text) == _head_of(raw), 'the disclaimer head must be verbatim'
    assert '引文位置已校验，不代表分析正确' in text
    assert '我方角色：' in text
    sources = raw[raw.index(SOURCES_MARKER):]
    assert text.endswith(sources), 'the method-source block must stay verbatim at the end'
    shown = _visible_gaps(text)
    total = len(draft.gaps)
    assert shown < total
    assert NOTICE_CAVEATS.format(count=total - shown) in text
    assert '另有' in text and '条待核事项未在正文显示' in text
    assert candidate.contract_review is not None
