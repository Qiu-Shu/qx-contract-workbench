"""The fixed task PDF widens assistant demos, never the historical matter policy."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from cn_contract.acceptance.assisted_registry import load_seed_policy
from cn_contract.ops.backup import _registered_hashes
from cn_contract.task_drafts.synthetic import PDF_HASHES
from test_api import create_case
from test_assistant_routes import native, chat, sign_in, create


FIXTURE = Path(__file__).resolve().parents[1]/'fixtures/task-pdf-v1/native-sales.pdf'


def upload(client, headers, url, scope, raw):
    value = {'request_id':str(uuid4()),'expected_scope':scope,
        'original_name':'native-sales.pdf','mime':'application/pdf',
        'policy':{'policy_id':'assistant-local-files-v2','material_mode':'synthetic',
                  'local_processing_accepted':True}}
    return client.post(url+'/attachments',headers=headers,files=[
        ('file',(value['original_name'],raw,value['mime'])),
        ('metadata',(None,json.dumps(value),'application/json'))])


def test_fixed_pdf_is_an_independent_backup_registered_fixture():
    raw=FIXTURE.read_bytes()
    manifest=json.loads(FIXTURE.with_name('manifest.json').read_text(encoding='utf-8'))
    checksum=hashlib.sha256(raw).hexdigest()
    assert manifest['synthetic'] is True
    assert len(raw)==manifest['bytes'] and checksum==manifest['sha256']
    assert PDF_HASHES==frozenset({checksum})
    assert checksum in _registered_hashes()
    assert checksum not in load_seed_policy().document_hashes


def test_default_native_assistant_uploads_and_reads_only_fixed_pdf(chat):
    client,database,_=chat
    headers=sign_in(client); conversation=create(client,headers)
    url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
    raw=FIXTURE.read_bytes()
    response=upload(client,headers,url,conversation['scope'],raw)
    assert response.status_code==201,response.text
    attachment=response.json()['attachment']
    parsed=client.post(url+'/attachments/'+attachment['id']+'/parses',headers=headers,
        json={'request_id':str(uuid4()),'expected_scope':client.get(url+'/materials').json()['scope']})
    assert parsed.status_code==200,parsed.text
    result=parsed.json()['parse']
    assert result['reading_status']=='readable' and result['baseline_view']=='original'
    assert result['parser_version']=='qx-pdf-attachments-v1'
    assert result['result']['pages']==[1,2]
    assert {a['page'] for a in result['result']['anchors']}=={1,2}
    assert all(a['bbox'] and a['kind']=='pdf_span' for a in result['result']['anchors'])
    assert client.get(url+'/attachments/'+attachment['id']+'/original').content==raw
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==0
        assert db.scalar(text('SELECT count(*) FROM task_executions'))==0


def test_unregistered_pdf_still_rejected_by_synthetic_assistant(chat):
    client,_,_=chat
    headers=sign_in(client); conversation=create(client,headers)
    url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
    response=upload(client,headers,url,conversation['scope'],FIXTURE.read_bytes()+b'\n')
    assert response.status_code==409,response.text
    assert response.json()['code']=='DATA_POLICY_UNAPPROVED'
    assert client.get(url+'/materials').json()['attachments']==[]


def test_pdf_task_registry_does_not_widen_ordinary_assisted_matter_upload(chat):
    client,_,_=chat
    headers=sign_in(client); matter=create_case(client,headers)
    response=client.post(f'/api/matters/{matter}/documents',headers=headers,
        files={'file':('native-sales.pdf',FIXTURE.read_bytes(),'application/pdf')},
        data={'baseline_view':'original'})
    assert response.status_code==409,response.text
    assert response.json()['code']=='DATA_POLICY_UNAPPROVED'
