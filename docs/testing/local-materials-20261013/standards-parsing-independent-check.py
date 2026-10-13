import ast
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
import zipfile

sys.path.insert(0, str(Path.cwd()))
from tests.integration import test_parsing as subject

root = Path(__file__).parent
original = subject.docx
def shifted_docx():
    raw = original()
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(raw)) as source, zipfile.ZipFile(out, 'w') as target:
        for info in source.infolist():
            content = source.read(info)
            info.date_time = (2001, 2, 3, 4, 5, 6)
            target.writestr(info, content)
    shifted = out.getvalue()
    assert raw != shifted
    with zipfile.ZipFile(BytesIO(raw)) as source, zipfile.ZipFile(BytesIO(shifted)) as target:
        assert source.namelist() == target.namelist()
        assert all(source.read(name) == target.read(name) for name in source.namelist())
    return shifted

old_source = subprocess.check_output(['git', 'show', 'HEAD:tests/integration/test_parsing.py'], text=True, encoding='utf-8')
old_function = next(node for node in ast.parse(old_source).body if isinstance(node, ast.FunctionDef) and node.name == 'test_parse_appends_without_overwriting_original')
old_namespace = dict(vars(subject))
exec(compile(ast.Module(body=[old_function], type_ignores=[]), 'HEAD-test_parsing.py', 'exec'), old_namespace)
old_namespace['docx'] = shifted_docx
try:
    old_namespace[old_function.name](Path(mkdtemp(prefix='parsing-old-', dir=root)))
except AssertionError:
    old_red = True
else:
    raise AssertionError('Old test unexpectedly passed forced distinct ZIP timestamp bytes')
subject.docx = shifted_docx
subject.test_parse_appends_without_overwriting_original(Path(mkdtemp(prefix='parsing-new-', dir=root)))
result = {'old_assertion_failed':old_red, 'new_assertion_passed':True,
          'zip_bytes_differ':True, 'each_zip_member_content_identical':True}
root.joinpath('parsing-independent-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
