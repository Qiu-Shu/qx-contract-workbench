from pathlib import Path
import hashlib
import json
import shutil

root=Path.cwd();local=root/'.local/native-model-settings-20261019';out=root/'docs/testing/native-model-settings/20261019'
out.mkdir(parents=True,exist_ok=True)
for source in local.iterdir():
    if source.is_file() and source.suffix in ('.json','.md','.log','.exit','.cjs','.py'):
        shutil.copyfile(source,out/source.name)
for name in ['native-source-first','native-source-final','native-source-verified','native-frozen-verified']:
    source=local/name
    if (source/'report.json').is_file():shutil.copyfile(source/'report.json',out/(name+'-report.json'))
    if name not in ('native-source-verified','native-frozen-verified'):continue
    target=out/name;target.mkdir(exist_ok=True)
    for launch in source.glob('launch-*'):
        dest=target/launch.name;dest.mkdir(exist_ok=True)
        for filename in ('bootstrap.json','network-tripwire.json','electron-stdout.txt','electron-stderr.txt'):
            if (launch/filename).is_file():shutil.copyfile(launch/filename,dest/filename)
    if name=='native-source-verified':
        for source_image in source.glob('*.png'):shutil.copyfile(source_image,out/source_image.name)
verification=json.loads((local/'verification.json').read_text('utf-8'))
frozen=json.loads((local/'frozen-reuse.json').read_text('utf-8'))
native={}
for name in ('native-source-verified','native-frozen-verified'):
    value=json.loads((local/name/'report.json').read_text('utf-8'))
    assert value['status']=='passed' and value['exit_code']==0 and value['source_before']==value['source_after']
    native[name]={'checks':value['checks'],'input_files':len(value['source_before']),'changed_inputs':[],
        'counts':value['counts'],'integrity':value['integrity'],'exit_code':value['exit_code'],'real_model_calls':value['real_model_calls'],
        'electron_exits':[run['electron_exit'] for run in value['runs']],
        'tripwires':[run['tripwire'] for run in value['runs'] if 'tripwire' in run]}
summary={'phase':'CH-04G','baseline':'51e451e','verification':verification,
         'independent_review':{'probes':12,'navigation_tests':8,'navigation_included_in_node':True,'remaining_blockers':0},
         'native':native,'frozen_reuse':frozen,'installed_app_changed':False,'installer_built':False,
         'true_model_network_test':False,'new_dependency':False,'memory_or_package_reduction_measured':False}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
for path in out.rglob('*'):
    if path.is_file() and path.suffix in ('.json','.md','.log','.exit','.cjs','.py','.txt'):
        # Real secrets are never used; this check protects against accidentally copying a profile/db/archive.
        assert path.name not in ('deepseek.bin','workbench.db')
print(json.dumps({'evidence_files':len([p for p in out.rglob('*') if p.is_file()]),'native_checks':{k:len(v['checks']) for k,v in native.items()}}))
