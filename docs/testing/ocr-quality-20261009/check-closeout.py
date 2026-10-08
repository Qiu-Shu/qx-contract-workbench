from pathlib import Path
import json,hashlib,subprocess
from datetime import datetime,timezone
root=Path.cwd();out=root/'docs/testing/ocr-quality-20261009'
def git(*args):return subprocess.check_output(['git',*args],cwd=root)
assert git('branch','--show-current').strip()==b'codex/contract-review-v2'
binding=json.loads((root/'plugins/qx-contract-offline-codex/runtime-binding.json').read_text(encoding='utf8'))
for name,digest in binding['repository_file_hashes'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
protected=['tests/fixtures/ocr-proofreading/independent-48-pages.pdf','tests/fixtures/ocr-proofreading/manifest.json','sources/ocr-assets.lock.json','sources/ocr-environment.lock.json','src/cn_contract/documents/ocr_worker.py']
for name in protected:assert git('show','HEAD:'+name)==(root/name).read_bytes(),name
for folder,source in [('before-results',root/'.audit-local/ocr-proofreading-20261008/acceptance-pdf-48'),('after-results',root/'.audit-local/ocr-quality-20261009/fixed-48')]:
    for i in range(1,49):
        name=f'result-{i:02}.json'
        assert (out/folder/name).read_bytes()==(source/name).read_bytes()
rows=json.loads((out/'observations.json').read_text(encoding='utf8'))
assert len(rows)==48 and {r['page'] for r in rows}==set(range(1,49))
db=json.loads((out/'browser-db-check.json').read_text(encoding='utf8'))
assert len(db['working_draft_confirmations'])==2
assert db['candidate_source_link_verified'] and db['candidate_blocks_unverified']
assert db['old_download_service']=={'code':'VERSION_CONFLICT','status':409}
receipt={'utc':datetime.now(timezone.utc).isoformat(),'branch':'codex/contract-review-v2','binding_files_verified':len(binding['repository_file_hashes']),'installed_versions_inventory':len(binding['installed_versions']),'protected_files_unchanged':protected,'raw_result_copies_exact':96,'observations':48,'browser_confirmations':2,'full_suite_this_turn':'NOT_RUN','success':True}
(out/'closeout-check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False))
