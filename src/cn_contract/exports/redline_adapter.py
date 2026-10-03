"""G04 ins/del construction method independently adapted to exact server anchors.

No fuzzy search, python-docx rewrite of originals, global revision IDs or PDF.
"""
from io import BytesIO
import copy,hashlib,re,zipfile
from uuid import uuid4
from lxml import etree
from ..domain import PatchResult
from ..security import ServiceError
from ..persistence import read_version,read_original,configured_database
from ..documents.docx_adapter import read_package
from ..documents.ingest import _parse
from ..documents import resolve_anchor
from . import storage as s

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
NS={'w':W}
XMLSPACE='{http://www.w3.org/XML/1998/namespace}space'


def xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ServiceError('FILE_UNSUPPORTED',400)
    return etree.fromstring(raw,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False))


def _node(root,anchor):
    parts=anchor.element_id.split('/')
    if not parts or parts[0]!='body':return None
    node=root.find(f'{{{W}}}body')
    if node is None:return None
    for token in parts[1:]:
        match=re.fullmatch(r'([A-Za-z]+)\[(\d+)\]',token)
        if not match:return None
        children=node.findall(f'{{{W}}}{match[1]}')
        index=int(match[2])-1
        if index<0 or index>=len(children):return None
        node=children[index]
    return node


def preconditions(version,patch,actor,db,*,audience=None):
    patch,run,approval=s.load_patch(version.matter_id,patch,actor,db,audience=audience)
    actual=read_version(version.matter_id,version.id,actor,db)
    if actual!=version or actual.id!=patch.document_version_id or run.manifest.document_hashes.get(actual.id)!=actual.sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    data=read_original(actual.matter_id,actual.id,actor,db)
    parsed=_parse(data,actual,configured_database(db).settings)
    anchor=next((a for a in parsed.anchors if a.id==patch.anchor_id),None)
    finding=next((f for f in run.findings if f.id==patch.finding_id),None)
    if anchor is None or finding is None or anchor.id not in (*finding.anchor_ids,*finding.cross_anchor_ids):raise ServiceError('VERSION_CONFLICT',409)
    resolve_anchor(anchor,actual,actor=actor,db=db)
    if anchor.kind!='body_paragraph' or anchor.part_name!='word/document.xml':return data,anchor,'非普通正文段落 需要人工修改'
    if patch.old_text!=anchor.quote or anchor.start!=0 or anchor.end!=len(anchor.quote):return data,anchor,'旧文必须是完整锚点段落 不推断子串位置'
    package=read_package(data,configured_database(db).settings)[0]
    root=xml(package['word/document.xml']);node=_node(root,anchor)
    if node is None:return data,anchor,'结构定位不可确定'
    allowed={f'{{{W}}}p',f'{{{W}}}pPr',f'{{{W}}}r',f'{{{W}}}rPr',f'{{{W}}}t'}
    # Ordinary pPr/rPr properties are retained; no field/bookmark/hidden object
    # or existing revisions may be altered by the initial adapter.
    for element in node.iter():
        if element.tag in {f'{{{W}}}pPr',f'{{{W}}}rPr'}:continue
        parent=element.getparent()
        if parent is not None and parent.tag in {f'{{{W}}}pPr',f'{{{W}}}rPr'}:
            if element.tag in {f'{{{W}}}vanish',f'{{{W}}}webHidden',f'{{{W}}}rPrChange',f'{{{W}}}pPrChange'}:
                return data,anchor,'隐藏文本或已有格式修订需要人工修改'
            continue
        if element.tag not in allowed:return data,anchor,'复杂对象 字段 书签或已有修订需要人工修改'
    if ''.join(t.text or '' for t in node.findall('.//w:t',NS))!=anchor.quote:return data,anchor,'非纯文本段落需要人工修改'
    return data,anchor,None


def _revision_id(package):
    used=set()
    for name,raw in package.items():
        if name.endswith(('.xml','.rels')):
            for node in xml(raw).iter():
                value=node.get(f'{{{W}}}id')
                if value is not None:
                    try:used.add(int(value))
                    except ValueError:pass
    return max(used|{0})+1


def _replace(node,patch,next_id):
    runs=node.findall(f'{{{W}}}r')
    deleted=etree.Element(f'{{{W}}}del',attrib={f'{{{W}}}id':str(next_id),f'{{{W}}}author':'群兴工程 模拟修改建议',
        f'{{{W}}}date':s.now().isoformat().replace('+00:00','Z')})
    for original in runs:
        run=copy.deepcopy(original)
        for text in run.findall(f'{{{W}}}t'):
            text.tag=f'{{{W}}}delText';text.set(XMLSPACE,'preserve')
        deleted.append(run)
    inserted=etree.Element(f'{{{W}}}ins',attrib={f'{{{W}}}id':str(next_id+1),f'{{{W}}}author':'群兴工程 模拟修改建议',
        f'{{{W}}}date':s.now().isoformat().replace('+00:00','Z')})
    run=etree.SubElement(inserted,f'{{{W}}}r')
    if runs and runs[0].find(f'{{{W}}}rPr') is not None:run.append(copy.deepcopy(runs[0].find(f'{{{W}}}rPr')))
    text=etree.SubElement(run,f'{{{W}}}t');text.set(XMLSPACE,'preserve');text.text=patch.new_text
    index=node.index(runs[0]) if runs else len(node)
    for original in runs:node.remove(original)
    node.insert(index,deleted);node.insert(index+1,inserted)


def _watermark(package,root):
    name='t09Draft'
    header=f'word/{name}Header.xml';footer=f'word/{name}Footer.xml'
    if header in package or footer in package:raise ServiceError('VERSION_CONFLICT',409)
    for part,tag in [(header,'hdr'),(footer,'ftr')]:
        item=etree.Element(f'{{{W}}}{tag}',nsmap={'w':W})
        p=etree.SubElement(item,f'{{{W}}}p');run=etree.SubElement(p,f'{{{W}}}r')
        text=etree.SubElement(run,f'{{{W}}}t');text.text='DRAFT MOCK 模拟材料 不构成正式法律意见'
        package[part]=etree.tostring(item,encoding='UTF-8',xml_declaration=True,standalone=True)
    relationships=xml(package.get('word/_rels/document.xml.rels',f'<Relationships xmlns="{REL}"/>'.encode()))
    used={n.get('Id') for n in relationships}
    ids=[]
    for suffix,part,kind in [('Header',header,'header'),('Footer',footer,'footer')]:
        value='rIdT09Draft'+suffix
        if value in used:raise ServiceError('VERSION_CONFLICT',409)
        ids.append(value)
        etree.SubElement(relationships,f'{{{REL}}}Relationship',Id=value,Type=R+'/'+kind,Target=part.removeprefix('word/'))
    package['word/_rels/document.xml.rels']=etree.tostring(relationships,encoding='UTF-8',xml_declaration=True,standalone=True)
    sections=root.findall('.//w:sectPr',NS)
    if not sections:sections=[etree.SubElement(root.find('w:body',NS),f'{{{W}}}sectPr')]
    for section in sections:
        if section.findall('w:headerReference',NS) or section.findall('w:footerReference',NS):raise ServiceError('NOT_SUPPORTED',409)
        for kind,identifier in zip(('header','footer'),ids):
            section.insert(0,etree.Element(f'{{{W}}}{kind}Reference',attrib={f'{{{W}}}type':'default',f'{{{R}}}id':identifier}))
    types=xml(package['[Content_Types].xml'])
    for part,kind in [(header,'header'),(footer,'footer')]:
        etree.SubElement(types,f'{{{CT}}}Override',PartName='/'+part,ContentType=f'application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml')
    package['[Content_Types].xml']=etree.tostring(types,encoding='UTF-8',xml_declaration=True,standalone=True)


def build_redline(data,changes,settings):
    package=read_package(data,settings)[0]
    root=xml(package['word/document.xml']);next_id=_revision_id(package)
    for patch,anchor in changes:
        node=_node(root,anchor)
        if node is None:raise ServiceError('VERSION_CONFLICT',409)
        _replace(node,patch,next_id);next_id+=2
    _watermark(package,root)
    package['word/document.xml']=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
    output=BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as original,zipfile.ZipFile(output,'w') as target:
        for info in original.infolist():target.writestr(info,package.pop(info.filename))
        for name,raw in package.items():target.writestr(name,raw)
    return output.getvalue()


def baseline_texts(raw,*,accept):
    """Structural oracle only; native Word accept/reject is separate validation."""
    with zipfile.ZipFile(BytesIO(raw)) as archive:root=xml(archive.read('word/document.xml'))
    result=[]
    def text(node):
        if node.tag==f'{{{W}}}del' and accept or node.tag==f'{{{W}}}ins' and not accept:return ''
        if node.tag in {f'{{{W}}}t',f'{{{W}}}delText'}:return node.text or ''
        return ''.join(text(child) for child in node)
    for node in root.findall('w:body/w:p',NS):result.append(text(node))
    return result


def apply_patch(version,patch,*,actor,db):
    data,anchor,manual=preconditions(version,patch,actor,db)
    with db.begin_nested():
        if manual:
            s.append('patch_result',patch.id,{'status':'manual_required','reason':manual,'target_sha256':None},actor,version.matter_id,db)
            return PatchResult(status='manual_required',reason=manual,target_sha256=None)
        try:raw=build_redline(data,[(patch,anchor)],configured_database(db).settings)
        except ServiceError as error:
            if error.code!='NOT_SUPPORTED':raise
            return PatchResult(status='manual_required',reason='已有页眉页脚结构需要人工保真处理',target_sha256=None)
        digest=hashlib.sha256(raw).hexdigest();path=s.store_bytes(raw,uuid4(),db)
        s.append('patch_result',patch.id,{'status':'applied','reason':'完整正文锚点 原生模拟修订',
            'target_sha256':digest,'storage_ref':path},actor,version.matter_id,db)
        return PatchResult(status='applied',reason='完整正文锚点 原生模拟修订',target_sha256=digest)
