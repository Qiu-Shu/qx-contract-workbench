"""Read-only local library routes on the existing authenticated application."""
import json
import re
import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from ..domain import LibraryQuery
from ..library import service
from ..library.catalog import ensure_root
from ..library.index import current_generation
from .request_context import actor_in, bounded_body


def _call(operation, *args):
    try:
        return operation(*args)
    except (ValueError, OSError, sqlite3.Error) as error:
        code = str(error) if type(error) is ValueError else ''
        hints = {
            'QUERY_TOO_LONG_AFTER_NORMALIZATION': '规范化后的检索词过长，请缩短到200字以内。',
            'QUERY_TOO_SHORT_OR_PUNCTUATION': '请输入至少两个连续汉字或完整的英文、数字词。',
            'QUERY_EMPTY': '请输入关键词，或使用案号等筛选条件。',
            'VERSION_MISMATCH': '资料版本已变化，请重新检索并打开原文。',
            'CURSOR_STALE_OR_DIFFERENT_QUERY': '索引或查询已更新，请重新检索。',
            'CURSOR_TOO_DEEP': '当前查询已浏览较多候选，请增加法院、地域或关键词等条件后重新检索。',
            'RECORD_NOT_FOUND': '未找到这份资料，请重新检索。',
            'FRAGMENT_NOT_FOUND': '未找到这个原文片段，请重新检索。',
        }
        if code.startswith('QUERY_'):
            return JSONResponse({'code': 'LIBRARY_QUERY_INVALID', 'message': hints.get(code, '请使用至少两个连续汉字或完整词，不要输入检索运算符。')}, status_code=422)
        return JSONResponse({'code': code if code in hints else 'LIBRARY_UNAVAILABLE',
            'message': hints.get(code, '资料或索引校验未通过，暂不能显示。请保留原件并检查资料库。')}, status_code=409)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)


def attach_library(app, database, root):
    root = ensure_root(root)
    app.state.library_root = root

    def authenticated(request, *, write=False):
        with database.session() as db:
            actor_in(request, db, write=write)

    @app.get('/library', response_class=HTMLResponse)
    def library_page(request: Request):
        authenticated(request)
        return HTMLResponse(app.state.template_environment.get_template('library.html').render())

    @app.get('/api/library/status')
    def status(request: Request):
        authenticated(request)
        def operation():
            current = current_generation(root)
            return {'state': 'ready' if current else 'not_ready',
                    'generation_id': current['generation_id'] if current else None,
                    'coverage': current['coverage'] if current else {}, 'verification_status': 'unverified'}
        return _call(operation)

    @app.post('/api/library/search')
    async def search(request: Request):
        authenticated(request, write=True)
        raw = await bounded_body(request, 16384)
        try:
            query = LibraryQuery.model_validate_json(raw)
        except ValueError:
            return JSONResponse({'code': 'LIBRARY_QUERY_INVALID', 'message': '检索条件格式不正确，请检查日期和输入长度。'}, status_code=422)
        return await run_in_threadpool(_call, service.search, root, query)

    @app.get('/api/library/records/{record_id}')
    def original(record_id: str, request: Request, version_id: str = ''):
        authenticated(request)
        if not _identifier(record_id) or not _identifier(version_id):
            return JSONResponse({'code': 'LIBRARY_ID_INVALID', 'message': '资料标识不正确，请从检索结果打开。'}, status_code=422)
        return _call(service.read_original, root, record_id, version_id)

    @app.get('/api/library/fragments/{fragment_id}')
    def fragment(fragment_id: str, request: Request):
        authenticated(request)
        if not _identifier(fragment_id):
            return JSONResponse({'code': 'LIBRARY_ID_INVALID', 'message': '原文片段标识不正确。'}, status_code=422)
        return _call(service.read_fragment, root, fragment_id)
