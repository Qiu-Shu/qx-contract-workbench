"""Bind archived profile replies to their source and one fixed saving receipt."""
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from .. import domain as d
from ..record_codec import sha as record_sha
from . import model_integrity as ledger, profile_integrity, conversation_history
from .providers import profile_codec, profile_preparation
from .providers.deepseek_protocol import json_bytes
from .providers.policy import encoded, sha


def validate_relations(db, attempts, outputs):
    """Check all owners before the shared empty-ledger shortcut, including orphans."""
    profiles = {row['id']: row for row in attempts if row['input_format'] == 'profile-text-v1'}
    adopted = profiles.keys() & outputs.keys()
    handlers = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().all()
    if len(handlers) != len(adopted) or {row['attempt_id'] for row in handlers} != adopted:
        ledger._fail()
    for identifier in profiles.keys() - adopted:
        row = profiles[identifier]
        request_id = uuid5(NAMESPACE_URL, 'qx-profile.save:1:' + row['run_id'])
        if db.scalar(text('''SELECT 1 FROM assistant_profile_receipts
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':row['conversation_id'], 'request':str(request_id)}):
            ledger._fail()
    events = db.execute(text('''SELECT * FROM assistant_run_events
        WHERE lower(event_type)='response.ready' OR lower(event_type) LIKE 'profile.%'
        ORDER BY run_id,seq''')).mappings().all()
    by_run = {}
    for event in events:
        by_run.setdefault(event['run_id'], []).append(event)
    if set(by_run) != {row['run_id'] for row in handlers}:
        ledger._fail()
    for handler in handlers:
        row = profiles[handler['attempt_id']]
        output = outputs[row['id']]
        pair = by_run[handler['run_id']]
        if (handler['run_id'] != row['run_id'] or handler['conversation_id'] != row['conversation_id']
                or handler['output_id'] != output['id'] or handler['handler_id'] != 'profile.save'
                or handler['handler_version'] != '1' or len(pair) != 2):
            ledger._fail()
        ready, result = pair
        outcome, reason, sequence = (handler[key] for key in ('outcome', 'reason_code', 'profile_receipt_sequence'))
        if (outcome not in ('applied', 'unchanged', 'blocked')
                or outcome == 'blocked' and (reason not in ('version_conflict', 'save_failed') or sequence is not None)
                or outcome != 'blocked' and (reason is not None or type(sequence) is not int or sequence < 1)):
            ledger._fail()
        ledger._hash(handler['basis_sha256'])
        payload = dict(attempt_id=row['id'], output_id=output['id'],
                       handler_id='profile.save', handler_version='1')
        if (ready['event_type'] != 'response.ready' or ready['seq'] != handler['event_seq']
                or json_bytes(ledger._json(ready['payload_json'], 16384)) != json_bytes(dict(payload, basis_sha256=handler['basis_sha256']))
                or result['event_type'] != {'applied':'profile.saved', 'unchanged':'profile.unchanged',
                                            'blocked':'profile.blocked'}[outcome]
                or json_bytes(ledger._json(result['payload_json'], 16384)) != json_bytes(dict(payload, event_seq=ready['seq'],
                    outcome=outcome, reason_code=reason, profile_receipt_sequence=sequence))):
            ledger._fail()
        finished = db.execute(text('''SELECT seq,created_at FROM assistant_run_events
            WHERE run_id=:run AND event_type='model.finished' '''), {'run':row['run_id']}).mappings().all()
        if (len(finished) != 1 or not ready['seq'] < result['seq'] < finished[0]['seq']
                or any(event['audience'] != 'internal' for event in pair)
                or not ledger._at(output['created_at']) <= ledger._at(ready['created_at'])
                    <= ledger._at(result['created_at']) <= ledger._at(finished[0]['created_at'])
                or not ledger._at(output['created_at']) <= ledger._at(handler['created_at'])
                    <= ledger._at(result['created_at'])):
            ledger._fail()


def _baseline(db, row, prepared, conversation):
    basis, scope = prepared.basis, prepared.basis.expected_scope
    at = ledger._at(row['created_at'])
    revisions = db.execute(text('''SELECT * FROM assistant_profile_revisions
        WHERE conversation_id=:cid ORDER BY revision'''), {'cid':row['conversation_id']}).mappings().all()
    preceding = [item for item in revisions if ledger._at(item['created_at']) <= at]
    if (preceding[-1]['revision'] if preceding else 0) != basis.base_profile_revision:
        ledger._fail()
    if preceding:
        saved = preceding[-1]
        previous = ledger._model(d.ProfileDraftState, saved['profile_json'])
        fixed = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
        if (sha(saved['profile_json']) != saved['profile_sha256'] or previous.revision != basis.base_profile_revision
                or any(getattr(previous.scope, key) != getattr(scope, key) for key in fixed)
                or previous.scope.input_revision > scope.input_revision
                or previous.scope.materials_revision > scope.materials_revision):
            ledger._fail()
    target = str(basis.expected_intake_id) if basis.expected_intake_id else None
    linked = conversation['scope_ref'] if scope.scope_kind == 'intake' else conversation['projection_intake_id']
    if target is not None:
        if target != linked:
            ledger._fail()
        profile_integrity._intake(db, target, basis.expected_intake_revision, conversation['owner_id'], at)
        newer = db.scalars(text('''SELECT saved_at FROM intake_revisions
            WHERE intake_id=:id AND revision>:rev'''), {'id':target, 'rev':basis.expected_intake_revision})
        if any(ledger._at(value) <= at for value in newer):
            ledger._fail()
    elif linked is not None:
        created = db.scalar(text('SELECT saved_at FROM intake_revisions WHERE intake_id=:id AND revision=1'), {'id':linked})
        if created is None or ledger._at(created) <= at:
            ledger._fail()


def validate_input(db, row, prepared, config, policy, run, conversation):
    request, basis = prepared.request, prepared.basis
    submission = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
        expected_composer_revision=basis.expected_composer_revision, content=request.content)
    digest = record_sha({'actor_id':run['actor_id'], 'workspace_id':conversation['workspace_id'],
        'conversation_id':conversation['id'], 'request':submission.model_dump(mode='json')})
    rebuilt = profile_preparation.build_basis(submission, config, base_profile_revision=basis.base_profile_revision,
        expected_intake_id=basis.expected_intake_id, expected_intake_revision=basis.expected_intake_revision,
        project_intake=basis.project_intake,
        conversation_history=(conversation_history.for_message(db, basis.expected_scope, request.content,
            config, before_at=ledger._at(row['created_at'])) if basis.conversation_history else ()))
    if (run['request_id'] != str(basis.request_id) or run['request_sha256'] != digest
            or run['requested_skill'] is not None or policy.max_calls != 1
            or policy.allowed_content_sha256s != (profile_preparation.basis_digest(basis),)
            or rebuilt != basis or row['round_no'] != 1
            or prepared.composer_revision > conversation['composer_revision']
            or row['request_sha256'] != sha(prepared.wire_payload_json)
            or json_bytes(profile_codec.build_request(request, config)).decode('utf-8') != prepared.wire_payload_json):
        ledger._fail()
    _baseline(db, row, prepared, conversation)


def validate_output(db, row, prepared, view, run):
    candidate = profile_preparation.validate_candidate(view.candidate, prepared.request)
    handler = db.execute(text('SELECT * FROM assistant_profile_handlers WHERE attempt_id=:id'),
                         {'id':row['id']}).mappings().one()
    if handler['basis_sha256'] != profile_preparation.basis_digest(prepared.basis):
        ledger._fail()
    request = profile_preparation.commit_request(prepared, candidate)
    receipt = db.execute(text('''SELECT * FROM assistant_profile_receipts
        WHERE conversation_id=:cid AND request_id=:request'''),
        {'cid':row['conversation_id'], 'request':str(request.request_id)}).mappings().first()
    if handler['outcome'] == 'blocked':
        if receipt is not None:
            ledger._fail()
        return
    if (receipt is None or receipt['sequence'] != handler['profile_receipt_sequence']
            or receipt['actor_id'] != run['actor_id'] or receipt['session_id'] != run['session_id']
            or receipt['request_json'] != encoded(request) or receipt['request_sha256'] != sha(encoded(request))
            or receipt['event_type'] != ('profile.saved' if handler['outcome'] == 'applied' else 'profile.unchanged')
            or not ledger._at(row['created_at']) <= ledger._at(receipt['created_at'])
                <= ledger._at(handler['created_at'])):
        ledger._fail()
