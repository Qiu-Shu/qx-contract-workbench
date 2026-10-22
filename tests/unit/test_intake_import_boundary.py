"""Reception can be imported without the Web stack or document processors."""
import subprocess
import sys


def test_intake_import_does_not_load_web_or_document_processing():
    probe = r'''
import importlib.abc
import sys

blocked = ('cn_contract.web', 'docx', 'cn_contract.documents.ingest',
           'cn_contract.review.workflow')

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('unexpected dependency: ' + fullname)

sys.meta_path.insert(0, Guard())
from cn_contract.intake import service
assert all(callable(getattr(service, name)) for name in ('create', 'save', 'read', 'convert', 'export'))
assert not any(name == prefix or name.startswith(prefix + '.')
               for name in sys.modules for prefix in blocked)
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', probe],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
