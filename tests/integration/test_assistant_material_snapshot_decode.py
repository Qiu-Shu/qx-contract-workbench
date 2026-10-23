"""Corrupt synthetic selection roots cannot masquerade as an empty selection."""
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, attachment_schema, attachment_records
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation


@pytest.fixture
def snapshot(workspace):
    database, actors, _, _ = workspace
    attachment_schema.initialize_storage(database)
    actor = actors['lawyer']
    value = conversation(workspace)
    request_id = uuid4()
    attachments.select_materials(actor, value.scope.conversation_id,
        d.AssistantMaterialSelectionInput(request_id=request_id, expected_scope=value.scope, items=()),
        database=database)
    return database, actor, value.scope.conversation_id, request_id


@pytest.mark.parametrize('raw', ['{}', '""', 'null', 'false', '42', '[{}]', '[',
    json.dumps([{'attachment_id':str(UUID(int=1)), 'parse_revision':None}]*2),
    json.dumps([{'attachment_id':str(UUID(int=i)), 'parse_revision':None} for i in range(1,22)]),
    '[{"attachment_id":"00000000-0000-0000-0000-000000000001","attachment_id":"00000000-0000-0000-0000-000000000002","parse_revision":null}]'])
@pytest.mark.parametrize('entry', ['current', 'receipt'])
def test_malformed_selection_is_rejected_by_current_and_receipt_reads(snapshot, raw, entry):
    database, actor, cid, request_id = snapshot
    with database.session() as db:
        triggers = db.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_material_snapshots'")).scalars().all()
        for name in triggers:
            # This corruption fixture affects only its new synthetic SQLite database.
            db.execute(text('DROP TRIGGER "' + name.replace('"', '""') + '"'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:raw'), {'raw':raw})
    with pytest.raises(ServiceError) as error:
        if entry == 'current':
            attachments.read_materials(actor, cid, database=database)
        else:
            attachments.find_material_request(actor, cid, request_id, database=database)
    assert error.value.code == 'VERSION_CONFLICT'
    assert raw not in str(error.value)


def test_valid_empty_selection_remains_readable_and_does_not_write(snapshot):
    database, actor, cid, request_id = snapshot
    with database.engine.connect() as db:
        before = '\n'.join(db.connection.driver_connection.iterdump())
    assert attachments.read_materials(actor, cid, database=database).items == ()
    receipt = attachments.find_material_request(actor, cid, request_id, database=database)
    assert receipt.items == () and receipt.request_id == request_id and receipt.materials_revision == 1
    with database.engine.connect() as db:
        assert '\n'.join(db.connection.driver_connection.iterdump()) == before


def test_valid_selection_keeps_order_at_the_existing_twenty_item_limit():
    values = [{'attachment_id':str(UUID(int=i)), 'parse_revision':i} for i in range(20,0,-1)]
    result = attachment_records.decode_items(json.dumps(values))
    assert [item.model_dump(mode='json') for item in result] == values
