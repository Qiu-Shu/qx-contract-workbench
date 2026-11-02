"""Synthetic source-bound case replies; never a live model or client material."""
import json
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

from docx import Document

from cn_contract import domain as d
from cn_contract.assistant import attachments, service


def draft_for(manifest):
    source = next(item for item in manifest.sources if item.reference.kind == 'document'
        and '2026年1月3日甲向乙借款30000元' in item.reference.anchor.quote)
    quotation = '2026年1月3日甲向乙借款30000元'
    start = source.reference.anchor.quote.index(quotation)
    return {
        'format_version': 'case-evidence-v1',
        'quotes': [{'id': 'loan', 'source_id': source.source_id, 'start': start,
            'end': start + len(quotation), 'exact_quote': quotation}],
        'statements': [{'kind': 'source_statement', 'text': '材料记载甲向乙借款30000元。',
            'support': ['loan'], 'opposing': [], 'unresolved': ['核对借条原件及款项交付记录。']},
            {'kind': 'legal_analysis', 'text': '责任承担及适用依据仍需律师核验。',
                'support': [], 'opposing': [], 'unresolved': ['尚未核验法律依据。']}],
        'timeline': [{'id': 'loan_event', 'event_text': '材料记载借款行为。',
            'raw_date': '2026年1月3日', 'quote_ids': ['loan'], 'conflict_group': None,
            'uncertainty': '记载尚不等于款项已实际交付。'}],
        'gaps': ['还款转账凭证尚未提供。'],
    }


def response(value):
    return json.dumps({'id': 'fictional-case-evidence', 'object': 'chat.completion',
        'created': 1, 'model': 'deepseek-flash', 'choices': [{'index': 0,
            'finish_reason': 'stop', 'message': {'role': 'assistant',
                'content': json.dumps(value, ensure_ascii=False)}}],
        'usage': {'prompt_tokens': 30, 'completion_tokens': 12, 'total_tokens': 42}},
        ensure_ascii=False).encode('utf-8')


def add_document(w, paragraphs):
    database, actor, cid, _ = w
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    stream = BytesIO()
    document.save(stream)
    # Store fixture entries without compression; repeated synthetic text must
    # not exercise the separate decompression-ratio guard.
    unpacked = BytesIO()
    with ZipFile(stream) as source, ZipFile(unpacked, 'w', compression=ZIP_STORED) as target:
        for entry in source.infolist():
            target.writestr(entry.filename, source.read(entry))
    data = unpacked.getvalue()
    database._assistant_synthetic_hashes |= frozenset({sha256(data).hexdigest()})
    with database.session() as db:
        view = service.read_conversation(actor, cid, db)
    uploaded = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=view.scope, original_name='独立虚构补充材料.docx',
        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),
        BytesIO(data), database=database)
    with database.session() as db:
        view = service.read_conversation(actor, cid, db)
    attachments.parse_attachment(actor, cid, uploaded.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=view.scope,
            baseline_view=None), database=database)
