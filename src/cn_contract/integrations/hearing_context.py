"""Same-task hearing continuation, rebuilt from owned immutable outputs."""
import re
from sqlalchemy import text
from .. import domain as d
from ..security import ServiceError
from ..assistant import business, material_history
from .chiheng import ROLES, STAGES


def explicit_role(question):
    direct = business._direct_text(question)
    if (re.search(r'(?:原告|被告)[^，,。；;\n]*[?？]', direct)
            or re.search(r'(?:不是|并非|不代表)[^，,。；;\n]{0,8}(?:原告|被告)', direct)):
        return None
    commands = business._command_text(question)
    found = re.findall(r'(?m)^(?:本案中)?(?:我是|我方是|我方为|我方代表|我代表|代表)(原告|被告)(?:方)?(?:的)?(?:代理律师|律师)?[ \t]*$', commands)
    # Conflicting or negated role statements require clarification, not inference.
    if not found or len(set(found)) != 1 or all(word in commands for word in ('原告', '被告')):
        return None
    return {'原告':'plaintiff', '被告':'defendant'}[found[0]]


def build(db, result, materials, capability, *, synthetic, validation_queue=None):
    scope = result.scope
    row = db.execute(text('''SELECT a.*, o.output_json FROM assistant_model_attempts a
        JOIN assistant_model_outputs o ON o.attempt_id=a.id JOIN assistant_runs r ON r.id=a.run_id
        WHERE a.conversation_id=:cid AND o.conversation_id=:cid AND r.conversation_id=:cid
        AND a.input_format='material-business-v1' AND a.state='received'
        AND r.state='completed' AND r.cancel_requested=0 AND o.created_at<=:at
        AND json_extract(a.input_json,'$.request.basis.manifest.stable_task_id')=:task
        AND json_extract(r.scope_snapshot,'$.input_revision')<:revision
        AND json_extract(o.output_json,'$.hearing') IS NOT NULL
        ORDER BY json_extract(r.scope_snapshot,'$.input_revision') DESC LIMIT 1'''),
        {'cid':str(scope.conversation_id), 'task':str(result.task_id), 'at':result.created_at.isoformat(),
         'revision':scope.input_revision}).mappings().first()
    previous = d.MainMaterialOutputView.model_validate_json(row['output_json']) if row else None
    if previous:
        from ..assistant.conversation_history import FIXED_SCOPE
        if (previous.manifest.stable_task_id != result.task_id
                or any(getattr(previous.scope,key) != getattr(scope,key) for key in FIXED_SCOPE)
                or previous.created_at > result.created_at):
            raise ValueError('HEARING_HISTORY_INVALID')
        if validation_queue is None:
            material_history._verify(db, [row], scope.workspace_id, None)
        else:
            validation_queue.append(row)
    parent = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(result.run_id)}).mappings().one()
    question = business._record(parent, db)[0].request.content
    role = explicit_role(question)
    if role is None and previous and re.fullmatch(r'(?:请)?继续(?:模拟法庭|演练|庭审准备)[。！!\s]*', question):
        role = previous.hearing.session.our_role
    if role is None:
        raise ServiceError('HEARING_ROLE_REQUIRED', 409)
    if previous and role != previous.hearing.session.our_role:
        raise ServiceError('HEARING_ROLE_CONFLICT', 409)
    reset = None
    session = previous.hearing.session if previous else None
    if previous and tuple(materials) != previous.manifest.materials:
        session, reset = None, 'materials_changed'
    elif previous and capability != previous.manifest.capability:
        session, reset = None, 'method_changed'
    if session and (session.completed or session.synthetic != synthetic):
        raise ServiceError('HEARING_RESTART_REQUIRED', 409)
    stage = 'issues' if session is None else STAGES[STAGES.index(session.stage)+1]
    return d.HearingContext(our_role=role, synthetic=synthetic, stage=stage, roles=ROLES[stage],
        previous_output_id=previous.id if previous else None, previous_session=session, reset_reason=reset)
