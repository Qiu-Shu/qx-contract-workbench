"""Provision isolated build tools from fixed public packages, never app data."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.local/desktop-tools'
NPM_VERSION = '12.2.0'
NPM_INTEGRITY = 'ZsJjKpTnlmSXOLLXiU1xDCzC4Wlok4IwZmh/aw2KUuXytU7q6qMv/cUT7MoeSf95Slwuw/lRXYefGzGCspHPNQ=='


def download(url):
    with urllib.request.urlopen(url, timeout=60) as stream:
        return stream.read()


def main():
    node = shutil.which('node')
    if not node or sys.version_info[:2] != (3, 12):
        raise SystemExit('Use the fixed project Python 3.12 environment and Node 24 on PATH.')
    TOOLS.mkdir(parents=True, exist_ok=True)
    npm_root = TOOLS / 'npm'
    npm = npm_root / 'package/bin/npm-cli.js'
    raw = download(f'https://registry.npmjs.org/npm/-/npm-{NPM_VERSION}.tgz')
    if base64.b64encode(hashlib.sha512(raw).digest()).decode() != NPM_INTEGRITY:
        raise SystemExit('npm integrity mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(npm_root, filter='data')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--require-hashes', '--target', str(TOOLS/'python-build'),
        '-r', str(ROOT/'desktop/requirements-build.lock'), '--disable-pip-version-check'], check=True)
    subprocess.run([node, str(npm), 'ci', '--ignore-scripts', '--no-fund', '--no-audit'], cwd=ROOT/'desktop', check=True)
    electron = ROOT / 'desktop/node_modules/electron'
    version = json.loads((electron/'package.json').read_text(encoding='utf-8'))['version']
    name = f'electron-v{version}-win32-x64.zip'
    expected = json.loads((electron/'checksums.json').read_text(encoding='utf-8'))[name]
    archive_path = TOOLS / name
    if not archive_path.exists() or hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
        archive_path.write_bytes(download(f'https://github.com/electron/electron/releases/download/v{version}/{name}'))
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Electron integrity mismatch')
    target = (electron/'dist').resolve()
    with zipfile.ZipFile(archive_path) as archive:
        if not all((target/name).resolve().is_relative_to(target) for name in archive.namelist()):
            raise SystemExit('Invalid Electron archive path')
        archive.extractall(target)
    (electron/'path.txt').write_text('electron.exe', encoding='utf-8')
    print('Desktop build dependencies verified. Run scripts/build_desktop.ps1 next.')


if __name__ == '__main__':
    main()
