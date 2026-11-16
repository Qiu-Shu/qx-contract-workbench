"""Build portable metadata only; original public files remain in the local collection."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--collection',type=Path,required=True)
p.add_argument('--destination',type=Path,default=Path(__file__).parent)
args=p.parse_args()
m=json.loads((args.collection/'manifest.json').read_text('utf-8'))
inspection=json.loads((args.collection/'inspection.json').read_text('utf-8'))
assert inspection['file_count']==len(m['files']) and inspection['sha256_all_match']
checks={x['url']:x for x in inspection['files']}
pages={x['url']:x for x in m['pages']}
done=set(pages)|{x['url'] for x in m['files']}
unresolved={x['url']:x for x in m['attempts'] if x['url'] not in done}
files=[]
for i,f in enumerate(m['files'],1):
    c=checks[f['url']]
    row={k:v for k,v in f.items() if k!='local_path'}
    row.update(id=f'T{i:03d}',local_relative_path=Path(f['local_path']).relative_to(args.collection).as_posix(),parse_status=c['parse_status'],sha256_matches=c['sha256_matches'],blank_markers_present=c.get('blank_markers_present'),example_markers_present=c.get('example_markers_present'))
    if f['source_id']=='spc-2025-notice': row['kind']='national_compilation_blank_forms_and_examples'
    elif f['extension']=='.zip': row['kind']='archive_blank_forms_guidance_and_examples'
    elif f['source_id']=='guangzhou-arbitration' or (f['source_id']=='baoshan-employment' and re.match(r'(15|16|17|18)\.',f['label'])): row['kind']='background_guidance_or_regulation'
    elif c.get('example_markers_present') or '实例' in f['label']: row['kind']='form_with_examples_or_example_markers'
    else: row['kind']='officially_listed_form_content_not_legally_validated'
    if 'pages' in c: row['pdf_pages']=c['pages']
    if 'members' in c:
        row['archive_members']=[]
        for member in c['members']:
            entry={k:v for k,v in member.items() if k not in {'opening_excerpt','extracted_path'}}
            if member.get('extracted_path'): entry['local_relative_path']=Path(member['extracted_path']).relative_to(args.collection).as_posix()
            row['archive_members'].append(entry)
    files.append(row)
catalog={'collection_id':'official-20261116','collected_utc':m['updated_utc'],'inspected_utc':inspection['inspected_utc'],'local_collection_root':str(args.collection),'scope':'常用法律文书；劳动用工优先；不是全部文书的穷尽集合','scrapling_version':m['scrapling_version'],'tls_verified':m['tls_verified'],'downloaded_objects':len(files),'format_counts':dict(Counter(f['extension'] for f in files)),'parse_counts':inspection['parse_counts'],'sha256_all_match':inspection['sha256_all_match'],'historical_failed_or_review_required_attempts':len(m['attempts']),'unresolved_sources_or_files':[{k:v for k,v in x.items() if k in {'url','label','source_id','id','error','fetched_utc'}} for x in unresolved.values()],'source_pages':[{k:v for k,v in x.items() if k not in {'links','local_path'}} for x in m['pages']],'files':files}
catalog['robots_checks']=m['robots']
log=args.collection/'inspection-final.log'
catalog['parser_warnings']=list(dict.fromkeys(line for line in log.read_text('utf-8-sig').splitlines() if line and not line.startswith('{'))) if log.exists() else []
args.destination.mkdir(parents=True,exist_ok=True)
(args.destination/'manifest.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# 已下载原件目录','',f'共 {len(files)} 个下载对象；ZIP 内文件另列于 manifest，不重复计入。原件本机根目录：`{args.collection.as_posix()}`。','', '|编号|文书/资料|类型|解析状态|来源|本机相对路径|','|---|---|---|---|---|---|']
for f in files:
    title=(f['label'] or Path(f['local_relative_path']).name).replace('|','／')
    lines.append(f'|{f["id"]}|{title}|{f["extension"]}|{f["parse_status"]}|[原页]({f["source_page"]}) / [附件]({f["url"]})|`{f["local_relative_path"]}`|')
(args.destination/'catalog.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
national=next(x for x in inspection['files'] if x['source_id']=='spc-2025-notice')
text=Path(national['text_path']).read_text('utf-8'); book=None; entries=[]
for line in text.splitlines():
    compact=re.sub(r'\s+','',line)
    if compact in {'上册','下册'}: book=compact
    match=re.match(r'^(.+?)\s*…{2,}\s*(\d+)\s*$',line)
    if match:
        entry={'title':match.group(1).strip(),'printed_page':int(match.group(2)),'volume':book,'contains_example':'实例' in match.group(1)}
        if entry not in entries: entries.append(entry)
(args.destination/'national-contents.json').write_text(json.dumps({'source_url':national['url'],'source_sha256':next(f['sha256'] for f in m['files'] if f['url']==national['url']),'pdf_pages':national['pages'],'page_note':'印刷页码不是PDF查看器页码；用标题在原件检索。目录自动提取，逐项正文适用性未复核。','entries':entries},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'downloaded_objects':len(files),'unresolved':len(unresolved),'national_contents':len(entries),'archive_members':sum(1 for f in files for e in f.get('archive_members',[]) if e.get('sha256'))},ensure_ascii=False))
