"""Bounded comparisons of explicit source assumptions, not actual entitlement."""
import re
from decimal import Decimal, ROUND_CEILING


def compare_term_scenario(stage, quote, context, start, end):
    # A whole independent line is required: never strip a preceding negation.
    left=max(context.rfind('\n',0,start),context.rfind('\r',0,start))+1
    stop=re.search('[\r\n]',context[end:])
    right=len(context) if stop is None else end+stop.start()
    if context[left:right].strip()!=quote.strip():
        raise ValueError('核算假设须为原始材料中独立完整一行，不得截去否定或条件。')
    text = quote.strip()
    pattern = r'试用期核算假设：(?:固定期限([0-9]{1,4})个月|(无固定期限|以完成任务为期限))，试用期([0-9]{1,4})个月。'
    match = re.fullmatch(pattern, text)
    if stage == 'hiring' and match:
        months, kind, proposed = match.groups()
        proposed = int(proposed)
        if proposed > 1200 or (months is not None and not 1 <= int(months) <= 1200):
            raise ValueError('核算月数超过范围。')
        maximum = (6 if kind == '无固定期限' else 0 if kind == '以完成任务为期限' else
                   0 if int(months) < 3 else 1 if int(months) < 12 else 2 if int(months) < 36 else 6)
        excess = max(0, proposed - maximum)
        return {'kind':'probation_duration','maximum_months':maximum,'excess_months':excess,
                'text':f'仅按所列假设：试用期上限{maximum}个月，拟约定{proposed}个月，超出上限{excess}个月（劳动合同法第19条）。未超过期限上限不等于约定整体合法；重复约定、仅约定试用期及实际用工状态另核，不认定实际赔偿。'}
    number = r'([0-9]{1,12}(?:\.[0-9]{1,2})?)'
    match = re.fullmatch('试用工资假设：合同工资'+number+'元，同岗最低档工资'+number+'元，适用最低工资'+number+'元，拟试用工资'+number+'元。', text)
    if stage == 'hiring' and match:
        contract, grade, minimum, proposed = map(Decimal, match.groups())
        if min(contract, grade, minimum) <= 0:
            raise ValueError('假设工资基准须大于零；未知值不能写成零。')
        # Round the threshold up to a cent so the comparison never undercuts 80%.
        floors = [max(base * Decimal('.8'), minimum).quantize(Decimal('.01'), rounding=ROUND_CEILING) for base in (contract, grade)]
        a,b = floors
        ga,gb = [max(Decimal(0),v-proposed) for v in floors]
        return {'kind':'probation_pay','contract_floor':format(a,'.2f'),'grade_floor':format(b,'.2f'),
                'contract_gap':format(ga,'.2f'),'grade_gap':format(gb,'.2f'),
                'text':f'仅按所列工资假设：合同工资80%与最低工资取高为{a:.2f}元，拟工资低于该口径{ga:.2f}元；同岗最低档工资80%与最低工资取高为{b:.2f}元，拟工资低于该口径{gb:.2f}元（实施条例第15条）。阈值不足一分向上取整；两个候选口径分别显示，未选定适用工资口径，不相加，不认定实际欠薪。地区、工资构成、适用时期及实际履行另核。'}
    match = re.fullmatch(r'竞业期限假设：离职后竞业([0-9]{1,4})个月。',text)
    if stage == 'noncompete' and match:
        proposed=int(match[1])
        if proposed > 1200:
            raise ValueError('核算月数超过范围。')
        excess=max(0,proposed-24)
        return {'kind':'noncompete_duration','maximum_months':24,'excess_months':excess,
                'text':f'仅按所列离职后竞业假设：期限上限24个月，拟约定{proposed}个月，超出上限{excess}个月（劳动合同法第24条）。不认定约定整体有效或无效；接触秘密、人员范围、地域、补偿及实际履行另核，不套用于在职限制。'}
    raise ValueError('不支持的核算假设或阶段。只接受工具说明列明的独立完整假设行，不从零散事实拼接假设。')
