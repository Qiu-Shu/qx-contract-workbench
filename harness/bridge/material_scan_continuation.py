"""Link explicit continued scan tables; never infer continuity from page order alone."""
import json
import re
from material_headers import annotate_headers,label_key,LABELS


def annotate_continuations(rows,complete_pages):
    tables={};pages={}
    def canonical(value):return re.sub(r'\s+','',value).translate(str.maketrans('（）','()'))
    for row in rows:
        if not re.fullmatch(r'(?:page|image):\d+:ocr-row:\d+:layout:\{.*\}',row['location']):continue
        base,payload=row['location'].split(':layout:',1);info=json.loads(payload)
        for key in ('header_bindings','header_unmapped','header_candidate','header_text','header_continuation'):
            info.pop(key,None)
        row['location']=base+':layout:'+json.dumps(info,ensure_ascii=False,separators=(',',':'))
        prefix,number,_=base.split(':',2);page=int(number)
        entry=(row,info,base);pages.setdefault((prefix,page),[]).append(entry)
        if info.get('scan_grid'):
            key=(prefix,page,info['scan_grid']['table_id']);tables.setdefault(key,[]).append(entry)

    def signature(entries):
        edges={}
        for _,info,_ in entries:
            for cell in info['scan_grid']['cells']:
                for col,x in ((cell['start_col'],cell['box'][0]),(cell['end_col']+1,cell['box'][2])):
                    edges.setdefault(col,[]).append(x)
        values={col:sum(xs)/len(xs) for col,xs in edges.items()}
        if len(values)<3:return None
        left=min(values.values());width=max(values.values())-left
        if width<=0:return None
        return {col:(x-left)/width for col,x in values.items()}

    def title(key,entries):
        top=min(c['box'][1] for _,info,_ in entries for c in info['scan_grid']['cells'])
        candidates=[]
        for row,info,base in pages[key[:2]]:
            if info.get('scan_grid') or info.get('flags') or not info.get('boxes'):continue
            bottom=max(p[1] for box in info['boxes'] for p in box)
            if not 0<=top-bottom<=160:continue
            value=re.sub(r'\s+','',row['value'])
            continuation=bool(re.search(r'[（(]续表[）)]$|续表$',value))
            name=re.sub(r'[（(]续表[）)]$|续表$','',value)
            if len(name)>=3:candidates.append((bottom,name,continuation,base,row['value']))
        return max(candidates,default=None)

    previous={}
    for key,entries in sorted(tables.items()):
        prefix,page,table_id=key;seed=[];link=None
        name=title(key,entries);shape=signature(entries)
        # shortcut: only explicit titles and matching visible column boundaries; borderless tables stay local.
        prior=previous.get(prefix)
        if (prior and page==prior['page']+1 and page in complete_pages and prior['page'] in complete_pages
                and name and name[2] and prior['title'] and name[1]==prior['title'][1] and shape
                and prior['shape'] and shape.keys()==prior['shape'].keys()
                and all(abs(shape[c]-prior['shape'][c])<=.02 for c in shape)):
            current=[r for r,_,_ in entries]
            annotate_headers(current)
            local=[];local_headers=[]
            for r in current:
                info=json.loads(r['location'].split(':layout:',1)[1])
                if info.get('header_candidate'):
                    local.append([(c['start_col'],c['end_col'],canonical(r['value'][c['text_start']:c['text_end']])) for c in info['scan_grid']['cells']])
                    local_headers.append([dict(start_col=c['start_col'],end_col=c['end_col'],start=c['text_start'],end=c['text_end'],
                        value=r['value'][c['text_start']:c['text_end']],location=r['location'].split(':layout:',1)[0],uncertain=bool(c.get('flags')))
                        for c in info['scan_grid']['cells'] if r['value'][c['text_start']:c['text_end']].strip()])
            inherited=prior['headers']
            def labels(level):return [(h['start_col'],h['end_col'],canonical(h['value'])) for h in level]
            # Repeated leaf headings must match their prior columns; a changed heading starts a local table.
            repeats=[level for level in local if any(label_key(v) in LABELS for _,_,v in level)]
            compatible=all(level in [labels(h) for h in inherited] for level in repeats)
            parents=[level for level in local if level not in repeats]
            compatible=compatible and all(level in [labels(h) for h in inherited] for level in parents)
            if compatible:
                missing=any(labels(level) not in local for level in inherited)
                seed=[local_headers[local.index(labels(level))] if labels(level) in local else level for level in inherited]
                if missing:link={'from_page':prior['page'],'from_table':prior['table'],
                    'previous_title':{'location':prior['title'][3],'value':prior['title'][4]},
                    'current_title':{'location':name[3],'value':name[4]}}
        table_key=f'{prefix}:{page}:table:{table_id}'
        annotate_headers([r for r,_,_ in entries],{table_key:seed if link else []},fixed_headers=bool(link))
        headers=list(seed) if link else []
        for row,_,base in entries:
            info=json.loads(row['location'].split(':layout:',1)[1])
            if info.get('header_candidate') and not link:
                headers.append([dict(start_col=c['start_col'],end_col=c['end_col'],start=c['text_start'],end=c['text_end'],
                    value=row['value'][c['text_start']:c['text_end']],location=base,uncertain=bool(c.get('flags')))
                    for c in info['scan_grid']['cells'] if row['value'][c['text_start']:c['text_end']].strip()])
            if link:
                info['header_continuation']=link
                row['location']=base+':layout:'+json.dumps(info,ensure_ascii=False,separators=(',',':'))
        previous[prefix]={'page':page,'table':table_id,'title':name,'shape':shape,'headers':headers}


def refresh_scan_headers(db,path,complete_pages):
    records=db.execute('SELECT ordinal,page,location,text FROM chunks WHERE path=? ORDER BY ordinal',(path,)).fetchall()
    rows=[]
    for record in records:
        match=re.fullmatch(r'((?:page|image):\d+:ocr-row:\d+:layout:\{.*\}):chars:0-(\d+)',record['location'])
        if not match or int(match[2])!=len(record['text']):continue
        info=json.loads(match[1].split(':layout:',1)[1])
        if info.get('text_length')!=len(record['text']):continue
        rows.append(dict(value=record['text'],location=match[1],page=record['page'],ordinal=record['ordinal']))
    annotate_continuations(rows,complete_pages)
    for row in rows:
        db.execute('UPDATE chunks SET location=? WHERE path=? AND ordinal=?',
            (row['location']+f':chars:0-{len(row["value"])}',path,row['ordinal']))
