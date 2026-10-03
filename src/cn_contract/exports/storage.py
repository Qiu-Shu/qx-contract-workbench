"""Immutable technical snapshots and transaction-owned derived bytes."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,stat
from uuid import UUID,uuid4
from sqlalchemy import Integer,String,Text,ForeignKey,select
from sqlalchemy.orm import Mapped,mapped_column
from ..persistence import Base,Database,UTCDateTime,configured_database,_remember_original,ExportRow,SessionRow,MembershipRow,UserRow
from ..security import ServiceError,_principal
from ..providers.qcc_registry import authorize_case
from ..domain import AuditEvent,Role,Patch,ReviewRun


class ExportRecordRow(Base):
    __tablename__='export_records'
    sequence:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    ref:Mapped[str]=mapped_column(String(36),unique=True)
    matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(String(36))
    kind:Mapped[str]=mapped_column(String(32))
    parent:Mapped[str]=mapped_column(String(36))
    payload:Mapped[str]=mapped_column(Text)
    sha256:Mapped[str]=mapped_column(String(64))
    timestamp:Mapped[datetime]=mapped_column(UTCDateTime())


def initialize_storage(database):
    if not isinstance(database,Database):raise TypeError('explicit Database required')
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=[ExportRecordRow.__table__])
        for action in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS immutable_export_records_{action.lower()} BEFORE {action} ON export_records BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END")
    database._export_storage_initialized=True


def require_storage(db):
    if not getattr(configured_database(db),'_export_storage_initialized',False):raise RuntimeError('initialize_storage(Database) required')


def now():return datetime.now(timezone.utc)
def encode(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def sha(value):return hashlib.sha256(encode(value).encode()).hexdigest()


def authorize(actor,matter_id,db,*,write=False,sign=False,review=False):
    require_storage(db)
    try:
        authorize_case(actor,matter_id,db)
        principal=_principal(db.get(SessionRow,str(actor.session_id),populate_existing=True),db,user_id=actor.user_id)
        if write and not principal.roles & {Role.HANDLING_LAWYER,Role.REVIEWING_LAWYER}:raise ServiceError('CROSS_MATTER_DENIED',403)
        if review and Role.REVIEWING_LAWYER not in principal.roles:raise ServiceError('CROSS_MATTER_DENIED',403)
        if sign:
            member=db.get(MembershipRow,(str(matter_id),str(actor.user_id)),populate_existing=True)
            if Role.REVIEWING_LAWYER not in principal.roles or not member.can_sign:raise ServiceError('CROSS_MATTER_DENIED',403)
    except ServiceError as error:
        audit(actor,matter_id,'authorization_denied',error.code,db,correlation=error.correlation_id)
        raise


def audit(actor,matter_id,action,reason,db,*,entity_id=None,after_hash=None,correlation=None):
    from ..audit import append_event
    append_event(AuditEvent(id=uuid4(),matter_id=matter_id,actor_id=actor.user_id,action=action,
        entity_type='matter',entity_id=entity_id or matter_id,before_hash=None,after_hash=after_hash,
        timestamp=now(),reason=reason,correlation_id=correlation or uuid4()),db)


def approver_valid(user_id,matter_id,db,*,high=False):
    user=db.get(UserRow,str(user_id),populate_existing=True)
    member=db.get(MembershipRow,(str(matter_id),str(user_id)),populate_existing=True)
    return bool(user and member and not user.disabled and
        (('reviewing_lawyer' in json.loads(user.roles)) if high else
         set(json.loads(user.roles))&{'handling_lawyer','reviewing_lawyer'}))


def append(kind,parent,payload,actor,matter_id,db):
    require_storage(db)
    row=ExportRecordRow(ref=str(uuid4()),kind=kind,parent=str(parent),matter_id=str(matter_id),actor_id=str(actor.user_id),
        payload=encode(payload),sha256=sha(payload),timestamp=now())
    db.add(row);db.flush();return row


def latest(kind,parent,db):
    require_storage(db)
    row=db.scalar(select(ExportRecordRow).where(ExportRecordRow.kind==kind,ExportRecordRow.parent==str(parent)).order_by(ExportRecordRow.sequence.desc()))
    if row and sha(json.loads(row.payload))!=row.sha256:raise ServiceError('VERSION_CONFLICT',409)
    return row


def load_run(run,actor,db):
    from ..review.storage import read_run
    authorize(actor,run.matter_id,db,write=True)
    from ..ops.storage import require_active
    require_active(db)
    actual=read_run(run.matter_id,run.id,actor,db=db,current=True)
    try:checked=ReviewRun.model_validate_json(run.model_dump_json())
    except Exception:raise ServiceError('VERSION_CONFLICT',409) from None
    if checked!=actual or actual.status!='completed':raise ServiceError('VERSION_CONFLICT',409)
    return actual


def load_patch(matter_id,patch,actor,db,*,audience=None,write=True):
    authorize(actor,matter_id,db,write=write)
    from ..ops.storage import require_active
    require_active(db)
    try:patch=Patch.model_validate_json(patch.model_dump_json())
    except Exception:raise ServiceError('VERSION_CONFLICT',409) from None
    row=latest('patch_approval',patch.id,db)
    if not row or row.matter_id!=str(matter_id) or not approver_valid(row.actor_id,matter_id,db):raise ServiceError('VERSION_CONFLICT',409)
    value=json.loads(row.payload)
    if latest('patch_revocation',row.ref,db) or value['patch']!=patch.model_dump(mode='json'):
        raise ServiceError('VERSION_CONFLICT',409)
    if audience is not None and audience not in value['audiences']:raise ServiceError('CROSS_MATTER_DENIED',403)
    from ..review.storage import read_run
    run=read_run(matter_id,UUID(value['run_id']),actor,db=db,current=True)
    if sha(run.model_dump(mode='json'))!=value['run_sha256']:raise ServiceError('APPROVAL_STALE',409)
    finding=next((f for f in run.findings if f.id==patch.finding_id),None)
    if finding is None:raise ServiceError('APPROVAL_STALE',409)
    if finding.severity=='high':
        from ..review.storage import ReviewRunRow
        run_row=db.get(ReviewRunRow,str(run.id),populate_existing=True)
        if row.actor_id==run_row.actor_id or not approver_valid(row.actor_id,matter_id,db,high=True):
            raise ServiceError('APPROVAL_STALE',409)
        try:
            if _principal(db.get(SessionRow,value['approval_session_id'],populate_existing=True),db,user_id=UUID(row.actor_id)) is None:
                raise ServiceError('APPROVAL_STALE',409)
        except (ServiceError,KeyError):raise ServiceError('APPROVAL_STALE',409) from None
    return patch,run,row


def file_root(db):return configured_database(db).storage_root/'derived_exports'


def store_bytes(data,identifier,db):
    root=file_root(db);root.mkdir(exist_ok=True)
    if redirected(root):raise ServiceError('VERSION_CONFLICT',409)
    path=root/(str(identifier)+'.docx')
    with open(path,'xb') as stream:
        _remember_original(db,path,root)
        stream.write(data)
    path.chmod(stat.S_IREAD)
    return str(path)


def redirected(path):
    try:return path.is_symlink() or bool(path.lstat().st_file_attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024))
    except AttributeError:return path.is_symlink()
    except OSError:return True


def checked_bytes(path,digest,db):
    from ..ops.storage import relocation
    path=relocation(path,digest,db)
    actual_root=file_root(db);root=actual_root.resolve();candidate=Path(path)
    if redirected(actual_root) or redirected(candidate) or candidate.stat().st_nlink>1 or not candidate.resolve().is_relative_to(root) or candidate.resolve().parent!=root:
        raise ServiceError('VERSION_CONFLICT',409)
    try:data=candidate.read_bytes()
    except OSError:raise ServiceError('VERSION_CONFLICT',409) from None
    if hashlib.sha256(data).hexdigest()!=digest:raise ServiceError('VERSION_CONFLICT',409)
    return data


def read_patch_artifact(matter_id,patch_id,actor,*,db):
    authorize(actor,matter_id,db)
    row=latest('patch_result',patch_id,db)
    if not row or row.matter_id!=str(matter_id):raise ServiceError('CROSS_MATTER_DENIED',403)
    approval=latest('patch_approval',patch_id,db)
    if not approval or approval.matter_id!=str(matter_id):raise ServiceError('CROSS_MATTER_DENIED',403)
    load_patch(matter_id,Patch.model_validate(json.loads(approval.payload)['patch']),actor,db,write=False)
    value=json.loads(row.payload)
    if value['status']!='applied':raise ServiceError('VERSION_CONFLICT',409)
    return checked_bytes(value['storage_ref'],value['target_sha256'],db)
