"""Source-bound payroll row arithmetic. No legal entitlement or cross-row joins."""
import re
from decimal import Decimal
from material_headers import source_bindings, source_header_info, field_header, label_key, unit_key
from material_scan import source_warnings

FIELDS={'姓名':'subject','劳动者':'subject','工资期间':'period','月份':'period',
        '应发工资':'gross','代扣合计':'deductions','实发工资':'paid'}
LABELS={'subject':'姓名','period':'工资期间','gross':'应发工资','deductions':'代扣合计','paid':'实发工资'}
MONEY=re.compile(r'((?:[0-9]{1,3}(?:,[0-9]{3}){1,3}|[0-9]{1,12})(?:\.[0-9]{1,2})?)\s*(元|万元)?[。]?')
PERIOD=re.compile(r'(19\d{2}|20\d{2}|21\d{2})(?:年(0?[1-9]|1[0-2])月|-(0[1-9]|1[0-2]))')


def _row(source,text,offset,cells,headers):
    params={};warnings=list(source_warnings(source));notices=[]
    for cell in cells:
        key=FIELDS.get(label_key(cell['label']))
        if not key:
            if cell['value'].strip():notices.append('其他字段照录，不纳入本行算式：'+cell['label']+'：'+cell['value'])
            continue
        raw=cell['value'];value=raw.strip();start=cell['start']+len(raw)-len(raw.lstrip())
        item={'raw':value,'start':start,'end':start+len(value),'value':None}
        if cell.get('headers'):item['header_sources']=cell['headers']
        if key in ('gross','deductions','paid'):
            match=MONEY.fullmatch(value)
            unit=match[2] if match else None
            inherited=cell.get('unit','')
            if not match or (unit or inherited) not in ('元','万元') or (unit and inherited and unit!=inherited):
                warnings.append(LABELS[key]+'金额或人民币单位不明确/不一致，未自动选值。')
            else:
                factor=Decimal(10000) if (unit or inherited)=='万元' else Decimal(1)
                amount=Decimal(match[1].replace(',',''))*factor
                if amount>Decimal('999999999999.99') or amount!=amount.quantize(Decimal('.01')):
                    warnings.append(LABELS[key]+'超出支持范围或精度。')
                else:item['value']=format(amount,'.2f')
        elif key=='period':
            if PERIOD.fullmatch(value):item['value']=value
            else:warnings.append('工资期间须为原文明确的年月；不推定年份或跨月拆分。')
        else:
            if (value and len(value)<=80
                and not re.search(r'未知|待核|待定|未提供|不详|多人|分别|[、/；;，,&+]|及其他',value)
                and not re.fullmatch(r'.{2,}[和与及].{2,}',value)):item['value']=value
            else:warnings.append('本行姓名不明确或涉及多人，不拼接工资记录。')
        params.setdefault(key,[]).append(item)
        if len(params[key])>1:warnings.append(LABELS[key]+'存在多列/多值，分别保留，未自动选择。')
    if not any(k in params for k in ('gross','deductions','paid')):return None
    missing=[k for k in LABELS if k not in params]
    if missing:warnings.append('本行缺少：'+'、'.join(LABELS[k] for k in missing)+'；不补零或借用其他行。')
    if headers:
        for binding in headers:
            values=' '.join(h['value'] for h in binding['headers'])
            if re.search(r'作废|待核|暂估|否认|非人民币|税后应发|美元|港元',values):warnings.append('表头有口径或适用限制，需核对本行。')
            units={unit_key(h['value']) for h in binding['headers'] if unit_key(h['value'])}
            if len(units)>1:warnings.append('表头单位存在冲突，未自动选用。')
            if any(h.get('uncertain') for h in binding['headers']):warnings.append('表头含不确定值，需核对对应关系。')
    calculation=None
    if not warnings:
        v={key:items[0]['value'] for key,items in params.items()}
        gross,deductions,paid=(Decimal(v[key]) for key in ('gross','deductions','paid'))
        net=gross-deductions;balance=net-paid
        message=(f'工资记录条件对账｜{v["subject"]}｜{v["period"]}：'
                 f'应发{gross:.2f}－代扣{deductions:.2f}＝净额候选{net:.2f}元；'
                 f'再减实发{paid:.2f}＝账面差额{balance:.2f}元。'
                 '仅依据此行所列口径计算，代扣合法性、支付事实及实际应付款未认定；不与其他行相加。')
        calculation={'gross':str(gross),'deductions':str(deductions),'paid':str(paid),
          'net_candidate':format(net,'.2f'),'balance':format(balance,'.2f'),'text':message,'legal_entitlement_verified':False}
    return {'path':source['path'],'sha256':source['sha256'],'chunk':source['chunk'],
            'source_text':source['text'],'start':offset,'end':offset+len(text),'parameters':params,
            'warnings':list(dict.fromkeys(warnings)),'notices':notices,'missing_parameters':missing,
            'calculation':calculation,'header_bindings':headers,'subject_verified':False}


def extract_payroll(contexts):
    groups=[]
    for source in contexts:
        info=source_header_info(source)
        if info.get('header_candidate'):continue
        bindings=source_bindings(source)
        if bindings:
            cells=[]
            for binding in bindings:
                header=field_header(binding['headers'])['value']
                unit=re.search(r'[（(](元)[）)]$',re.sub(r'\s+','',header))
                unit=unit[1] if unit else next((unit_key(h['value']) for h in reversed(binding['headers']) if unit_key(h['value'])),'')
                cells.append({'label':header,'value':binding['value'],'start':binding['start'],'unit':unit,'headers':binding['headers']})
            group=_row(source,source['text'],0,cells,bindings)
            if group:groups.append(group)
        else:
            offset=0
            for line in source['text'].splitlines(keepends=True):
                text=line.rstrip('\r\n');cells=[]
                for match in re.finditer(r'(?:^|[；;])\s*([^：:；;]+)[：:]([^；;]*)',text):
                    cells.append({'label':match[1].strip(),'value':match[2],'start':offset+match.start(2)})
                group=_row(source,text,offset,cells,[])
                if group:groups.append(group)
                offset+=len(line)
        if len(groups)>60:raise ValueError('工资记录超过60行，请分批处理；没有截断保存。')
    lines=['工资记录自动提取与条件对账（不是欠薪认定）',
           '逐行保留来源，不跨人、月份或文件拼金额，不累计全案应付款。同人同月多条记录也分别列示，不能重复相加。']
    for i,g in enumerate(groups,1):
        lines.extend([f'记录{i}：'+g['source_text'][g['start']:g['end']],
                      f'出处：{g["path"]}；片段{g["chunk"]}；SHA-256 {g["sha256"]}；位置{g["start"]}:{g["end"]}'])
        for key,values in g['parameters'].items():
            for item in values:
                lines.append(f'{LABELS[key]}原文“{item["raw"]}”；位置{item["start"]}:{item["end"]}')
                for h in item.get('header_sources',[]):lines.append(f'表头原文“{h["value"]}”；{h["location"]}；位置{h["start"]}:{h["end"]}')
        lines.extend(g['notices']);lines.extend('本行待核：'+w for w in g['warnings'])
        if g['calculation']:lines.append(g['calculation']['text'])
    if not groups:lines.append('未识别到支持的工资行；原文照录，可继续处理其他材料。')
    return {'groups':groups,'blocked_groups':sum(bool(g['warnings']) for g in groups),'legal_verified':False},'\n'.join(lines)
