"""Extract bounded, source-positioned candidates; never infer missing operands."""
import re
from decimal import Decimal
from employment_term_scenarios import compare_term_scenario
from employment_parameter_linking import distinct_parameter_values
from material_scan import source_warnings
from material_headers import source_header_info

NUM=r'(?:[0-9]{1,12}(?:\.[0-9]{1,2})?|[零〇一二两三四五六七八九十百]{1,4})'
LINK=r'\s*(?:为|是|[:：]|约定为)?\s*'
END=r'(?![0-9.半零〇一二三四五六七八九十百千万亿])'
DURATION=r'(?P<n>'+NUM+r')\s*(?P<u>个月|月|年)'+END
MONEY=r'(?P<n>'+NUM+r')\s*(?P<u>万元|元)'+END
PATTERNS={
 'contract_months':re.compile(r'(?:劳动合同期限|合同期限|固定期限(?:劳动)?合同)'+LINK+DURATION+r'|(?<![0-9A-Za-z.,+\-−－负正零〇一二两三四五六七八九十百千万亿])(?P<before>'+NUM+r')\s*(?P<before_unit>个月|月|年)的?固定期限(?:劳动)?合同'),
 'probation_months':re.compile(r'试用期(?:限)?'+LINK+DURATION),
 'contract_pay':re.compile(r'(?:合同约定(?:月)?工资|合同(?:月)?工资)'+LINK+MONEY),
 'grade_pay':re.compile(r'(?:同岗|相同岗位)最低档(?:月)?工资'+LINK+MONEY),
 'minimum_pay':re.compile(r'(?:适用)?最低工资(?:标准)?'+LINK+MONEY),
 'probation_pay':re.compile(r'试用(?:期)?(?:月)?工资'+LINK+MONEY),
 'noncompete_months':re.compile(r'离职后竞业(?:限制)?(?:期限)?'+LINK+DURATION),
}
CN={c:i for i,chars in enumerate(['零〇','一','二两','三','四','五','六','七','八','九']) for c in chars}
BULLET=re.compile(r'^\s*[-*•]\s+')
DISPLAY={'contract_months':'合同期限','probation_months':'试用期限','contract_pay':'合同工资',
 'grade_pay':'同岗最低档工资','minimum_pay':'适用最低工资','probation_pay':'试用工资',
 'noncompete_months':'离职后竞业期限','contract_kind':'合同类型','contract_months_or_kind':'合同期限或类型'}
LABELS={
 'contract_months':r'劳动合同期限|合同期限|(?<!无)固定期限(?:劳动)?合同',
 'probation_months':r'试用期(?:限)?(?!工资|月工资)',
 'contract_pay':r'合同约定(?:月)?工资|合同(?:月)?工资',
 'grade_pay':r'(?:同岗|相同岗位)最低档(?:月)?工资',
 'minimum_pay':r'(?:适用)?最低工资(?:标准)?',
 'probation_pay':r'试用(?:期)?(?:月)?工资',
 'noncompete_months':r'离职后竞业(?:限制)?(?:期限)?'}


def _plain_gap(value, *, prefix=False):
    # Only simple field separators/connectors are consumed. Names, qualifiers,
    # extra units and unsupported operands remain visible and block comparisons.
    if prefix:value=BULLET.sub('',value,count=1)
    return not re.sub(r'\s|[，,；;。:：、]|/月|每月|劳动合同|合同|约定|拟定|其中|以及|为|是|并|和','',value)


def _number(text):
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',text):return Decimal(text)
    if text in CN:return Decimal(CN[text])
    match=re.fullmatch(r'([一二两三四五六七八九]?)十([一二两三四五六七八九]?)',text)
    if match:return Decimal(CN.get(match[1],1)*10+CN.get(match[2],0))
    if text=='一百':return Decimal(100)
    raise ValueError('中文数字超出当前确定性识别范围')


def _extract_lines(stage,contexts):
    if stage not in ('hiring','noncompete'):raise ValueError('自动参数提取目前只支持录用和离职后竞业候选。')
    groups=[];count=0
    for source in contexts:
        if source_header_info(source).get('header_candidate'):continue
        offset=0
        for line in source['text'].splitlines(keepends=True):
            text=line.rstrip('\r\n');params={};warnings=source_warnings(source)
            for field,pattern in PATTERNS.items():
                if (stage=='noncompete')!=(field=='noncompete_months'):continue
                for match in pattern.finditer(text):
                    if (re.search(r'(?:[+\-−－]|负|正)\s*$',text[:match.start()])
                            and not BULLET.fullmatch(text[:match.start()])):
                        warnings.append('数值有带空白的符号前缀，未提取成无符号候选。')
                        continue
                    try:
                        n=match.groupdict().get('n') or match['before'];unit=match.groupdict().get('u') or match['before_unit']
                        value=_number(n)*(12 if unit=='年' else 10000 if unit=='万元' else 1)
                        if field.endswith('months') and (value!=value.to_integral_value() or not 0<=value<=1200):raise ValueError('期限不是范围内整数月')
                        if field.endswith('pay') and (value>Decimal('999999999999.99') or value!=value.quantize(Decimal('.01'))):raise ValueError('金额超范围或不足一分')
                        rendered=format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')
                        params.setdefault(field,[]).append({'value':rendered,'raw':match.group(),
                          'start':offset+match.start(),'end':offset+match.end(),'unit':'months' if field.endswith('months') else 'yuan'})
                        count+=1
                    except (ValueError,ArithmeticError):warnings.append('存在未能确定转换的数值或单位，不执行本行核算。')
            if stage=='hiring':
                for m in re.finditer(r'无固定期限|以完成(?:一定)?(?:工作)?任务为期限',text):
                    value='indefinite' if m.group()=='无固定期限' else 'task'
                    params.setdefault('contract_kind',[]).append({'value':value,'raw':m.group(),'start':offset+m.start(),'end':offset+m.end(),'unit':'kind'})
                    count+=1
            for field,label in LABELS.items():
                if (stage=='noncompete')!=(field=='noncompete_months'):continue
                resolved=len(params.get(field,[]))+(len(params.get('contract_kind',[])) if field=='contract_months' else 0)
                if len(list(re.finditer(label,text)))>resolved:
                    warnings.append(f'{DISPLAY[field]}标签存在未完整解析的值，可能未知、复合或格式不支持；不忽略该处核算。')
            if params or warnings:
                for field,values in params.items():
                    if len(distinct_parameter_values(values))>1:warnings.append(f'{DISPLAY[field]}出现不同值候选，未自动选值。')
                guarded=text.replace('无固定期限','').replace('以完成一定工作任务为期限','')
                if re.search(r'不|未|非|否认|未知|待定|待核|或|至|分别|另一|例如|举例|假设|税后|到手|争议|约为|大约|左右|以上|以下',guarded):
                    warnings.append('本行含否定、不确定、替代或不同口径标记，保留候选但暂停核算。')
                if re.search(r'/年|/日|/天|/周|/小时|每年|每天|每日|每小时|年薪|日薪|周薪|时薪',text):
                    warnings.append('存在非月度或不同工资期间，本程序不自动换算或比较。')
                if re.search(r'(?:[+\-−－]|负|正)\s*[0-9零〇一二两三四五六七八九十百]',text):
                    warnings.append('存在带符号数值或日期分隔，不能去掉前缀作为无符号期限核算。')
                spans=sorted((v['start']-offset,v['end']-offset) for values in params.values() for v in values)
                if spans:
                    prefix=text[:spans[0][0]]
                    if re.search(r'与|和|及|、|分别|多人',prefix) or any(not _plain_gap(text[a[1]:b[0]]) for a,b in zip(spans,spans[1:])) or not _plain_gap(text[spans[-1][1]:]):
                        warnings.append('字段之间或尾部存在未解析的主体、条件或数值，不自动拼接。')
                names=set(re.findall(r'[\u4e00-\u9fff]某',text))|set(re.findall(r'[甲乙丙丁]',text))
                if len(names)>1:
                    warnings.append('本行可能涉及多主体或多段事实，不自动拼接。')
                if 'contract_kind' in params and 'contract_months' in params:warnings.append('合同类型与期限并列，需先核归属。')
                comparisons=[];missing=[]
                def val(key):
                    values=distinct_parameter_values(params.get(key,[]))
                    return values[0]['value'] if len(values)==1 else None
                def compare(formula):
                    result=compare_term_scenario(stage,formula,formula,0,len(formula))
                    result['text']='自动提取候选条件核算：若本行参数识别及同一主体/合同归属经核实，'+result['text']+' 本次候选不是已确认事实，也不是用户已确认的计算假设。'
                    result['input_mode']='extracted_candidates'
                    return result
                if stage=='hiring':
                    duration_ready=val('probation_months') is not None and (val('contract_months') is not None or val('contract_kind') is not None)
                    required=['contract_pay','grade_pay','minimum_pay','probation_pay']
                    missing=[k for k in ['probation_months',*required] if not val(k)]
                    if not val('contract_months') and not val('contract_kind'):missing.append('contract_months_or_kind')
                    if not warnings:
                        if duration_ready:
                            kind={'indefinite':'无固定期限','task':'以完成任务为期限'}.get(val('contract_kind'),f'固定期限{val("contract_months")}个月')
                            try:comparisons.append(compare(f'试用期核算假设：{kind}，试用期{val("probation_months")}个月。'))
                            except ValueError:warnings.append('期限参数无法适用已支持的比较规则。')
                        if all(val(k) is not None for k in required):
                            try:comparisons.append(compare(f'试用工资假设：合同工资{val("contract_pay")}元，同岗最低档工资{val("grade_pay")}元，适用最低工资{val("minimum_pay")}元，拟试用工资{val("probation_pay")}元。'))
                            except ValueError:warnings.append('工资基数缺乏有效正值，不能将未知当作零。')
                elif not warnings and val('noncompete_months') is not None:
                    comparisons.append(compare(f'竞业期限假设：离职后竞业{val("noncompete_months")}个月。'))
                if warnings:comparisons=[]
                groups.append({'path':source['path'],'sha256':source['sha256'],'chunk':source['chunk'],
                    'start':offset,'end':offset+len(text),'source_text':text,'parameters':params,'warnings':warnings,
                    'missing_parameters':missing,'comparisons':comparisons,'subject_verified':False})
                if len(groups)>60 or count>200:raise ValueError('参数候选超过60行或200项，请拆分材料；未截断或保存。')
            offset+=len(line)
    return {'groups':groups,'blocked_groups':sum(bool(g['warnings']) for g in groups),'legal_verified':False},_render_lines(groups)


def _render_lines(groups):
    lines=['劳动材料自动提取候选（不是已确认事实）',
       '逐行识别；完整劳动者和合同编号标识段可作同源连续跨行候选关联，不跨越缺失片段。跨文件另须相同劳动者姓名、明确劳动者编号和合同编号；编号命名范围、版本及归属仍待核。遗漏或未支持表达仍需人工核对。数值共现不证明同一主体或同一合同。']
    for i,g in enumerate(groups,1):
        lines.extend([f'候选行{i}：'+g['source_text'],f'出处：{g["path"]}；片段{g["chunk"]}；SHA-256 {g["sha256"]}；位置{g["start"]}:{g["end"]}'])
        if g.get('header_continuation'):
            link=g['header_continuation']
            lines.append(f'跨页表头候选：承接第{link["from_page"]}页表格{link["from_table"]}，依据明确续表标题和相同列边界；不是已确认的适用关系。')
            for key in ('previous_title','current_title'):
                lines.append(f'续表依据原文“{link[key]["value"]}”；{link[key]["location"]}')
        for binding in g.get('header_bindings',[]):
            lines.append('表头对应：'+' → '.join(h['value'] for h in binding['headers'])+'；本格原值“'+binding['value']+'”')
            for header in binding['headers']:lines.append(f'表头原文“{header["value"]}”；{header["location"]}；位置{header["start"]}:{header["end"]}')
        for field,values in g['parameters'].items():
            for v in values:
                value={'indefinite':'无固定期限','task':'以完成任务为期限'}.get(v['value'],v['value'])
                unit={'months':'个月','yuan':'元','kind':''}[v['unit']]
                lines.append(f'{DISPLAY[field]}候选={value}{unit}；原文“{v["raw"]}”；位置{v["start"]}:{v["end"]}')
        lines.extend('暂停核算：'+w for w in g['warnings'])
        if g['missing_parameters']:lines.append('未识别完整参数：'+'、'.join(DISPLAY[k] for k in g['missing_parameters'])+'；不从其他行或到手收入补值。')
        lines.extend(c['text'] for c in g['comparisons'])
    if not groups:lines.append('未识别到已支持格式的参数；不表示材料没有相关约定。')
    return '\n'.join(lines)


def extract_term_parameters(stage,contexts):
    from employment_parameter_linking import link_parameter_blocks,link_cross_source_blocks
    result,_=_extract_lines(stage,contexts)
    from employment_header_parameters import header_groups
    mapped=header_groups(stage,contexts,_extract_lines)
    mapped_keys={(g['path'],g['sha256'],g['chunk']) for g in mapped}
    result['groups']=[g for g in result['groups'] if (g['path'],g['sha256'],g['chunk']) not in mapped_keys]+mapped
    linked=link_parameter_blocks(stage,contexts,result['groups'],_extract_lines,_plain_gap)
    cross_source=link_cross_source_blocks(stage,contexts,linked,result['groups'],_extract_lines)
    result['blocked_groups']=sum(bool(g['warnings']) for g in result['groups'])
    result['linked_groups']=linked
    result['cross_source_groups']=cross_source
    result['blocked_cross_source_groups']=sum(bool(g['warnings']) for g in cross_source)
    result['blocked_linked_groups']=sum(bool(g['warnings']) for g in linked)
    lines=[_render_lines(result['groups'])]
    for i,g in enumerate(linked,1):
        if g.get('cross_page_candidate'):lines.append('跨页关联候选：连续页边界重复姓名、劳动者编号与合同编号；原文及各页位置保留，身份与适用关系仍须核对。')
        lines.extend([f'跨行关联候选{i}：劳动者{g["subject"]}；合同编号{g["contract_id"]}（归属未核实）',
            g['source_text'],f'出处：{g["path"]}；片段{g["chunks"]}；SHA-256 {g["sha256"]}；各行位置见关联原文'])
        for span in g["source_spans"]:lines.append(f'关联原文“{span["raw"]}”；片段{span["chunk"]}；位置{span["start"]}:{span["end"]}')
        for key,values in g['parameters'].items():
            for v in values:lines.append(f'{DISPLAY[key]}关联原文“{v["raw"]}”；片段{v["chunk"]}；位置{v["start"]}:{v["end"]}')
        lines.extend('暂停跨行核算：'+w for w in g['warnings'])
        if g['missing_parameters']:lines.append('跨行仍缺参数：'+'、'.join(DISPLAY[k] for k in g['missing_parameters']))
        lines.extend(c['text'] for c in g['comparisons'])
    for i,g in enumerate(cross_source,1):
        lines.append(f'跨文件关联候选{i}：劳动者{g["subject"]}；劳动者编号{g["worker_id"]}；合同编号{g["contract_id"]}（身份、编号命名范围及归属未核实）')
        for span in g['source_spans']:
            lines.append(f'关联原文“{span["raw"]}”；出处：{span["path"]}；SHA-256 {span["sha256"]}；片段{span["chunk"]}；位置{span["start"]}:{span["end"]}')
        for key,values in g['parameters'].items():
            for v in values:
                lines.append(f'{DISPLAY[key]}关联原文“{v["raw"]}”；出处：{v["path"]}；SHA-256 {v["sha256"]}；片段{v["chunk"]}；位置{v["start"]}:{v["end"]}')
        lines.extend('暂停跨文件核算：'+w for w in g['warnings'])
        if g['missing_parameters']:lines.append('跨文件仍缺参数：'+'、'.join(DISPLAY[k] for k in g['missing_parameters']))
        lines.extend(c['text'] for c in g['comparisons'])
    return result,'\n'.join(lines)
