"""Select one still-valid user declaration from the verified business ledger."""
from sqlalchemy import text

from . import business, contract_review


def contract_stance_sources(db, current, question):
    """The v3 caller supplies the current record; model replies never supply stance."""
    if current.workflow != 'contract' or current.task_id is None:
        return ()
    intent = contract_review.stance_intent(question)
    if intent['invalid'] or intent['roles'] or len(intent['continuation']) != 1:
        return ()
    identity = next(iter(intent['continuation']))
    scope = current.scope
    rows = db.execute(text('''SELECT r.* FROM assistant_runs r
        JOIN assistant_run_events e ON e.run_id=r.id AND e.event_type='business.accepted'
        WHERE r.conversation_id=:cid
        AND json_extract(r.scope_snapshot,'$.workspace_id')=:workspace
        AND json_extract(r.scope_snapshot,'$.scope_kind')=:kind
        AND json_extract(r.scope_snapshot,'$.scope_ref') IS :ref
        AND json_extract(r.scope_snapshot,'$.binding_revision')=:binding
        AND json_extract(r.scope_snapshot,'$.input_revision')<:revision
        ORDER BY json_extract(r.scope_snapshot,'$.input_revision')'''),
        {'cid':str(scope.conversation_id), 'workspace':str(scope.workspace_id), 'kind':scope.scope_kind,
         'ref':str(scope.scope_ref) if scope.scope_ref else None, 'binding':scope.binding_revision,
         'revision':scope.input_revision}).mappings()
    latest = None
    for row in rows:
        accepted, previous = business._record(row, db)
        if previous.created_at > current.created_at:
            continue
        # Match the business entry's explicit new-task boundary before using a declined request's task.
        new_task = accepted.request.new_task or any(word in accepted.request.content
            for word in ('重新审查', '新建任务', '开始新任务'))
        same_task = previous.task_id == current.task_id or (previous.task_id is None
            and not new_task and accepted.request.task_id == current.task_id)
        if not same_task:
            # Unbound stance changes can stop inference, but can never establish another task's role.
            if (previous.task_id is None and accepted.request.task_id is None and not new_task
                    and contract_review.stance_intent(accepted.request.content)['relevant']):
                latest = None
            continue
        previous_intent = contract_review.stance_intent(accepted.request.content)
        if not previous_intent['relevant']:
            continue
        named = previous_intent['named']
        if (not previous_intent['invalid'] and len(named) == 1
                and previous_intent['roles'] == frozenset({named[0][1]})):
            latest = (named[0][0], row, accepted.request.content)
        elif (not previous_intent['invalid'] and not previous_intent['roles'] and latest is not None
                and previous_intent['continuation'] == frozenset({latest[0]})):
            continue
        else:
            latest = None
    if latest is None or latest[0] != identity:
        return ()
    from .material_preparation import consultation_source
    return (consultation_source(latest[1], latest[2]),)
