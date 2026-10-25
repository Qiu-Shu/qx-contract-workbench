"""Probe a fixed v19 query against corrupt pre-generation dispatch history."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import text

from cn_contract.persistence import Database
from cn_contract.storage_schema import identify_schema
from cn_contract.weixin_inbox import dispatch, generation_dispatch
from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
from tests.integration.test_weixin_dispatch import seed, message
from tests.integration.test_weixin_dispatch_integrity import corrupt, rehash_receipt
from tests.integration.test_weixin_ingress_atomic import world

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
label = sys.argv[1]
assert label in ('red','green','green-final')
DATA = OUT/('independent-query-zero-data-'+label)
DATA.mkdir(exist_ok=False)
names = ('src/cn_contract/weixin_inbox/generation_dispatch.py',
         'src/cn_contract/weixin_inbox/dispatch_integrity.py',
         'src/cn_contract/weixin_inbox/generation_integrity.py')
before = {name:sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
fixture = world.__wrapped__(DATA)
sample = next(fixture)
try:
    root,database,actor,_,_ = sample
    account,mapping,poll = seed(sample,[message(1)])
    receipt = dispatch.dispatch_synthetic_descriptor(actor,poll.descriptors[0].id,database=database)
    with database.session() as records:
        assert records.scalar(text('SELECT count(*) FROM weixin_peer_generations')) == 0
        corrupt(records,'UPDATE weixin_dispatch_receipts SET created_at=:stamp WHERE id=:id',
                {'stamp':'2000-01-01T00:00:00Z','id':str(receipt.id)})
        rehash_receipt(records,receipt.id)
    returned,refusal = None,None
    try:
        returned = generation_dispatch.find_generation_dispatch_receipt(actor,receipt.descriptor_id,database=database)
    except Exception as error:
        refusal = type(error).__name__+': '+str(error)
    with closing(sqlite3.connect(database.engine.url.database)) as source, closing(sqlite3.connect(DATA/'v18.db')) as copy:
        source.backup(copy)
        copy.execute('DROP INDEX weixin_dispatch_binding_cursor')
        copy.commit()
    old = Database('sqlite:///'+str(DATA/'v18.db'),DATA/'v18-protected',database.settings,initialize_schema=False)
    rejected = False
    try:
        with old.session() as records:
            rows=[tuple(row) for row in records.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
            assert identify_schema(rows,native=True) == 'weixin-target-provenance-v1'
            try:
                validate_dispatch_records(records,allow_dispatch=True)
            except ValueError:
                rejected=True
    finally:
        old.engine.dispose()
    after={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    result={'v18_public_validator_rejects':rejected,'new_fixed_query_returned_corrupt_receipt':returned is not None,
            'new_fixed_query_refusal':refusal,'source_before':before,'source_after':after,'source_stable':before==after}
    (OUT/('independent-no-generation-query-'+label+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    assert rejected
    assert returned is None, 'v19 fixed query returned a rehashed receipt predating its source while no generation row exists'
finally:
    fixture.close()
