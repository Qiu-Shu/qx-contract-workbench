"""Unknown commit outcomes must survive the final JSON-RPC sanitizer."""
from types import SimpleNamespace
from datetime import timedelta
import anyio
import pytest
from sqlalchemy import func, select
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp_types import JSONRPCError, ErrorData
from cn_contract.mcp import case_client, offline_server
from cn_contract.review.storage import ReviewProposalRow
from cn_contract.security import ServiceError
from tests.integration.test_assisted_review import assisted_api
from tests.integration.test_case_bridge import selected, grant
from tests.integration.test_plugin_candidates import input_body, open_write


def test_committed_lost_response_survives_final_sanitizer(selected,monkeypatch):
    client,database,*_=selected
    body=input_body(selected); _,auth=open_write(selected); attempts=[]
    def lose(value):
        response=client.post('/api/case-bridge/candidates',headers=auth,json=value.model_dump(mode='json'))
        assert response.status_code==201
        attempts.append(1)
        raise TimeoutError('PRIVATE_SENTINEL')
    monkeypatch.setattr(case_client,'_exchange',lose)
    server=offline_server.create_server()
    ctx=SimpleNamespace(request_id=7,method='tools/call',params={'name':'submit_selected_candidates','arguments':{'candidate':body}})
    emitted=[]
    class Stream:
        async def send(self,item): emitted.append(item)
    async def call(context): return await server.call_tool(context.params['name'],context.params['arguments'])
    async def invoke():
        with pytest.raises(MCPError) as error:
            await offline_server._offline_boundary(ctx,call)
        await offline_server._SanitizedWriteStream(Stream()).send(SessionMessage(JSONRPCError(
            jsonrpc='2.0',id=7,error=ErrorData(code=error.value.code,message=error.value.message,data=error.value.data))))
    anyio.run(invoke)
    error=emitted[0].message.error
    assert 'CHECK_WORKBENCH' in error.message
    assert 'PRIVATE_SENTINEL' not in error.message and error.data is None
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(ReviewProposalRow))==1
    assert attempts==[1]


def test_read_rechecks_expiry_after_context_work(selected,monkeypatch):
    from cn_contract.review import proposals
    _,database,_,bridge,*_=selected
    _,auth=grant(selected)
    expiry=bridge.active[0].expires_at
    bridge.now=lambda:expiry-timedelta(seconds=1)
    original=proposals.review_context
    def slow(*args,**kwargs):
        result=original(*args,**kwargs)
        bridge.now=lambda:expiry
        return result
    monkeypatch.setattr(proposals,'review_context',slow)
    with database.session() as db:
        with pytest.raises(ServiceError) as error: bridge.read(auth['Authorization'],db)
    assert error.value.status_code==401
    assert bridge.active is None


@pytest.mark.parametrize('code,message,data', [
    (-32001,'PRIVATE_EXCEPTION',None),(-32602,'CANDIDATE_SUBMISSION_UNCONFIRMED_CHECK_WORKBENCH',None),
    (-32001,'CANDIDATE_SUBMISSION_UNCONFIRMED_CHECK_WORKBENCH',{'private':'SECRET'})])
def test_only_exact_safe_unknown_outcome_survives_sanitizer(code,message,data):
    emitted=[]
    class Stream:
        async def send(self,item): emitted.append(item)
    async def invoke():
        await offline_server._SanitizedWriteStream(Stream()).send(SessionMessage(JSONRPCError(
            jsonrpc='2.0',id=7,error=ErrorData(code=code,message=message,data=data))))
    anyio.run(invoke)
    assert emitted[0].message.error.message=='OFFLINE_REQUEST_REJECTED'
    assert emitted[0].message.error.data is None
