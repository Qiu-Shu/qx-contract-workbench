"""Shared request authentication and bounded input parsing, independent of app assembly."""
import json
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ValidationError

from ..security import ServiceError, authenticate, authorize, verify_csrf


def same_origin(request):
    origin=request.headers.get('origin')
    if origin:
        parsed=urlsplit(origin)
        if parsed.scheme not in ('http','https') or origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            raise ServiceError('CROSS_MATTER_DENIED',403)
    if request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:
        raise ServiceError('CROSS_MATTER_DENIED',403)


def actor_in(request,db,matter_id=None,action='read',*,write=False):
    actor=authenticate(request.cookies.get('qx_session'),db)
    if write:
        same_origin(request);verify_csrf(actor,request.headers.get('X-CSRF-Token'),matter_id or UUID(int=0),db)
    if matter_id is not None:authorize(actor,matter_id,action,db)
    return actor


async def bounded_body(request,limit):
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>limit:raise ServiceError('FILE_LIMIT',413)
        data.extend(chunk)
    request._body=bytes(data)
    return bytes(data)


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate key')
        result[k]=v
    return result


async def body_input(request,model):
    try:
        raw=await bounded_body(request,256*1024)
        payload=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite')))
        todo=[(payload,0)]
        while todo:
            value,depth=todo.pop()
            if depth>30:raise ValueError('depth')
            if isinstance(value,dict):todo.extend((v,depth+1) for v in value.values())
            elif isinstance(value,list):todo.extend((v,depth+1) for v in value)
        return model.model_validate(payload)
    except (ValueError,TypeError,RecursionError,UnicodeDecodeError,ValidationError):
        raise ServiceError('STATE_CONFLICT',422) from None
