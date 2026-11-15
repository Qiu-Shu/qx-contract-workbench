"""Real Harness shell, source or packaged integration, synthetic fixtures, network blocked."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent

def settle_sidebar(page):
    page.evaluate('''async()=>{let last='',stable=0;for(let i=0;i<120&&stable<12;i++){
      await new Promise(requestAnimationFrame);const el=document.querySelector('.hHd-Xa_root');
      const center=document.querySelector('.pI_x6G_centerCol'),preview=document.querySelector('[data-document-preview]');
      const key=el.className+el.getBoundingClientRect().width+':'+center?.getBoundingClientRect().width+':'+preview?.getBoundingClientRect().x;stable=key===last?stable+1:0;last=key;
    }}''')
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
    rich_before='采购合同（虚构示例）\n第一条 标的：办公桌。\n旧条款：乙方免费保管库存。\n第二条 付款安排\n合同价款为人民币10,000元。\n甲方在验收合格后30日内付款。\n第三条 质量保证\n质保期为12个月。\n第四条 违约责任\n甲方逾期付款的违约金为每日1%。\n第五条 争议解决\n双方应先友好协商。\n'
    rich_after='采购合同（虚构示例）\n第一条 标的：办公桌。\n第二条 付款安排\n合同价款为人民币20,000元。\n甲方在验收合格后15日内付款。\n第三条 质量保证\n质保期为12个月。\n第四条 违约责任\n甲方逾期付款的违约金为每日2%。\n第五条 争议解决\n双方应先友好协商。\n乙方收到通知后48小时内响应。\n'
    (workspace/'采购原稿.txt').write_bytes(rich_before.encode('utf-8'));(workspace/'采购修改稿.txt').write_bytes(rich_after.encode('utf-8'))
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
        balance_reply={'status':'unavailable','balances':[]}
        context.route('**/api/qx-account/balance*',lambda route:route.fulfill(json=balance_reply))
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def select_file(label,name):
            if not page.get_by_label(label,exact=True).is_visible():page.get_by_role('button',name='更换文件',exact=True).click()
            page.get_by_label(label,exact=True).select_option(label=name)
            expect(page.get_by_role('button',name='正在对比…',exact=True)).to_have_count(0,timeout=30000)
        page.goto(runtime['url'],wait_until='domcontentloaded')
        start=page.get_by_role('button',name='开始使用',exact=True)
        try:start.click(timeout=15000)
        except Exception:pass
        # General/reception entry must not contain a persistent comparison control.
        page.get_by_role('button',name='新建客户接待对话',exact=True).click(timeout=60000)
        expect(page.get_by_role('region',name='客户接待业务引导')).to_be_visible()
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_count(0)
        for title in ['拓客内容','功能组件','知识库','微信连接']:
            expect(page.get_by_role('button',name=title,exact=True)).to_be_visible()
        report['layoutMatrix']=[]
        for width,height in [(1280,720),(1366,768),(1920,1080)]:
            for scale in [1,1.25,1.5]:
                page.set_viewport_size({'width':round(width/scale),'height':round(height/scale)})
                settle_sidebar(page)
                expect(page.locator('.hHd-Xa_fading')).to_have_count(0)
                if page.locator('.hHd-Xa_collapsed').count():
                    page.locator('.hHd-Xa_toggle').click()
                    settle_sidebar(page)
                expect(page.locator('.hHd-Xa_collapsed')).to_have_count(0)
                for title in ['拓客内容','功能组件','知识库','微信连接']:
                    page.get_by_role('button',name=title,exact=True).click(trial=True)
                page.locator('.qx-balance').scroll_into_view_if_needed()
                layout=page.locator('.hHd-Xa_footerActions').evaluate('''el=>{
                    const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}};
                    return {footer:box(el),balance:box(el.querySelector('.qx-balance')),lastBusiness:box(document.querySelector('button[aria-label="新建律师账号运营对话"]')),viewport:{width:innerWidth,height:innerHeight},
                      actions:[...el.querySelectorAll('button[aria-label]')].filter(e=>['拓客内容','功能组件','知识库','微信连接'].includes(e.ariaLabel)).map(e=>({name:e.ariaLabel,...box(e)}))};
                }''')
                report['layoutMatrix'].append({'physicalSize':[width,height],'scale':scale,**layout})
                page.screenshot(path=str(folder/f'layout-{width}-{height}-{scale}.png'))
                assert layout['balance']['bottom']<=layout['viewport']['height']+2,layout
                assert layout['footer']['y']>=layout['lastBusiness']['bottom'],layout
                assert layout['balance']['width']>=layout['footer']['width']-4,layout
                assert len({round(a['y']) for a in layout['actions']})==2,layout
                page.get_by_role('button',name='新建律师账号运营对话',exact=True).click(trial=True)
        report['scalingMethod']='Equivalent CSS viewport sizes; Windows system DPI itself was not changed.'
        page.set_viewport_size({'width':1440,'height':1000})
        settle_sidebar(page)
        for status,balances,expected_text in [('ok',[{'currency':'CNY','total_balance':'0.00'}],'0.00 CNY'),('error',[],'更新失败，显示上次余额'),('unavailable',[],'暂未配置 DeepSeek 账户')]:
            balance_reply.update(status=status,balances=balances)
            page.get_by_role('button',name='刷新 DeepSeek 余额',exact=True).click()
            expect(page.locator('.qx-balance')).to_have_attribute('data-qx-balance',status)
            expect(page.locator('.qx-balance')).to_contain_text(expected_text)
        page.locator('.hHd-Xa_toggle').click();settle_sidebar(page)
        expect(page.locator('.hHd-Xa_collapsed')).to_have_count(1)
        for title in ['拓客内容','功能组件','知识库','微信连接']:
            page.get_by_role('button',name=title,exact=True).click(trial=True)
        page.get_by_role('button',name='刷新 DeepSeek 余额',exact=True).click(trial=True)
        page.screenshot(path=str(folder/'after-collapsed.png'))
        page.locator('.hHd-Xa_toggle').click();settle_sidebar(page)
        report['balanceStatesAndCollapsedActions']=True
        page.screenshot(path=str(folder/'after-reception.png'))
        for title in ['客户接待','合同审查','办案整理','模拟法庭','律师账号运营']:
            expect(page.get_by_role('button',name='新建'+title+'对话',exact=True)).to_be_visible()
        page.get_by_role('button',name='新建合同审查对话',exact=True).click()
        page.get_by_role('button',name='合同对比',exact=True).click(timeout=60000)
        compare_calls=[]
        page.on('request',lambda req:compare_calls.append(req.url) if req.url.endswith('/api/qx-compare/compare') else None)
        report['fiveEntriesAndNoGeneralDock']=True
        expect(page.get_by_label('原版本',exact=True)).to_be_enabled(timeout=15000)
        select_file('原版本','原合同.txt')
        select_file('新版本','新合同.txt')
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_role('heading',name='原稿',exact=True)).to_be_visible()
        expect(page.get_by_role('heading',name='修改稿',exact=True)).to_be_visible()
        expect(page.locator('.qx-compare-results')).to_contain_text('第一条 保密。')
        expect(page.get_by_role('region',name='AI法律影响分析',exact=True)).to_have_count(0)
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('.qx-compare input')).to_have_count(0)
        assert page.get_by_role('button',name='AI分析修改影响',exact=True).evaluate('(el)=>{const button=el.getBoundingClientRect(),body=el.closest(".qx-compare-body").getBoundingClientRect();return button.top>=body.top&&button.bottom<=body.bottom}')
        page.screenshot(path=str(folder/'side-by-side-inline.png'))
        page.get_by_role('button',name='返回原对话',exact=True).click()
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible()
        assert len(compare_calls)==1
        report['automaticComparisonInlineAndExplicitReturn']=True
        page.evaluate("""() => {const original=window.fetch;window.fetch=(url,...args)=>String(url).endsWith('/qx-compare/compare')?new Promise(resolve=>{window.releaseCompare=()=>resolve(original(url,...args));}):original(url,...args);window.restoreCompare=()=>window.fetch=original;}""")
        page.get_by_role('button',name='重新对比',exact=True).click()
        expect(page.get_by_role('button',name='回看原版本 第2行',exact=True)).to_have_count(0)
        page.evaluate('() => {window.releaseCompare();window.restoreCompare();}')
        expect(page.get_by_role('button',name='重新对比',exact=True)).to_be_enabled()
        report['pendingComparisonCannotUseOldLocation']=True
        for width in (1440,768,390):
            page.set_viewport_size({'width':width,'height':1000});expect(page.locator('.qx-compare-body')).to_be_visible();page.screenshot(path=str(folder/f'comparison-{width}.png'))
            assert page.locator('.qx-compare').evaluate('(el)=>el.scrollWidth <= el.clientWidth+2')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('button',name='回看原版本 第2行',exact=True).click()
        expect(page.get_by_role('region',name='已核验原文位置')).to_contain_text('100元')
        expect(page.locator('[data-textpreview-path]:visible')).to_contain_text('原合同.txt',timeout=15000)
        page.screenshot(path=str(folder/'desktop.png'));report['textComparisonAndOriginalNavigation']=True
        # The file action reuses the current path; no second uploader or workbench.
        before_preview=len(compare_calls)
        page.get_by_role('button',name='对比版本',exact=True).click()
        expect(page.locator('.qx-compare-preview.qx-compare-open')).to_contain_text('原合同.txt')
        expect(page.locator('.qx-compare-preview.qx-compare-open')).to_contain_text('已发现 1 处文字变化')
        assert len(compare_calls)==before_preview
        page.screenshot(path=str(folder/'after-file-preview.png'))
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible()
        assert len(compare_calls)==before_preview
        before_return=len(compare_calls)
        page.get_by_role('button',name='合同对比',exact=True).click()
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible()
        assert len(compare_calls)==before_return
        report['previewReusesFileAndReturnDoesNotCompare']=True
        composer=page.locator('[data-composer-input][contenteditable=true]').first
        composer.fill('待发送草稿：请保留这一段。')
        page.locator('input[type=file]').set_input_files({'name':'待发送附件.txt','mimeType':'text/plain','buffer':b'Synthetic unsent attachment'})
        attachment=page.locator('.gSkjMW_card').filter(has_text='待发送附件.txt')
        expect(attachment).to_be_visible()
        expect(attachment.locator('.gSkjMW_spinner')).to_have_count(0,timeout=15000)
        page.get_by_role('button',name='AI分析修改影响',exact=True).click()
        expect(page.locator('.qx-compare-results')).to_be_visible()
        expect(page.get_by_role('alert').filter(has_text='草稿和附件')).to_be_visible()
        expect(composer).to_have_text('待发送草稿：请保留这一段。')
        page.get_by_role('button',name='合同对比',exact=True).click()
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(composer).to_have_text('待发送草稿：请保留这一段。')
        assert len(compare_calls)==before_return
        report['existingDraftPreserved']=True
        page.get_by_role('button',name='客户接待历史对话',exact=True).click()
        page.locator('.qx-business-history button').first.click()
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_count(0)
        page.get_by_role('button',name='合同审查历史对话',exact=True).click()
        page.locator('.qx-business-history button').first.click()
        expect(composer).to_have_text('待发送草稿：请保留这一段。')
        expect(attachment).to_be_visible()
        expect(page.get_by_text('已发现 1 处文字变化',exact=True)).to_be_visible()
        assert len(compare_calls)==before_return
        settle_sidebar(page)
        page.screenshot(path=str(folder/'after-draft-attachment-return.png'))
        split_layout=page.locator('.qx-business-dock').evaluate('''el=>{
          const rows=[];for(let p=el;p&&rows.length<15;p=p.parentElement){const r=p.getBoundingClientRect(),s=getComputedStyle(p);rows.push({tag:p.tagName,class:p.className,width:r.width,right:r.right,client:p.clientWidth,scroll:p.scrollWidth,display:s.display,minWidth:s.minWidth,overflow:s.overflow})}return rows;
        }''')
        (folder/'split-layout.json').write_text(json.dumps(split_layout,ensure_ascii=False,indent=2),encoding='utf-8')
        preview_box=page.locator('[data-document-preview]:visible').bounding_box()
        dock_box=page.locator('.qx-business-dock').bounding_box()
        assert dock_box['x']+dock_box['width']<=preview_box['x']+2,split_layout
        assert page.get_by_role('button',name='对比版本',exact=True).bounding_box()['height']<=44
        report['sessionReturnPreservesDraftAttachmentAndResult']=True
        attachment.locator('.gSkjMW_remove').click()
        composer.press('ControlOrMeta+A');composer.press('Backspace')
        expect(composer).to_have_text('')
        # A draft entered while version checks are pending must not be overwritten.
        page.evaluate("""() => {const original=window.fetch;window.fetch=(url,...args)=>String(url).endsWith('/qx-compare/analysis-draft')?new Promise(resolve=>{window.releaseAnalysis=()=>resolve(original(url,...args));}):original(url,...args);window.restoreAnalysis=()=>window.fetch=original;}""")
        page.get_by_role('button',name='AI分析修改影响',exact=True).click()
        expect(page.get_by_role('button',name='正在核对版本…',exact=True)).to_be_disabled()
        composer.fill('核验期间输入的新草稿')
        page.evaluate('() => {window.releaseAnalysis();window.restoreAnalysis();}')
        expect(page.get_by_role('alert').filter(has_text='草稿和附件')).to_be_visible()
        expect(composer).to_have_text('核验期间输入的新草稿')
        composer.press('ControlOrMeta+A');composer.press('Backspace')
        # Verify the one-click UI and real preparation API without invoking a model.
        # The original composer submission bridge is separately exercised with fake inputActions in Node.
        page.evaluate("""() => {window.realAnalysis=window.qxAnalyzeComparison;window.analysisSent=[];window.qxAnalyzeComparison=async(id,prepare)=>{const text=await prepare('甲方（买方）');window.analysisSent.push({id,text});};}""")
        original_session=page.evaluate('document.documentElement.dataset.qxSessionId')
        page.get_by_role('button',name='AI分析修改影响',exact=True).click()
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_attribute('aria-expanded','false')
        sent=page.evaluate('window.analysisSent')
        assert len(sent)==1 and sent[0]['id']==original_session and '甲方（买方）' in sent[0]['text'] and '文字差异事实与法律判断分开' in sent[0]['text']
        expect(composer).to_have_text('')
        page.evaluate('() => {window.qxAnalyzeComparison=window.realAnalysis;}')
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.locator('.qx-compare-results')).to_be_visible()
        report['singleAIActionOriginalConversationWithMockedSubmission']=True
        report['analysisRechecksLiveComposerBeforeSending']=True
        select_file('原版本','已解析：上传合同.txt · abcdef');expect(page.locator('.qx-compare-results article')).to_have_count(1);report['indexedUploadSelectable']=True
        for suffix in ['.docx','.pdf']:
            select_file('原版本','原合同'+suffix);select_file('新版本','新合同'+suffix)
            expect(page.locator('.qx-compare-results article')).to_have_count(1)
            if suffix=='.pdf':
                page.get_by_role('button',name='回看原版本 第2页 · 提取段2',exact=True).click()
                expect(page.locator('[data-document-preview]:visible [data-pdf-page="2"] canvas')).to_be_visible(timeout=30000)
                page.wait_for_timeout(600)
                assert page.locator('[data-document-preview]:visible [data-pdf-page="2"]').evaluate('(el)=>{const r=el.getBoundingClientRect();return r.top>=0&&r.top<innerHeight}')
                page.screenshot(path=str(folder/'pdf-page-2.png'));report['pdfOriginalPage2']=True
            else:report['docxOriginalParserComparison']=True
        select_file('原版本','采购原稿.txt')
        expect(page.get_by_label('新版本',exact=True)).to_be_visible()
        select_file('新版本','采购修改稿.txt')
        page.get_by_role('button',name='收起文件选择',exact=True).click()
        report['changingBothFilesNeedsOnePickerExpansion']=True
        expect(page.locator('.qx-compare-results article')).to_have_count(5)
        expect(page.get_by_role('button',name='新增 1',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='删除 1',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='修改 3',exact=True)).to_be_visible()
        for label,count,excerpt in [('金额 1',1,'20,000元'),('日期／期限 2',2,'15日'),('违约责任文字 1',1,'每日2%')]:
            page.get_by_role('button',name=label,exact=True).click()
            expect(page.locator('.qx-compare-results article')).to_have_count(count)
            expect(page.locator('.qx-compare-results')).to_contain_text(excerpt)
        page.get_by_role('button',name='全部 5',exact=True).click()
        expect(page.locator('.qx-compare-results')).to_contain_text('质保期为12个月。')
        page.get_by_role('button',name='下一处',exact=True).click()
        expect(page.locator('.qx-compare-current')).to_have_attribute('data-change-index','1')
        page.get_by_role('button',name='上一处',exact=True).click()
        expect(page.locator('.qx-compare-current')).to_have_attribute('data-change-index','0')
        assert page.locator('.qx-compare-results .qx-compare-versions').evaluate_all('''rows=>rows.every(row=>{const [a,b]=row.querySelectorAll('.qx-compare-cell');const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();return Math.abs(x.y-y.y)<1&&Math.abs(x.height-y.height)<1})''')
        page.screenshot(path=str(folder/'purchase-side-by-side.png'))
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('.qx-compare input')).to_have_count(0)
        expect(page.get_by_role('button',name='AI分析修改影响',exact=True)).to_be_visible()
        page.screenshot(path=str(folder/'text-and-ai-entry.png'))
        report['fiveChangesFiltersAlignedRowsAndInlineAIEntry']=True
        select_file('原版本','原合同.txt');select_file('新版本','新合同.txt');expect(page.locator('.qx-compare-results article')).to_have_count(1)
        (workspace/'原合同.txt').write_text('第一条 外部修改。',encoding='utf-8')
        page.get_by_role('button',name='回看原版本 第2行',exact=True).click()
        expect(page.get_by_role('alert').filter(has_text='原文件已变化')).to_be_visible()
        report['staleCitationRejected']=True
        page.get_by_role('button',name='AI分析修改影响',exact=True).click()
        expect(page.get_by_role('alert').filter(has_text='原文件已变化')).to_be_visible()
        report['staleAnalysisDraftRejected']=True
        report['widths']=[1440,768,390]
        assert all(hashlib.sha256((workspace/name).read_bytes()).hexdigest()==value for name,value in originals.items() if name!='原合同.txt')
        report['otherFiveOriginalsUnchanged']=True
        assert hashlib.sha256(uploaded.read_bytes()).hexdigest()==uploaded_hash;report['uploadedOriginalUnchanged']=True
        # Real case/material links and real binding APIs: both cases share this synthetic workspace.
        from business_store import CaseStore
        cases=CaseStore(material)
        case_a=cases.create('虚构验收甲案');case_b=cases.create('虚构验收乙案')
        cases.link_materials(case_a['id'],['原合同.pdf','新合同.pdf'])
        cases.link_materials(case_b['id'],['原合同.docx','新合同.docx'])
        session_id=page.evaluate('document.documentElement.dataset.qxSessionId')
        origin=runtime['url'].split('/?')[0]
        def layered(action,data=None):
            headers={'x-qx-layered':'1'}
            response=page.request.post(origin+'/api/qx-layered/'+action,data=data,headers=headers) if data is not None else page.request.get(origin+'/api/qx-layered/'+action,headers=headers)
            assert response.ok,response.text()
            return response.json()
        for case in [case_a,case_b]:layered('project',{'id':case['id'],'title':case['title']})
        def bind(case):
            old=layered('state?sessionId='+session_id)['binding']
            layered('bind',{'session':session_id,'project':case['id'],'expectedProject':old['project'],'revision':old['revision']})
        bind(case_a)
        page.evaluate("window.dispatchEvent(new Event('qx-knowledge-binding-changed'))")
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_attribute('aria-expanded','false')
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_label('原版本',exact=True)).to_be_enabled()
        expect(page.get_by_label('原版本',exact=True).locator('option').filter(has_text='原合同.docx')).to_have_count(0)
        select_file('原版本','原合同.pdf');select_file('新版本','新合同.pdf')
        expect(page.locator('.qx-compare-results article')).to_have_count(1)
        # A link change has no focus or binding event. Recovery must refresh scope, without retrying.
        cases.link_materials(case_a['id'],[str(uploaded)])
        before_scope_change=len(compare_calls)
        page.get_by_role('button',name='重新对比',exact=True).click()
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_attribute('aria-expanded','false')
        expect(page.get_by_role('region',name='合同审查业务引导')).to_contain_text('材料归属已更新')
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_label('原版本',exact=True)).to_be_enabled()
        expect(page.get_by_label('原版本',exact=True).locator('option').filter(has_text='上传合同.txt')).to_have_count(1)
        expect(page.locator('.qx-compare-results article')).to_have_count(0)
        assert len(compare_calls)==before_scope_change+1
        report['materialScopeRecoveryWithoutAutomaticRetry']=True
        select_file('原版本','原合同.pdf');select_file('新版本','新合同.pdf')
        page.evaluate("""() => {const original=window.fetch;window.fetch=(url,...args)=>String(url).endsWith('/qx-compare/compare')?new Promise(resolve=>{window.releaseCompare=()=>resolve(original(url,...args));}):original(url,...args);window.restoreCompare=()=>window.fetch=original;}""")
        page.get_by_role('button',name='重新对比',exact=True).click()
        bind(case_b)
        page.evaluate('() => {window.releaseCompare();window.restoreCompare();}')
        expect(page.get_by_role('button',name='合同对比',exact=True)).to_have_attribute('aria-expanded','false')
        page.get_by_role('button',name='合同对比',exact=True).click()
        expect(page.get_by_label('原版本',exact=True)).to_be_enabled()
        expect(page.get_by_label('原版本',exact=True).locator('option').filter(has_text='原合同.pdf')).to_have_count(0)
        expect(page.locator('.qx-compare-results article')).to_have_count(0)
        select_file('原版本','原合同.docx');select_file('新版本','新合同.docx')
        expect(page.locator('.qx-compare-results article')).to_have_count(1)
        report['crossCaseAndMidRequestScopeIsolation']=True
        page.screenshot(path=str(folder/'after-case-b.png'))
        report['compareRequests']=len(compare_calls)
        for _ in range(8):
            for mode in ['客户接待','合同审查']:
                page.get_by_role('button',name='新建'+mode+'对话',exact=True).click()
                expect(page.get_by_role('region',name=mode+'业务引导')).to_be_visible()
        page.set_viewport_size({'width':1280,'height':720});settle_sidebar(page)
        toggle=page.get_by_role('button',name='合同审查历史对话',exact=True)
        if toggle.get_attribute('aria-expanded')!='true':toggle.click()
        history=page.locator('.qx-business-history')
        assert history.locator('button').count()>=9
        assert history.evaluate('(el)=>el.scrollHeight>el.clientHeight')
        history.locator('button').last.click(trial=True)
        page.get_by_role('button',name='新建律师账号运营对话',exact=True).click(trial=True)
        page.get_by_role('button',name='刷新 DeepSeek 余额',exact=True).click(trial=True)
        page.screenshot(path=str(folder/'after-long-history.png'))
        report['longHistoryScrollAndFooterReachable']=True
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
