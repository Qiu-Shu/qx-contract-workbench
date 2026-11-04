"""Actual privacy client -> actual Node routes -> Python -> local upload fixture.

Uses only synthetic TXT/DOCX/PNG files and an independent headless Chrome.
Run with the Playwright environment; --python selects the workbench reader/OCR
environment. Original test files and the private vault exist only under one
temporary directory. Reports contain synthetic safe output, never user data.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.local/privacy-improvement-20261104' / ('end-to-end-' + time.strftime('%Y%m%d-%H%M%S'))
REPORT = {'status': 'running', 'scope': 'real local privacy routes, Python extraction/redaction and browser file replay; synthetic downstream only',
          'checks': [], 'cases': [], 'page_errors': [], 'console_errors': [], 'blocked_requests': []}
SAMPLE = ('乙方：示例青枫科技有限公司（品牌：远岸成长）。\n'
          '自主研发的星穹学习大模型已完成备案。\n'
          '备案编号：Beijing-Fiction-202601010001。\n'
          '备案时间2026年4月3日。\n'
          '具有国家级高新技术企业资质，累计服务1200余所中小学校。\n'
          '面向中小学校。\n'
          '合同金额125000.50元，交付24套设备，期限36个月。\n'
          '联系电话：13800138000。')

HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>本机脱敏上传验证</title>
<style>body{font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:40px auto;max-width:760px;padding:0 20px;background:#f7f8fa;color:#253043}h1{font-size:24px}p{color:#667085}[data-composer-card]{padding:14px;background:white;border:1px solid #dce2eb;border-radius:14px}[contenteditable]{min-height:80px;padding:12px;outline:none}button{padding:8px 20px}input{max-width:100%}#received{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;border-radius:12px;padding:16px;font-size:13px}.test-note{font-size:12px}</style>
<h1>上传前本机脱敏</h1><p class="test-note">合成资料验收：真实文档读取与图片识字，结果只交给本机测试收件端。</p>
<div data-composer-card><input type="file" id="chatfiles" multiple><div role="textbox" contenteditable="true">选择文件、拖入 Word 或粘贴图片</div><button aria-label="发送">发送</button></div><pre id="received"></pre>
<script>
window.received=[];window.downstreamErrors=[];
for(const type of ['change','paste','drop'])document.addEventListener(type,async event=>{
 const files=event.type==='change'?event.target.files:(event.clipboardData||event.dataTransfer)?.files;
 for(const file of files||[]){
  try{
   const query=new URLSearchParams({name:file.name,event:type,type:file.type,case:window.__case||'unknown'});
   const response=await fetch('/fixture-upload?'+query,{method:'POST',headers:{'content-type':file.type},body:file});
   if(!response.ok)throw Error('Synthetic upload sink failed');
   const receipt=await response.json();window.received.push(receipt);
   document.getElementById('received').textContent=window.received.map(item=>item.event+' · '+item.name+'\n'+item.text).join('\n\n');
  }catch(error){window.downstreamErrors.push(error.message);}
 }
});
</script><script src="/api/qx-privacy/client.js"></script></html>'''

HOST = r'''
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {pathToFileURL} from 'node:url';
const [pluginPath,python,runtime,htmlPath]=process.argv.slice(2);
const plugin=await import(pathToFileURL(pluginPath));
const routes=new Map(),disposers=[],events=[],receipts=[];
plugin.apply({effect:run=>disposers.push(run()),connection:{fetch:{register:route=>routes.set(route.path,route)}}},{workspace:runtime+'/workspace',python});
let sequence=0;
const server=http.createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,`http://127.0.0.1:${server.address().port}`);
  if(url.pathname==='/'){
   const body=await readFile(htmlPath);res.writeHead(200,{'content-type':'text/html; charset=utf-8'});res.end(body);return;
  }
  if(url.pathname==='/fixture-state'){
   res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({events,receipts}));return;
  }
  if(url.pathname==='/fixture-upload'&&req.method==='POST'){
   const chunks=[];for await(const chunk of req)chunks.push(chunk);
   const body=Buffer.concat(chunks),entry={sequence:++sequence,name:url.searchParams.get('name'),event:url.searchParams.get('event'),type:url.searchParams.get('type'),case:url.searchParams.get('case'),text:body.toString('utf8'),bytes:body.length};
   receipts.push(entry);events.push({sequence:entry.sequence,phase:'downstream_received',case:entry.case,name:entry.name});
   res.writeHead(200,{'content-type':'application/json; charset=utf-8'});res.end(JSON.stringify(entry));return;
  }
  if(url.pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}
  const route=routes.get(url.pathname);
  if(!route||!route.methods.includes(req.method)){res.writeHead(404);res.end();return;}
  const prepare=url.pathname==='/api/qx-privacy/prepare';
  if(prepare)events.push({sequence:++sequence,phase:'prepare_started',mode:url.searchParams.get('mode'),name:url.searchParams.get('name')});
  const controller=new AbortController();res.on('close',()=>{if(!res.writableEnded)controller.abort();});
  const request=new Request(url,{method:req.method,headers:req.headers,signal:controller.signal,...req.method==='POST'?{body:Readable.toWeb(req),duplex:'half'}:{}});
  const response=await route.fetch(request);
  if(prepare)events.push({sequence:++sequence,phase:'prepare_finished',mode:response.headers.get('x-qx-privacy-mode'),requestedMode:url.searchParams.get('mode'),status:response.status,name:url.searchParams.get('name')});
  res.writeHead(response.status,Object.fromEntries(response.headers));
  if(response.body)await pipeline(Readable.fromWeb(response.body),res);else res.end();
 }catch(error){if(!res.headersSent)res.writeHead(500,{'content-type':'application/json'});res.end(JSON.stringify({error:error.message}));}
});
server.listen(0,'127.0.0.1',()=>console.log(JSON.stringify({origin:`http://127.0.0.1:${server.address().port}`})));
function close(){for(const dispose of disposers)if(typeof dispose==='function')dispose();server.close(()=>process.exit(0));}
process.on('SIGINT',close);process.on('SIGTERM',close);
'''

MAKE_FILES = r'''
import json,sys
from pathlib import Path
from docx import Document
from PIL import Image,ImageDraw,ImageFont
args=json.loads(sys.stdin.read());target=Path(args['directory']);text=args['text']
(target/'synthetic.txt').write_text(text,encoding='utf-8')
document=Document()
for line in text.splitlines():
 paragraph=document.add_paragraph()
 middle=len(line)//2
 paragraph.add_run(line[:middle]);paragraph.add_run(line[middle:])
document.core_properties.author='合成隐藏作者'
document.save(target/'synthetic.docx')
image=Image.new('RGB',(2300,40+len(text.splitlines())*86),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',48)
for index,line in enumerate(text.splitlines()):draw.text((30,20+index*86),line,font=font,fill='black')
image.save(target/'synthetic.png')
'''


def check_output(receipt, mode):
    text = re.sub(r'\s+', '', receipt['text'])
    for value in ['示例青枫科技有限公司', '远岸成长', '星穹学习', 'Beijing-Fiction-202601010001', '13800138000', '合成隐藏作者']:
        assert value not in text, f'{mode}: identifier survived: {value}'
    assert '中小学校' in text, f'{mode}: ordinary school category disappeared: {text}'
    for value in ['2026年4月3日', '125000.50元', '24套', '36个月']:
        assert value in text, f'{mode}: business datum changed: {value}; {text}'
    for value in ['国家级高新技术企业', '1200']:
        assert (value in text) == (mode == 'standard'), f'{mode}: qualification/scale handling incorrect: {value}; {text}'
    assert receipt['name'].endswith('.txt') and receipt['type'] == 'text/plain'
    assert '【' in text and '】' in text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe', help='Actual reader/OCR Python environment')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    node = shutil.which('node') or 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    temp = tempfile.TemporaryDirectory(prefix='synthetic-runtime-', dir=OUT)
    runtime = Path(temp.name).resolve()
    assert runtime.is_relative_to(OUT.resolve())
    host = None
    stderr_file = (OUT / 'host-stderr.log').open('w', encoding='utf-8')
    try:
        (runtime / 'fixture.html').write_text(HTML, encoding='utf-8')
        (runtime / 'host.mjs').write_text(HOST, encoding='utf-8')
        subprocess.run([args.python, '-X', 'utf8', '-c', MAKE_FILES], input=json.dumps({'directory': str(runtime), 'text': SAMPLE}, ensure_ascii=False), capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
        files = {extension: runtime / ('synthetic.' + extension) for extension in ['txt', 'docx', 'png']}
        hashes = {extension: hashlib.sha256(path.read_bytes()).hexdigest() for extension, path in files.items()}
        REPORT['product_hashes'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ['plugins/privacy/index.mjs', 'plugins/privacy/client.js', 'bridge/privacy.py']}
        host = subprocess.Popen([node, str(runtime / 'host.mjs'), str(ROOT / 'plugins/privacy/index.mjs'), args.python, str(runtime), str(runtime / 'fixture.html')], cwd=ROOT, stdout=subprocess.PIPE, stderr=stderr_file, text=True, encoding='utf-8')
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(host.stdout.readline()), daemon=True).start()
        origin = json.loads(ready.get(timeout=20))['origin']
        REPORT['origin'] = origin
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            context = browser.new_context(viewport={'width': 1100, 'height': 900}, service_workers='block')

            def route_request(route):
                if route.request.url.startswith(origin + '/'):
                    route.continue_()
                else:
                    REPORT['blocked_requests'].append(route.request.url)
                    route.abort()

            context.route('**/*', route_request)
            page = context.new_page()
            page.on('pageerror', lambda error: REPORT['page_errors'].append(str(error)))
            page.on('console', lambda message: REPORT['console_errors'].append(message.text) if message.type == 'error' else None)
            page.goto(origin, wait_until='networkidle')
            control = page.locator('[data-composer-card] .qx-privacy')
            expect(control).to_be_visible()
            control.locator('input[type=checkbox]').check()
            counter = 0
            for mode in ['standard', 'deep']:
                page.get_by_label('脱敏方式', exact=True).select_option(mode)
                for extension, event in [('txt', 'change'), ('docx', 'drop'), ('png', 'paste')]:
                    case = f'{mode}-{extension}-{event}'
                    page.evaluate('name=>window.__case=name', case)
                    if event == 'change':
                        page.locator('#chatfiles').set_input_files(str(files[extension]))
                    else:
                        payload = {'kind': event, 'name': files[extension].name, 'mime': 'image/png' if extension == 'png' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'body': base64.b64encode(files[extension].read_bytes()).decode()}
                        page.locator('[contenteditable]').evaluate('''(element,data)=>{const bytes=Uint8Array.from(atob(data.body),char=>char.charCodeAt(0)),transfer=new DataTransfer();transfer.items.add(new File([bytes],data.name,{type:data.mime}));element.dispatchEvent(data.kind==='paste'?new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:transfer}):new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));}''', payload)
                    review=page.get_by_role('dialog',name='脱敏复核',exact=True)
                    expect(review).to_be_visible(timeout=180000)
                    assert page.evaluate('window.received.length') == counter, 'File uploaded before review'
                    review.get_by_role('button',name='确认使用此版本',exact=True).click()
                    counter += 1
                    page.wait_for_function('count=>window.received.length===count||document.querySelector(".qx-privacy").dataset.error==="true"', arg=counter, timeout=180000)
                    assert page.evaluate('window.received.length') == counter, control.locator('[role=status]').inner_text()
                    receipt = page.evaluate('window.received.at(-1)')
                    check_output(receipt, mode)
                    assert receipt['event'] == event and receipt['case'] == case
                    REPORT['cases'].append({'case': case, 'passed': True, 'receipt': receipt})
            state = page.evaluate('fetch("/fixture-state").then(response=>response.json())')
            REPORT['events'] = state['events']
            assert len(state['receipts']) == 6
            assert len(state['events']) == 18
            for index, case in enumerate(REPORT['cases']):
                started, finished, uploaded = state['events'][index * 3:index * 3 + 3]
                assert [started['phase'], finished['phase'], uploaded['phase']] == ['prepare_started', 'prepare_finished', 'downstream_received']
                assert finished['status'] == 200 and finished['mode'] == started['mode'] == case['case'].split('-')[0]
                assert uploaded['sequence'] > finished['sequence'] and uploaded['case'] == case['case']
            REPORT['checks'].extend(['Both standard/deep traverse the real Node route and Python redactor for TXT, DOCX and PNG',
                                     'Picker, drag and clipboard replay only a safe text File after Python completes with the requested mode',
                                     'Brands/product names/filing IDs/phone removed; ordinary school category retained',
                                     'Standard retains qualifications and coverage scale; deep removes them; both preserve money/date/quantity/duration'])
            for extension, path in files.items():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[extension]
            assert list((runtime / '.qx-private/uploads').rglob('original.*')), 'No local originals retained'
            assert not list((runtime / 'workspace').rglob('*')), 'Original or private map entered model workspace'
            REPORT['checks'].append('Original synthetic files unchanged; private archive exists outside the empty model workspace')
            page.locator('.qx-privacy summary').click()
            page.screenshot(path=str(OUT / 'desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(OUT / 'narrow-390.png'), full_page=True)
            assert not page.evaluate('window.downstreamErrors')
            assert not REPORT['page_errors'], REPORT['page_errors']
            assert not REPORT['console_errors'], REPORT['console_errors']
            assert not REPORT['blocked_requests'], REPORT['blocked_requests']
            REPORT['status'] = 'passed'
            page.evaluate('window.qxPrivacy.dispose()')
            context.close()
            browser.close()
    finally:
        if host is not None:
            host.terminate()
            try:
                host.wait(timeout=15)
            except subprocess.TimeoutExpired:
                host.kill()
                host.wait(timeout=5)
        stderr_file.close()
        assert runtime.is_relative_to(OUT.resolve()) and runtime != OUT.resolve()
        temp.cleanup()
        REPORT['temporary_runtime_removed'] = not runtime.exists()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        REPORT.update(status='failed', error=str(error))
        raise
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        REPORT['artifacts'] = str(OUT)
        (OUT / 'report.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': REPORT['status'], 'cases': len(REPORT['cases']), 'artifacts': str(OUT)}, ensure_ascii=False))
