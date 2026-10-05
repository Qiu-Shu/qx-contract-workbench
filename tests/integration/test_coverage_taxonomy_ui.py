"""Actual HTTP markup/script labels and selected IDs against the v2 taxonomy.

Node runs the served production script with a small DOM adapter. This is a
behavior check, not an actual browser or a visual acceptance claim.
"""
from copy import deepcopy
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from cn_contract.config import PROJECT_ROOT
from cn_contract.domain import CoverageId
from cn_contract.exports.audience_filter import DIMENSIONS
from tests.integration.test_api import api, create_case, sign_in
from tests.integration.test_assisted_review import (assisted_api, CASES,
    ready_case, proposal_body, docx_text)


def canonical_taxonomy():
    specification = (PROJECT_ROOT / 'sources/specification-v2.0.md').read_text(encoding='utf-8')
    paragraph = specification.split('### 5.2 18维枚举', 1)[1].split('\n\n')[1]
    result = re.findall(r'(C\d{2})([^；。]+)', paragraph)
    schema = json.loads((PROJECT_ROOT / 'schemas/review-report.v2.schema.json').read_text(encoding='utf-8'))
    assert [key for key, _ in result] == schema['$defs']['CoverageId']['enum'] == [v.value for v in CoverageId]
    assert [name for _, name in result] == list(DIMENSIONS)
    return result


class TaxonomyMarkup(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.active = False
        self.options = []
        self.current = None
        self.purpose = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'body': self.purpose = values.get('data-purpose', 'mock_demo')
        if tag == 'template' and values.get('id') == 'coverage-taxonomy': self.active = True
        if self.active and tag == 'option': self.current = [values.get('value'), '']

    def handle_data(self, data):
        if self.current is not None: self.current[1] += data

    def handle_endtag(self, tag):
        if tag == 'option' and self.current is not None:
            self.options.append(tuple(self.current)); self.current = None
        if tag == 'template': self.active = False


NODE_DOM = r"""
const vm=require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
class Element {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this._text='';this.value='';this.elements=[];}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(item=>item.textContent).join('');}
  addEventListener(){}
}
const nodes=Object.fromEntries(['coverage','candidate-opinion-form','candidate-opinion-anchor',
  'candidate-dimension','candidate-opinion-list','message'].map(id=>[id,new Element()]));
if(!input.candidatePresent)delete nodes['candidate-opinion-form'];
const options=input.taxonomy.map(([id,name])=>{const option=new Element('option');option.value=id;option.textContent=name;return option;});
if(options.length)nodes['coverage-taxonomy']={content:{querySelectorAll:selector=>selector==='option'?options:[]}};
class FormData {
  get(name){return name==='coverage_id'?nodes['candidate-dimension'].value:({analysis:'独立虚构维度核对',
    business_effect:'只核对所选维度编号',recommendation:'待律师核对',severity:'low',basis_kind:'material_observation',
    authority_refs:'',unknowns:''}[name]||'');}
  getAll(name){return name==='anchor_ids'?['synthetic-source-anchor']:[];}
}
const context=vm.createContext({document:{body:{dataset:{section:'taxonomy_test',matter:'synthetic-case',purpose:input.purpose}},
  cookie:'',getElementById:id=>nodes[id]||null,createElement:tag=>new Element(tag)},FormData,
  fetch:async()=>({ok:true,json:async()=>({matter:{status:'ready_for_review',review_mode:'pre_sign'},documents:[]})}),
  crypto:{randomUUID:()=> 'synthetic-id'},setTimeout,console});
vm.runInContext(input.script,context);
(async()=>{
  vm.runInContext('run='+JSON.stringify({coverage:input.ids.map(coverage_id=>({coverage_id,status:'insufficient_material'}))})+';coverage();',context);
  await vm.runInContext("setupCandidateOpinions('ready_for_review')",context);
  const candidates=nodes['candidate-dimension'].children.map(option=>[option.value,option.textContent]);
  const selected={};
  for(const id of input.candidatePresent?['C05','C08','C09']:[]){
    nodes['candidate-dimension'].value=id;
    selected[id]=vm.runInContext('candidateFromForm()',context);
  }
  process.stdout.write(JSON.stringify({cards:nodes.coverage.children.map(card=>card.children[0].textContent),candidates,selected}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
"""


def ui_behavior(client, matter):
    page = client.get(f'/matters/{matter}/review')
    script = client.get('/static/workbench.js')
    assert page.status_code == script.status_code == 200
    markup = TaxonomyMarkup(page.text)
    node = shutil.which('node')
    assert node, 'installed local Node runtime is required for production-script behavior'
    ids = [key for key, _ in canonical_taxonomy()]
    # Deliberately reorder server coverage to catch rendering by loop position.
    ids = ids[8:] + ids[:8]
    executed = subprocess.run([node, '-e', NODE_DOM], input=json.dumps({'script': script.text,
        'taxonomy': markup.options, 'purpose': markup.purpose, 'ids': ids,
        'candidatePresent': 'id="candidate-opinion-form"' in page.text}, ensure_ascii=False),
        text=True, encoding='utf-8', capture_output=True, timeout=20)
    assert executed.returncode == 0, executed.stderr
    return markup, json.loads(executed.stdout), ids


@pytest.mark.parametrize('fixture_name', ['api', 'assisted_api'])
def test_server_markup_uses_existing_report_taxonomy_and_schema_ids(request, fixture_name):
    client, _, _, _ = request.getfixturevalue(fixture_name)
    headers = sign_in(client)
    matter = create_case(client, headers)
    response = client.get(f'/matters/{matter}/review')
    assert response.status_code == 200
    assert TaxonomyMarkup(response.text).options == canonical_taxonomy()


@pytest.mark.parametrize('fixture_name', ['api', 'assisted_api'])
def test_actual_served_script_renders_coverage_by_id_and_candidate_options(request, fixture_name):
    client, _, _, _ = request.getfixturevalue(fixture_name)
    headers = sign_in(client)
    matter = create_case(client, headers)
    _, actual, ids = ui_behavior(client, matter)
    expected = dict(canonical_taxonomy())
    assert actual['cards'] == [key + ' ' + expected[key] for key in ids]
    if fixture_name == 'assisted_api':
        assert actual['candidates'] == [[key, key + ' ' + name] for key, name in canonical_taxonomy()]
        assert all(actual['selected'][key]['coverage_ids'] == [key] for key in ('C05', 'C08', 'C09'))
    else:
        assert actual['candidates'] == [] and actual['selected'] == {}


def test_login_script_remains_usable_without_an_authenticated_taxonomy(api):
    client, _, _, _ = api
    page = client.get('/login')
    script = client.get('/static/workbench.js')
    assert page.status_code == script.status_code == 200
    markup = TaxonomyMarkup(page.text)
    assert markup.options == []
    node = shutil.which('node')
    assert node
    executed = subprocess.run([node, '-e', NODE_DOM], input=json.dumps({'script': script.text,
        'taxonomy': [], 'purpose': markup.purpose, 'ids': [], 'candidatePresent': False}),
        text=True, encoding='utf-8', capture_output=True, timeout=20)
    assert executed.returncode == 0, executed.stderr


def test_selected_ui_dimensions_survive_real_proposal_api_and_downloaded_docx(assisted_api):
    client, _, _, _ = assisted_api
    case = CASES[0]
    matter, sent, parsed, confirmed, context, headers = ready_case(assisted_api, case)
    _, actual, _ = ui_behavior(client, matter)
    expected = dict(canonical_taxonomy())
    chosen = ('C05', 'C08', 'C09')
    assert {key: name for key, name in actual['candidates'] if key in chosen} == {
        key: key + ' ' + expected[key] for key in chosen}
    body = proposal_body(case, sent, parsed, confirmed, context)
    seed = body['opinions'][0]
    body['opinions'] = []
    for key in chosen:
        item = deepcopy(seed)
        item['coverage_ids'] = actual['selected'][key]['coverage_ids']
        item['analysis'] = key + expected[key] + '独立虚构人工候选核对。'
        body['opinions'].append(item)
    saved = client.post(f'/api/matters/{matter}/review-proposals', headers=headers, json=body)
    assert saved.status_code == 201, saved.text
    run = client.get(f'/api/matters/{matter}/reviews/{saved.json()["id"]}').json()
    assert [item['coverage_ids'] for item in run['findings']] == [[key] for key in chosen]
    for finding in run['findings']:
        decision = client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision', headers=headers,
            json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': 'accept',
                'reason': '仅核对独立虚构候选对应的维度，未验证法律质量'})
        assert decision.status_code == 201, decision.text
    preview = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'client', 'patch_ids': []})
    assert preview.status_code == 201, preview.text
    artifact = preview.json()['artifacts'][0]
    download = client.get(f'/api/matters/{matter}/exports/{artifact["id"]}/download')
    assert download.status_code == 200, download.text
    text = docx_text(download.content)
    assert all(key + ' ' + name in text for key, name in canonical_taxonomy())
    assert all(key + expected[key] + '独立虚构人工候选核对。' in text for key in chosen)
    assert hashlib.sha256(download.content).hexdigest() == artifact['content_sha256']
    evidence = os.environ.get('TAXONOMY_EVIDENCE_DIR')
    if evidence:
        folder = Path(evidence)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'selected-dimensions-client.docx').write_bytes(download.content)
        (folder / 'selected-dimensions.json').write_text(json.dumps({'server_taxonomy': canonical_taxonomy(),
            'ui_selected_ids': {key: actual['selected'][key]['coverage_ids'] for key in chosen},
            'run_id': run['id'], 'run_sha256': run['run_sha256'], 'artifact_sha256': artifact['content_sha256'],
            'docx_sentence_assertions': 'PASS', 'browser_visual': 'NOT_RUN',
            'legal_quality': 'NOT_EVALUATED'}, ensure_ascii=False, indent=2), encoding='utf-8')
