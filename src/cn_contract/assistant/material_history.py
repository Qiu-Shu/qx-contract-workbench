"""Bounded same-task replies rebuilt and verified from the persisted ledger."""
from decimal import Context, localcontext

from sqlalchemy import text

from .. import domain as d
from .conversation_history import FIXED_SCOPE, MAX_BYTES, MAX_TURNS
from .providers.deepseek_protocol import json_bytes


def _verify(db, queue, workspace, attachment_rows):
    from . import model_integrity as ledger
    checked = set()
    files = {row['id'] for row in attachment_rows} if attachment_rows is not None else set()
    # Validate the history dependency graph once, without recursive call depth.
    with localcontext(Context(prec=60)):
        while queue:
            row = queue.pop()
            if row['id'] in checked:
                continue
            checked.add(row['id'])
            if (db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts WHERE run_id=:id'),
                    {'id':row['run_id']}) != 1
                    or db.scalar(text("SELECT COUNT(*) FROM assistant_model_attempts WHERE policy_id=:id AND state!='failed_before_send'"),
                        {'id':row['policy_id']}) != 1):
                ledger._fail()
            receipts = {r['attempt_id']:r for r in db.execute(text(
                'SELECT * FROM assistant_model_receipts WHERE attempt_id=:id'), {'id':row['id']}).mappings()}
            outputs = {r['attempt_id']:r for r in db.execute(text(
                'SELECT * FROM assistant_model_outputs WHERE attempt_id=:id'), {'id':row['id']}).mappings()}
            ledger._validate(db, [row], receipts, outputs, str(workspace), context_schema=True,
                material_schema=True, selected_only=True, material_history_queue=queue)
            if attachment_rows is not None:
                prepared = ledger._model(d.MainMaterialPreparedInput, row['input_json'])
                for material in prepared.request.basis.manifest.materials:
                    identifier = str(material.attachment_id)
                    if identifier not in files:
                        attachment_rows.append(dict(db.execute(text('SELECT * FROM assistant_attachments WHERE id=:id'),
                            {'id':identifier}).mappings().one()))
                        files.add(identifier)


def select_history(db, scope, task_id, *, before_at, validation_queue=None, attachment_rows=None, budget=MAX_BYTES):
    from . import model_integrity as ledger
    # Filter before the bounded selection so another task cannot evict this one.
    rows = db.execute(text('''SELECT * FROM (SELECT a.*,
        ROW_NUMBER() OVER (PARTITION BY json_extract(a.input_json,'$.request.basis.parent_business_run_id')
            ORDER BY json_extract(r.scope_snapshot,'$.input_revision') DESC) AS parent_order
        FROM assistant_model_attempts a
        JOIN assistant_runs r ON r.id=a.run_id
        JOIN assistant_model_outputs o ON o.attempt_id=a.id
        WHERE a.conversation_id=:cid AND r.conversation_id=:cid AND o.conversation_id=:cid
        AND a.input_format='material-business-v1' AND a.state='received' AND a.round_no=1
        AND r.state='completed' AND r.cancel_requested=0
        AND json_extract(a.input_json,'$.request.basis.manifest.stable_task_id')=:task
        AND json_extract(r.scope_snapshot,'$.workspace_id')=:workspace
        AND json_extract(r.scope_snapshot,'$.scope_kind')=:kind
        AND json_extract(r.scope_snapshot,'$.scope_ref') IS :ref
        AND json_extract(r.scope_snapshot,'$.binding_revision')=:binding
        AND json_extract(r.scope_snapshot,'$.input_revision')<:revision
        AND o.created_at<=:at) WHERE parent_order=1
        ORDER BY json_extract(input_json,'$.request.basis.manifest.sources[0].reference.source_revision') DESC LIMIT 9'''),
        {'cid':str(scope.conversation_id), 'task':str(task_id), 'workspace':str(scope.workspace_id),
         'kind':scope.scope_kind, 'ref':str(scope.scope_ref) if scope.scope_ref else None,
         'binding':scope.binding_revision, 'revision':scope.input_revision, 'at':before_at.isoformat()}).mappings().all()
    turns, selected = (), []
    for row in rows:
        prepared = ledger._model(d.MainMaterialPreparedInput, row['input_json'])
        request, manifest = prepared.request, prepared.request.basis.manifest
        output_row = db.execute(text('SELECT * FROM assistant_model_outputs WHERE attempt_id=:id'),
            {'id':row['id']}).mappings().one()
        output = ledger._model(d.MainMaterialOutputView, output_row['output_json'], 262144)
        source = next((item.reference for item in manifest.sources if isinstance(item.reference, d.ProfileMessageRef)), None)
        if (source is None or manifest.stable_task_id != task_id or output.manifest != manifest
                or any(getattr(request.scope, key) != getattr(scope, key) for key in FIXED_SCOPE)
                or not source.source_revision < request.scope.input_revision < scope.input_revision
                or output.created_at > before_at):
            ledger._fail()
        pair = (d.ConversationHistoryMessage(message_id=source.message_id, role='user',
                    source_revision=source.source_revision, content=manifest.question),
                d.ConversationHistoryMessage(message_id=output.id, role='assistant',
                    source_revision=source.source_revision, content=output.candidate.text))
        candidate = (*pair, *turns)
        if len(turns) == MAX_TURNS * 2 or len(json_bytes([item.model_dump(mode='json') for item in candidate])) > min(MAX_BYTES, budget):
            break
        turns = candidate
        selected.append(row)
    if validation_queue is None:
        _verify(db, selected, scope.workspace_id, attachment_rows)
    else:
        validation_queue.extend(selected)
    return turns


def statement_sources(db, current, selected):
    """Court may cite earlier same-case user statements; model text is never a fact source."""
    if current.workflow != 'court':
        return ()
    from . import business, attachment_records
    from .material_preparation import consultation_source
    scope = current.scope
    rows = db.execute(text('''SELECT r.* FROM assistant_runs r
        JOIN assistant_run_events e ON e.run_id=r.id AND e.event_type='business.accepted'
        WHERE r.conversation_id=:cid AND r.state='completed' AND r.cancel_requested=0
        AND json_extract(e.payload_json,'$.workflow')='case'
        AND json_extract(r.scope_snapshot,'$.workspace_id')=:workspace
        AND json_extract(r.scope_snapshot,'$.scope_kind')=:kind
        AND json_extract(r.scope_snapshot,'$.scope_ref') IS :ref
        AND json_extract(r.scope_snapshot,'$.binding_revision')=:binding
        AND json_extract(r.scope_snapshot,'$.input_revision')<:revision
        ORDER BY json_extract(r.scope_snapshot,'$.input_revision') DESC'''),
        {'cid':str(scope.conversation_id), 'workspace':str(scope.workspace_id), 'kind':scope.scope_kind,
         'ref':str(scope.scope_ref) if scope.scope_ref else None, 'binding':scope.binding_revision,
         'revision':scope.input_revision}).mappings().all()
    candidates = [(row, business._record(row, db)) for row in rows]
    candidates = [(row, record) for row, record in candidates
                  if record is not None and record[1].created_at <= current.created_at]
    materials = frozenset((item.attachment_id, item.parse_revision) for item in selected)
    if scope.scope_kind != 'matter':
        if not materials:
            return ()
        snapshots = {}
        for _, record in candidates:
            revision = record[1].scope.materials_revision
            if revision not in snapshots:
                raw = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
                    {'cid':str(scope.conversation_id), 'rev':revision})
                items = attachment_records.decode_items(raw) if raw is not None else ()
                snapshots[revision] = frozenset((item.attachment_id, item.parse_revision) for item in items)
        tasks = {record[1].task_id for _, record in candidates if snapshots[record[1].scope.materials_revision] == materials}
        if len(tasks) != 1:
            return ()
        task = next(iter(tasks))
        candidates = [(row, record) for row, record in candidates if record[1].task_id == task
                      and snapshots[record[1].scope.materials_revision] <= materials]
    sources = ()
    for row, record in candidates:
        source = consultation_source(row, record[0].request.content)
        candidate = (source, *sources)
        if len(sources) == MAX_TURNS or len(json_bytes([item.model_dump(mode='json') for item in candidate])) > MAX_BYTES - 2:
            break
        sources = candidate
    return sources


def history_budget(context):
    return MAX_BYTES - len(json_bytes([item.model_dump(mode='json') for item in context])) if context else MAX_BYTES
