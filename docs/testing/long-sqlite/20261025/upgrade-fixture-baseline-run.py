"""Controlled HEAD module interception; all actual imported source is audited."""
from hashlib import sha256
import importlib.abc
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


workspace = Path(__file__).resolve().parents[2]
evidence = Path(__file__).resolve().parent
baseline = '916d55bf47ffb513508b81c5ebf40a5482372a67'
snapshot = evidence/'upgrade-fixture-baseline'
paths = [name for name in subprocess.check_output(
    ['git', 'ls-tree', '-r', '--name-only', baseline, 'src'], cwd=workspace).decode('utf-8').splitlines()
    if name.endswith('.py')]
expected = {}
overrides = {}
for name in paths:
    frozen = subprocess.check_output(['git', 'show', baseline+':'+name], cwd=workspace)
    expected[name] = sha256(frozen).hexdigest()
    if (workspace/name).read_bytes() != frozen:
        target = snapshot/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(frozen)
        module_name = name[4:-3].replace('/', '.')
        overrides[module_name] = target
test = 'tests/integration/test_workspace_upgrade.py'
old_test = subprocess.check_output(['git', 'show', baseline+':'+test], cwd=workspace)
frozen_test = snapshot/test
frozen_test.parent.mkdir(parents=True, exist_ok=True)
frozen_test.write_bytes(old_test)
working_test_unchanged = (workspace/test).read_bytes() == old_test
sys.path.insert(0, str(workspace))
sys.path.insert(0, str(workspace/'src'))


class FrozenModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in overrides:
            return importlib.util.spec_from_file_location(fullname, overrides[fullname])


sys.meta_path.insert(0, FrozenModules())
import pytest

argv = [str(frozen_test)+'::test_upgrade_keeps_identity_login_case_and_independent_backup',
        '-q', '--tb=short', '--basetemp='+str(evidence/'upgrade-fixture-baseline-temp'),
        '--junitxml='+str(evidence/'upgrade-fixture-baseline-red.xml')]
started = time.monotonic()
code = pytest.main(argv)
loaded = []
for name, module in list(sys.modules.items()):
    filename = getattr(module, '__file__', None)
    if (name == 'cn_contract' or name.startswith('cn_contract.')) and filename:
        path = Path(filename).resolve()
        relative = path.relative_to(snapshot) if path.is_relative_to(snapshot) else path.relative_to(workspace)
        relative = relative.as_posix()
        actual = sha256(path.read_bytes()).hexdigest()
        assert actual == expected[relative], 'Non-baseline imported module: '+name
        loaded.append({'module': name, 'path': str(path), 'sha256': actual})
cases = list(ET.parse(evidence/'upgrade-fixture-baseline-red.xml').getroot().iter('testcase'))
result = {'baseline': baseline, 'pytest_argv': argv, 'exit_code': int(code),
          'seconds': round(time.monotonic()-started, 3), 'source_py_count': len(paths),
          'overridden_modules': {name: str(path) for name, path in overrides.items()},
          'actual_loaded_module_count': len(loaded), 'all_actual_modules_match_baseline': True,
          'test_unchanged_from_baseline': frozen_test.read_bytes() == old_test,
          'actual_test_path': str(frozen_test),
          'working_test_unchanged_from_baseline': working_test_unchanged,
          'test_sha256': sha256(old_test).hexdigest(),
          'test_count': len(cases), 'errors': sum(case.find('error') is not None for case in cases),
          'failures': sum(case.find('failure') is not None for case in cases), 'loaded': loaded}
(evidence/'upgrade-fixture-baseline-red.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'loaded'}, ensure_ascii=False))
assert code == 1 and len(cases) == 1 and result['errors'] == 1 and result['failures'] == 0
sys.exit(code)
