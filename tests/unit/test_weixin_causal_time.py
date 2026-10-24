"""All valid UTC representations participate in the account causal boundary."""
from datetime import datetime,timedelta

import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session

from cn_contract.weixin_inbox.accounts import _activity_time


@pytest.mark.parametrize('stamp',[
    '2026-10-24 01:00:00+00:00','2026-10-24T01:00:00Z',
    '2026-10-24T01:00:00.000001+00:00','2026-10-24 01:00:00.000001Z',
])
@pytest.mark.parametrize('grants',[False,True])
def test_causal_boundary_compares_parsed_utc_across_representations(stamp,grants):
    engine=create_engine('sqlite://')
    try:
        with Session(engine) as db:
            db.execute(text('CREATE TABLE weixin_accounts(id TEXT,created_at TEXT,revoked_at TEXT)'))
            db.execute(text('CREATE TABLE weixin_peer_bindings(id TEXT,account_id TEXT,created_at TEXT,revoked_at TEXT)'))
            db.execute(text('CREATE TABLE weixin_poll_receipts(account_id TEXT,created_at TEXT)'))
            db.execute(text("INSERT INTO weixin_accounts VALUES('account','2026-10-24T00:00:00Z',NULL)"))
            db.execute(text('INSERT INTO weixin_peer_bindings VALUES(:id,:account,:at,NULL)'),
                {'id':'mapping','account':'account','at':stamp if not grants else '2026-10-24T00:00:00Z'})
            if grants:
                db.execute(text('CREATE TABLE weixin_peer_scope_grants(mapping_id TEXT,created_at TEXT)'))
                db.execute(text('INSERT INTO weixin_peer_scope_grants VALUES(:mapping,:at)'),{'mapping':'mapping','at':stamp})
            expected=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            result=_activity_time('account',db,now='2026-10-24T00:00:00Z',after=True)
            assert datetime.fromisoformat(result.replace('Z','+00:00'))==expected+timedelta(microseconds=1)
            assert datetime.fromisoformat(_activity_time('account',db,now='2026-10-24T00:00:00Z').replace('Z','+00:00'))==expected
    finally:engine.dispose()
