from pathlib import Path
from datetime import datetime,timezone
import sys,json,time,threading,hashlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'src'))
from PIL import Image,ImageDraw,ImageFont
from cn_contract.documents import ocr_process,ocr_candidates,_windows_ocr,ocr_workspace
from cn_contract.domain import PageOCRInput
from cn_contract.security import ServiceError
out=ROOT/'docs/testing/qx08-ocr-cleanup-20261011/native-final';out.mkdir(exist_ok=False)
(out/'.gitattributes').write_bytes(b'* -text\n')
image=Image.new('RGB',(1000,280),'white');draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',34)
draw.text((30,25),'独立虚构清理测试 价款 38521 元',fill='black',font=font)
draw.text((30,120),'不得自动验收 2026-10-11',fill='black',font=font)
buffer=BytesIO();image.save(buffer,format='PDF',resolution=144);original=buffer.getvalue()
(out/'synthetic.pdf').write_bytes(original)
value=PageOCRInput(document_version_id=UUID('aba591e8-4fd5-4dfe-9302-ac94a974479c'),document_sha256=hashlib.sha256(original).hexdigest(),page=1)
phases=[];entered=threading.Event();jobs=[];native=[];copy_sizes=[]
history={p.name for p in (ROOT/'.local/ocr-jobs').iterdir()}
def wrap(module,name):
 fn=getattr(module,name)
 def measured(*args,**kwargs):
  if name=='require_ocr_runtime':entered.set()
  start=time.perf_counter()
  try:
   result=fn(*args,**kwargs)
   if name=='run_sandboxed':native.append(result)
   if name=='stage_models':
    jobs.append(args[0]);copy_sizes.append(sum(p.stat().st_size for p in (args[0]/'models').rglob('*') if p.is_file()))
   return result
  finally:phases.append(dict(phase=name,seconds=round(time.perf_counter()-start,6),thread=threading.get_ident()))
 setattr(module,name,measured)
for module,name in [(ocr_process,'require_ocr_runtime'),(ocr_candidates,'page_bitmap'),(ocr_process,'stage_models'),(_windows_ocr,'run_sandboxed'),(ocr_process,'decode_output'),(ocr_workspace,'cleanup')]:wrap(module,name)
start=time.perf_counter();started=datetime.now(timezone.utc).isoformat();failure=None
with ThreadPoolExecutor(max_workers=1) as pool:
 pending=pool.submit(ocr_candidates.predict_page,original,value)
 assert entered.wait(10)
 busy_start=time.perf_counter()
 try:ocr_candidates.predict_page(original,value)
 except ServiceError as e:busy=e.code
 else:busy='unexpected_success'
 busy_seconds=time.perf_counter()-busy_start
 try:
  result=pending.result(timeout=180)
  (out/'synthetic-result.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
 except Exception as e:failure=dict(type=type(e).__name__,code=getattr(e,'code',None))
receipt=dict(scope='one local synthetic job, instrumented current code; not cold/warm benchmark or legal quality acceptance',started_utc=started,total_seconds=round(time.perf_counter()-start,6),busy_code=busy,busy_seconds=round(busy_seconds,6),phases=phases,native=native,failure=failure,model_copy_bytes=sum(copy_sizes),job_directory_retained=bool(jobs and jobs[0].exists()),real_predictions_returned=int(failure is None),source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['src/cn_contract/documents/ocr_process.py','src/cn_contract/documents/ocr_candidates.py','src/cn_contract/documents/_windows_ocr.py','src/cn_contract/documents/ocr_workspace.py']})
(out/'timing.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
assert busy=='OCR_BUSY' and failure is None
assert len(phases)==6 and all(row['thread']!=threading.get_ident() for row in phases)

assert len(jobs)==1 and not jobs[0].exists()
assert history=={p.name for p in (ROOT/'.local/ocr-jobs').iterdir()}
print('OWN_JOB_REMOVED; HISTORICAL_ENTRY_NAMES_UNCHANGED',flush=True)
