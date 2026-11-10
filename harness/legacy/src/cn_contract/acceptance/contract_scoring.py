"""Offline checks of synthetic contract outputs, never legal/model approval.

Like ocr_scoring, these dictionaries are engineering reports, not business DTOs.
Narrative judgments come from separate human annotations, not model self-grading.
"""
from copy import deepcopy
import hashlib
import json

VERSION = 'synthetic-contract-v2'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _ids(value):
    return isinstance(value, list) and all(_text(x) for x in value) and len(value) == len(set(value))


def _sources(case, expected):
    if not isinstance(case, dict) or not _text(case.get('id')):
        raise ValueError('synthetic case id required')
    entries = case.get('anchors')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise ValueError('bounded nonempty source anchors required')
    anchors = {}
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {'id', 'quote'}
                or not _text(entry['id']) or not _text(entry['quote']) or entry['id'] in anchors):
            raise ValueError('invalid or duplicate source anchor')
        anchors[entry['id']] = entry['quote']
    if not isinstance(expected, dict):
        raise ValueError('expected relationships must be a dictionary')
    for kind, rule in expected.items():
        if (not _text(kind) or not isinstance(rule, dict) or set(rule) != {'required', 'optional'}
                or not _ids(rule['required']) or not rule['required'] or not _ids(rule['optional'])):
            raise ValueError('invalid relationship expectation')
        required, optional = set(rule['required']), set(rule['optional'])
        if required & optional or not (required | optional) <= anchors.keys():
            raise ValueError('invalid expectation anchor references')
    return anchors


def _refutations(case, answer, anchors, annotations):
    if not isinstance(annotations, (list, tuple)) or len(annotations) > 256:
        raise ValueError('bounded manual annotations required')
    for note in annotations:
        fields = {'source_sha256', 'answer_sha256', 'issue_index', 'field', 'claim_quote', 'evidence', 'note'}
        if not isinstance(note, dict) or set(note) != fields:
            raise ValueError('invalid annotation fields')
        if note['source_sha256'] != fingerprint(case) or note['answer_sha256'] != fingerprint(answer):
            raise ValueError('annotation does not match source and output bytes')
        issues = answer.get('issues') if isinstance(answer, dict) else None
        index = note['issue_index']
        if not isinstance(issues, list) or type(index) is not int or not 0 <= index < len(issues):
            raise ValueError('annotation issue does not exist')
        item = issues[index]
        if (note['field'] not in ('analysis', 'recommendation') or not isinstance(item, dict)
                or not isinstance(item.get(note['field']), str) or not _text(note['claim_quote'])
                or note['claim_quote'] not in item[note['field']] or not _text(note['note'])):
            raise ValueError('annotation claim is not in the selected output field')
        evidence = note['evidence']
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('annotation needs source evidence')
        ids = []
        for ref in evidence:
            if (not isinstance(ref, dict) or set(ref) != {'id', 'quote'} or not _text(ref['id'])
                    or ref['id'] not in anchors or ref['quote'] != anchors[ref['id']]):
                raise ValueError('annotation evidence does not match source')
            ids.append(ref['id'])
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate annotation evidence')
    return deepcopy(list(annotations))


def score_contract(case, answer, expected, *, contradictions=()):
    """Check exact evidence; keep additional observations and prose under review.

    `expected` and `contradictions` are evaluator-owned inputs, never read from
    model output. Validating a manual annotation binds it to evidence; it does
    not independently prove its semantic judgment. No result enables promotion.
    """
    anchors = _sources(case, expected)
    errors, queue, relations = [], [], {}
    seen, cited_by_kind = set(), {}
    answer_object = answer if isinstance(answer, dict) else {}
    if not isinstance(answer, dict) or set(answer) != {'examined_anchor_ids', 'formal_signoff', 'legal_status', 'issues'}:
        errors.append({'code': 'output_schema'})
    if answer_object.get('formal_signoff') is not False or answer_object.get('legal_status') != 'not_verified':
        errors.append({'code': 'approval_boundary'})
    examined = answer_object.get('examined_anchor_ids')
    if not _ids(examined) or set(examined) != anchors.keys():
        errors.append({'code': 'anchor_coverage'})
    issues = answer_object.get('issues')
    if not isinstance(issues, list) or len(issues) > 256:
        errors.append({'code': 'issues_schema'})
        issues = []
    for index, item in enumerate(issues):
        if (not isinstance(item, dict) or set(item) != {'kind', 'citations', 'analysis', 'recommendation'}
                or not all(_text(item.get(key)) for key in ('kind', 'analysis', 'recommendation'))):
            errors.append({'code': 'issue_schema', 'issue_index': index})
            continue
        kind = item['kind']
        duplicate_kind = kind in seen
        if duplicate_kind:
            errors.append({'code': 'duplicate_relationship', 'issue_index': index})
        seen.add(kind)
        refs = item['citations']
        if not isinstance(refs, list) or not 1 <= len(refs) <= 256:
            errors.append({'code': 'citations_schema', 'issue_index': index})
            refs = []
        ids, valid_ids = [], set()
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {'id', 'quote'} or not _text(ref.get('id')):
                errors.append({'code': 'citation_schema', 'issue_index': index})
                continue
            ids.append(ref['id'])
            if ref['id'] not in anchors or ref['quote'] != anchors[ref['id']]:
                errors.append({'code': 'citation_mismatch', 'issue_index': index, 'anchor_id': ref['id']})
            else:
                valid_ids.add(ref['id'])
        if len(ids) != len(set(ids)):
            errors.append({'code': 'duplicate_citation', 'issue_index': index})
        if not duplicate_kind:
            cited_by_kind[kind] = valid_ids
        if kind not in expected:
            queue.append({'issue_index': index, 'reason': 'additional_observation', 'kind': kind})
        else:
            allowed = set(expected[kind]['required']) | set(expected[kind]['optional'])
            extra = valid_ids - allowed
            if extra:
                queue.append({'issue_index': index, 'reason': 'additional_citations', 'anchor_ids': sorted(extra)})
    for kind, rule in expected.items():
        present = kind in cited_by_kind
        missing = set(rule['required']) - cited_by_kind.get(kind, set())
        relations[kind] = {'present': present, 'missing_anchor_ids': sorted(missing)}
        if not present or missing:
            errors.append({'code': 'missing_relationship_evidence', 'kind': kind})
    notes = _refutations(case, answer, anchors, contradictions)
    return {'version': VERSION, 'case_id': case['id'], 'engineering_passed': not errors,
            'errors': errors, 'relations': relations, 'review_queue': queue,
            'reasoning_status': 'contradicted' if notes else 'pending_manual_review',
            'contradictions': notes, 'legal_status': 'not_verified', 'promotion_allowed': False}
