"""Prepare fixed, fictional A/B inputs only; no provider, account or transport.

This is a prompt/protocol ablation, not a replay of the whole historical app.
References are logical fixture paragraphs, not parsed DOCX/PDF evidence.
"""
import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cn_contract import domain as d
from cn_contract.assistant import case_evidence, contract_review, criminal_analysis, material_codec, trademark_triage
from cn_contract.assistant.providers.policy import encoded, sha

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/legal_method_ab/cases.json'
GUIDE = ROOT / 'docs/testing/legal-method-ab/README.md'
RUBRIC = ROOT / 'docs/testing/legal-method-ab/rubric.md'
CASE_IDS = ('chronology', 'brief_section', 'criminal_case', 'defense_strategy', 'commercial_review', 'trademark_triage')
METHOD_FIELDS = ('case_method', 'criminal_analysis', 'contract_review', 'trademark_triage')
EXPECTED = dict(zip(CASE_IDS, (
    'case-evidence-v1', 'case-evidence-v1', 'criminal-analysis-v1',
    'criminal-analysis-v1', 'contract-review-v1', 'trademark-triage-v1')))


def json_data(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load_cases():
    value = json.loads(FIXTURE.read_bytes())
    if value['version'] != 'legal-method-ab-v1' or value['synthetic'] is not True:
        raise ValueError('FIXTURE_INVALID')
    cases = value['cases']
    if tuple(case['id'] for case in cases) != CASE_IDS:
        raise ValueError('FIXTURE_INVALID')
    return cases


def validate_case(case):
    if (case['id'] not in EXPECTED or case['expected_method'] != EXPECTED[case['id']]
            or case['workflow'] != ('contract' if case['id'] == 'commercial_review' else 'case')):
        raise ValueError('FIXTURE_INVALID')
    documents = {item['id']: item for item in case['documents']}
    if (len(documents) != len(case['documents']) or not documents
            or any(not re.fullmatch(r'd[1-9][0-9]*', key) for key in documents)
            or any(not item['paragraphs'] or any(not isinstance(p, str) or not p.strip()
                for p in item['paragraphs']) for item in documents.values())):
        raise ValueError('FIXTURE_INVALID')
    keys = [item['id'] for item in case['checkpoints']]
    if len(keys) < 4 or len(keys) != len(set(keys)):
        raise ValueError('CHECKPOINT_INVALID')
    for checkpoint in case['checkpoints']:
        if not checkpoint['refs']:
            raise ValueError('CHECKPOINT_INVALID')
        for ref in checkpoint['refs']:
            doc = documents.get(ref['document_id'])
            number, quote = ref['paragraph'], ref['exact_quote']
            if (doc is None or type(number) is not int or not 1 <= number <= len(doc['paragraphs'])
                    or not isinstance(quote, str) or not quote.strip()
                    or doc['paragraphs'][number - 1].count(quote) != 1):
                raise ValueError('CHECKPOINT_INVALID')


def fixture_manifest(case):
    """Reuse business DTOs with explicitly synthetic, deterministic references."""
    validate_case(case)
    uid = lambda name: uuid5(NAMESPACE_URL, 'qx/legal-method-ab-v1/' + case['id'] + '/' + name)
    cid = uid('conversation')
    question = case['question']
    message = d.ProfileMessageRef(kind='message', conversation_id=cid, message_id=uid('question'),
        source_revision=1, start=0, end=len(question), quote=question, quote_sha256=sha(question))
    sources = [d.MainMaterialSource(source_id=sha(encoded(message)), reference=message)]
    materials = []
    for document in case['documents']:
        attachment = uid(document['id'])
        original_sha = sha256(json_data(document)).hexdigest()
        result_sha = sha256(json_data(document['paragraphs'])).hexdigest()
        part = 'synthetic/paragraphs.json'
        materials.append(d.MainMaterialFile(attachment_id=attachment, name=document['title'] + '.json',
            original_sha256=original_sha, parse_revision=1, result_sha256=result_sha,
            reading_status='readable', pages=(), parts=(part,), unread_parts=(), quality_issues=()))
        for index, text in enumerate(document['paragraphs'], 1):
            anchor = d.Anchor(id=uid(document['id'] + '/p' + str(index)), document_version_id=attachment,
                part_name=part, element_id='p' + str(index), kind='body_paragraph', quote=text,
                quote_sha256=sha(text), start=0, end=len(text), table=None, row=None, cell=None, page=None, bbox=None)
            ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=attachment,
                original_sha256=original_sha, parse_revision=1, result_sha256=result_sha, anchor=anchor)
            sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref))
    return d.MainMaterialManifest(workflow=case['workflow'], stable_task_id=uid('task'),
        parent_business_run_id=uid('parent'), question=question, materials=tuple(materials), sources=tuple(sources))


def prepare_pair(case):
    base = fixture_manifest(case)
    if case['expected_method'] == 'case-evidence-v1':
        field, snapshot = 'case_method', case_evidence.select_method(base.workflow, base.question,
            method_id=case['expected_method'])
    elif case['expected_method'] == 'criminal-analysis-v1':
        field, snapshot = 'criminal_analysis', criminal_analysis.select_method(base.workflow, base.question, base.sources)
    elif case['expected_method'] == 'contract-review-v1':
        field, snapshot = 'contract_review', contract_review.select_method(base.workflow, base.materials, base.sources,
            method_id=case['expected_method'])
    else:
        field, snapshot = 'trademark_triage', trademark_triage.select_method(base.workflow, base.question,
            method_id=case['expected_method'])
    if snapshot is None or snapshot.method_id != case['expected_method']:
        raise ValueError('METHOD_NOT_SELECTED')
    enhanced = d.MainMaterialManifest.model_validate({**base.model_dump(mode='python'), field: snapshot})
    # Synthetic rates identify local construction only, never actual provider prices.
    config = d.MainModelConfig(enabled=False, model='deepseek-flash', max_output_tokens=8192,
        input_usd_per_million='1', output_usd_per_million='1', price_reference='fictional fixture rates; no billing')
    return {'A': material_codec.build_manifest_request(base, config),
            'B': material_codec.build_manifest_request(enhanced, config)}


def write_package(output):
    files = {'README.md': GUIDE.read_bytes(), 'reviewer/rubric.md': RUBRIC.read_bytes()}
    scorecard = ['# AI 独立评分记录', '', '用户已指定由 Codex 评分，另请独立评审复核。模型结果尚未生成；以下全部留空。协调人另存身份映射。', '',
        '评审编号：________　日期：________　结果文件摘要：________', '',
        '| 场景 | 匿名成果 | 重复序号 | 成果 SHA-256 | 事实 | 定位 | 法律依据 | 争点 | 反方 | 可用性 | 风险控制 | 用时分钟 | 硬伤及出处 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    checkpoints = ['# 材料核对清单', '', '仅给评审者。检查点是材料阅读线索，未经律师审定，不是法律标准答案。不得装入模型输入。', '']
    status = {'version': 'legal-method-ab-v1', 'preparation': 'PREPARED_INPUTS', 'case_count': 6,
        'request_count': 12, 'model_calls': 0, 'model_evaluation': 'NOT_RUN', 'lawyer_evaluation': 'NOT_RUN',
        'reviewer_type': 'AI', 'ai_evaluation': 'NOT_RUN', 'scores': None, 'quality_decision': 'PENDING', 'cases': []}
    for case in load_cases():
        pair = prepare_pair(case)
        key = case['id']
        material_lines = ['# ' + case['title'], '', '本文件全部为独立虚构材料。不是现实人物、合同或案件。', '',
            '## 本次指令', '', case['question'], '']
        for document in case['documents']:
            files[f'inputs/{key}/{document["id"]}.json'] = json_data(document)
            material_lines += ['## ' + document['id'] + ' ' + document['title'], '']
            material_lines += [f'第{i}段：{text}\n' for i, text in enumerate(document['paragraphs'], 1)]
        files[f'inputs/{key}/materials.md'] = '\n'.join(material_lines).encode('utf-8')
        for arm, wire in pair.items():
            files[f'coordinator/requests/{key}/{arm}.json'] = json_data(wire)
        manifest = fixture_manifest(case)
        by_attachment = {item.attachment_id: document['id'] for item, document in zip(manifest.materials, case['documents'])}
        source_index = {s.source_id: {'document_id': by_attachment[s.reference.attachment_id],
            'paragraph': int(s.reference.anchor.element_id[1:]), 'quote': s.reference.anchor.quote}
            for s in manifest.sources if s.reference.kind == 'document'}
        files[f'inputs/{key}/source-index.json'] = json_data({
            'origin': 'constructed_fixture_not_parsed_document', 'sources': source_index})
        checkpoints += ['## ' + key + ' ' + case['title'], '']
        for point in case['checkpoints']:
            checkpoints += ['- ' + point['id'] + ' ' + point['text']]
            for ref in point['refs']:
                text = next(doc for doc in case['documents'] if doc['id'] == ref['document_id'])['paragraphs'][ref['paragraph'] - 1]
                start = text.index(ref['exact_quote'])
                checkpoints += [f'  - {ref["document_id"]} 第{ref["paragraph"]}段，字符 [{start}, {start + len(ref["exact_quote"])}): 「{ref["exact_quote"]}」']
        checkpoints += ['']
        for label in ('X', 'Y'):
            scorecard += [f'| {key} | {label} | | | | | | | | | | | |']
        status['cases'].append({'id': key, 'method': case['expected_method'], 'baseline': 'NOT_RUN',
            'enhanced': 'NOT_RUN', 'legal_gold': 'UNAPPROVED', 'live_gate':
            'BLOCKED_SYNTHETIC_ONLY' if key in ('criminal_case', 'defense_strategy') else 'AWAIT_APPROVED_RUNNER_AND_BUDGET'})
    scorecard += ['', '每个场景另记：引用抽查正确数/抽查总数；已读全文是否齐全；遗漏/幻觉及对应原文；X/Y偏好及理由。',
        '其他记录：________', '', '分歧复核及开发保留/修改/停用建议：________（不代表律师签发或生产验收）', '']
    files['reviewer/checkpoints.md'] = '\n'.join(checkpoints).encode('utf-8')
    files['reviewer/scorecard.md'] = '\n'.join(scorecard).encode('utf-8')
    files['status.json'] = json_data(status)
    source_files = [FIXTURE, GUIDE, RUBRIC, Path(__file__), ROOT / 'src/cn_contract/domain.py']
    source_files += sorted((ROOT / 'src/cn_contract/assistant').rglob('*.py'))
    files['coordinator/source-snapshot.json'] = json_data({
        p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in source_files})
    files['sha256.json'] = json_data({name: sha256(data).hexdigest() for name, data in sorted(files.items())})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='仅准备独立虚构对照输入，不调用模型、不计算律师分数')
    parser.add_argument('--output', type=Path, required=True, help='新的输出目录；拒绝覆盖已有目录')
    args = parser.parse_args()
    print(json.dumps(write_package(args.output), ensure_ascii=False))
