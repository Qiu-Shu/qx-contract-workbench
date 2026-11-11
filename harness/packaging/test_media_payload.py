"""A fresh source overlay must boot media without inherited application config."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_media_service_starts_from_checkout(tmp_path):
    from media.service import MediaService
    service = MediaService(tmp_path)
    status = service.dispatch('status', {})
    assert {source['id'] for source in status['sources']} == {'national', 'jilin', 'labor-contract-law'}
    assert status['jobs'] == []


def test_clean_media_payload_starts_without_bootstrap_sources(tmp_path):
    payload = tmp_path / 'payload'
    payload.mkdir()
    script = """
const fs=require('node:fs'),path=require('node:path');
const {overlay,copyMediaRegistry}=require('./packaging/stage.cjs');
const payload=process.argv[1],manifest=[];
fs.mkdirSync(path.join(payload,'bridge'));
overlay('bridge',path.join(payload,'bridge'),manifest,'resources/workbench/bridge');
copyMediaRegistry('sources/media-source-registry.json',payload,manifest);
console.log(JSON.stringify(manifest.filter(item=>item.target.includes('/sources/'))));
"""
    staged = subprocess.run([os.environ.get('QX_TEST_NODE', 'node'), '-e', script, str(payload)],
                            cwd=ROOT, check=True, capture_output=True, text=True, encoding='utf-8')
    manifest = json.loads(staged.stdout)
    assert len(manifest) == 1
    assert manifest[0]['source'] == 'sources/media-source-registry.json'
    assert manifest[0]['target'] == 'resources/workbench/sources/media-source-registry.json'
    source = ROOT / 'sources/media-source-registry.json'
    assert (payload / 'sources/media-source-registry.json').read_bytes() == source.read_bytes()
    code = """
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'bridge'))
from media.service import MediaService
service=MediaService(sys.argv[2])
print(json.dumps(service.dispatch('status',{})))
"""
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'DEEPSEEK_API_KEY': ''}
    result = subprocess.run([sys.executable, '-c', code, str(payload), str(tmp_path/'workspace')],
                            cwd=tmp_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8')
    status = json.loads(result.stdout)
    assert len(status['sources']) == 3
    assert status['jobs'] == [] and status['source_health'] == []
    assert status['model_configured'] is False
