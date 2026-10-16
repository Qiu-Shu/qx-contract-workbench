# Explicit source assets only. Never collect a workspace or repository tree.
from pathlib import Path
import importlib.metadata
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
assets = []
for source, target in [
    ('config/defaults.json', 'config'),
    ('tests/fixtures/assisted-v1', 'tests/fixtures/assisted-v1'),
    ('tests/fixtures/synthetic', 'tests/fixtures/synthetic'),
    ('rules/default-draft-cards.json', 'rules'),
    ('prompts', 'prompts'),
    ('src/cn_contract/web/templates', 'cn_contract/web/templates'),
    ('src/cn_contract/web/static', 'cn_contract/web/static'),
]:
    assets.append((str(root / source), target))
assets += collect_data_files('docx')
# Carry dependency license texts with the private executable, not just a list.
for distribution in importlib.metadata.distributions():
    for file in distribution.files or ():
        if '.dist-info/' in str(file).replace('\\','/') and any(word in file.name.lower() for word in ('license','copying','notice')):
            source = Path(distribution.locate_file(file))
            if source.is_file(): assets.append((str(source), 'third-party-licenses/'+distribution.metadata['Name']+'/'+str(file.parent)))
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file(): assets.append((str(python_license), 'third-party-licenses/python'))
analysis = Analysis([str(root / 'scripts/desktop_backend_entry.py')],
    pathex=[str(root/'src')], binaries=[], datas=assets,
    hiddenimports=collect_submodules('uvicorn') + ['sqlalchemy.dialects.sqlite', 'pwdlib.hashers.argon2'],
    excludes=['pytest','scrapling','playwright','tkinter'], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='qx-backend',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='qx-backend')
