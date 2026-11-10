"""Use explicit table header candidates, retaining data-cell and header provenance."""
import re,json
from material_headers import label_key,source_bindings,source_header_info,unit_key,field_header
from material_scan import source_warnings


def header_groups(stage,contexts,extract_lines,partition=True):
    groups=[]
    for source in contexts:
        bindings=source_bindings(source)
        if not bindings:continue
        if partition:
            scopes={};fields={}
            for binding in bindings:
                field=field_header(binding['headers']);key=label_key(field['value'])
                if key in ('劳动者','姓名','劳动者编号','合同编号','备注','说明'):continue
                scope=tuple(h['value'] for h in binding['headers'][:binding['headers'].index(field)])
                scopes.setdefault(scope,[]).append(binding);fields.setdefault(key,set()).add(scope)
            if any(len(v)>1 for v in fields.values()):
                shared=[b for b in bindings if all(b not in values for values in scopes.values())]
                for scope,values in scopes.items():
                    info=dict(source_header_info(source));info['header_bindings']=shared+values
                    delimiter=':grid:' if ':grid:' in source['location'] else ':layout:'
                    base=source['location'].split(delimiter,1)[0];suffix=source['location'].rsplit(':chars:',1)[1]
                    copy={**source,'location':base+delimiter+json.dumps(info,ensure_ascii=False,separators=(',',':'))+':chars:'+suffix}
                    separate=header_groups(stage,[copy],extract_lines,False)
                    for g in separate:g['column_scope']=list(scope)
                    groups.extend(separate)
                continue
        pieces=[];mapped=[];issues=list(source_warnings(source))
        if source_header_info(source).get('header_unmapped'):issues.append('本行部分单元格没有唯一表头对应，保留可映射候选，不跳过其余内容核算。')
        if any(h.get('uncertain') for b in bindings for h in b['headers']):issues.append('来源表头含公式缓存、隐藏或其他不确定值，保留对应关系，核对后再核算。')
        for binding in bindings:
            header=field_header(binding['headers'])['value'].strip();key=label_key(header);value=binding['value'].strip()
            if key in ('劳动者','姓名','劳动者编号','合同编号'):
                if re.search(r'未知|待核|待定|未提供|多人|分别|[、/；;]',value):issues.append('本行身份字段含未确定或多主体标记，保留参数候选，不自动核算。')
                continue
            if key in ('备注','说明'):
                if value:issues.append('本行还有备注或说明，保留原文供核对，不忽略条件进行核算。')
                continue
            if key not in ('合同期限','试用期','试用期限','合同工资','合同月工资','试用工资','试用期工资','同岗最低档工资','最低工资','离职后竞业期限'):
                issues.append('本行有未支持的表头字段，保留原值，不自动合并核算。');continue
            unit=re.search(r'[（(](年|个月|月|元)[）)]$',re.sub(r'\s+','',header))
            suffix=unit[1] if unit else next((unit_key(h['value']) for h in reversed(binding['headers']) if unit_key(h['value'])),'')
            operand=value+(suffix if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value) else '')
            piece=key+'：'+operand
            one=extract_lines(stage,[{**source,'text':piece}])[0]['groups']
            if not one:continue
            issues.extend(one[0]['warnings'])
            for field,values in one[0]['parameters'].items():
                for item in values:
                    start=binding['start']+len(binding['value'])-len(binding['value'].lstrip())
                    mapped.append((field,{**item,'raw':value,'start':start,'end':start+len(value),
                                          'header_sources':binding['headers']}))
            pieces.append(piece)
        if not mapped:continue
        combined=extract_lines(stage,[{**source,'text':'；'.join(pieces)}])[0]['groups'][0]
        params={}
        for field,value in mapped:params.setdefault(field,[]).append(value)
        # Cell values alone are not a replacement for qualifiers in a parent heading.
        if any(re.search(r'不|未|作废|旧版|历史|示例|待核',h['value']) for b in bindings for h in b['headers']):
            issues.append('表头含否定、版本或待核限制，保留候选，不自动认定适用。')
        if any(re.search(r'年薪|日薪|周薪|时薪|/年|/日|/天|/周|/小时|每年|每天|每日|每小时|税后|到手',h['value']) for b in bindings for h in b['headers']):
            issues.append('上级表头含不同工资期间或收入口径，保留原值，不按月工资自动比较。')
        if any(len(set(re.findall(r'[（(](年|个月|月|元)[）)]',' '.join(h['value'] for h in b['headers']))) |
                   {unit_key(h['value']) for h in b['headers'] if unit_key(h['value'])})>1 for b in bindings):
            issues.append('上下级表头单位不一致，保留对应关系，不自动选用其中一种单位。')
        warnings=list(dict.fromkeys(issues+combined['warnings']))
        group={**combined,'source_text':source['text'],'start':0,'end':len(source['text']),
               'parameters':params,'header_bindings':bindings,'warnings':warnings,
               'comparisons':[] if warnings else combined['comparisons']}
        if source_header_info(source).get('header_continuation'):
            group['header_continuation']=source_header_info(source)['header_continuation']
        for comparison in group['comparisons']:
            comparison['input_mode']='header_extracted_candidates'
            comparison['text']=comparison['text'].replace('自动提取候选条件核算：','表头映射候选条件核算：')
        groups.append(group)
    return groups
