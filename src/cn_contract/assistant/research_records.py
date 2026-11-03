"""Pure persisted research identity, shared by readers and offline archives."""
import json
from uuid import UUID

from .. import domain as d
from .library_records import model


def initial_call(run, content, events):
    """Return None for legacy B1 history; malformed research evidence raises."""
    marked = any(event['event_type'].lower().startswith('research.') for event in events)
    # A renamed acceptance event still declares its workflow in the payload.
    for event in events:
        try:
            payload = json.loads(event['payload_json'])
            marked |= isinstance(payload, dict) and payload.get('workflow') == 'local-research-v1'
        except (ValueError, TypeError):
            pass
    if not marked:
        return None
    try:
        selected = [event for event in events if event['event_type'] == 'research.accepted'
            or event['event_type'].lower().startswith('tool.')]
        if (run['requested_skill'] != 'legal_research' or len(selected) != 2
                or any(event['seq'] != seq for seq, event in enumerate(events, 1))
                or selected[0]['event_type'] != 'research.accepted' or selected[0]['seq'] != 2
                or selected[0]['audience'] != 'internal' or selected[1]['seq'] != 3
                or selected[1]['event_type'] != 'tool.before' or selected[1]['audience'] != 'internal'):
            raise ValueError('initial research identity')
        accepted = model(d.AssistantResearchAccepted, selected[0]['payload_json'])
        call = d.LibraryHandlerCall(run_id=UUID(run['id']), event_seq=selected[1]['seq'],
            payload=model(d.LibraryHandlerEvent, selected[1]['payload_json']))
        scope = model(d.ScopeSnapshot, run['scope_snapshot'])
        # 检索来源随运行记录一起留存：老记录是本地资料库，接上只读知识服务之后
        # 是 legal_knowledge.search。这里只认「检索类工具 + 关键词等于消息正文」，
        # 换来源不改身份判定，也不放宽到能塞进别的工具名。
        request = call.payload.request
        if request.tool not in ('legal_library.search', 'legal_knowledge.search'):
            raise ValueError('initial research tool')
        expected = d.AssistantLibraryQuery(text=content, limit=5)
        if (accepted.request_sha256 != run['request_sha256'] or not content or len(content) > 200
                or call.payload.call_id != accepted.call_id or call.payload.scope != scope
                or request.query != expected or request.saved_citation_id is not None):
            raise ValueError('initial research query')
        return call
    except (ValueError, TypeError, KeyError, IndexError):
        raise ValueError('LIBRARY_RECORD_INVALID') from None
