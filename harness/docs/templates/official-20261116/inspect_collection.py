"""Verify downloaded bytes and parse Office XML/PDF without running Office or macros."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile

def inspect_bytes(raw, extension):
    result={}
    text=''
    if extension in {'.docx','.xlsx'}:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(x.file_size for x in archive.infolist())>100*1024*1024:
                raise ValueError('Expanded Office file exceeds inspection limit')
            result['zip_crc_ok']=archive.testzip() is None
            result['macro_payloads']=[n for n in archive.namelist() if n.lower().endswith('vbaproject.bin')]
            if extension=='.docx':
                root=ET.fromstring(archive.read('word/document.xml'))
                paras=[''.join(p.itertext()) for p in root.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
                text='\n'.join(p for p in paras if p.strip())
            else:
                for name in archive.namelist():
                    if name=='xl/sharedStrings.xml' or name.startswith('xl/worksheets/sheet'):
                        root=ET.fromstring(archive.read(name))
                        text+='\n'.join(t.text or '' for t in root.iter() if t.tag.rsplit('}',1)[-1]=='t')+'\n'
            result['parse_status']='parsed_ooxml'
    elif extension=='.pdf':
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(raw)); result['pages']=len(pdf.pages)
        text='\n'.join(page.extract_text() or '' for page in pdf.pages)
        result['parse_status']='parsed_pdf' if text.strip() else 'image_pdf_text_unverified'
    elif extension=='.zip':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist())>200 or sum(x.file_size for x in archive.infolist())>100*1024*1024:
                raise ValueError('Archive exceeds inspection limit')
            result['members']=[]
            for x in archive.infolist():
                display=x.filename
                if not x.flag_bits & 0x800:
                    try: display=x.filename.encode('cp437').decode('gbk')
                    except (UnicodeEncodeError,UnicodeDecodeError): pass
                path=PurePosixPath(display.replace('\\','/'))
                entry={'name':x.filename,'display_name':display,'bytes':x.file_size,'compressed_bytes':x.compress_size,'safe_path':not path.is_absolute() and '..' not in path.parts}
                if not x.is_dir():
                    payload=archive.read(x)
                    entry['sha256']=hashlib.sha256(payload).hexdigest()
                    ext=path.suffix.lower()
                    if ext in {'.docx','.xlsx','.doc','.pdf'}:
                        info,_=inspect_bytes(payload,ext); entry.update(info)
                    else: entry['parse_status']='unsupported_member'
                result['members'].append(entry)
            result['zip_crc_ok']=True
            result['parse_status']='archive_members_inspected'
    elif extension=='.doc':
        if not raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
            raise ValueError('Legacy Office signature mismatch')
        result['parse_status']='legacy_doc_signature_only'
    else:
        result['parse_status']='not_parsed'
    if text:
        result['text_characters']=len(text)
        result['blank_markers_present']=bool(re.search(r'___|＿|□|××|姓名[：:]\s*(?:\n|性别)|年\s+月\s+日',text))
        result['example_markers_present']=bool(re.search('实例|填写示例|示范案例|样例|张三|李四',text))
        result['opening_excerpt']=text[:450]
    return result,text

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    options=p.parse_args(); manifest=json.loads((options.output/'manifest.json').read_text('utf-8'))
    results=[]; textdir=options.output/'extracted-text'; textdir.mkdir(exist_ok=True)
    for i,item in enumerate(manifest['files'],1):
        raw=Path(item['local_path']).read_bytes()
        result={'url':item['url'],'local_path':item['local_path'],'label':item['label'],'source_id':item['source_id'],'sha256_matches':hashlib.sha256(raw).hexdigest()==item['sha256']}
        try:
            inspection,text=inspect_bytes(raw,item['extension']); result.update(inspection)
            if item['extension']=='.zip':
                folder=options.output/'extracted-archives'/f'{i:03d}-{item["source_id"]}'; folder.mkdir(parents=True,exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for n,entry in enumerate(result['members'],1):
                        if entry.get('sha256') and entry['safe_path'] and entry.get('parse_status')!='unsupported_member':
                            name=PurePosixPath(entry['display_name'].replace('\\','/')).name
                            name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name)
                            target=folder/f'{n:03d}-{name}'
                            target.write_bytes(archive.read(entry['name'])); entry['extracted_path']=str(target)
            if text:
                target=textdir/f'{i:03d}-{item["source_id"]}.txt'; target.write_text(text,encoding='utf-8'); result['text_path']=str(target)
        except Exception as exc:
            result.update(parse_status='parse_failed',error=str(exc))
        results.append(result)
    summary={'inspected_utc':datetime.now(timezone.utc).isoformat(),'file_count':len(results),'sha256_all_match':all(r['sha256_matches'] for r in results),'parse_counts':dict(Counter(r['parse_status'] for r in results)),'files':results}
    (options.output/'inspection.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='files'},ensure_ascii=False))
    return 0 if summary['sha256_all_match'] and all(r['parse_status']!='parse_failed' for r in results) else 1

if __name__=='__main__':
    raise SystemExit(main())
