"""Read-only product review; mutate only disposable synthetic databases."""
import json
from pathlib import Path
import sys
from uuid import uuid4, uuid5, NAMESPACE_URL

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests' / 'integration'))

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, profile_store
from cn_contract.assistant.profiles import merge_profile
from cn_contract.intake import service as intake
from cn_contract.record_codec import encode, sha
from cn_contract.security import ServiceError
from tests.integration.test_assistant_attachment_backup import source, corrupt
from tests.integration.test_assistant_profile_integrity import chain


def test_profile_read_rejects_rehashed_other_conversation(chain):
    source, _, first, *_ = chain
    _, database, actor, cid, *_ = source
    with database.session() as db:
        value = json.loads(db.scalar(text('SELECT profile_json FROM assistant_profile_revisions')))
    value['scope']['conversation_id'] = str(uuid4())
    for field in value['fields']:
        for candidate in field['candidates']:
            for ref in candidate['source_refs']:
                ref['conversation_id'] = value['scope']['conversation_id']
    corrupt(database, 'assistant_profile_revisions',
            'UPDATE assistant_profile_revisions SET profile_json=?,profile_sha256=?', (encode(value),sha(value)))
    with pytest.raises(ServiceError):
        profile_store.read_profile(actor, cid, database=database, revision=first.profile_revision)


def test_receipt_read_rejects_broken_projection_hash(chain):
    source, request, *_ = chain
    _, database, actor, cid, *_ = source
    corrupt(database, 'assistant_profile_receipts',
            'UPDATE assistant_profile_receipts SET intake_sha256=? WHERE sequence=1', ('0'*64,))
    with pytest.raises(ServiceError):
        profile_store.find_receipt(actor, cid, request.request_id, database=database)


def test_projection_create_does_not_reuse_unrelated_intake_nonce(source):
    _, database, actor, cid, *_ = source
    scope = attachments.read_materials(actor, cid, database=database).scope
    request = d.ProfileCommitInput(request_id=uuid4(), patch=d.ProfilePatch(scope=scope,base_profile_revision=0),
        manual_edits=(d.ProfileEdit(field='consultation',value={'kind':'text','value':'合成首次手工记录'}),),
        project_intake=True)
    draft = merge_profile(None,request.patch,d.ProfileSourceSnapshot(scope=scope),
                          manual_edits=request.manual_edits,project_intake=True).projection
    with database.session() as db:
        existing = intake.create(d.IntakeCreateInput(request_id=uuid5(NAMESPACE_URL,
            f'qx-profile:{cid}:{request.request_id}'),draft=draft),actor,db)
        intake.save(existing.id,d.IntakeUpdateInput(expected_revision=1,
            draft=draft.model_copy(update={'consultation':'已由律师修订的旧接待'})),actor,db)
    with pytest.raises(ServiceError):
        profile_store.save_profile(actor,request,database=database)
