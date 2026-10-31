"""Conservative source routing. Capability never determines matter identity."""
import re
from .. import domain as d
from ..assistant import business
from ..task_drafts import service as tasks


def control(request):
    clean=re.sub(r'[\s，,。.!！?？；;、]', '',request.text)
    if any(word in clean for word in ('先别开始','先不要开始','不要开始','暂不开始','还没发完',
            '尚未发完','没有发完','先别处理','先不要处理','请等待','稍等','等一下','先等等')) or clean=='等待':
        return 'paused'
    if clean in {'开始','开始处理','发送完毕','可以开始','发完了'} or any(word in clean for word in (
            '可以开始','发送完毕','材料发完了','请开始处理')):
        return 'collecting'
    return tasks._control(request)


def readiness(content):
    # Later messages release earlier holds; within a message an explicit negative wins.
    values=[control(d.TaskInboxEventInput(event_id='routing',text=line)) for line in content.splitlines() if line.strip()]
    return next((value for value in reversed(values) if value),None)


def decide(content, candidates, *, reference=None):
    content = content.strip()
    clean = re.sub(r'[\s，,。.!！?？；;、]', '', content)
    if clean in {'测试', '你好', '您好', '在吗', '连接测试'}:
        return d.ServiceRouteDecision(action='ack', notice='已连接，消息已收到。')
    if not content or readiness(content) in {'paused','cancelled'}:
        return d.ServiceRouteDecision(action='wait', notice='材料已保留，等待您发送完毕并说明处理要求。')
    workflow = business.classify(content)
    workflow = None if workflow == 'ambiguous' else workflow
    explicit = [c for c in candidates if c['id'] == reference or c['id'] in content
                or len(c['title']) >= 2 and c['title'] in content]
    new = any(x in content for x in ('新事项', '另一个案件', '新案件', '另一份合同', '新业务'))
    if len(explicit) == 1:
        return d.ServiceRouteDecision(action='start', relation='existing',
            conversation_id=explicit[0]['id'], workflow=workflow)
    if new or not candidates and workflow:
        return d.ServiceRouteDecision(action='start', relation='new', workflow=workflow)
    continuation = business.continuing(content) or any(x in content for x in ('这个', '这份', '上述', '接着', '开始', '庭审准备'))
    if len(candidates) == 1 and continuation:
        return d.ServiceRouteDecision(action='start', relation='existing',
            conversation_id=candidates[0]['id'], workflow=workflow)
    if candidates:
        choices = '；'.join(c['title'] + '（' + c['id'] + '）' for c in candidates)
        return d.ServiceRouteDecision(action='clarify', notice='这批材料属于哪个事项？请回复事项名称或编号；新业务请说“新事项”。' + choices)
    return d.ServiceRouteDecision(action='wait', notice='材料已保留。请说明合同审查、案件整理、庭审准备或客户接待。')
