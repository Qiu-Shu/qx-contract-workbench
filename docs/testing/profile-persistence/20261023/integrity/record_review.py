from pathlib import Path
import ast
from datetime import datetime, timezone
import hashlib
import json
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).parent
files = (
    'src/cn_contract/domain.py', 'src/cn_contract/assistant/profile_store.py',
    'src/cn_contract/assistant/profile_schema.py', 'src/cn_contract/storage_schema.py',
    'src/cn_contract/schema_migrations.py', 'src/cn_contract/storage_bootstrap.py',
    'src/cn_contract/assistant/model_integrity.py', 'src/cn_contract/assistant/judge_integrity.py',
    'src/cn_contract/assistant/library_integrity.py', 'src/cn_contract/assistant/attachment_integrity.py',
    'src/cn_contract/intake/service.py', 'src/cn_contract/assistant/profile_integrity.py',
    'src/cn_contract/ops/backup.py', 'tests/integration/test_assistant_profile_integrity.py',
)
before = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
for name in files:
    ast.parse((root/name).read_text('utf-8'))
after = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
assert before == after
suite = ET.parse(folder/'review-final.xml').getroot().find('testsuite')
assert suite.attrib['tests'] == '31' and all(suite.attrib[k] == '0' for k in ('failures','errors','skipped'))
evidence = ('red.log','target.log','final.log','review-probes-valid.log','review-probes-valid.xml',
            'review-final.log','review-final.xml','review_probes.py')
result = {
    'reviewer':'profile_persistence_integrity',
    'workspace':str(root),
    'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
    'baseline':'2b72c9a02a25607761705811550323fa9fcfce00',
    'scope':'Independent review of profile store/domain and migration/schema/version wiring; own integrity implementation excluded from independent approval.',
    'source_sha256':after,
    'hashes_stable_during_final_capture':before == after,
    'hash_binding_note':'Captured after targeted tests and final source read; parent final verification should bind the complete changed-input snapshot.',
    'findings':[
        {'id':'PROFILE-READ-SCOPE','priority':2,'status':'fixed_and_retested',
         'problem':'Rehashed profile payload could name another conversation/revision while read_profile returned it for the requested row.',
         'fix':'_profile checks requested conversation, actual row revision and workspace identity as well as payload digest.',
         'probe':'test_profile_read_rejects_rehashed_other_conversation'},
        {'id':'RECEIPT-READ-DIGEST','priority':2,'status':'fixed_and_retested',
         'problem':'find_receipt returned a DTO despite a damaged projection digest.',
         'fix':'_receipt validates immutable request identity/digest and referenced profile/intake records and intake digest.',
         'probe':'test_receipt_read_rejects_broken_projection_hash'},
        {'id':'INTAKE-CREATION-NONCE','priority':2,'status':'fixed_and_retested',
         'problem':'Predictable derived intake creation key could silently reuse an independently preexisting and later edited intake.',
         'fix':'Reject a preexisting derived owner/request key before intake.create inside the same serialized savepoint.',
         'probe':'test_projection_create_does_not_reuse_unrelated_intake_nonce'},
    ],
    'checks':[
        'Profile schema is additive, with two tables, four immutable triggers, composite foreign keys and bounded payloads.',
        'Historical schema identifiers remain explicit; new current version retains rounds v2 handling in model integrity.',
        'Bootstrap and both native/database migration paths consume the same fixed DDL; migration transaction and marker-recovery seams remain existing implementations.',
        'All profile mutation writes, including intake creation, revisions, conversation link and receipt, are inside one savepoint.',
        'Current authorization and restore fence precede idempotent returns; source file reads occur outside write transaction and scope/auth are rechecked.',
        'Historical profile and receipt retrieval works from qxbak after old sessions are revoked; new writes are blocked.',
        'No live model, remote service, real documents or existing desktop workspace was used.'
    ],
    'external_review_fix':{
        'reviewer':'profile_persistence_http',
        'problem':'A no-change receipt could be retimed after a later manual intake revision while still claiming the older after version.',
        'fix':'Reject any later intake revision whose saved_at is no later than receipt created_at.',
        'test':'test_semantic_tamper_rejects_backup_before_publish[stale_intake_at_receipt_time]',
        'status':'fixed_and_retested'
    },
    'test_result':{'command':'python -m pytest tests/integration/test_assistant_profile_integrity.py .local/profile-persistence-20261023/integrity/review_probes.py -q --tb=short',
                   'passed':31,'failures':0,'errors':0,'skipped':0,'exit_code':0,
                   'formal_integrity_tests':28,'independent_store_probes':3,'reported_seconds':37.90},
    'open_findings':[],
    'limits':['Not a complete project audit or full regression run.',
              'No GUI, frozen binary, installer, memory/RSS, real-model or cloud validation.',
              'Synthetic binding-change test verifies historical tolerance; no current product rebind API was found.'],
    'evidence_sha256':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in evidence},
}
(folder/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sources':len(after),'hashes_stable':before==after,'test_passed':31,'open_findings':0,
                  'output':str(folder/'review.json')},ensure_ascii=False))
