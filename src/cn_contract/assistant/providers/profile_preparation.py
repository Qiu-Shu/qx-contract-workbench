"""Offline profile send description; no grants, storage, secrets or network."""
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from ... import domain as d
from . import profile_codec
from .deepseek_protocol import configuration, json_bytes


# Expanded source identities can be much larger than the provider's short quotes.
# Keep 16 KiB for the bounded output envelope within the existing 256 KiB reader.
MAX_CANDIDATE_BYTES = 240 * 1024


def _validated(kind, value):
    if type(value) is not kind:
        raise ValueError('PROFILE_INPUT_INVALID')
    return kind.model_validate(value.model_dump(mode='python', warnings=False))


def _sha(raw):
    return sha256(raw).hexdigest()


def basis_digest(basis: d.MainProfileSendBasis) -> str:
    """Include the local save plan; a wire/content hash alone cannot bind it."""
    basis = _validated(d.MainProfileSendBasis, basis)
    return _sha(json_bytes(basis.model_dump(mode='json')))


def build_basis(message: d.AssistantMessageInput, config: d.MainModelConfig, *,
                base_profile_revision: int, expected_intake_id=None,
                expected_intake_revision=None, project_intake=False, conversation_history=()) -> d.MainProfileSendBasis:
    message = _validated(d.AssistantMessageInput, message)
    config = configuration(config)
    if message.requested_skill is not None or message.attachment_ids:
        raise ValueError('profile-text-v1 supports only current text')
    wire = json_bytes(profile_codec._text_request(message.content, config, conversation_history))
    return d.MainProfileSendBasis(
        template_version='profile-text-system-v2' if conversation_history else 'profile-text-system-v1',
        conversation_history=conversation_history, request_id=message.request_id, expected_scope=message.expected_scope,
        expected_composer_revision=message.expected_composer_revision, content_sha256=_sha(message.content.encode('utf-8')),
        base_profile_revision=base_profile_revision, expected_intake_id=expected_intake_id,
        expected_intake_revision=expected_intake_revision, project_intake=project_intake,
        system_sha256=_sha(profile_codec.system(conversation_history).encode('utf-8')),
        config_sha256=_sha(json_bytes(config.model_dump(mode='json'))),
        wire_sha256=_sha(wire), wire_bytes=len(wire))


def prepare(run: d.AssistantRunView, message: d.AssistantMessageView, basis: d.MainProfileSendBasis,
            config: d.MainModelConfig, *, composer_revision: int) -> d.MainProfilePreparedInput:
    """Bind saved views; their database existence and current access stay outside."""
    run = _validated(d.AssistantRunView, run)
    message = _validated(d.AssistantMessageView, message)
    basis = _validated(d.MainProfileSendBasis, basis)
    config = configuration(config)
    if (run.request_id != basis.request_id or run.message_id != message.id or message.role != 'user'
            or run.requested_skill is not None
            or basis.system_sha256 != _sha(profile_codec.system(basis.conversation_history).encode('utf-8'))
            or basis.config_sha256 != _sha(json_bytes(config.model_dump(mode='json')))):
        raise ValueError('PROFILE_INPUT_INVALID')
    request = d.MainProfileRequest(run_id=run.id, message_id=message.id, scope=run.scope,
        template_version=basis.template_version, conversation_history=basis.conversation_history,
        content=message.content, source_sha256=_sha(message.content.encode('utf-8')),
        source_revision=message.source_revision, base_profile_revision=basis.base_profile_revision)
    return d.MainProfilePreparedInput(request=request, basis=basis, composer_revision=composer_revision,
        wire_payload_json=json_bytes(profile_codec.build_request(request, config)).decode('utf-8'))


def validate_candidate(candidate, request):
    """Keep live settlement and historical replay on the same text-only contract."""
    candidate = _validated(d.MainProfileCandidate, candidate)
    request = _validated(d.MainProfileRequest, request)
    if len(json_bytes(candidate.model_dump(mode='json'))) > MAX_CANDIDATE_BYTES:
        raise ValueError('PROFILE_OUTPUT_INVALID')
    patch = candidate.profile_patch
    if (candidate.citations or patch.scope != request.scope
            or patch.base_profile_revision != request.base_profile_revision):
        raise ValueError('PROFILE_OUTPUT_INVALID')
    for change in patch.changes:
        if (change.origin not in ('user_statement', 'model_inference')
                or change.value.kind == 'materials' and any(item.state != 'needed' for item in change.value.value)):
            raise ValueError('PROFILE_OUTPUT_INVALID')
        for ref in change.source_refs:
            if (type(ref) is not d.ProfileMessageRef or ref.conversation_id != request.scope.conversation_id
                    or ref.message_id != request.message_id or ref.source_revision != request.source_revision
                    or request.content[ref.start:ref.end] != ref.quote
                    or _sha(ref.quote.encode('utf-8')) != ref.quote_sha256):
                raise ValueError('PROFILE_OUTPUT_INVALID')
    return candidate


def commit_request(prepared, candidate):
    """A fixed event cannot acquire a second saving identity on replay."""
    prepared = _validated(d.MainProfilePreparedInput, prepared)
    candidate = validate_candidate(candidate, prepared.request)
    basis = prepared.basis
    return d.ProfileCommitInput(request_id=uuid5(NAMESPACE_URL, 'qx-profile.save:1:' + str(prepared.request.run_id)),
        patch=candidate.profile_patch, expected_intake_id=basis.expected_intake_id,
        expected_intake_revision=basis.expected_intake_revision, project_intake=basis.project_intake)
