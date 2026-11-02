"""Pinned existing Chiheng code; ephemeral files, one durable workbench output.

The local administrator approves executable source hashes. This is not a sandbox.
Sources are captured before compilation; no import runs from an unpinned checkout.
External module imports are private to this adapter, not added to sys.modules.
"""
import builtins
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
from .. import domain as d
from ..assistant.providers.policy import sha
from ..config import canonical_json

ROLES = {'issues':('moderator', 'plaintiff', 'defendant'), 'evidence':('plaintiff', 'defendant'),
    'questions':('moderator', 'plaintiff', 'defendant'), 'debate':('plaintiff', 'defendant'), 'review':('reviewer',)}
STAGES = tuple(ROLES)


def material_texts(manifest):
    values = {item.source_id:item.reference.anchor.quote for item in manifest.sources
        if isinstance(item.reference, d.ProfileDocumentRef)}
    if not 1 <= len(values) <= 100:
        raise ValueError('HEARING_MATERIAL_LIMIT')
    return values


def packet_for(manifest):
    return dict(case_id=str(manifest.stable_task_id), procedure='civil_first_instance',
        our_role=manifest.hearing.our_role, synthetic=manifest.hearing.synthetic, human_review=None,
        materials=[dict(id=key, relative_path=key+'.txt', sha256=sha(value))
            for key,value in material_texts(manifest).items()])


def check_candidate(candidate, manifest):
    context = manifest.hearing
    if context is None:
        if candidate.hearing_turns:
            raise ValueError('HEARING_OUTPUT_INVALID')
        return
    if (tuple(turn.role for turn in candidate.hearing_turns) != context.roles
            or any(turn.stage != context.stage or not set(turn.material_ids) <= set(material_texts(manifest))
                or not set(turn.material_ids) <= set(candidate.citations) for turn in candidate.hearing_turns)):
        raise ValueError('HEARING_OUTPUT_INVALID')
    knowledge = {item.source_id for item in manifest.knowledge.passages} if manifest.knowledge else set()
    if any(not set(turn.knowledge_ids) <= knowledge or not set(turn.knowledge_ids) <= set(candidate.citations)
            or len(set(turn.knowledge_ids)) != len(turn.knowledge_ids) for turn in candidate.hearing_turns):
        raise ValueError('HEARING_OUTPUT_INVALID')


def stored_turns(candidate, manifest):
    knowledge = {item.source_id:item for item in manifest.knowledge.passages} if manifest.knowledge else {}
    return tuple(d.HearingStoredTurn(**turn.model_dump(mode='python',exclude={'knowledge_ids'}), case_id=manifest.stable_task_id,
        source_cards=tuple(knowledge[key] for key in turn.knowledge_ids),
        synthetic=manifest.hearing.synthetic) for turn in candidate.hearing_turns)


def validate_result(view):
    manifest, result = view.manifest, view.hearing
    check_candidate(view.candidate, manifest)
    if manifest.hearing is None:
        if result is not None:
            raise ValueError('HEARING_OUTPUT_INVALID')
        return
    if result is None:
        raise ValueError('HEARING_OUTPUT_INVALID')
    session = result.session
    packet = packet_for(manifest)
    previous = manifest.hearing.previous_session
    turns = (*previous.turns, *stored_turns(view.candidate, manifest)) if previous else stored_turns(view.candidate, manifest)
    if (any(session.model_dump(mode='json')[key] != value for key,value in packet.items())
            or session.turns != turns or session.stage != manifest.hearing.stage
            or session.completed != (manifest.hearing.stage == 'review')
            or result.structural_completed != session.completed):
        raise ValueError('HEARING_OUTPUT_INVALID')


class ChihengAdapter:
    def __init__(self, binding, sources):
        files = tuple(sorted(binding.files, key=lambda item:item.path))
        self.capability = d.CapabilityInvocation(workflow='court', kind='local_adapter',
            source_id='chiheng-legal-workbench', version=binding.version,
            source_reference=binding.source_reference, license_notice=binding.license_notice,
            method_source='mock_hearing:create_session/append_turn/load_session/hearing_progress',
            method_sha256=sha(canonical_json([item.model_dump(mode='json') for item in files])), code_files=files)
        self._sources = {name[:-3]:raw for name,raw in sources.items()}
        self._engine = self._load()  # Missing platform dependencies block before a model send.
        if not all(callable(getattr(self._engine, name, None)) for name in
                ('create_session', 'append_turn', 'load_session', 'hearing_progress')):
            raise ValueError('CAPABILITY_API_UNAVAILABLE')

    def _load(self):
        modules = {}
        def local_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name in self._sources:
                return load(name)
            return builtins.__import__(name, globals, locals, fromlist, level)
        def load(name):
            if name not in modules:
                module = ModuleType('qx_pinned_chiheng.'+name)
                modules[name] = module
                module.__dict__['__builtins__'] = dict(vars(builtins), __import__=local_import)
                exec(compile(self._sources[name], '<pinned-chiheng/'+name+'.py>', 'exec'), module.__dict__)
            return modules[name]
        return load('mock_hearing')

    def record(self, manifest, candidate):
        if manifest.capability != self.capability:
            raise ValueError('CAPABILITY_SOURCE_CHANGED')
        check_candidate(candidate, manifest)
        engine = self._engine
        # The upstream owns ACLs, ordering and file verification. The ledger owns
        # the result: a crash discards only temporary files and cannot double-append.
        with tempfile.TemporaryDirectory(prefix='qx-hearing-') as temporary:
            root = Path(temporary)/'session'
            if os.name == 'nt':
                engine.windows_private.private_directory(root, create=True)
            else:
                root.mkdir(mode=0o700)
            for key,value in material_texts(manifest).items():
                path = root/(key+'.txt')
                fd = (engine.windows_private.open_file(path, private=True, writable=True, create=True, exclusive=True)
                    if os.name == 'nt' else os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600))
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(value.encode('utf-8'))
            engine.create_session(root, packet_for(manifest))
            previous = manifest.hearing.previous_session
            if previous:
                for turn in previous.turns:
                    engine.append_turn(root, turn.model_dump(mode='json'))
                if engine.load_session(root) != previous.model_dump(mode='json'):
                    raise ValueError('HEARING_HISTORY_INVALID')
            for turn in stored_turns(candidate, manifest):
                engine.append_turn(root, turn.model_dump(mode='json'))
            session = engine.load_session(root)
            progress = engine.hearing_progress(root)
            return d.HearingResult(session=session, structural_completed=progress['structural_completed'], notice=progress['notice'])


def readable_text(result, candidate):
    labels = dict(plaintiff='原告', defendant='被告', moderator='主持追问', reviewer='复盘')
    stages = dict(issues='争点整理', evidence='证据核对', questions='双方问答', debate='辩论', review='复盘')
    return '\n\n'.join([stages[result.session.stage] + ' · 模拟演练 · 待律师核对',
        *[labels[turn.role] + '：' + turn.text + '\n待核事项：' + '；'.join(turn.unresolved)
            for turn in candidate.hearing_turns], result.notice])
