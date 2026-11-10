"""Link source-positioned candidates; explicit identifiers are not verified identity."""
import re
from material_scan import adjacent_rows,adjacent_sheet_rows,source_warnings,source_layout,printed_table_label as _printed_table_label

HEADER=re.compile(r'\s*劳动者\s*[:：\t]\s*(?P<subject>[\u4e00-\u9fff]{2,8})\s*[;；\t]\s*'
    r'(?:劳动者编号\s*[:：\t]\s*(?P<worker>[A-Za-z0-9][A-Za-z0-9_-]{0,63})\s*[;；\t]\s*)?'
    r'合同编号\s*[:：\t]\s*(?P<contract>[A-Za-z0-9][A-Za-z0-9_-]{0,63})\s*')
PERSON=re.compile(r'\s*劳动者\s*[:：\t]\s*[\u4e00-\u9fff]{2,8}\s*')
PARAGRAPH=re.compile(r'(word/document\.xml:.*?/)(?:w:)?(?:p|tr)\[(\d+)\](?::grid:\{.*\})?:chars:0-\d+$')
EMPLOYER=re.compile(r'(?:^|[\r\n；;。，,])[ \t]*(?:用人单位(?:名称)?|单位名称|雇主)[ \t]*[:：][ \t]*([^\r\n；;。，,]*)')


def distinct_parameter_values(values):
    # Collapse only normalized operands for calculation; callers retain every source occurrence.
    unique={}
    for value in values:
        unique.setdefault((value['value'],value['unit']),value)
    return list(unique.values())


def link_parameter_blocks(stage,contexts,groups,extract_lines,plain_gap):
    linked=[]; segments=[]; previous=None
    for source in sorted(contexts,key=lambda s:(s['path'],s['sha256'],s['chunk'])):
        key=(source['path'],source['sha256'],source['chunk'])
        left=PARAGRAPH.fullmatch(previous.get('location','')) if previous else None
        right=PARAGRAPH.fullmatch(source.get('location',''))
        adjacent=bool(previous and key[:2]==(previous['path'],previous['sha256']) and key[2]==previous['chunk']+1
                      and ((left and right and left[1]==right[1] and int(right[2])==int(left[2])+1)
                           or adjacent_rows(previous,source) or adjacent_sheet_rows(previous,source)))
        # Chunk ordinals omit blank paragraphs and are not physical adjacency.
        if not adjacent:segments.append([])
        offset=0
        for line in source['text'].splitlines(keepends=True):
            segments[-1].append((source,offset,line.rstrip('\r\n')));offset+=len(line)
        previous=source
    indexed={(g['path'],g['sha256'],g['chunk'],g['start']):g for g in groups}
    for segment in segments:
        block=None
        def finish():
            nonlocal block
            if block is None:return
            rows=block.pop('_rows');warnings=block['warnings'];fields=[];params={}
            for source,start,line in rows:
                g=indexed.get((source['path'],source['sha256'],source['chunk'],start))
                if not g or not g['parameters']:
                    warnings.append('标识段内有未解析行，不能跳过后继续拼接核算。');continue
                g['comparisons']=[];g['linked_block']=len(linked)
                warnings.extend(g['warnings'])
                spans=sorted(v['start'] for values in g['parameters'].values() for v in values)
                if not plain_gap(line[:spans[0]-start],prefix=True):warnings.append('参数行含另一主体或未解析前缀，不能跨行合并。')
                for key,values in g['parameters'].items():
                    for v in values:
                        params.setdefault(key,[]).append({**v,'path':g['path'],'sha256':g['sha256'],'chunk':g['chunk']})
                        # Internal comparison text only; source positions stay on original operands.
                        fields.append(v['raw'].replace('：','').replace(':',''))
            block['parameters']=params
            for values in params.values():
                if len(distinct_parameter_values(values))>1:warnings.append('同一标识段有不同值参数，未自动选择版本。')
            combined=None
            if fields:
                combined=extract_lines(stage,[{**segment[0][0],'text':'，'.join(fields)}])[0]['groups'][0]
                warnings.extend(combined['warnings'])
            block['warnings']=list(dict.fromkeys(warnings))
            block['missing_parameters']=combined['missing_parameters'] if combined else []
            block['comparisons']=[] if warnings or combined is None else combined['comparisons']
            for c in block['comparisons']:
                c['text']=c['text'].replace('自动提取候选条件核算：','跨行候选条件核算：').replace('本行参数识别及同一主体/合同归属','本标识段参数识别及同一主体/合同归属')
                c['input_mode']='linked_extracted_candidates'
            linked.append(block);block=None
            if len(linked)>30:raise ValueError('跨行标识段超过30项，请拆分材料；未截断或保存。')
        i=0
        while i<len(segment):
            source,offset,value=segment[i];m=HEADER.fullmatch(value);header_rows=[segment[i]]
            if not m and PERSON.fullmatch(value) and i+1<len(segment):
                for size in (2,3):
                    candidate=segment[i:i+size]
                    m=HEADER.fullmatch('；'.join(row[2] for row in candidate))
                    if m:header_rows=candidate;i+=len(candidate)-1;break
            if m:
                finish()
                block={k:source[k] for k in ('path','sha256','chunk')}
                block.update(subject=m['subject'],worker_id=m['worker'],contract_id=m['contract'],subject_verified=False,
                    header={'raw':'\n'.join(t[2] for t in header_rows),'start':offset,'end':offset+len(value),'chunk':source['chunk']},
                    chunks=list(dict.fromkeys(t[0]['chunk'] for t in header_rows)),
                    source_spans=[{'path':s['path'],'sha256':s['sha256'],'chunk':s['chunk'],'start':o,'end':o+len(t),'raw':t} for s,o,t in header_rows],
                    start=offset,end=offset+len(value),source_text='\n'.join(t[2] for t in header_rows),warnings=[],_rows=[])
                block['warnings'].extend(warning for s,_,_ in header_rows for warning in source_warnings(s))
                if re.search(r'未知|待核|待定|不详|示例|例如|假设',m['subject']):block['warnings'].append('劳动者标识未确定，不自动关联。')
                if any(re.fullmatch(r'unknown|tbd|pending|none|null|na|n_a|x+|0+',v,re.I) for v in (m['worker'],m['contract']) if v):
                    block['warnings'].append('劳动者或合同编号为占位标识，不自动关联。')
            elif not value.strip():finish()
            elif source_layout(source) and not source_warnings(source) and _printed_table_label(value):finish()
            elif block is not None:
                block['_rows'].append((source,offset,value));block['end']=offset+len(value)
                block['source_spans'].append({'path':source['path'],'sha256':source['sha256'],'chunk':source['chunk'],'start':offset,'end':offset+len(value),'raw':value})
                if source['chunk'] not in block['chunks']:block['chunks'].append(source['chunk'])
                block['source_text']+='\n'+value
            i+=1
        finish()
    linked=_link_page_continuations(stage,linked,contexts,extract_lines)
    identities={}
    for b in linked:identities.setdefault((b['path'],b['sha256'],b['subject'],b['contract_id']),[]).append(b)
    for blocks in identities.values():
        if len(blocks)>1:
            for b in blocks:
                b['warnings'].append('同一来源重复出现相同劳动者与合同编号，版本关系待核。');b['comparisons']=[]
    return linked


def _link_page_continuations(stage,blocks,contexts,extract_lines):
    """Join explicit repeated identities only at complete consecutive OCR page edges."""
    lookup={(s['path'],s['sha256'],s['chunk']):s for s in contexts}
    merged=[]
    def edge(block,last):
        span=block['source_spans'][-1 if last else 0]
        source=lookup[(span['path'],span['sha256'],span['chunk'])]
        parsed=source_layout(source)
        if not parsed:return None
        match,layout=parsed
        if (match[4]!='0' or layout.get('flags') or layout.get('row_linking_uncertain')
                or len(source['text'])!=layout.get('text_length')):return None
        if last and span['end']!=len(source['text']):return None
        if not last and span['start']!=0:return None
        count=layout.get('row_count')
        if not isinstance(count,int):return None
        needed=set(range(int(match[2])+1,count+1) if last else range(1,int(match[2])))
        if int(match[2])==layout.get('content_last_row' if last else 'content_first_row'):
            needed.clear()
        # Printed headers/folios do not terminate a table; substantive omitted rows do.
        for candidate in contexts:
            if (candidate['path'],candidate['sha256'])!=(source['path'],source['sha256']):continue
            extra=source_layout(candidate)
            if not extra or extra[0][1]!=match[1] or int(extra[0][2]) not in needed:continue
            m,meta=extra
            if (m[4]!='0' or meta.get('flags') or meta.get('row_linking_uncertain')
                    or len(candidate['text'])!=meta.get('text_length')):continue
            text=candidate['text'].strip()
            if _printed_table_label(text):
                needed.discard(int(m[2]))
        if needed:return None
        prefix,page=match[1].split(':')
        return prefix,int(page)
    for current in blocks:
        previous=merged[-1] if merged else None
        same=bool(previous and current['worker_id'] and all(previous[k]==current[k]
                  for k in ('path','sha256','subject','worker_id','contract_id')))
        left=edge(previous,True) if same else None
        right=edge(current,False) if same else None
        if (not same or previous['warnings'] or current['warnings'] or not left or not right
                or left[0]!=right[0] or right[1]!=left[1]+1):
            merged.append(current);continue
        params={k:list(v) for k,v in previous['parameters'].items()}
        for key,values in current['parameters'].items():params.setdefault(key,[]).extend(values)
        fields=[v['raw'].replace('：','').replace(':','') for values in params.values() for v in values]
        if not fields:
            merged.append(current);continue
        combined=extract_lines(stage,[{**previous,'text':'，'.join(fields)}])[0]['groups'][0]
        previous.update(parameters=params,comparisons=combined['comparisons'],warnings=combined['warnings'],
                        missing_parameters=combined['missing_parameters'],cross_page_candidate=True)
        previous['chunks'].extend(current['chunks']);previous['source_spans'].extend(current['source_spans'])
        previous['source_text']+='\n'+current['source_text']
        for comparison in previous['comparisons']:
            comparison['text']=comparison['text'].replace('自动提取候选条件核算：','跨页候选条件核算：').replace(
                '本行参数识别及同一主体/合同归属','连续页重复身份栏及参数归属')
            comparison['input_mode']='cross_page_extracted_candidates'
    return merged


def link_cross_source_blocks(stage, contexts, blocks, groups, extract_lines):
    """Only exact worker number + contract number + name may form a candidate."""
    identities={};names={};versions={};source_text={};employers={};unresolved_employers=set()
    for source in contexts:
        versions.setdefault(source['path'],set()).add(source['sha256'])
        key=(source['path'],source['sha256'])
        source_text.setdefault(key,[]).append(source['text'])
        employer_names=employers.setdefault(key,set())
        for value in EMPLOYER.findall(source['text']):
            name=value.strip();employer_names.add(name)
            if (not name or re.search(r'未知|待核|待定|不详|待确认|未确认|无法确认|或|、|/|\\',name)
                    or re.fullmatch(r'[-—_]+|无|未提供|unknown|tbd|pending|none|null|na',name,re.I)):
                unresolved_employers.add(key)
    for block in blocks:
        if not block['worker_id']:continue
        names.setdefault(block['worker_id'],set()).add(block['subject'])
        identities.setdefault((block['worker_id'],block['contract_id']),[]).append(block)
    for block in blocks:
        if block['worker_id'] and len(names[block['worker_id']])>1:
            block['warnings'].append('同一劳动者编号对应不同姓名，身份归属冲突。')
            block['comparisons']=[]
    linked=[]
    for (worker,contract),members in identities.items():
        if len({b['path'] for b in members})<2:continue
        warnings=[w for b in members for w in b['warnings']];params={};spans=[]
        employer_sets=[employers[(b['path'],b['sha256'])] for b in members]
        # Explicit employer labels constrain a local employee-number namespace; absence proves nothing.
        if (any((b['path'],b['sha256']) in unresolved_employers for b in members) or
                (any(employer_sets) and (any(len(values)!=1 for values in employer_sets) or
                                        len(set().union(*employer_sets))!=1))):
            warnings.append('各来源用人单位标识冲突、存在多个候选或无法对应；不能仅凭劳动者编号及合同编号认定同一命名范围。')
        for block in members:
            block['comparisons']=[]
            block['cross_source_group']=len(linked)
            spans.extend(block['source_spans'])
            for field,values in block['parameters'].items():params.setdefault(field,[]).extend(values)
            if len(versions[block['path']])>1:warnings.append('同一路径存在不同来源版本，不选择其中一个版本。')
            context=block['path']+'\n'+'\n'.join(source_text[(block['path'],block['sha256'])])
            if re.search(r'旧版|版本|作废|替换|修订|草稿|示例|假设|未知|待核|待定|不详|否认|非本人|不是本人|不属于|无法确认|尚未确认',context):
                warnings.append('来源含版本、示例或归属待核标记，不能确定跨文件适用关系。')
            if any(g['path']==block['path'] and g['sha256']==block['sha256'] and 'linked_block' not in g for g in groups):
                warnings.append('同一来源还有未归入标识段的参数或未解析值，不能跳过后跨文件核算。')
        if len({b['path'] for b in members})<len(members):warnings.append('同一文件重复出现标识段，版本关系待核。')
        if any(len(distinct_parameter_values(values))>1 for values in params.values()):warnings.append('跨文件出现不同值或冲突参数，未自动选择版本。')
        fields=[v['raw'].replace('：','').replace(':','') for values in params.values() for v in values]
        combined=extract_lines(stage,[{**members[0],'text':'，'.join(fields)}])[0]['groups'][0] if fields else None
        if combined:warnings.extend(combined['warnings'])
        if warnings:
            affected={(b['path'],b['sha256']) for b in members}
            for candidate in groups:
                if (candidate['path'],candidate['sha256']) in affected and 'linked_block' not in candidate:
                    candidate['comparisons']=[]
                    candidate['warnings'].append('同来源跨文件身份、版本或参数归属尚未解决，暂停未归属行核算。')
        group={'subject':members[0]['subject'],'worker_id':worker,'contract_id':contract,'subject_verified':False,
            'sources':[{'path':b['path'],'sha256':b['sha256'],'chunks':b['chunks']} for b in members],
            'source_spans':spans,'parameters':params,'warnings':list(dict.fromkeys(warnings)),
            'missing_parameters':combined['missing_parameters'] if combined else [],
            'comparisons':combined['comparisons'] if combined and not warnings else []}
        for comparison in group['comparisons']:
            comparison['text']=comparison['text'].replace('自动提取候选条件核算：','跨文件候选条件核算：').replace(
                '本行参数识别及同一主体/合同归属','各来源参数识别、劳动者编号的同一命名范围及同一主体/合同归属')
            comparison['input_mode']='cross_source_extracted_candidates'
        linked.append(group)
    return linked
