"""Parse in a separate process; PDF and plain text are indexed incrementally."""
from pathlib import Path
from io import BytesIO
import codecs
import ctypes
import json
import os
import re
import sqlite3
import sys
from uuid import UUID
from zipfile import ZipFile

LEGACY = Path(os.environ['QX_LEGACY_ROOT'])
sys.path.insert(0,str(LEGACY/'src'))
from store import MaterialStore, material_extension

CHARS = 4000
IMAGE_EXTENSIONS={'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff'}


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
        db.execute('CREATE TABLE IF NOT EXISTS parse_failures(path TEXT,page INTEGER,detail TEXT,PRIMARY KEY(path,page))')
        existing=set(x[0] for x in db.execute('SELECT page FROM parsed_pages WHERE path=?',(key,)))
        if record['status']=='pending' and existing:
            db.execute('DELETE FROM parsed_pages WHERE path=?',(key,));existing=set()
        if record['status']=='pending':db.execute('DELETE FROM parse_failures WHERE path=?',(key,))
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
        def scan(image,number,prefix='page',native='',native_regions=()):
            from material_scan import ocr_rows
            rows,issues=ocr_rows(image,number,prefix,**({'native_regions':native_regions} if native_regions else {}))
            for row in rows:
                add(row['value'],row['location'],number)
            warnings.extend(issues)
            warnings.append('OCR 文字需核对数字、日期及否定词；位置框基于识别用图像。')
            if not native.strip() and not rows:warnings.append(f'{prefix}:{number} 未识别到文字，可对照原图；其他页继续处理。')
        def page_start(number):
            nonlocal ordinal
            db.execute('DELETE FROM chunks WHERE path=? AND page=?',(key,number));ordinal=0
            db.execute('DELETE FROM parsed_pages WHERE path=? AND page=?',(key,number));existing.discard(number)
        def page_done(number,error=None):
            if error is not None:
                if isinstance(error,sqlite3.Error):raise error
                detail=f'未完成页 {number}：{type(error).__name__}；已提取文字保留，可单独重试该页。'
                db.execute('INSERT OR REPLACE INTO parse_failures VALUES(?,?,?)',(key,number,detail))
            else:
                db.execute('DELETE FROM parse_failures WHERE path=? AND page=?',(key,number))
                db.execute('INSERT OR REPLACE INTO parsed_pages VALUES(?,?)',(key,number));existing.add(number)
        if extension=='.pdf':
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(str(source)) as document:
                total_pages=len(document)
                if start_page>total_pages:raise ValueError('起始页超过文件总页数。')
                end=min(total_pages,start_page+page_count-1)
                for number in range(start_page,end+1):
                    page_start(number);page=None
                    try:
                        page=document[number-1]
                        textpage=page.get_textpage()
                        native_rects=[]
                        try:
                            value=textpage.get_text_bounded()
                            if value.strip():
                                try:
                                    for index in range(textpage.count_rects()):
                                        rect=textpage.get_rect(index)
                                        native_rects.append((rect,textpage.get_text_bounded(*rect)))
                                except Exception:
                                    native_rects=[]
                                    warnings.append(f'page:{number} 原生文字定位未完成，保留全部识别文字供核对，可能有重复。')
                        finally:textpage.close()
                        # Image-backed pages can contain only a native watermark/header.
                        images=any(obj.type==3 for obj in page.get_objects())
                        if value.strip():add(value,f'page:{number}:native',number)
                        if force_ocr or not value.strip() or images:
                            width,height=page.get_size()
                            bitmap=page.render(scale=min(2,2400/max(width,height)))
                            try:
                                regions=[];converter=bitmap.get_posconv(page)
                                for (left,bottom,right,top),text in native_rects:
                                    corners=[converter.to_bitmap(x,y) for x,y in ((left,bottom),(right,bottom),(right,top),(left,top))]
                                    xs,ys=zip(*corners)
                                    regions.append({'text':text,'box':[min(xs),min(ys),max(xs),max(ys)]})
                                scan(bitmap.to_pil().convert('RGB'),number,native=value,native_regions=regions)
                            finally:bitmap.close()
                    except Exception as error:page_done(number,error)
                    else:page_done(number)
                    finally:
                        if page is not None:page.close()
                next_page=next((n for n in range(1,total_pages+1) if n not in existing),None)
        elif extension in IMAGE_EXTENSIONS:
            from PIL import Image,ImageOps
            with Image.open(source) as image:
                total_pages=getattr(image,'n_frames',1)
                if start_page>total_pages:raise ValueError('起始页超过图片帧数。')
                for number in range(start_page,min(total_pages,start_page+page_count-1)+1):
                    page_start(number)
                    try:
                        image.seek(number-1)
                        frame=ImageOps.exif_transpose(image)
                        frame.thumbnail((2400,2400))
                        try:scan(frame.convert('RGB'),number,'image')
                        finally:frame.close()
                    except Exception as error:page_done(number,error)
                    else:page_done(number)
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
                if extension=='.xlsx':
                    from material_spreadsheets import xlsx_rows
                    spreadsheet_rows,issues=xlsx_rows(raw,settings)
                    for item in spreadsheet_rows:add(item['value'],item['location'])
                    warnings.extend(issues);result=None
                elif extension=='.docx':
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
                entries=[(value,location,None) for value,location in docx_style_fallback(raw,revision_mode)] if style_fallback else []
                for anchor in result.anchors if result is not None else []:
                    if style_fallback and anchor.part_name == 'word/document.xml': continue
                    entries.append((anchor.quote,anchor.part_name+':'+anchor.element_id,anchor.page))
                covered=set();row_starts={}
                if extension=='.docx':
                    from material_tables import docx_table_rows
                    rows,covered,issues=docx_table_rows(raw,[(value,location) for value,location,_ in entries])
                    warnings.extend(issues)
                    row_starts={row['source_locations'][0]:row for row in rows if row['source_locations']}
                for value,location,page in entries:
                    if location in row_starts:
                        row=row_starts[location];add(row['value'],row['location'],page)
                    if location not in covered:add(value,location,page)
                if result is not None:
                    warnings.extend(result.quality_issues)
                    if result.unsupported_parts:warnings.append('部分嵌入对象或版式未提取；必要时对照原件。')
            existing={0};db.execute('INSERT OR REPLACE INTO parsed_pages VALUES(?,0)',(key,))
        if extension=='.pdf' or extension in IMAGE_EXTENSIONS:
            from material_scan_continuation import refresh_scan_headers
            refresh_scan_headers(db,key,existing)
        # Never publish an index assembled across a concurrent source edit.
        store.current(path,db)
        count=db.execute('SELECT COUNT(*) FROM chunks WHERE path=?',(key,)).fetchone()[0]
        status='partial' if next_page else 'ready' if count else 'no_text'
        old_warnings=[w for w in json.loads(record['warnings']) if not w.startswith('未完成页 ')] if total_pages else []
        failures=db.execute('SELECT page,detail FROM parse_failures WHERE path=? ORDER BY page',(key,)).fetchall()
        warnings.extend(row['detail'] for row in failures)
        warnings=list(dict.fromkeys(old_warnings+warnings))
        db.execute('UPDATE materials SET status=?,page_count=?,warnings=? WHERE path=?',
                   (status,total_pages,json.dumps(warnings,ensure_ascii=False),key))
    return {'path':key,'status':status,'chunks':count,'total_pages':total_pages,
            'next_page':next_page,'failed_pages':[row['page'] for row in failures],'warnings':warnings[:20],
            'next_step':'已提取内容可先 read_material 使用；未完成页可用 start_page 和 page_count=1 单独重试。'}


if __name__=='__main__':
    payload=json.loads(sys.stdin.read())
    try:
        result=parse(MaterialStore(payload.pop('workspace')),**payload)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
    except Exception as error:
        code=getattr(error,'code',None)
        detail=str(error) if isinstance(error,ValueError) else code or type(error).__name__
        print(json.dumps({'ok':False,'error':'解析未完成，原文件保留。'+detail[:400]},ensure_ascii=False))
