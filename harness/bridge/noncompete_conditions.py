"""Source-owned compensation state and rule-owned noncompete release sections.

These sections run after free-prose review. They are conditional guidance, not a
finding that an agreement, nonpayment, release or entitlement exists in a case.
"""
import re
from draft_review import CONDITIONAL

SOURCE='https://www.court.gov.cn/zixun/xiangqing/282121.html'
COMPENSATION=re.compile(r'补偿|对价')
RELEASE=re.compile(r'(?:解除|终止|放弃|豁免|免除)(?:该|此|本|双方的|离职后)?竞业'
    r'|竞业(?:限制)?(?:协议|约定|义务|条款)?(?:的)?(?:提前|协商|单方|自动|可以|可)*(?:解除|终止|放弃)'
    r'|(?:公司|单位|企业|劳动者|员工)[^，,。；;\n]{0,12}(?:可|请求|有权|可以)(?:单方|书面|直接|立即)*(?:解除|放弃)(?!劳动合同|劳动关系|该劳动|其劳动)'
    r'|不(?:再)?(?:受|履行)[^，,。；;\n]{0,8}竞业(?:限制)?(?:义务|约定|约束)?'
    r'|(?:本|该|此)(?:竞业)?(?:协议|约定)(?:自动|即行|即|可以|可)?解除'
    r'|补偿.{0,12}(?:停止|停付)|(?:停止|停付).{0,12}补偿')
RELEASE_RULES=(
    '竞业解除须分路径核对，不自动认定本案已经解除：'
    '劳动者路径（解释一第38条）：已约定竞业限制和经济补偿，劳动合同解除或终止后，'
    '因用人单位原因导致三个月未支付经济补偿，劳动者请求解除竞业限制约定，人民法院应予支持；'
    '不能把未提供支付材料当作已经欠付，也不能仅因日期经过就认定义务自动终止。'
    '用人单位路径（第39条）：在竞业限制期限内，用人单位请求解除竞业协议，人民法院应予支持；'
    '解除时劳动者请求用人单位额外支付三个月竞业经济补偿的，人民法院应予支持。'
    '先核有效解除时间、已履行期间应付及已付金额、额外补偿请求，不把单方通知或停止未来限制等同全部免付。'
    '本案约定、原因、履行期间、请求及支付记录不足时按以上条件准备方案，其他已明确事项继续完成。 '+SOURCE)
COMPENSATION_RISK=(
    '补偿状态按本项匹配原文分别核对：材料未提供不能认定实际为零、偏低、未约定或未支付；'
    '原文明确的0元、其他金额、已付款及不同主体的争议陈述均保留，匹配不等于事实认证。'
    '是否足额须有适用标准、期间和已付记录；是否需要调整违约金须另核有效义务、违约事实、损失及适用规则，'
    '不以未知补偿推断对价失衡或应当大幅调减。可先明确支付安排、整理凭证、提出有条件的修改方案。')


def _parts(text):
    return re.findall(r'[^。！？\n；;]+[。！？\n；;]?|[。！？\n；;]',text)


def single_source_citation(cases,case_id):
    """Recover a missing reference only for one current material with one chunk.

    No selection among files, people or versions; quote the whole source and keep
    attribution rather than interpreting it as a proven fact.
    """
    sources=cases.materials(case_id)
    if len(sources)!=1:return []
    source=sources[0]
    if source.get('changed') or source.get('missing') or source['path'].lower().startswith('drafts/'):return []
    data=cases.read_material(case_id,source['path'],start=0,limit=1)
    if data.get('total_chunks')!=1 or data.get('warnings') or data.get('failed_pages') or data.get('sha256')!=source['sha256']:return []
    chunks=data.get('chunks',[])
    if len(chunks)!=1 or not 0<len(chunks[0]['text'])<=12000:return []
    return [dict(path=source['path'],sha256=source['sha256'],chunk=chunks[0]['ordinal'],quote=chunks[0]['text'])]


def release_requested(item):
    """Capture a noncompete release issue before compensation prose is normalized."""
    topic=item.get('topic','')
    return (isinstance(topic,str) and '竞业' in topic and
            not re.search(r'劳动(?:合同|关系).{0,4}(?:解除|终止)',topic) and
            bool(re.search(r'解除|终止|停付|不受.*约束',topic))) or any(
                isinstance(item.get(k),str) and RELEASE.search(item[k])
                for k in ('basis','risk','action','pending'))


def finalize_noncompete_conditions(item,review,index,*,release_issue=False):
    """Keep independent prose; replace source-dependent compensation assertions.

    shortcut: sentence routing is bounded to compensation and release vocabulary;
    unrelated free legal reasoning still needs its own acceptance tests.
    """
    item=dict(item)
    refs=item.get('citations',[])
    if not isinstance(refs,list):return item  # Producer retains validation.
    contexts=list(dict.fromkeys(review.sources(refs)))
    finance=any(COMPENSATION.search(item.get(k,'')) for k in ('topic','fact','basis','risk') if isinstance(item.get(k),str))
    def change(field,value,reason):
        original=item.get(field,'')
        if original==value:return
        review.changes.append(dict(label=f'第{index}项{field}',original=original,replacement=value,reason=reason,citations=refs))
        item[field]=value

    if 'source' not in item and contexts:
        change('source','本案已匹配原始引用；路径、版本与原文见本项引用。','用已验证引用生成遗漏的来源说明，不补造来源。')

    if finance and isinstance(item.get('fact'),str):
        original=item['fact']
        kept=''.join(s for s in _parts(original) if not COMPENSATION.search(s))
        # Restore full bound sentences once, not an unverified numeric/status rewrite.
        quotes='\n'.join('“'+s+'”' for s in contexts)
        fact=('补偿及关联事实的匹配原文（保留主体、陈述和未知状态）：\n'+quotes if contexts and len(quotes)<=12000 else
              '补偿来源较长，完整内容见本项原始引用；不据缺材料认定零或低补偿。' if contexts else
              '补偿约定及支付状态尚无可匹配原文，不据此认定实际不存在；仅本项待核。')
        # Do not multiply already quoted source paragraphs from earlier normalization.
        if any(s in original for s in contexts) and '本案匹配原文' in original:kept=''
        change('fact',(kept+'\n'+fact).strip(),'补偿事实由关联原文呈现；不由模型补出零、低或欠付状态。')

    release_seen=release_issue
    for field in ('topic','basis','risk','action','pending'):
        value=item.get(field)
        if not isinstance(value,str):continue
        output=[];release=False;compensation=False
        for part in _parts(value):
            # Employment termination as a date/starting point is a different object.
            is_date=bool(re.search(r'劳动(?:合同|关系)(?:解除|终止)',part) and re.search(r'起算|之日起|日期|解除日',part)
                         and not re.search(r'请求|停付|放弃|额外',part))
            if RELEASE.search(part) and not is_date:
                release=True
                if field=='topic':output.append('竞业解除条件核对')
                continue
            if finance and field=='risk' and COMPENSATION.search(part):
                if CONDITIONAL.search(part):
                    output.append(part)
                    continue
                compensation=True
                # Preserve independently stated nonfinancial issues, not a bare
                # conclusion whose omitted subject was the compensation assertion.
                for clause in re.findall(r'[^，,、]+[，,、]?',part):
                    if not COMPENSATION.search(clause) and re.search(r'证据|举证|秘密|保密|地域|期限|岗位|人员|义务内容',clause):
                        output.append(clause)
                continue
            output.append(part)
        if compensation:output.append(COMPENSATION_RISK)
        if release and field!='topic':output.append(RELEASE_RULES)
        release_seen=release_seen or release
        revised=''.join(output)
        if revised!=value:change(field,revised,'局部采用来源状态或完整解除条件；独立建议和原稿继续保留。')
    # Do not feed a program-generated rule block back through the prose router.
    basis=item.get('basis')
    if release_seen and isinstance(basis,str) and RELEASE_RULES not in basis:
        change('basis',basis+'\n'+RELEASE_RULES,'区分劳动者与用人单位解除路径，保留完整条件。')
    return item
