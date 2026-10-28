"""Render one saved internal material result using the existing Word draft style."""
import hashlib

from .. import domain as d
from ..config import canonical_json
from .assistant_docx import build as build_draft


def build(output):
    manifest = output.manifest
    files = {item.attachment_id:item for item in manifest.materials}
    notes = ['律师内部工作草稿，事实、依据与建议待律师核对；未修改原合同。', '材料目录']
    for item in manifest.materials:
        notes.append(f'{item.name}；解析版本 {item.parse_revision}；原件 SHA256 {item.original_sha256}')
        if item.unread_parts or item.quality_issues:
            notes.append('读取范围待核：'+'；'.join((*item.unread_parts, *item.quality_issues)))
        elif item.reading_status == 'partial':
            notes.append('材料仅部分可读，未读内容需补充核对。')
    if not manifest.materials:
        notes.append('本次仅依据已保存的咨询文字，未使用附件。')
    sources = {item.source_id:item.reference for item in manifest.sources}
    citations = []
    for identifier in output.candidate.citations:
        reference = sources[identifier]
        if isinstance(reference, d.ProfileDocumentRef):
            anchor = reference.anchor
            location = f'第 {anchor.page} 页' if anchor.page is not None else anchor.part_name+' · '+anchor.element_id
            citations.append(f'[{identifier}] {files[reference.attachment_id].name} · {location}\n原文：{anchor.quote}')
        else:
            citations.append(f'[{identifier}] 聊天原始陈述\n原文：{reference.quote}')
    title = {'sales':'接待意见草稿', 'case':'案件办理草稿', 'contract':'合同审查意见草稿', 'court':'庭审演练草稿'}[manifest.workflow]
    projection = dict(id=str(output.id), conversation_id=str(output.scope.conversation_id),
        selection=d.AssistantOutputSelection(source=d.AssistantOutputSource(kind='model', output_id=output.id), audience='internal').model_dump(mode='json'),
        title=title, source_label='已保存材料模型结果 · '+output.created_at.isoformat(),
        text=output.candidate.text, notes=tuple(notes), citations=tuple(citations))
    digest = hashlib.sha256(canonical_json(projection).encode('utf-8')).hexdigest()
    return build_draft(d.AssistantOutputPreview(**projection, content_sha256=digest))
