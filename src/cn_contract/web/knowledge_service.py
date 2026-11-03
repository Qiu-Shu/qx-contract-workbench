"""只读知识服务的工作台接线：页面 + 三个 API。

边界（对应试点任务书）
----------------------
- 鉴权复用既有 `actor_in`：未登录 401，POST 走同源 + CSRF 校验（与本地法库检索一致）。
- 浏览器只与这里通信；服务地址与凭据只在本进程，不进模板、不进静态文件、不进日志。
- 来源 ID 先在本层按格式校验，再交给客户端；不存在"前端传路径"的入口。
- 服务未配置时：页面入口隐藏，API 返回 503 `KB_SERVICE_NOT_CONFIGURED`，
  本地法库与普通对话完全不受影响。
"""
from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..assistant.tools.kb_readonly import (
    MESSAGES, STATUS_BY_CODE, KnowledgeServiceClient, KnowledgeServiceConfig, KnowledgeServiceError,
)
from ..security import ServiceError
from .request_context import actor_in, body_input

SOURCE_ID = re.compile(r'^(?:law_unit:unit_[0-9a-f]{24}|case_book:\d{4}年度案例【[^】]{1,40}】#\d{3})$')
VERSION = re.compile(r'[0-9a-f]{64}')


def attach_knowledge_service(app, database, config: KnowledgeServiceConfig) -> None:
    client = KnowledgeServiceClient(config)
    app.state.knowledge_service = config

    # 把服务接进原聊天「检索法律资料」的显式检索路径。没有本地法库时，这条路过去
    # 只能拿到 not_configured（界面上的「本机尚未连接法律资料库」）；接了这里之后，
    # 同一个会话、同一套权限与回执就能真正查到法条与案例。
    tasks = getattr(app.state, 'assistant_generation_tasks', None)
    if tasks is not None:
        from ..assistant.tools.knowledge_source import KnowledgeLibraryAdapter
        tasks.knowledge_adapter = KnowledgeLibraryAdapter(client)

    def fail(error: KnowledgeServiceError):
        return JSONResponse({'code': error.code, 'message': MESSAGES.get(error.code, '知识服务请求未完成。')},
                            status_code=STATUS_BY_CODE.get(error.code, 502))

    def call(operation, *args):
        try:
            return operation(*args)
        except KnowledgeServiceError as error:
            return fail(error)

    @app.get('/knowledge', response_class=HTMLResponse)
    def knowledge_page(request: Request):
        with database.session() as db:
            actor_in(request, db)
        return HTMLResponse(app.state.template_environment.get_template('knowledge.html').render(
            readonly=getattr(app.state, 'recovery_copy', False)))

    @app.get('/api/knowledge/status')
    def status(request: Request):
        with database.session() as db:
            actor_in(request, db)
        return call(client.status)

    @app.post('/api/knowledge/search')
    async def search(request: Request):
        with database.session() as db:
            actor_in(request, db, write=True)
        try:
            query = await body_input(request, d.KnowledgeSearchRequest)
        except ServiceError as error:
            # body_input 把所有模型校验都收口成 STATE_CONFLICT；检索词不合法
            # 要给出可分辨的错误码，否则前端只能显示一句泛化的失败提示。
            if error.code == 'STATE_CONFLICT':
                return fail(KnowledgeServiceError('KNOWLEDGE_QUERY_INVALID'))
            raise
        return await run_in_threadpool(call, client.search, query)

    @app.get('/api/knowledge/sources/{source_id}')
    def source(source_id: str, request: Request, start: int | None = None, end: int | None = None,
               version: str | None = None):
        with database.session() as db:
            actor_in(request, db)
        if not SOURCE_ID.fullmatch(source_id):
            return fail(KnowledgeServiceError('KNOWLEDGE_ID_INVALID'))
        if (start is not None and start < 0) or (end is not None and end <= 0):
            return fail(KnowledgeServiceError('KNOWLEDGE_RANGE_INVALID'))
        # 预期版本由前端从检索结果里带过来；格式不对就是调用方出错，不能退化成"不比版本"
        if version is not None and not VERSION.fullmatch(version):
            return fail(KnowledgeServiceError('KNOWLEDGE_QUERY_INVALID'))
        return call(client.source, source_id, start, end, version)
