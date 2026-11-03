"""Parse in a separate process; PDF and plain text are indexed incrementally."""
from pathlib import Path
from io import BytesIO
import codecs
import ctypes
import json
import os
import sys
from uuid import UUID
from zipfile import ZipFile

LEGACY = Path('D:/qx-contract-workbench-20261102')
sys.path.insert(0,str(LEGACY/'src'))
from store import MaterialStore, material_extension

CHARS = 4000


def available_memory():
    if os.name=='nt':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
                ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
        state=Memory();state.length=ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):return state.avail_phys
    try:return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
    except (ValueError,AttributeError):return 1024**3


def text_encoding(path):
    with path.open('rb') as stream:sample=stream.read(65536)
    if sample.startswith((codecs.BOM_UTF16_LE,codecs.BOM_UTF16_BE)):return 'utf-16'
    for encoding in ('utf-8-sig','gb18030'):
        try:codecs.getincrementaldecoder(encoding)().decode(sample,final=False);return encoding
        except UnicodeDecodeError:continue
    raise ValueError('文本编码无法识别，请另存为 UTF-8 后重试。')


def docx_style_fallback(raw, revision_mode):
    """Read body text from the same package bytes already checked by parse_docx."""
    from docx_delivery import _paragraphs, _w, _xml
    from cn_contract.documents.docx_styles import EffectiveStyles, StyleDependencyError
    with ZipFile(BytesIO(raw)) as archive:
        root = _xml(archive.read('word/document.xml'))
        styles = EffectiveStyles(_xml(archive.read('word/styles.xml')) if 'word/styles.xml' in archive.namelist() else None)
    excluded = {'del', 'moveFrom'} if revision_mode == 'accepted_view' else {'ins', 'moveTo'}
    excluded.update({'drawing', 'pict', 'object'})
    excluded = {_w(tag) for tag in excluded}
    for _, paragraph in _paragraphs(root):
        if any(node.tag in excluded for node in paragraph.iterancestors()): continue
        tables = [node for node in paragraph.iterancestors() if node.tag == _w('tbl')]
        try:
            if any(styles.table_hidden(table) for table in tables): continue
        except StyleDependencyError:
            pass  # Unresolved inherited appearance is reported, not a reason to lose text.
        values = []
        for node in paragraph.iter():
            if node.tag not in {_w(tag) for tag in ('t', 'delText', 'tab', 'br', 'cr')}: continue
            ancestors = list(node.iterancestors())
            if next((a for a in ancestors if a.tag == _w('p')), None) is not paragraph: continue
            if any(a.tag in excluded for a in ancestors): continue
            run = next((a for a in ancestors if a.tag == _w('r')), None)
            if run is not None:
                try:
                    hidden = styles.run_hidden(paragraph, run)
                except StyleDependencyError:
                    # Still honour explicit hidden text even if its imported style is missing.
                    hidden = any(flag.get(_w('val'), 'true') in {'1', 'true', 'on'}
                                 for prop in run.findall(_w('rPr')) for flag in prop
                                 if flag.tag in {_w('vanish'), _w('webHidden')})
                if hidden: continue
            values.append(node.text or '' if node.tag in {_w('t'), _w('delText')}
                          else '\t' if node.tag == _w('tab') else '\n')
        value = ''.join(values)
        if value.strip(): yield value, 'word/document.xml:' + root.getroottree().getpath(paragraph)


def parse(store,path,start_page=1,page_count=20,force_ocr=False,revision_mode='original'):
    if start_page<1 or page_count<1:raise ValueError('页码和批次页数必须为正数。')
    with store.db() as db:
        source,key,record=store.current(path,db)
        db.execute('CREATE TABLE IF NOT EXISTS parsed_pages(path TEXT,page INTEGER,PRIMARY KEY(path,page))')
        existing=set(x[0] for x in db.execute('SELECT page FROM parsed_pages WHERE path=?',(key,)))
        if record['status']=='pending' and existing:
            db.execute('DELETE FROM parsed_pages WHERE path=?',(key,));existing=set()
        warnings=[];extension=material_extension(source);ordinal=0
        def add(value,location,page=None):
            nonlocal ordinal
            for offset in range(0,len(value),CHARS):
                part=value[offset:offset+CHARS]
                if not part.strip():continue
                index=page*1000000+ordinal if page is not None else ordinal
                db.execute('INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?)',
                    (key,index,page,location+(f':chars:{offset}-{offset+len(part)}'),part))
                ordinal+=1
        total_pages=None;next_page=None
        if extension=='.pdf':
            import pypdfium2 as pdfium
            from cn_contract.documents.material_ocr import recognize
            with pdfium.PdfDocument(str(source)) as document:
                total_pages=len(document)
                if start_page>total_pages:raise ValueError('起始页超过文件总页数。')
                end=min(total_pages,start_page+page_count-1)
                for number in range(start_page,end+1):
                    db.execute('DELETE FROM chunks WHERE path=? AND page=?',(key,number));ordinal=0
                    page=document[number-1]
                    try:
                        textpage=page.get_textpage()
                        try:value=textpage.get_text_bounded()
                        finally:textpage.close()
                        # Image-backed pages can contain only a native watermark/header.
                        images=any(obj.type==3 for obj in page.get_objects())
                        if value.strip():add(value,f'page:{number}:native',number)
                        if force_ocr or not value.strip() or images:
                            width,height=page.get_size()
                            bitmap=page.render(scale=min(2,2400/max(width,height)))
                            try:blocks=recognize(bitmap.to_pil().convert('RGB'))
                            finally:bitmap.close()
                            for index,(_,text,_) in enumerate(blocks):
                                if text.strip() not in value:add(text,f'page:{number}:ocr:{index}',number)
                            warnings.append('OCR 文字需核对数字、日期及否定词。')
                            if not value.strip() and not blocks:warnings.append(f'第 {number} 页未识别到文字。')
                    finally:page.close()
                    db.execute('INSERT OR REPLACE INTO parsed_pages VALUES(?,?)',(key,number));existing.add(number)
                next_page=next((n for n in range(1,total_pages+1) if n not in existing),None)
        else:
            db.execute('DELETE FROM chunks WHERE path=?',(key,))
            if extension in {'.txt','.md','.csv','.tsv','.json'}:
                with source.open('r',encoding=text_encoding(source),newline='') as stream:
                    offset=0
                    while value:=stream.read(CHARS):
                        add(value,f'text:{offset}');offset+=len(value)
            else:
                # Office packages and image decoders remain whole-file parsers. Admit by
                # currently available RAM, not by a fixed conversation/file-count quota.
                budget=max(1,available_memory()//8)
                if source.stat().st_size>budget:
                    raise ValueError('文件已保留，但当前可用内存不足以整体解析此格式；请释放内存或转为可逐页读取的 PDF。')
                from cn_contract.config import load_settings
                from cn_contract.domain import BaselineView,DocumentParseInput
                from cn_contract.documents.docx_adapter import parse_docx
                from cn_contract.documents.material_adapter import parse_material
                settings=load_settings().model_copy(update={'upload_max_file_mib':max(1,(record['size']+1024**2-1)//1024**2),
                    'archive_uncompressed_max_mib':max(1,budget//1024**2),'parse_max_pages_per_file':1000000})
                raw=source.read_bytes();identifier=UUID(record['sha256'][:32])
                if extension=='.docx':
                    result=parse_docx(raw,DocumentParseInput(id=identifier,baseline_view=BaselineView(revision_mode)),settings)
                    warnings.append('DOCX 修订视图：'+revision_mode)
                else:
                    # Only the parser's format hint changes; the stored path and bytes do not.
                    parser_name=source.name if source.suffix else source.name+extension
                    result=parse_material(raw,parser_name,identifier,settings)
                style_fallback = extension == '.docx' and any(
                    'STYLE_DEPENDENCY_REQUIRES_CONFIRMATION' in issue for issue in result.quality_issues)
                if style_fallback:
                    warnings.append('样式依赖不完整，已按段落、表格及指定修订视图读取正文；未能确定的隐藏样式、颜色和自动编号请对照原件。')
                    for value, location in docx_style_fallback(raw, revision_mode): add(value, location)
                for anchor in result.anchors:
                    if style_fallback and anchor.part_name == 'word/document.xml': continue
                    add(anchor.quote,anchor.part_name+':'+anchor.element_id,anchor.page)
                warnings.extend(result.quality_issues)
                if result.unsupported_parts:warnings.append('部分嵌入对象或版式未提取；必要时对照原件。')
            existing={0};db.execute('INSERT OR REPLACE INTO parsed_pages VALUES(?,0)',(key,))
        # Never publish an index assembled across a concurrent source edit.
        store.current(path,db)
        count=db.execute('SELECT COUNT(*) FROM chunks WHERE path=?',(key,)).fetchone()[0]
        status='partial' if next_page else 'ready' if count else 'no_text'
        old_warnings=json.loads(record['warnings']) if extension=='.pdf' else []
        warnings=list(dict.fromkeys(old_warnings+warnings))
        db.execute('UPDATE materials SET status=?,page_count=?,warnings=? WHERE path=?',
                   (status,total_pages,json.dumps(warnings,ensure_ascii=False),key))
    return {'path':key,'status':status,'chunks':count,'total_pages':total_pages,
            'next_page':next_page,'warnings':warnings[:20],
            'next_step':'使用 read_material 分页读取；PDF 未读完时继续 parse_material(next_page)。'}


if __name__=='__main__':
    payload=json.loads(sys.stdin.read())
    try:
        result=parse(MaterialStore(payload.pop('workspace')),**payload)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
    except Exception as error:
        code=getattr(error,'code',None)
        detail=str(error) if isinstance(error,ValueError) else code or type(error).__name__
        print(json.dumps({'ok':False,'error':'解析未完成，原文件保留。'+detail[:400]},ensure_ascii=False))
