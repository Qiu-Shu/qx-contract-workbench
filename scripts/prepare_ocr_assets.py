"""Explicit local preparation; HTTP/business requests never install or download."""
import argparse,hashlib,json,shutil,subprocess,sys,urllib.request
from pathlib import Path
from cn_contract.documents import ocr_assets as gate
from cn_contract.documents.pdfjs_assets import _regular


def manifest():
    raw=gate.MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=gate.MANIFEST_SHA256:raise ValueError('manifest changed')
    return json.loads(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-assets',action='store_true',help='download fixed public files into a fresh asset directory')
    parser.add_argument('--install-environment',action='store_true',help='offline wheel-only installation into a fresh dedicated directory')
    args=parser.parse_args();lock=manifest()
    if args.download_assets:
        if gate.ASSET_ROOT.exists():raise ValueError('asset directory already exists; verify or preserve it before recovery')
        urls={'wheels/'+p['wheel']:p['url'] for p in lock['packages']}
        urls.update({'models/'+m['name']+'/'+f['path']:f['url'] for m in lock['models'] for f in m['files']})
        for row in lock['files']:
            url=urls[row['path']]
            if not url.startswith(('https://files.pythonhosted.org/','https://huggingface.co/PaddlePaddle/')):raise ValueError('unexpected host')
            with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(row['bytes']+1)
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('download digest mismatch')
            dest=gate.ASSET_ROOT/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);_regular(dest.parent,directory=True)
            with dest.open('xb') as stream:stream.write(raw)
    print(json.dumps(gate.verify_ocr_assets()))
    if args.install_environment:
        if lock['runtime_approved'] is not True:raise ValueError('local execution approval missing')
        if sys.version_info[:3]!=(3,12,14):raise ValueError('fixed Python version required')
        dest=gate.PROJECT_ROOT/'.local/ocr-worker/python'
        if dest.exists():raise ValueError('environment already exists; never overwrite or refreeze automatically')
        dest.parent.mkdir(parents=True,exist_ok=True);_regular(dest.parent,directory=True)
        shutil.copytree(Path(sys.base_prefix),dest,ignore=shutil.ignore_patterns('site-packages','__pycache__','Scripts','include','libs','tcl'))
        (dest/'Lib/site-packages').mkdir()
        subprocess.run([sys.executable,'-m','pip','--python',str(dest/'python.exe'),'install','--no-index',
            '--find-links',str(gate.ASSET_ROOT/'wheels'),'--require-hashes','--no-compile',
            '-r',str(gate.PROJECT_ROOT/'requirements-ocr-windows-py312.lock')],check=True)
    gate.require_ocr_runtime()
    print('LOCAL_SYNTHETIC_RUNTIME_VERIFIED; production remains blocked')


if __name__=='__main__':main()
