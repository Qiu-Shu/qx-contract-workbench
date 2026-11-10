"""Attach physical multi-row header candidates without rewriting source text."""
import json
import re

LABELS={'劳动者','姓名','劳动者编号','合同编号','合同期限','试用期','试用期限','合同工资','合同月工资',
        '试用工资','试用期工资','同岗最低档工资','最低工资','离职后竞业期限','备注','说明',
        '工资期间','月份','应发工资','代扣合计','实发工资'}

def label_key(value):
    return re.sub(r'[（(](?:年|个月|月|元)[）)]$','',re.sub(r'\s+','',value))

def unit_key(value):
    match=re.fullmatch(r'[（(]?(年|个月|月|元)[）)]?',re.sub(r'\s+','',value))
    return match[1] if match else None

def field_header(headers):
    return next((h for h in reversed(headers) if not unit_key(h['value'])),headers[-1])

def annotate_headers(rows,initial_headers=None,fixed_headers=False):
    states={key:{'headers':list(value),'data':False} for key,value in (initial_headers or {}).items()};sheets={}
    from material_spreadsheets import _ref
    for row in rows:
        location=row['location'];delimiter=':grid:' if ':grid:' in location else ':layout:'
        if delimiter not in location:continue
        base,payload=location.split(delimiter,1);info=json.loads(payload)
        if base.startswith('xlsx:') and base.endswith(':metadata'):
            sheets[base.removesuffix(':metadata')]=info;continue
        cells=[]
        if info.get('scan_grid'):
            grid=info['scan_grid'];key=base.split(':ocr-row:',1)[0]+f':table:{grid["table_id"]}'
            cells=[dict(start_col=c['start_col'],end_col=c['end_col'],start=c['text_start'],end=c['text_end'],
                        value=row['value'][c['text_start']:c['text_end']],uncertain=bool(c.get('flags')))
                   for c in grid['cells']]
        elif delimiter==':grid:':
            key=base.rsplit('/tr[',1)[0]
            if not all('text_start' in c for c in info.get('cells',[])):continue
            cells=[dict(start_col=c['start_col'],end_col=c['end_col'],start=c['text_start'],end=c['text_end'],
                        value=row['value'][c['text_start']:c['text_end']]) for c in info['cells']]
        elif base.startswith('xlsx:') and re.search(r':row:\d+$',base):
            key,number=base.rsplit(':row:',1);number=int(number);offset=0
            merges=[]
            for address in sheets.get(key,{}).get('merged_ranges',[]):
                try:
                    left,right=address.split(':');c1,r1=_ref(left);c2,r2=_ref(right)
                    if r1==number:merges.append((c1,c2))
                except (ValueError,TypeError):continue
            precise=[c for c in info.get('cells',[]) if 'text_start' in c]
            values=[(c['column'],row['value'][c['text_start']:c['text_end']],c['text_start']) for c in precise] if precise else [(col,value,None) for col,value in enumerate(row['value'].split('\t'),1)]
            for col,value,position in values:
                if position is not None:offset=position
                ends=[end for start,end in merges if start==col]
                cells.append(dict(start_col=col,end_col=max(ends,default=col),start=offset,end=offset+len(value),value=value))
                offset+=len(value)+1
        else:continue
        state=states.setdefault(key,{'headers':[],'data':False})
        nonempty=[c for c in cells if c['value'].strip()]
        leaves=bool(nonempty) and all(label_key(c['value']) in LABELS for c in nonempty)
        units=bool(nonempty) and bool(state['headers']) and all(unit_key(c['value']) for c in nonempty)
        group=bool(nonempty) and not state['data'] and any(c['end_col']>c['start_col'] for c in nonempty)
        marked=bool(info.get('header_row'))
        if leaves or group or marked or units:
            if not (fixed_headers and key in (initial_headers or {})):
                if state['data']:state['headers']=[];state['data']=False
                uncertain=bool(info.get('row_hidden') or info.get('sheet_state','visible')!='visible' or
                               any(c.get('formula') or c.get('date_format') or c.get('type')=='e' for c in info.get('cells',[])))
                state['headers'].append([{**c,'location':base,'uncertain':uncertain or c.get('uncertain',False)} for c in nonempty])
            info['header_candidate']=True
            info['header_text']=row['value']
            row['location']=base+delimiter+json.dumps(info,ensure_ascii=False,separators=(',',':'))
            continue
        state['data']=True
        if not state['headers']:continue
        bindings=[]
        for cell in cells:
            if not cell['value'].strip():continue
            path=[]
            for level in state['headers']:
                matches=[h for h in level if h['start_col']<=cell['start_col'] and h['end_col']>=cell['end_col']]
                if len(matches)==1:path.append(matches[0])
                elif matches:path=[];break
            if path:bindings.append({**cell,'headers':info.get('table_context',[])+path})
        if bindings:
            info['header_bindings']=bindings
            info['header_unmapped']=len(bindings)!=len(nonempty)
            row['location']=base+delimiter+json.dumps(info,ensure_ascii=False,separators=(',',':'))

def source_header_info(source):
    location=source.get('location','')
    if not re.search(r':chars:0-\d+$',location):return {}
    delimiter=':grid:' if ':grid:' in location else ':layout:'
    try:
        info=json.loads(location.split(delimiter,1)[1].rsplit(':chars:',1)[0])
        if info.get('header_candidate') and source['text']!=info.get('header_text'):return {}
        bindings=info.get('header_bindings',[])
        if any(source['text'][b['start']:b['end']]!=b['value'] for b in bindings):return {}
        return info
    except (ValueError,IndexError,KeyError,TypeError):return {}

def source_bindings(source):
    return source_header_info(source).get('header_bindings',[])
