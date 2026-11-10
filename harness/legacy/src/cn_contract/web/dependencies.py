"""Cookie-only server identity and CSRF dependencies for subsequent HTTP routes."""
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from ..persistence import Database
from ..security import ServiceError, authenticate, authorize, verify_csrf


def configure_app(app, database: Database) -> None:
    app.state.database = database


def get_db(request: Request):
    database = getattr(request.app.state, 'database', None)
    if not isinstance(database, Database):
        raise RuntimeError('configure_app must supply an explicit Database')
    with database.session() as db:
        yield db


def get_actor(request: Request, db=Depends(get_db)):
    actor = authenticate(request.cookies.get('qx_session'), db)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        try:
            matter_id = UUID(str(request.path_params.get('matter_id', UUID(int=0))))
        except (ValueError, TypeError):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        verify_csrf(actor, request.headers.get('X-CSRF-Token'), matter_id, db)
    return actor


def require_matter(action: str):
    def dependency(request: Request, actor=Depends(get_actor), db=Depends(get_db)):
        try:
            matter_id = UUID(str(request.path_params['matter_id']))
        except (KeyError, ValueError, TypeError):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        authorize(actor, matter_id, action, db)
        return actor
    return dependency


async def service_error_handler(request: Request, error: ServiceError):
    return JSONResponse(status_code=error.status_code, content={
        'code': error.code, 'message': str(error), 'correlation_id': str(error.correlation_id),
        'retryable': error.retryable,
    })
