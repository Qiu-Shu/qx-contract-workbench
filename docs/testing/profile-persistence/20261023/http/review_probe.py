from datetime import timedelta
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tests/integration'))

import pytest
from cn_contract import domain as d
from cn_contract.intake import service as intake
from test_assistant_profile_integrity import chain, source, validate
from test_assistant_attachment_backup import corrupt


def test_reject_noop_retimed_after_newer_manual_intake(chain):
    source, _, first, _, second = chain
    _, database, actor, *_ = source
    with database.session() as db:
        current = intake.read(first.intake_id,actor,db)
        draft = d.IntakeDraft.model_validate(current.model_dump(include=set(d.IntakeDraft.model_fields)))
        next_record = intake.save(current.id,d.IntakeUpdateInput(expected_revision=1,
            draft=draft.model_copy(update={'title':'人工的新标题'})),actor,db)
    assert next_record.revision == 2
    later = (next_record.saved_at+timedelta(seconds=1)).isoformat()
    corrupt(database,'assistant_profile_receipts',
            'UPDATE assistant_profile_receipts SET created_at=? WHERE sequence=2',(later,))
    with pytest.raises(ValueError,match='ASSISTANT_PROFILE_INTEGRITY'):
        validate(database)
