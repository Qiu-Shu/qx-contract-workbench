import json
from pathlib import Path
from docx import Document
from lxml import html
from fastapi.testclient import TestClient
from cn_contract.web import local_server as module
from tests.integration.test_local_workbench import login
from tests.integration.test_api import create_case
out=Path('.audit-local/local-materials-20261013/spec-review').resolve()
project=max(out.glob('sandbox-*'),key=lambda p:p.stat().st_mtime)
module.PROJECT_ROOT=project
result=json.loads((out/'results.json').read_text(encoding='utf-8'))
with TestClient(module.build_local_app(project/'.local'/'workbench')) as client:
    headers=login(client)
    local_id=client.get('/api/matters').json()[0]['id']
    local_html=html.fromstring(client.get('/matters/'+local_id+'/exports').text)
    result['local_patch_reason']=local_html.xpath('//form[@id="patch-form"]//input[@name="reason"]/@value')
    synthetic_id=create_case(client,headers,title='独立虚构旧模式对照')
    synthetic_html=html.fromstring(client.get('/matters/'+synthetic_id+'/exports').text)
    result['synthetic_patch_reason']=synthetic_html.xpath('//form[@id="patch-form"]//input[@name="reason"]/@value')
texts=[p.text for p in Document(out/'internal.docx').paragraphs]
result['internal_plugin_labels']=[t for t in texts if '插件候选' in t]
result['internal_manual_fallback']=[t for t in texts if t=='待律师核对人工候选、来源状态及未完成维度。']
assert all(result[a+'_simulation_labels']==[] for a in ('client','internal','counterparty'))
assert result['local_patch_reason']==['']
assert result['synthetic_patch_reason']==['已核对虚构原文和拟订文字']
assert not result['internal_plugin_labels'] and result['internal_manual_fallback']
(out/'re-review-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
