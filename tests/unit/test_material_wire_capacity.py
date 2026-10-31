"""Complete independently fictional source manifests use a bounded main-model wire."""
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.assistant import material_codec
from cn_contract.assistant.providers.policy import encoded, sha


def fictional_manifest(paragraphs=105):
    cid, attachment, parent = uuid4(), uuid4(), uuid4()
    sentence = '独立虚构甲乙双方约定交货验收支付价款履行义务违约通知。'
    content = (sentence * (7133 // len(sentence) + 1))[:7133]
    question = '我们是甲方 合同审查'
    current = d.ProfileMessageRef(kind='message',conversation_id=cid,message_id=uuid4(),source_revision=1,
        start=0,end=len(question),quote=question,quote_sha256=sha(question))
    sources = [d.MainMaterialSource(source_id=sha(encoded(current)),reference=current)]
    for index in range(paragraphs):
        quote = content[len(content)*index//paragraphs:len(content)*(index+1)//paragraphs]
        anchor = d.Anchor(id=uuid4(),document_version_id=attachment,part_name='word/document.xml',
            element_id=f'p:{index}',kind=d.AnchorKind.BODY_PARAGRAPH,quote=quote,quote_sha256=sha(quote),
            start=0,end=len(quote),table=None,row=None,cell=None,page=None,bbox=None)
        ref = d.ProfileDocumentRef(kind='document',conversation_id=cid,attachment_id=attachment,
            original_sha256='a'*64,parse_revision=1,result_sha256='b'*64,anchor=anchor)
        sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)),reference=ref))
    material = d.MainMaterialFile(attachment_id=attachment,name='独立虚构分段合同.docx',original_sha256='a'*64,
        parse_revision=1,result_sha256='b'*64,reading_status='readable',pages=(),parts=('word/document.xml',),
        unread_parts=(),quality_issues=())
    return d.MainMaterialManifest(workflow='contract',stable_task_id=uuid4(),parent_business_run_id=parent,
        question=question,materials=(material,),sources=tuple(sources)), content


def configuration(**changes):
    return d.MainModelConfig(enabled=True,model='deepseek-flash',input_usd_per_million='0.3',
        output_usd_per_million='1.2',price_reference='fictional-capacity',**changes)


def test_default_accepts_complete_105_paragraph_7133_character_material():
    manifest, content = fictional_manifest()
    body = material_codec.build_manifest_request(manifest,configuration())
    wire = material_codec.json_bytes(body)
    assert 65536 < len(wire) <= 262144
    sent = json.loads(body['messages'][1]['content'])
    assert len(sent['sources']) == 106
    assert ''.join(item['reference']['anchor']['quote'] for item in sent['sources'][1:]) == content


def test_explicit_smaller_scope_and_over_cap_material_still_reject_whole_selection():
    manifest, _ = fictional_manifest()
    with pytest.raises(ValueError,match='MATERIAL_INPUT_TOO_LARGE'):
        material_codec.build_manifest_request(manifest,configuration(max_input_bytes=65536))
    manifest, _ = fictional_manifest(400)
    with pytest.raises(ValueError,match='MATERIAL_INPUT_TOO_LARGE'):
        material_codec.build_manifest_request(manifest,configuration())
    assert len(manifest.sources) == 401
    with pytest.raises(ValidationError):configuration(max_input_bytes=262145)
