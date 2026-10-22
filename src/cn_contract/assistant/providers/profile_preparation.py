"""Offline profile send description; no grants, storage, secrets or network."""
from hashlib import sha256

from ... import domain as d
from . import profile_codec
from .deepseek_protocol import configuration, json_bytes


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
                expected_intake_revision=None, project_intake=False) -> d.MainProfileSendBasis:
    message = _validated(d.AssistantMessageInput, message)
    config = configuration(config)
    if message.requested_skill is not None or message.attachment_ids:
        raise ValueError('profile-text-v1 supports only current text')
    wire = json_bytes(profile_codec._text_request(message.content, config))
    return d.MainProfileSendBasis(request_id=message.request_id, expected_scope=message.expected_scope,
        expected_composer_revision=message.expected_composer_revision, content_sha256=_sha(message.content.encode('utf-8')),
        base_profile_revision=base_profile_revision, expected_intake_id=expected_intake_id,
        expected_intake_revision=expected_intake_revision, project_intake=project_intake,
        system_sha256=_sha(profile_codec._SYSTEM.encode('utf-8')),
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
            or basis.system_sha256 != _sha(profile_codec._SYSTEM.encode('utf-8'))
            or basis.config_sha256 != _sha(json_bytes(config.model_dump(mode='json')))):
        raise ValueError('PROFILE_INPUT_INVALID')
    request = d.MainProfileRequest(run_id=run.id, message_id=message.id, scope=run.scope,
        content=message.content, source_sha256=_sha(message.content.encode('utf-8')),
        source_revision=message.source_revision, base_profile_revision=basis.base_profile_revision)
    return d.MainProfilePreparedInput(request=request, basis=basis, composer_revision=composer_revision,
        wire_payload_json=json_bytes(profile_codec.build_request(request, config)).decode('utf-8'))
