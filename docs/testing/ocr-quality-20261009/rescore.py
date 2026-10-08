from pathlib import Path
import importlib.util,json,hashlib
root=Path.cwd();out=root/'.audit-local/ocr-quality-20261009'
spec=importlib.util.spec_from_file_location('scorer',root/'scripts/ocr_synthetic_acceptance.py');scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)
manifest=json.loads((root/'tests/fixtures/ocr-proofreading/manifest.json').read_text(encoding='utf8'))
records={}
for name,path in [('before',root/'docs/testing/ocr-proofreading-20261008/pdf-rendered-observations.json'),('after',out/'fixed-48/observations.json')]:
 data=path.read_bytes();rows=json.loads(data);assert len(rows)==48
 rescored=[]
 for row in rows:
  expected=manifest['pages'][row['page']-1]['expected']
  legacy=row['status'];strict=legacy
  if legacy in ('CORRECT','INCORRECT_CANDIDATE'):
   raw_dir=root/'.audit-local/ocr-proofreading-20261008/acceptance-pdf-48' if name=='before' else out/'fixed-48'
   result=json.loads((raw_dir/f"result-{row['page']:02}.json").read_text(encoding='utf8'))
   assert result['source']['document_sha256']==manifest['pdf_sha256'] and result['source']['page']==row['page']
   strict='CORRECT' if scorer.critical_fields_match([b['raw_text'] for b in result['blocks']],expected) else 'INCORRECT_CANDIDATE'
  rescored.append({'page':row['page'],'group':row['group'],'legacy':legacy,'numeric_boundary':strict})
 records[name]={'observation_sha256':hashlib.sha256(data).hexdigest(),'legacy_correct':sum(x['legacy']=='CORRECT' for x in rescored),'numeric_boundary_correct':sum(x['numeric_boundary']=='CORRECT' for x in rescored),'by_group':{g:sum(x['group']==g and x['numeric_boundary']=='CORRECT' for x in rescored) for g in dict.fromkeys(r['group'] for r in rows)},'downgraded_pages':[x['page'] for x in rescored if x['legacy']=='CORRECT' and x['numeric_boundary']!='CORRECT'],'pages':rescored}
records['scope']='same48 development regression; numeric boundary field check, not full text or legal quality'
(out/'numeric-boundary-comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({name:{k:v for k,v in row.items() if k!='pages'} if isinstance(row,dict) else row for name,row in records.items()},ensure_ascii=False))
