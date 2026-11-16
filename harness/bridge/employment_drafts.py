"""Compile a small set of candidate texts without caller-authored factual slots.

Intent selection and the surrounding AI analysis remain unverified. These texts
express conditions/questions, never establish facts from a matched citation.
"""

DRAFTS = {
    'probation_clause': (
        '试用条件候选条款',
        '同一用人单位与同一劳动者只能约定一次试用期。拟约定试用期前，应核实双方既往试用记录。'
        '若双方已约定过试用期，不再设置新的试用期；记录未明时，本条不确认本次为首次试用。'
        '以完成一定工作任务为期限或期限不满三个月的劳动合同不约定试用期。'
        '合同期限三个月以上不满一年的，试用期不超过一个月；一年以上不满三年的，不超过二个月；'
        '三年以上固定期限及无固定期限合同，不超过六个月。'
        '具体期限以来源材料及后续确认结果为准，纳入劳动合同期限，本条不延长或另填期限。'
        '试用工资需另按适用标准约定。',
    ),
    'attendance_inquiry': (
        '考勤及请假核实通知候选文字',
        '为核对相关日期的出勤、工作安排及请假情况，请核对所涉日期、实际出勤或工作情况、'
        '请假申请及审批经过，并提供可核对的记录；如对公司掌握的材料有异议，请一并说明。'
        '公司应向员工明确核对期间及材料，结合双方说明和相关记录继续核实；涉及健康或产检的材料按必要范围提供。'
        '本通知仅用于核实情况，不认定旷工、违纪或劳动关系已经解除。'
        '反馈方式及合理期限由双方结合实际情况确定，本稿不预填发送、收到或回复日期。',
    ),
    'noncompete_inquiry': (
        '竞业解除及款项核对函候选文字',
        '为核对竞业限制的履行及后续安排，请提供解除通知的完整内容、提出方、发出及送达记录、'
        '拟生效时间，并确认各方对解除的意思表示。请逐期核对竞业补偿约定、应付期间、付款凭证和到账情况；'
        '如认为已经结清，请列明对应期间和款项依据。双方对通知及款项的陈述请分别记录，保留尚未解决的异议。'
        '如涉及用人单位在竞业限制期限内请求解除，请一并核对劳动者请求额外三个月竞业补偿的适用条件及处理意见。'
        '本函为核对请求，不确认任一方已经同意解除、款项已经支付或竞业义务已经终止。',
    ),
}


def compile_drafts(intents):
    if (not isinstance(intents,list) or not 1 <= len(intents) <= len(DRAFTS)
            or any(not isinstance(i,str) or i not in DRAFTS for i in intents)
            or len(set(intents)) != len(intents)):
        raise ValueError('drafts须为不重复的候选类型列表：'+', '.join(DRAFTS)+'；不接受自由正文或事实状态。')
    return '\n\n'.join(title+'：\n'+body for title,body in (DRAFTS[i] for i in intents))
