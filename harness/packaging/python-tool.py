"""Entrypoints without virtualenv launchers that embed development-machine paths."""
import os
from pathlib import Path
import sys

tool=sys.argv.pop(1)
if tool=='scrapling':
    if 'mcp' in sys.argv and '--executable-path' not in sys.argv:
        candidates=[Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe',
                    Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',
                    Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/Application/chrome.exe']
        browser=next((p for p in candidates if p.is_file()),None)
        if browser:sys.argv.extend(['--executable-path',str(browser)])
    from scrapling.cli import main
elif tool=='windows':
    from windows_mcp.__main__ import main
else:raise SystemExit('Unknown tool')
main()
