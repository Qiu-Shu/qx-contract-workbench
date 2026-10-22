"""Pure, unverified archive proposals. No authorization, persistence or model I/O.

The caller supplies an authorized source snapshot; exact matching here proves
location, not the truth of a statement or permission to commit it.
"""
import json

from ..record_codec import encode, sha
from ..domain import (
    IntakeDraft, ProfileDraftState, ProfileFieldState, ProfileMergeResult,
    ProfileEdit, ProfilePatch, ProfileProposal, ProfileSourceSnapshot,
    _profile_verification,
)


def _validate(model, value):
    # Unwrap nested instances so model_copy/model_construct cannot bypass validation.
    return model.model_validate(value.model_dump(mode='python'))


def _value_key(value):
    data = value.model_dump(mode='json')
    if value.kind == 'money':
        number = format(value.value, 'f')
        data['value'] = '0' if value.value == 0 else (number.rstrip('0').rstrip('.') if '.' in number else number)
    return encode(data)


def _candidates(items):
    merged = {}
    for item in items:
        key = (_value_key(item.value), item.origin)
        old = merged.get(key)
        refs = {encode(x.model_dump(mode='json')): x for x in old.source_refs} if old else {}
        refs.update({encode(x.model_dump(mode='json')): x for x in item.source_refs})
        data = item.model_dump(mode='python')
        if item.value.kind == 'money':
            data['value'] = json.loads(key[0])
        data['source_refs'] = [refs[k] for k in sorted(refs)]
        merged[key] = ProfileProposal.model_validate(data)
    known = {k: v for k, v in merged.items() if v.value.kind != 'null'}
    return tuple(v for k, v in sorted((known or merged).items()))


def _field(name, candidates, protected=None):
    candidates = _candidates(candidates)
    return ProfileFieldState(field=name, candidates=candidates, protected_value=protected,
                             verification=_profile_verification(candidates, protected))


def _source_maps(sources):
    messages = {x.id: x for x in sources.messages}
    documents = {x.attachment_id: x for x in sources.documents}
    if (len(messages) != len(sources.messages) or any(
            m.source_revision > sources.scope.input_revision for m in sources.messages)):
        raise ValueError('duplicate or future profile message')
    if len(documents) != len(sources.documents):
        raise ValueError('duplicate selected profile document')
    for d in sources.documents:
        if (d.conversation_id != sources.scope.conversation_id
                or d.result.version_id != d.attachment_id
                or d.parse_revision > sources.scope.materials_revision
                or sha(d.result.model_dump(mode='json')) != d.result_sha256):
            raise ValueError('profile document snapshot mismatch')
    return messages, documents


def _check_sources(proposal, scope, messages, documents):
    for ref in proposal.source_refs:
        if ref.conversation_id != scope.conversation_id:
            raise ValueError('profile source belongs to another conversation')
        if ref.kind == 'message':
            message = messages.get(ref.message_id)
            if (message is None or message.role != 'user'
                    or ref.source_revision != message.source_revision
                    or message.content[ref.start:ref.end] != ref.quote
                    or proposal.origin == 'document_statement'):
                raise ValueError('profile message source mismatch')
        else:
            document = documents.get(ref.attachment_id)
            if (document is None or document.parse_revision != ref.parse_revision
                    or document.original_sha256 != ref.original_sha256
                    or document.result_sha256 != ref.result_sha256
                    or ref.anchor not in document.result.anchors or not ref.anchor.quote
                    or proposal.origin == 'user_statement'):
                raise ValueError('profile document source mismatch')
    if proposal.value.kind == 'materials':
        names = {documents[r.attachment_id].original_name for r in proposal.source_refs if r.kind == 'document'}
        if any(m.state == 'received' and m.name not in names for m in proposal.value.value):
            raise ValueError('received material requires its selected attachment source')


def _intake_value(field, value):
    kind = {'questions': 'list', 'materials': 'materials', 'follow_up_at': 'datetime'}.get(field, 'text')
    return ProfileEdit(field=field, value={'kind': 'null' if value is None else kind, 'value': value}).value


def merge_profile(previous, patch, source_snapshot, *, intake_baseline=None,
                  intake_current=None, manual_edits=(), project_intake=False):
    """Merge into a proposal snapshot; no write or authority is implied by the result.

    manual_edits, intake snapshots and project_intake are trusted caller inputs,
    never fields accepted from a model response. Only known source-backed changes
    project by default; ambiguity remains in candidates, not a guessed value.
    """
    patch = _validate(ProfilePatch, patch)
    sources = _validate(ProfileSourceSnapshot, source_snapshot)
    previous = _validate(ProfileDraftState, previous) if previous is not None else None
    baseline = _validate(IntakeDraft, intake_baseline) if intake_baseline is not None else None
    current = _validate(IntakeDraft, intake_current) if intake_current is not None else None
    edits = tuple(_validate(ProfileEdit, x) for x in manual_edits)
    if type(project_intake) is not bool or len(edits) > 12 or len({x.field for x in edits}) != len(edits):
        raise ValueError('invalid trusted profile controls')
    if baseline is not None and (current is None or previous is None):
        raise ValueError('projection baseline requires a previous profile and current intake')
    revision = previous.revision if previous is not None else 0
    if patch.scope != sources.scope or patch.base_profile_revision != revision:
        raise ValueError('profile scope/revision mismatch')
    if previous is not None:
        fixed = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
        if (any(getattr(previous.scope, k) != getattr(sources.scope, k) for k in fixed)
                or previous.scope.input_revision > sources.scope.input_revision
                or previous.scope.materials_revision > sources.scope.materials_revision):
            raise ValueError('profile cannot change binding or move to an older source snapshot')
    messages, documents = _source_maps(sources)
    fields = {f.field: _field(f.field, f.candidates, f.protected_value)
              for f in previous.fields} if previous else {}
    if previous and len(fields) != len(previous.fields):
        raise ValueError('duplicate profile field')
    before = tuple(fields[k] for k in sorted(fields))
    if current is not None:
        for name in IntakeDraft.model_fields:
            if name == 'status':
                continue
            if baseline is None or getattr(current, name) != getattr(baseline, name):
                prior = fields.get(name)
                fields[name] = _field(name, prior.candidates if prior else (),
                                      _intake_value(name, getattr(current, name)))
    for edit in edits:
        prior = fields.get(edit.field)
        fields[edit.field] = _field(edit.field, prior.candidates if prior else (), edit.value)
    for proposal in patch.changes:
        _check_sources(proposal, sources.scope, messages, documents)
        prior = fields.get(proposal.field)
        fields[proposal.field] = _field(proposal.field, (*prior.candidates, proposal) if prior else (proposal,),
                                       prior.protected_value if prior else None)
    after = tuple(fields[k] for k in sorted(fields))
    changed = after != before
    state = (previous if previous is not None and not changed else
             ProfileDraftState(scope=sources.scope, revision=revision + int(changed), fields=after))
    draft = None
    if project_intake and (current is not None or any(
            f.field in IntakeDraft.model_fields and (f.protected_value is not None
                or any(c.value.kind != 'null' for c in f.candidates)) for f in after)):
        defaults = IntakeDraft(title='待整理咨询').model_dump(mode='python')
        values = current.model_dump(mode='python') if current is not None else dict(defaults)
        for f in after:
            if f.field not in IntakeDraft.model_fields:
                continue
            value = f.protected_value
            if value is None and f.verification == 'unverified' and f.candidates:
                value = f.candidates[0].value
            if value is not None and value.kind != 'null':
                values[f.field] = value.value
            else:
                values[f.field] = defaults[f.field]
        draft = IntakeDraft.model_validate(values)
    return ProfileMergeResult(profile=state, changed=changed, projection=draft)
