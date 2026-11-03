"""Append the owner-authenticated privacy plugin without replacing saved profile settings."""
from pathlib import Path
from datetime import datetime
import shutil

ROOT=Path(__file__).resolve().parents[1]
MARKER='# qunxing-upload-privacy-v1'
BLOCK=f'''\n{MARKER}
- insert:
    - id: qx-upload-privacy
      name: {ROOT.as_posix()}/plugins/privacy/index.mjs
      config:
        workspace: {ROOT.as_posix()}/workspace
        python: D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe
'''
for target in [ROOT/'config/cordis.patch.yml',ROOT/'.local/dsh-home/profiles/web/cordis.patch.yml']:
    if MARKER in target.read_text(encoding='utf-8-sig'):continue
    if '.local' in target.parts:
        backup=ROOT/'.local/backups'/('privacy-profile-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.yml')
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
    with target.open('a',encoding='utf-8') as stream:stream.write(BLOCK)
print('Privacy plugin appended; other profile settings preserved.')

# Remove an obsolete partial override: Cordis replaces the complete config,
# so partial env-only overrides would remove the stdio command and server name.
refresh='''\n# qunxing-business-delivery-tools-v2
- id: qx-materials
  config:
    env:
      PYTHONIOENCODING: utf-8
      QX_DOCUMENT_DELIVERY_VERSION: '2'
- id: qx-legal
  config:
    env:
      PYTHONIOENCODING: utf-8
      QX_BUSINESS_RECORD_VERSION: '2'
'''
for target in [ROOT/'config/cordis.patch.yml',ROOT/'.local/dsh-home/profiles/web/cordis.patch.yml']:
    current=target.read_text(encoding='utf-8-sig')
    if refresh in current:target.write_text(current.replace(refresh,''),encoding='utf-8')
