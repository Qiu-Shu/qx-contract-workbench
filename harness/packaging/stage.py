"""Compatibility entry: use the portable, checksummed Node release pipeline."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

if __name__ == '__main__':
    node = os.environ.get('QX_BUILD_NODE') or shutil.which('node')
    if not node:
        raise SystemExit('Node.js 24 is required. Set QX_BUILD_NODE or add node to PATH.')
    raise SystemExit(subprocess.call([node, str(Path(__file__).with_suffix('.cjs')), *sys.argv[1:]]))
