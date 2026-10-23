"""Supplement strict decoder edge cases and independent historical lookup."""
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachment_records as records, attachments, service
from cn_contract.security import ServiceError
from tests.integration.test_assistant_storage import workspace
from test_trusted_standards import source


@pytest.mark.parametrize('raw', [
    '['*4000+']'*4000,
    '[{"attachment_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","parse_revision":NaN}]',
    '[{"attachment_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","parse_revision":true}]',
    json.dumps([{'attachment_id':value,'parse_revision':None} for value in (
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA')]),
], ids=['deep-json','nonfinite-json','boolean-revision','normalized-duplicate-id'])
def test_shared_decoder_rejects_nonfinite_nested_and_normalized_aliases(raw):
    with pytest.raises(ServiceError) as error:
        records.decode_items(raw)
    assert error.value.code == 'VERSION_CONFLICT'
    assert raw not in str(error.value)


def test_old_corrupt_receipt_rejects_even_when_current_selection_is_valid(source):
    database, actors, value = source
    actor = actors['lawyer']
    cid = value.scope.conversation_id
    old_id, current_id = uuid4(), uuid4()
    with database.session() as db:
        row = service._owned(actor,cid,db)
        records.snapshot(row, (), 'selection', old_id, 'a'*64,actor,db)
        row = service._owned(actor,cid,db)
        records.snapshot(row, (), 'selection', current_id, 'b'*64,actor,db)
        names = db.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_material_snapshots' AND sql LIKE '%UPDATE%'" )).scalars().all()
        for name in names:
            db.execute(text('DROP TRIGGER "'+name.replace('"','""')+'"'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:bad WHERE request_id=:id'),
                   {'bad':'{}','id':str(old_id)})
    # A valid current snapshot must not hide corruption of an earlier request.
    assert attachments.read_materials(actor,cid,database=database).items == ()
    assert attachments.find_material_request(actor,cid,current_id,database=database).items == ()
    with pytest.raises(ServiceError) as error:
        attachments.find_material_request(actor,cid,old_id,database=database)
    assert error.value.code == 'VERSION_CONFLICT'
