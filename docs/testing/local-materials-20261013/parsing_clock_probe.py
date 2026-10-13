from pathlib import Path
from tempfile import mkdtemp
from io import BytesIO
import sys,json,zipfile
sys.path.insert(0,str(Path.cwd()))
from tests.integration import test_parsing as subject
original=subject.docx
def changed_clock_docx():
 raw=original();out=BytesIO()
 with zipfile.ZipFile(BytesIO(raw)) as z,zipfile.ZipFile(out,'w') as target:
  for info in z.infolist():
   content=z.read(info);info.date_time=(2020,1,2,3,4,6);target.writestr(info,content)
 rewritten=out.getvalue()
 with zipfile.ZipFile(BytesIO(raw)) as a,zipfile.ZipFile(BytesIO(rewritten)) as b:
  assert raw!=rewritten
  assert all(a.read(name)==b.read(name) for name in a.namelist())
 return rewritten
subject.docx=changed_clock_docx
folder=mkdtemp(prefix='clock-probe-',dir=Path(__file__).parent)
subject.test_parse_appends_without_overwriting_original(Path(folder))
print('Original preservation passes with independently shifted ZIP timestamps')
