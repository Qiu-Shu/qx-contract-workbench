"""Real Harness shell, source or packaged integration, synthetic fixtures, network blocked."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent
def pdf(path,amount):
    objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    for value in ['Synthetic contract first page','Payment '+amount+' CNY']:
        stream='BT /F1 16 Tf 50 750 Td ('+value+') Tj ET';objects.append('<< /Length '+str(len(stream))+' >>\nstream\n'+stream+'\nendstream')
    content=b'%PDF-1.4\n';offsets=[0]
    for number,obj in enumerate(objects,1):offsets.append(len(content));content+=(str(number)+' 0 obj\n'+obj+'\nendobj\n').encode('ascii')
    xref=len(content);content+=('xref\n0 8\n0000000000 65535 f \n'+''.join(f'{at:010d} 00000 n \n' for at in offsets[1:])+'trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n'+str(xref)+'\n%%EOF').encode('ascii');path.write_bytes(content)
host=subprocess.Popen(['node',str(ROOT/'contract-compare-smoke.cjs')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
report={};browser=None
try:
    runtime=json.loads(host.stdout.readline());folder=Path(runtime['data']);workspace=Path(runtime['workspace'])
    code=Path(os.environ['QX_TEST_APP']) if runtime['packaged'] else ROOT.parent
    os.environ['QX_LEGACY_ROOT']=str(code/'legacy');sys.path.insert(0,str(code/'bridge'))
    report['packagedIntegrationAndParser']=runtime['packaged']
    from store import MaterialStore
    from reader import parse
    from docx import Document
    material=MaterialStore(workspace)
    uploaded=workspace/'inbox/.harness/attachments/v1/files/ab/abcdef/上传合同.txt';uploaded.parent.mkdir(parents=True);uploaded.write_bytes('第一条 保密。\n第二条 价款为人民币100元。\n第三条 保留。'.encode('utf-8'));material.register(str(uploaded));parse(material,str(uploaded));uploaded_hash=hashlib.sha256(uploaded.read_bytes()).hexdigest()
    for name,amount in [('原合同','100'),('新合同','200')]:
        pdf(workspace/(name+'.pdf'),amount)
        document=Document();document.add_paragraph('第一条 保密。');document.add_paragraph('第二条 价款为人民币'+amount+'元。');document.save(workspace/(name+'.docx'))
        for suffix in ['.pdf','.docx']:
            material.register(name+suffix);parsed=parse(material,name+suffix);assert parsed['status']=='ready',parsed
    originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.iterdir() if p.is_file()}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(('http://127.0.0.1:','data:','blob:')) else route.abort())
        context.route('**/api/qx-account/balance*',lambda route:route.fulfill(json={'status':'unavailable','balances':[]}))
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(runtime['url'],wait_until='domcontentloaded')
        start=page.get_by_role('button',name='开始使用',exact=True)
        try:start.click(timeout=15000)
        except Exception:pass
        page.get_by_role('button',name='合同对比',exact=True).click(timeout=60000)
        expect(page.get_by_label('原版本',exact=True)).to_be_enabled(timeout=15000)
        page.get_by_label('原版本',exact=True).select_option(label='原合同.txt')
        page.get_by_label('新版本',exact=True).select_option(label='新合同.txt')
        page.get_by_role('button',name='开始对比',exact=True).click()
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible(timeout=15000)
        page.evaluate("""() => {const original=window.fetch;window.fetch=(url,...args)=>String(url).endsWith('/qx-compare/compare')?new Promise(resolve=>{window.releaseCompare=()=>resolve(original(url,...args));}):original(url,...args);window.restoreCompare=()=>window.fetch=original;}""")
        page.get_by_role('button',name='开始对比',exact=True).click()
        expect(page.get_by_role('button',name='回看原版本 第2行',exact=True)).to_have_count(0)
        page.evaluate('() => {window.releaseCompare();window.restoreCompare();}')
        expect(page.get_by_role('button',name='开始对比',exact=True)).to_be_enabled()
        report['pendingComparisonCannotUseOldLocation']=True
        for width in (1440,768,390):
            page.set_viewport_size({'width':width,'height':1000});expect(page.locator('.qx-compare-body')).to_be_visible();page.screenshot(path=str(folder/f'comparison-{width}.png'))
            assert page.locator('.qx-compare').evaluate('(el)=>el.scrollWidth <= el.clientWidth+2')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('button',name='回看原版本 第2行',exact=True).click()
        expect(page.get_by_role('region',name='已核验原文位置')).to_contain_text('100元')
        expect(page.locator('[data-textpreview-path]:visible')).to_contain_text('原合同.txt',timeout=15000)
        page.screenshot(path=str(folder/'desktop.png'));report['textComparisonAndOriginalNavigation']=True
        page.get_by_role('button',name='准备批注说明',exact=True).click()
        expect(page.locator('[data-composer-input][contenteditable=true]').first).to_contain_text('默认另存批注版')
        report['draftPreservedWithoutSending']=True
        page.get_by_label('原版本',exact=True).select_option(label='已解析：上传合同.txt · abcdef');page.get_by_role('button',name='开始对比',exact=True).click();expect(page.locator('.qx-compare-results article')).to_have_count(1);report['indexedUploadSelectable']=True
        for suffix in ['.docx','.pdf']:
            page.get_by_label('原版本',exact=True).select_option(label='原合同'+suffix);page.get_by_label('新版本',exact=True).select_option(label='新合同'+suffix)
            page.get_by_role('button',name='开始对比',exact=True).click();expect(page.locator('.qx-compare-results article')).to_have_count(1)
            if suffix=='.pdf':
                page.get_by_role('button',name='回看原版本 第2页 · 提取段2',exact=True).click()
                expect(page.locator('[data-document-preview]:visible [data-pdf-page="2"] canvas')).to_be_visible(timeout=30000)
                page.wait_for_timeout(600)
                assert page.locator('[data-document-preview]:visible [data-pdf-page="2"]').evaluate('(el)=>{const r=el.getBoundingClientRect();return r.top>=0&&r.top<innerHeight}')
                page.screenshot(path=str(folder/'pdf-page-2.png'));report['pdfOriginalPage2']=True
            else:report['docxOriginalParserComparison']=True
        page.get_by_label('原版本',exact=True).select_option(label='原合同.txt');page.get_by_label('新版本',exact=True).select_option(label='新合同.txt');page.get_by_role('button',name='开始对比',exact=True).click();expect(page.locator('.qx-compare-results article')).to_have_count(1)
        (workspace/'原合同.txt').write_text('第一条 外部修改。',encoding='utf-8')
        page.get_by_role('button',name='回看原版本 第2行',exact=True).click()
        expect(page.get_by_role('alert').filter(has_text='原文件已变化')).to_be_visible()
        report['staleCitationRejected']=True
        report['widths']=[1440,768,390]
        assert all(hashlib.sha256((workspace/name).read_bytes()).hexdigest()==value for name,value in originals.items() if name!='原合同.txt')
        report['otherFiveOriginalsUnchanged']=True
        assert hashlib.sha256(uploaded.read_bytes()).hexdigest()==uploaded_hash;report['uploadedOriginalUnchanged']=True
        report['pageErrors']=errors;assert not errors,errors
        browser.close();browser=None
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'report':report,'directory':str(folder)},ensure_ascii=False))
except Exception:
    try:page.screenshot(path=str(folder/'failure.png'));(folder/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
    except Exception:pass
    raise
finally:
    if browser:
        try:browser.close()
        except Exception:pass
    subprocess.run(['taskkill','/PID',str(host.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
