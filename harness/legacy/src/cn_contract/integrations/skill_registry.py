"""Read approved, pinned local methods into the existing material execution ledger."""
import hashlib
from pathlib import Path
from .. import domain as d
from ..ops.backup import redirected
from ..review.model_adapter import strict_json
from ..security import ServiceError
from ..assistant.contract_method import METHOD, METHOD_ID

METHOD_PATH = 'skills/instructions/SKILL.md'
METADATA_PATH = '.codex-plugin/plugin.json'
MAX_FILE_BYTES = 65536


def _read(path):
    path = Path(path).absolute()
    if any(redirected(item) for item in (path, *path.parents)):
        raise ValueError('CAPABILITY_SOURCE_REDIRECTED')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('CAPABILITY_SOURCE_TOO_LARGE')
    return raw


class SkillRegistry:
    def __init__(self, config):
        config = d.LocalSkillRegistryConfig.model_validate(config.model_dump(mode='python'))
        if any(not Path(binding.root).is_absolute() for binding in config.skills):
            raise ValueError('ABSOLUTE_CAPABILITY_ROOT_REQUIRED')
        self._bindings = {binding.workflow:binding for binding in config.skills}
        self._chiheng = config.chiheng
        self._knowledge = config.knowledge
        if self._chiheng is not None and not Path(self._chiheng.root).is_absolute():
            raise ValueError('ABSOLUTE_CAPABILITY_ROOT_REQUIRED')

    @classmethod
    def from_file(cls, path):
        return cls(d.LocalSkillRegistryConfig.model_validate(strict_json(_read(path).decode('utf-8'))))

    def resolve(self, workflow):
        if workflow == 'court':
            return self.hearing_adapter().capability
        if workflow == 'contract':
            return d.CapabilityInvocation(workflow='contract', kind='builtin', source_id='qx-contract-workbench',
                version=METHOD_ID, source_reference='https://github.com/Qiu-Shu/qx-contract-workbench',
                license_notice='群兴现有 C4 材料草稿适配方法；保留项目来源说明。',
                method_source='cn_contract.assistant.contract_method:METHOD',
                method_sha256=hashlib.sha256(METHOD.encode('utf-8')).hexdigest())
        binding = self._bindings.get(workflow)
        if binding is None or not binding.local_use_approved:
            raise ServiceError('CAPABILITY_UNAVAILABLE', 409)
        try:
            metadata_raw = _read(Path(binding.root) / METADATA_PATH)
            method_raw = _read(Path(binding.root) / METHOD_PATH)
            if (hashlib.sha256(metadata_raw).hexdigest() != binding.metadata_sha256
                    or hashlib.sha256(method_raw).hexdigest() != binding.method_sha256):
                raise ValueError('CAPABILITY_SOURCE_CHANGED')
            metadata = strict_json(metadata_raw.decode('utf-8'))
            if (not isinstance(metadata, dict) or metadata.get('name') != binding.source_id
                    or metadata.get('version') != binding.version):
                raise ValueError('CAPABILITY_IDENTITY_CHANGED')
            return d.CapabilityInvocation(workflow=workflow, kind='local_skill', source_id=binding.source_id,
                version=binding.version, source_reference=binding.source_reference, license_notice=binding.license_notice,
                method_source=METHOD_PATH, method_sha256=binding.method_sha256,
                metadata_sha256=binding.metadata_sha256, method_text=method_raw.decode('utf-8'))
        except (OSError, ValueError, TypeError):
            raise ServiceError('CAPABILITY_UNAVAILABLE', 409) from None

    def hearing_adapter(self):
        from .chiheng import ChihengAdapter
        if self._chiheng is None or not self._chiheng.local_use_approved:
            raise ServiceError('CAPABILITY_UNAVAILABLE', 409)
        try:
            sources = {item.path:_read(Path(self._chiheng.root)/item.path) for item in self._chiheng.files}
            if any(hashlib.sha256(sources[item.path]).hexdigest() != item.sha256 for item in self._chiheng.files):
                raise ValueError('CAPABILITY_SOURCE_CHANGED')
            return ChihengAdapter(self._chiheng, sources)
        except (OSError, ValueError, ImportError):
            raise ServiceError('CAPABILITY_UNAVAILABLE', 409) from None

    def retrieve(self, workflow, question):
        if self._knowledge is None:
            return None
        from .knowledge import retrieve
        return retrieve(self._knowledge, self._bindings, workflow, question)


def resolve_for(db, workflow):
    registry = getattr(db.info.get('database'), '_capability_registry', None)
    if registry is None:
        return None
    if type(registry) is not SkillRegistry:
        raise ServiceError('CAPABILITY_UNAVAILABLE', 409)
    return registry.resolve(workflow)


def contract_review_for(workflow, materials, sources):
    """Finite host-authored adjuncts; no arbitrary Skill paths or tool dispatch."""
    from ..assistant.contract_review import select_method
    return select_method(workflow, materials, sources)


def criminal_analysis_for(workflow, question, sources):
    """Finite adjunct; the existing family capability remains independently bound."""
    from ..assistant.criminal_analysis import select_method
    return select_method(workflow, question, sources)


def trademark_triage_for(workflow, question):
    from ..assistant.trademark_triage import select_method
    return select_method(workflow, question)
