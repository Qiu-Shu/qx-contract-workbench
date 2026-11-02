"""Independent fictional documents for unified retrieval, no private originals."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from docx import Document
from cn_contract.reception.knowledge import import_plugin
from tests.unit.test_skill_registry import package

ROOT=Path(__file__).resolve().parents[2]

def knowledge_config(tmp_path, *, public=False):
    bindings=[package(tmp_path,'sales'),package(tmp_path,'case')]
    archive=tmp_path/'synthetic-reception.zip'
    originals=[]
    with ZipFile(archive,'w') as zipped:
        for index in range(8):
            document=Document();document.add_paragraph(f'合成接待资料{index}：借款咨询先核对材料和客户诉求，不承诺结果。')
            stream=BytesIO();document.save(stream);originals.append(stream.getvalue())
            zipped.writestr(f'skills/instructions/references/接待{index}.docx',originals[-1])
        zipped.writestr('skills/instructions/references/接待重复别名.docx',originals[0])
    reception=tmp_path/'reception-knowledge'
    import_plugin(archive,reception)
    family=Path(bindings[1]['root'])/'skills/instructions/references'
    family.mkdir()
    pins=[]
    for index in range(5):
        path=family/f'{index:02}-合成办案.txt'
        path.write_text(f'独立虚构办案资料{index}：借款争议需要整理证据、时间线与待补材料。',encoding='utf-8')
        pins.append(dict(path=str(path.relative_to(bindings[1]['root'])).replace('\\','/'),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    knowledge=dict(local_use_approved=True,reception_root=str(reception),
        reception_manifest_sha256=hashlib.sha256((reception/'manifest.json').read_bytes()).hexdigest(),family_files=pins)
    if public:
        engine=ROOT/'.local/integrations/chiheng-legal-workbench'
        corpus=tmp_path/'synthetic-law.json'
        corpus.write_text(json.dumps(dict(laws={'synthetic-law':dict(title='合成借款规则（非真实法律）',group='合成',status='待核',
            effective_date='',urls=['https://example.invalid/synthetic-law'],
            provisions=[dict(article='合成第一条',text='合成借款规则仅用于工程检索测试，不是真实法律。')])}),ensure_ascii=False),encoding='utf-8')
        knowledge['public_law']=dict(adapter_root=str(engine),adapter_sha256=hashlib.sha256((engine/'shared_corpus.py').read_bytes()).hexdigest(),
            corpus_path=str(corpus),corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
            source_reference='https://github.com/Qiu-Shu/chiheng-legal-workbench',version='8a0d640bb58c82b909409a2e689a6cecd7f06058')
    return dict(schema_version=1,skills=bindings,knowledge=knowledge)
