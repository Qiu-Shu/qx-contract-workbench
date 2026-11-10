"""Engineering scores for annotated synthetic pages; never legal acceptance.

This deliberately narrow scorer expects one amount, one ISO date and one
prohibition. Ambiguous/split currency spans fail closed. It does not repair OCR.
Reports are evaluation dictionaries, not business DTOs or approval records.
"""
from collections import Counter
from datetime import date as calendar_date
from decimal import Decimal
import re
import unicodedata

VERSION = 'synthetic-ocr-v2'
NUMBER = r'[+\-]?[0-9]+(?:[.,][0-9]+)*'
DATE = r'[0-9]{4}-[0-9]{2}-[0-9]{2}'
TOKENS = re.compile(DATE + '|' + NUMBER + r'|[+\-.,]')
CURRENCY = re.compile(r'(?<![0-9.,+\-])(' + NUMBER + r')\s*(亿元|万元|元)(?![元万亿])')
DATE_TOKEN = re.compile(r'(?<![0-9.,+\-])' + DATE + r'(?![0-9.,]|-\d)')


def _blocks(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or not all(isinstance(x, str) for x in value):
        raise ValueError('text blocks required')
    if len(value) > 128 or sum(map(len, value)) > 4096:
        raise ValueError('synthetic score page exceeds text budget')
    return list(value)


def _field_text(text):
    # Keep spaces and block boundaries: fragmented digits are not one number.
    canonical = unicodedata.normalize('NFKC', text).translate(str.maketrans({'−': '-', '﹣': '-', '–': '-', '—': '-'}))
    return re.sub(r'([+\-])\s+(?=[0-9])', r'\1', canonical)


def _inventory(blocks):
    return Counter(token for block in blocks for token in TOKENS.findall(block))


def _fields(blocks, amount, unit, date, prohibition, reference):
    canonical = [_field_text(block) for block in blocks]
    candidates = []
    for index, block in enumerate(canonical):
        for match in CURRENCY.finditer(block):
            token, seen_unit = match.groups()
            # Multiple separators or comma notation are ambiguous, never guessed.
            valid = re.fullmatch(r'[+\-]?[0-9]+(?:\.[0-9]+)?', token) is not None
            candidates.append({'block': index, 'text': match.group(), 'value': token,
                               'unit': seen_unit, 'sign': '-' if token.startswith('-') else '+',
                               'value_match': valid and Decimal(token).copy_abs() == Decimal(amount).copy_abs(),
                               'sign_match': token.startswith('-') == amount.startswith('-'),
                               'unit_match': seen_unit == unit})
    unique = len(candidates) == 1
    money = {'expected': {'value': amount, 'unit': unit}, 'observed': candidates,
             'single_occurrence': unique,
             'value_match': unique and candidates[0]['value_match'],
             'sign_match': unique and candidates[0]['sign_match'],
             'unit_match': unique and candidates[0]['unit_match']}
    money['match'] = all(money[key] for key in ('single_occurrence', 'value_match', 'sign_match', 'unit_match'))
    dates = [token for block in canonical for token in DATE_TOKEN.findall(block)]
    phrases = sum(block.count(prohibition) for block in canonical)
    inventory = _inventory(canonical)
    expected_inventory = _inventory([_field_text(block) for block in reference])
    return {'amount': money,
            'date': {'expected': date, 'observed': dates, 'match': dates == [date]},
            'prohibition': {'expected': prohibition, 'occurrences': phrases, 'match': phrases == 1},
            'numeric_inventory': {'expected': dict(expected_inventory), 'observed': dict(inventory),
                                  'match': inventory == expected_inventory}}


def character_errors(reference, recognized):
    """Levenshtein errors from reference to hypothesis; diagonal wins ties.

CER is a decimal string plus exact numerator/denominator, and can exceed one.
Empty references are invalid, including for aggregate denominators.
"""
    if not isinstance(reference, str) or not reference or not isinstance(recognized, str):
        raise ValueError('nonempty reference and recognized text required')
    if max(len(reference), len(recognized)) > 4224:
        raise ValueError('synthetic character metric exceeds text budget')
    # (distance, substitutions, deletions, insertions), one DP row in memory.
    previous = [(j, 0, 0, j) for j in range(len(recognized) + 1)]
    for i, expected in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, actual in enumerate(recognized, 1):
            diagonal = previous[j - 1]
            deletion, insertion = previous[j], current[j - 1]
            choices = [
                (diagonal[0] + (expected != actual), diagonal[1] + (expected != actual), diagonal[2], diagonal[3]),
                (deletion[0] + 1, deletion[1], deletion[2] + 1, deletion[3]),
                (insertion[0] + 1, insertion[1], insertion[2], insertion[3] + 1),
            ]
            current.append(min(choices, key=lambda item: item[0]))
        previous = current
    distance, substitutions, deletions, insertions = previous[-1]
    return {'distance': distance, 'substitutions': substitutions, 'deletions': deletions,
            'insertions': insertions, 'reference_characters': len(reference),
            'recognized_characters': len(recognized), 'cer': str(Decimal(distance) / Decimal(len(reference))),
            'exact': distance == 0}


def score_page(blocks, *, reference_blocks, amount, unit, date, prohibition):
    blocks, reference = _blocks(blocks), _blocks(reference_blocks)
    if (not isinstance(amount, str) or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', amount)
            or len(amount) > 40 or unit not in ('元', '万元', '亿元')
            or not isinstance(prohibition, str) or not prohibition.strip()):
        raise ValueError('explicit amount, currency unit and prohibition required')
    if not isinstance(date, str) or calendar_date.fromisoformat(date).isoformat() != date:
        raise ValueError('ISO date required')
    if not reference or not ''.join(reference).strip():
        raise ValueError('nonempty complete reference required')
    expected = _fields(reference, amount, unit, date, prohibition, reference)
    if not all(item['match'] for item in expected.values()):
        raise ValueError('reference and annotated fields disagree')
    fields = _fields(blocks, amount, unit, date, prohibition, reference)
    raw_reference, raw_text = '\n'.join(reference), '\n'.join(blocks)
    compact = lambda text: ''.join(text.split())
    return {'version': VERSION, 'scope': 'annotated_single_amount_synthetic_page_only',
            'fields': fields, 'fields_match': all(item['match'] for item in fields.values()),
            'full_text': {'raw': character_errors(raw_reference, raw_text),
                          'layout_normalized': character_errors(compact(raw_reference), compact(raw_text))}}


def summarize_scores(scores):
    """Micro-average characters over scored pages; failures stay in page counts."""
    scored = [score for score in scores if score is not None]
    if any(score['version'] != VERSION for score in scored):
        raise ValueError('cannot mix scorer versions')
    metrics = {}
    for kind in ('raw', 'layout_normalized'):
        totals = {key: sum(score['full_text'][kind][key] for score in scored)
                  for key in ('distance', 'substitutions', 'deletions', 'insertions',
                              'reference_characters', 'recognized_characters')}
        denominator = totals['reference_characters']
        totals['cer'] = str(Decimal(totals['distance']) / Decimal(denominator)) if denominator else None
        totals['exact_pages'] = sum(score['full_text'][kind]['exact'] for score in scored)
        metrics[kind] = totals
    return {'version': VERSION, 'pages': len(scores), 'scored_pages': len(scored),
            'unscored_pages': len(scores) - len(scored),
            'field_matches': sum(score['fields_match'] for score in scored),
            'field_matches_by_kind': {key: sum(score['fields'][key]['match'] for score in scored)
                                      for key in ('amount', 'date', 'prohibition', 'numeric_inventory')},
            'full_text': metrics}
