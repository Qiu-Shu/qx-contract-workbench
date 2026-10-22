"""Run the declared node list without Windows command-line length limits."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path.cwd()))
nodes = (Path(__file__).parent / 'target-nodeids.txt').read_text(encoding='utf-8-sig').splitlines()
raise SystemExit(pytest.main(['-q', '--tb=short', '-o', 'junit_family=xunit1', '--basetemp='+sys.argv[1],
    '--junitxml='+sys.argv[2], *nodes]))

