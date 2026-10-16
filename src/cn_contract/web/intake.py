"""Reception routes reuse existing authentication, origin, CSRF and transactions."""
from uuid import UUID

from fastapi import Request, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from .. import domain as d
from ..intake import service
from .request_context import actor_in, body_input


def register_routes(app,database):
    def page(request,identifier=None):
        with database.session() as db:
            actor=actor_in(request,db)
            record=service.read(identifier,actor,db) if identifier else None
        return HTMLResponse(app.state.template_environment.get_template('intake.html' if identifier else 'workspace.html').render(
            record=record,library_enabled=hasattr(app.state,'library_root'),
            local_materials_enabled=getattr(database,'_local_materials_enabled',False)))

    @app.get('/workspace',response_class=HTMLResponse)
    def workspace(request:Request):return page(request)

    @app.get('/intakes/{identifier}',response_class=HTMLResponse)
    def intake_page(identifier:UUID,request:Request):return page(request,identifier)

    @app.get('/api/intakes')
    def intakes(request:Request,offset:int=Query(default=0,ge=0,le=1000000)):
        with database.session() as db:return service.listing(actor_in(request,db),db,offset)

    @app.get('/api/intakes/{identifier}')
    def detail(identifier:UUID,request:Request):
        with database.session() as db:return service.read(identifier,actor_in(request,db),db)

    @app.get('/api/intakes/{identifier}/revisions/{revision}')
    def history(identifier:UUID,revision:int,request:Request):
        if revision<1:
            from ..security import ServiceError
            raise ServiceError('VERSION_CONFLICT',409)
        with database.session() as db:return service.read(identifier,actor_in(request,db),db,revision)

    async def write(request,model,operation,identifier=None):
        # Authenticate and authorize before parsing potentially sensitive bodies.
        with database.session() as db:
            actor=actor_in(request,db,write=True)
            service._owned(identifier,actor,db) if identifier else service._lawyer(actor,db)
        value=await body_input(request,model)
        with database.session() as db:
            actor=actor_in(request,db,write=True)
            return operation(value,actor,db)

    @app.post('/api/intakes',status_code=201)
    async def create(request:Request):
        return await write(request,d.IntakeCreateInput,service.create)

    @app.put('/api/intakes/{identifier}')
    async def save(identifier:UUID,request:Request):
        return await write(request,d.IntakeUpdateInput,lambda v,a,db:service.save(identifier,v,a,db),identifier)

    @app.post('/api/intakes/{identifier}/convert')
    async def convert(identifier:UUID,request:Request):
        return await write(request,d.IntakeConvertInput,lambda v,a,db:service.convert(identifier,v,a,db),identifier)

    @app.post('/api/intakes/{identifier}/export')
    async def export(identifier:UUID,request:Request):
        data=await write(request,d.IntakeExportInput,lambda v,a,db:service.export(identifier,v,a,db),identifier)
        return Response(data,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition':'attachment; filename="reception-draft.docx"'})

    @app.get('/api/workspace/tasks')
    def tasks(request:Request):
        with database.session() as db:
            actor=actor_in(request,db)
            if not actor.roles & {d.Role.HANDLING_LAWYER,d.Role.REVIEWING_LAWYER,d.Role.ASSISTANT}:
                return []
            rows=db.execute(text('''SELECT j.id,j.matter_id,j.stage,j.state,m.title FROM web_jobs j
                JOIN matter_memberships g ON g.matter_id=j.matter_id AND g.user_id=:user
                JOIN matters m ON m.id=j.matter_id WHERE j.state IN ('queued','running')
                ORDER BY j.timestamp DESC LIMIT 50'''),{'user':str(actor.user_id)}).mappings().all()
            from ..security import authorize
            for identifier in {row['matter_id'] for row in rows}:
                authorize(actor,UUID(identifier),'read',db)
            return [dict(row) for row in rows]
