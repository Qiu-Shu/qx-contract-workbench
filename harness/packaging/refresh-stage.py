"""Refresh source overlays in a stage created by stage.cjs."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Use refresh-stage.py <stage-directory>; version is in app-template.json.')
    node = os.environ.get('QX_BUILD_NODE') or shutil.which('node')
    if not node:
        raise SystemExit('Node.js 24 is required. Set QX_BUILD_NODE or add node to PATH.')
    raise SystemExit(subprocess.call([node, str(Path(__file__).with_name('stage.cjs')), sys.argv[1], '--refresh']))
