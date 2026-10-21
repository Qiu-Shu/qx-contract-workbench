"""Independent synthetic Spec probes; no database, sockets, or model account."""
import ast
import asyncio
import builtins
import copy
import json
import subprocess
import types
from pathlib import Path
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.assistant.citation_identity import citation_identity
from cn_contract.assistant.library_records import encoded, sha
from cn_contract.assistant.providers import context_codec as codec, main
from cn_contract.assistant.providers.context import DeepSeekContextProvider
from cn_contract.assistant.providers.context_preview import project_source
from tests.unit.test_library_records import synthetic_citation, citation_container
from tests.unit.test_assistant_context_preview import config

ROOT = Path(__file__).resolve().parents[2]
BASE = 'aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9'


def fixed_source():
    first = citation_container(synthetic_citation(), 'saved')
    data = first.citation.model_dump(mode='json')
    data.update(quote='另一片段', quote_sha256=sha('另一片段'), version_id='9'*64)
    data['citation_id'] = citation_identity(data)
    second = first.model_copy(update={'id': uuid4(), 'citation': d.CitationRef.model_validate(data)})
    records = first, second
    manifest = d.MainContextManifest(format_version='saved-library-context-v1',
        question='独立合成核对问题', sources=tuple(project_source(item) for item in records))
    cfg = config()
    basis = codec.build_basis(uuid4(), manifest, first.scope, 8, cfg, records)
    request = d.MainContextRequest(run_id=uuid4(), message_id=uuid4(),
        scope=first.scope.model_copy(update={'input_revision':first.scope.input_revision+1}),
        composer_revision=9, manifest=manifest, basis=basis)
    return cfg, records, request


def response(candidate, cfg):
    return canonical_json({'id':'spec-synthetic-response','model':cfg.model,
        'object':'chat.completion','created':1,
        'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10},
        'choices':[{'index':0,'finish_reason':'stop','message':{
            'role':'assistant','content':canonical_json(candidate)}}]}).encode()


def test_legacy_domain_and_v1_wire_and_reply_are_frozen():
    old_domain = subprocess.check_output(['git','show',f'{BASE}:src/cn_contract/domain.py'], cwd=ROOT).decode('utf-8')
    current_domain = (ROOT/'src/cn_contract/domain.py').read_text('utf-8')
    now = {node.name:ast.dump(node) for node in ast.parse(current_domain).body if isinstance(node,ast.ClassDef)}
    for node in ast.parse(old_domain).body:
        if isinstance(node,ast.ClassDef):
            assert now[node.name] == ast.dump(node), node.name
    old = types.ModuleType('cn_contract.assistant.providers._spec_frozen_main')
    old.__package__ = 'cn_contract.assistant.providers'
    source = subprocess.check_output(['git','show',f'{BASE}:src/cn_contract/assistant/providers/main.py'],cwd=ROOT).decode('utf-8')
    exec(compile(source,'frozen-main.py','exec'),old.__dict__)
    cfg, _, request = fixed_source()
    plain = d.MainRequest(run_id=request.run_id,message_id=request.message_id,scope=request.scope,
        content='旧路径合成文字😀',source_sha256=sha('旧路径合成文字😀'))
    assert old._json_bytes(old.build_request(plain,cfg)) == main._json_bytes(main.build_request(plain,cfg))
    variants = [
        {'text':'候选','citations':[]},
        {'text':'候选','citations':[{'message_id':str(plain.message_id),'quote_sha256':plain.source_sha256}]},
        {'text':'候选','citations':[{'message_id':str(uuid4()),'quote_sha256':plain.source_sha256}]},
        {'text':'候选','support_status':'verified'},
        {'text':'   '},
    ]
    for candidate in variants:
        raw = response(candidate,cfg)
        assert encoded(old._decode(raw,plain,cfg,'SPEC_SECRET')) == encoded(main._decode(raw,plain,cfg,'SPEC_SECRET'))


def test_full_hidden_identity_and_saved_scope_are_not_quote_identity():
    cfg, records, request = fixed_source()
    changed = records[0].citation.model_dump(mode='json')
    changed.update(registered_source_sha256='8'*64)
    changed['citation_id'] = citation_identity(changed)
    source = records[0].model_copy(update={'citation':d.CitationRef.model_validate(changed)})
    assert project_source(source) == request.manifest.sources[0]
    with pytest.raises(ValueError):
        codec.validate_sources(request.manifest,request.basis.expected_scope,request.basis.source_bindings,(source,records[1]))
    invalid_scope = records[0].scope.model_copy(update={'scope_kind':'matter','scope_ref':uuid4()})
    source = records[0].model_copy(update={'scope':invalid_scope})
    with pytest.raises(ValueError):
        codec.validate_sources(request.manifest,request.basis.expected_scope,request.basis.source_bindings,(source,records[1]))
    codec.validate_sources(request.manifest,request.basis.expected_scope,request.basis.source_bindings,records)
    assert codec.prepare(request,cfg).wire_payload_json


def test_deep_constructed_candidate_input_cannot_skip_literal_validation():
    cfg, records, request = fixed_source()
    source = request.manifest.sources[0].model_copy(update={'support_status':'verified'})
    manifest = request.manifest.model_copy(update={'sources':(source,request.manifest.sources[1])})
    basis = request.basis.model_copy(update={'manifest_sha256':sha(canonical_json(manifest.model_dump(mode='json')))})
    forged = request.model_copy(update={'manifest':manifest,'basis':basis})
    with pytest.raises(ValueError):
        codec.prepare(forged,cfg)
    corrupt = records[0].model_copy(update={'citation':records[0].citation.model_copy(update={'citation_id':'0'*64})})
    with pytest.raises(ValueError):
        codec.build_basis(uuid4(),request.manifest,request.basis.expected_scope,8,cfg,(corrupt,records[1]))


def test_candidate_matches_same_selected_uuid_hash_pair_and_retains_usage():
    cfg, _, request = fixed_source()
    first, second = request.manifest.sources
    valid = {'text':'合成候选','citations':[{'saved_citation_id':str(second.saved_citation_id),'quote_sha256':second.quote_sha256}]}
    reply = codec.decode_response(response(valid,cfg),request,cfg,'SPEC_SECRET')
    assert reply.output is not None and reply.usage.total_tokens == 10
    bad = copy.deepcopy(valid)
    bad['citations'][0]['quote_sha256'] = first.quote_sha256
    reply = codec.decode_response(response(bad,cfg),request,cfg,'SPEC_SECRET')
    assert reply.state == 'received' and reply.output is None and reply.error_code == 'MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens == 10 and reply.provider_request_id == 'spec-synthetic-response'


@pytest.mark.parametrize('mode',['default','exception-after-secret'])
def test_no_network_client_for_denied_or_late_rejected_preflight(monkeypatch,mode):
    cfg, _, request = fixed_source()
    calls=[]
    def secret():
        calls.append('secret')
        return 'SPEC_SYNTHETIC_SECRET'
    def preflight():
        calls.append('check')
        if 'secret' in calls:
            raise RuntimeError('SPEC_PRIVATE_DENIAL')
        return True
    original = builtins.__import__
    def forbidden(name,*args,**kwargs):
        assert name != 'httpx2', 'blocked input reached network client import'
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',forbidden)
    provider=DeepSeekContextProvider(cfg,secret)
    reply=asyncio.run(provider.generate(request,preflight=None if mode=='default' else preflight))
    assert reply.state=='failed_before_send' and reply.error_code=='BLOCKED_LIVE'
    assert calls==([] if mode=='default' else ['check','secret','check'])
    assert 'SPEC_PRIVATE_DENIAL' not in reply.model_dump_json()
