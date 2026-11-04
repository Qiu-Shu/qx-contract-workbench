"""Check the shipped Skill UI with real React in an isolated, offline Chrome.

Run with a Playwright-enabled Python; optional --bundle selects a client.js.
The fixture uses the actual Skill plugin, TextShimmer, ReferenceChip, ranking
functions and CSS from the installed Harness frontend. Only host services and
decorative icons are fixtures. No live sessions, model requests or accounts.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.local/skill-audit-20261104' / ('labels-ui-' + time.strftime('%Y%m%d-%H%M%S'))
REPORT = {'status': 'running', 'checks': [], 'page_errors': [], 'console_errors': [], 'blocked_requests': []}


def installed_package(name):
    node = shutil.which('node') or 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    script = "import fs from 'node:fs'; import {createRequire} from 'node:module'; const req=createRequire(fs.realpathSync('node_modules/@deepseek-ai/dsh/package.json')); console.log(req.resolve(process.argv[1]+'/package.json'));"
    result = subprocess.run([node, '--input-type=module', '-e', script, name], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    return Path(result.stdout.strip()).parent


def native_primitives(frontend):
    """Select exact shipped implementations; fail clearly if upstream layout changes."""
    text = frontend.read_text(encoding='utf-8')
    for key, name in [('rankByName', 'SA'), ('ReferenceChip', 'QR'), ('TextShimmer', '_2')]:
        if f'{key}:{name}' not in text:
            raise RuntimeError(f'Frontend changed: locate the native {key} implementation before adapting this fixture.')

    def section(start, end):
        begin = text.index(start)
        return text[begin:text.index(end, begin)]

    def css_map(name):
        match = re.search(r'\b' + re.escape(name) + r'=\{([^}]+)\}', text)
        result = {}
        for field in match.group(1).split(','):
            key, variable = field.split(':', 1)
            value = re.search(r'\b' + re.escape(variable) + r'="([^"]+)"', text)
            if value is None:
                raise RuntimeError(f'Unable to resolve native CSS class {name}.{key}')
            result[key] = value.group(1)
        return f'const {name}={json.dumps(result)};'

    return '\n'.join([
        'const k=React,p=window.__jsx,fe=(...items)=>items.filter(Boolean).join(" ");',
        css_map('ii'), css_map('S1'), css_map('It'),
        section('function rp(', 'function IA('),
        section('const I1=k.createContext', ',jD=') + ';',
        section('function QR(', 'const eA='),
        'window.__nativePrimitives={rankByName:SA,ReferenceChip:QR,TextShimmer:_2};',
    ])


HARNESS = r"""
window.__jsx={Fragment:React.Fragment,jsx:(type,props,key)=>React.createElement(type,key===undefined?props:{...props,key}),jsxs:(type,props,key)=>{const {children,...rest}=props;return React.createElement(type,key===undefined?rest:{...rest,key},...(Array.isArray(children)?children:[children]));}};
window.__fixture={slots:{},dictionaries:{},opened:[],inspected:0,checks:[]};
window.__ModuleLoader__={load({id,factory}){
  const f=window.__fixture;
  f.moduleId=id;
  const Icon=()=>React.createElement('span',{'aria-hidden':true},'◇');
  const primitives={...window.__nativePrimitives,IconSkillOutlineRegular:Icon,IconChevronDownOutlineRegular:Icon,IconInspectOutlineRegular:Icon};
  const plugin=factory(name=>{
    if(name==='react')return React;
    if(name==='react/jsx-runtime')return window.__jsx;
    if(name==='@deepseek-ai/dsh-client-ui-primitives')return primitives;
    throw Error('Unexpected module '+name);
  });
  const catalog=Object.keys(window.__labels).map(name=>({name,description:'合成技能说明',modelInvocable:true,path:'.dsh/skills/'+name+'/SKILL.md'}));
  catalog.push({name:'external-unknown-skill',description:'外部技能说明',modelInvocable:true,path:'.dsh/skills/external-unknown-skill/SKILL.md'});
  const sessions={binding:()=>({}),scope:()=>({}),subagentAddress:()=>undefined,list:{getSnapshot:()=>({byId:{fixture:{cwd:'D:/fixture'}}})},using:async(id,options,run)=>run({binding:{session:{getSnapshot:()=>({openState:'open'})}}})};
  const ctx={
    effect:fn=>fn(),
    locale:{register:(ns,dictionaries)=>{f.dictionaries=dictionaries;return()=>{};},bind:()=>key=>f.dictionaries.zh[key]},
    uiConversation:{userText:{register:rule=>{f.rule=rule;}}},
    slots:{inject:(name,run)=>run(),register:(options,component)=>{f.slots[options.name]={options,component};}},
    sessions,remote:{skills:{list:async()=>({ok:true,value:{skills:catalog}})},$on:()=>{}},
    sidebarRight:{openResource:address=>f.opened.push(address)},on:()=>{},
    get:name=>{if(name!=='inputTriggers')throw Error('Unexpected service '+name);return{registerSource:source=>{f.source=source;return()=>{};}};}
  };
  plugin.apply(ctx);
}};
window.__root=ReactDOM.createRoot(document.getElementById('root'));
window.__render=async children=>{ReactDOM.flushSync(()=>window.__root.render(children));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));};
window.__block=(name,state)=>state==='running'?{callId:'synthetic-'+name,argsRaw:JSON.stringify({name})}:{kind:'tool_result',callId:'synthetic-'+name,call:{argsRaw:JSON.stringify({name})},isError:state==='error',error:state==='stopped'?{name:'Interrupted',code:'interrupted'}:undefined,content:[{type:'text',text:state==='error'?'合成错误第一行\n合成错误详细说明':'合成说明正文'}]};
window.__runChecks=async()=>{
  const f=window.__fixture,check=(condition,message)=>{if(!condition)throw Error(message);};
  const entries=Object.entries(window.__labels),Row=f.slots['tool.call.toolview'].component,Ref=f.slots['conversation.user.text.node'].component,t=key=>f.dictionaries.zh[key];
  check(f.moduleId==='@deepseek-ai/dsh-client-ui-skill','Wrong module registration');
  const states=['running','ok','error','stopped'];
  const blocks=[];
  const nodes=entries.flatMap(([name,label])=>states.map(state=>{const block=window.__block(name,state);blocks.push(block);return React.createElement(Row,{key:name+state,phase:'started',block,t,inspect:()=>f.inspected++});}));
  const before=JSON.stringify(blocks);
  await window.__render(React.createElement('div',{},nodes));
  const rows=[...document.querySelectorAll('[data-tool="skill"]')];
  check(rows.length===entries.length*4,'Missing rows');
  for(let i=0;i<entries.length;i++)for(let j=0;j<4;j++){
    const [name,label]=entries[i],row=rows[i*4+j];
    check(row.dataset.state===states[j],'Incorrect state for '+name);
    check(row.dataset.skillId===name,'Protocol ID changed for '+name);
    const summary=row.querySelector('.iWrAna_summary').textContent;
    check(summary.includes(label),'Chinese label missing: '+name+' '+states[j]);
    check(!summary.includes(name),'Raw ID leaked into visible summary: '+name);
    if(states[j]==='error')check(summary.includes('合成错误第一行'),'Error summary lost');
    if(states[j]==='stopped')check(summary.includes(t('row.stopped')),'Stopped status lost');
  }
  check(before===JSON.stringify(blocks),'Tool blocks mutated');
  f.checks.push('All 185 skills render Chinese names in running/ok/error/stopped; original IDs and blocks retained');
  const opened=[];
  await window.__render(React.createElement('div',{},entries.map(([name])=>React.createElement(Ref,{key:name,node:{data:{name}},raw:'/'+name,interactive:true,openSkill:id=>opened.push(id)}))));
  const chips=[...document.querySelectorAll('[data-ref-chip="skill"]')];
  check(chips.length===entries.length,'Missing reference chips');
  chips.forEach((chip,i)=>{const [name,label]=entries[i];check(chip.textContent==='/'+label,'Reference label incorrect');check(chip.title==='/'+name,'Raw title lost');chip.click();});
  check(JSON.stringify(opened)===JSON.stringify(entries.map(([name])=>name)),'openSkill received translated IDs');
  f.checks.push('All 185 native reference chips display Chinese and call openSkill with the original ID');
  await window.__render(React.createElement(Ref,{node:{data:{name:'qx-contract-review'}},raw:'/qx-contract-review',interactive:false,openSkill:()=>{throw Error('Preview unexpectedly interactive');}}));
  check(document.querySelector('button')===null,'Preview chip should not activate');
  const signal=new AbortController().signal,session={sessionId:'fixture'};
  const candidates=await f.source.candidates(session,{query:'',signal});
  for(const [name,label] of entries){const candidate=candidates.find(item=>item.name===name);check(candidate?.label===label,'Candidate label mismatch: '+name);check(f.source.onPick({candidate}).text==='/'+name+' ','onPick changed protocol ID');}
  for(const name of ['qx-contract-review','legal-zh-privacy-dsar-response','legal-zh-ip-fto-triage','legal-zh-employment-international-expansion','humanizer'])for(const query of [name,window.__labels[name]]){
    const found=await f.source.candidates(session,{query,signal});check(found.some(item=>item.name===name),'Search failed: '+query);
  }
  const unknown=candidates.find(item=>item.name==='external-unknown-skill');check(unknown.label===unknown.name,'Unknown candidate does not fall back');
  check(f.source.lexicon(session).includes('qx-contract-review'),'Protocol lexicon lost');
  const match=f.rule.match('请使用 /qx-contract-review 处理',0,{read:()=>f.source.lexicon(session)});check(match?.data.name==='qx-contract-review','Slash parser changed');
  const inject=f.slots['conversation.user.text.node'].options.inject('fixture');inject.openSkill('qx-contract-review');
  check(f.opened.some(address=>address.endsWith('/.dsh/skills/qx-contract-review/SKILL.md')),'Preview address changed');
  f.checks.push('Candidate labels, Chinese and English search, slash pick, lexicon/parser and preview navigation preserve IDs');
  for(const name of ['external-unknown-skill','__proto__']){
    await window.__render(React.createElement('div',{},React.createElement(Row,{phase:'started',block:window.__block(name,'ok'),t}),React.createElement(Ref,{node:{data:{name}},raw:'/'+name,interactive:false})));
    check(document.querySelector('.iWrAna_summary').textContent===name,'Unknown tool name not retained: '+name);
    check(document.querySelector('[data-ref-chip]').textContent==='/'+name,'Unknown reference name not retained: '+name);
  }
  f.checks.push('Unknown external names, including inherited-object-key names, safely fall back to the original name');
  return f.checks;
};
window.__showSamples=async()=>{
  const f=window.__fixture,Row=f.slots['tool.call.toolview'].component,Ref=f.slots['conversation.user.text.node'].component,t=key=>f.dictionaries.zh[key];
  const names=['legal-zh-criminal-compliance-non-prosecution','humanizer','legal-zh-clinic-plain-language-letters','legal-zh-commercial-review-proposals'];
  await window.__render(React.createElement('main',{},React.createElement('h1',{},'技能调用中文显示'),React.createElement('p',{},'使用合成材料检查状态、展开说明与中文标签'),...['running','ok','error','stopped'].map((state,index)=>React.createElement('section',{className:'sample',key:state},React.createElement('h2',{},state),React.createElement(Row,{phase:'started',block:window.__block(names[index],state),t,inspect:()=>f.inspected++}))),React.createElement('section',{className:'chips'},...names.map(name=>React.createElement(Ref,{key:name,node:{data:{name}},raw:'/'+name,interactive:true,openSkill:id=>f.opened.push(id)})))));
};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', help='Actual ui-skill/lib/client.js to verify; defaults to installed localized bundle')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    labels = json.loads((ROOT / 'config/skill-labels.zh-CN.json').read_text(encoding='utf-8'))['labels']
    actual = {path.parent.name for path in (ROOT / 'workspace/.dsh/skills').glob('*/SKILL.md')}
    assert set(labels) == actual, {'missing': sorted(actual - labels.keys()), 'extra': sorted(labels.keys() - actual)}
    assert len(labels) == 185 and len(set(labels.values())) == 185
    assert all(isinstance(value, str) and value == value.strip() and re.search('[\u4e00-\u9fff]', value) for value in labels.values())
    REPORT['checks'].append('185 distinct Chinese labels cover the exact project Skill catalog')
    bundle = Path(args.bundle).resolve() if args.bundle else installed_package('@deepseek-ai/dsh-client-ui-skill') / 'lib/client.js'
    client = bundle.read_bytes()
    frontend = next((installed_package('@deepseek-ai/dsh-web-frontend') / 'dist/assets').glob('index-*.js'))
    REPORT.update(bundle=str(bundle), bundle_sha256=hashlib.sha256(client).hexdigest(), frontend=str(frontend), frontend_sha256=hashlib.sha256(frontend.read_bytes()).hexdigest())
    vendor = ROOT / '.local/knowledge-ui-check/vendor'
    primitives = native_primitives(frontend)
    css = b'\n'.join(path.read_bytes() for path in sorted(frontend.parent.glob('*.css')))
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Skill label verification</title>
<link rel="stylesheet" href="/native.css"><style>
:root{--dsw-alias-label-tertiary:#626975;--dsw-alias-label-secondary:#344054;--dsw-alias-label-primary:#182230;--dsw-alias-label-caption:#86909c;--dsw-alias-state-error-primary:#b42318;--dsw-alias-state-warn-label:#9a6700;--dsw-alias-border-l1:#dde1e8;--dsw-alias-border-l2:#e4e7ec;--dsw-alias-markdown-code-block:#f6f7f9;--dsw-alias-markdown-code-block-banner:#edf0f4;--dsw-radius-lg:10px;--dsw-font-markdown-code-block-small:13px/1.5 monospace}
html,body{margin:0;min-height:100%;height:auto;overflow:auto;background:#fafafa;color:#182230;font-family:system-ui,"Microsoft YaHei",sans-serif}#root{padding:24px;max-width:760px;margin:auto;box-sizing:border-box}h1{font-size:22px;margin:0 0 10px}p{font-size:13px;color:#667085}h2{font-size:12px;margin:0 0 8px;color:#667085}.sample{padding:16px 0;border-top:1px solid #e4e7ec}.chips{line-height:2.2}.chips [data-ref-chip]{margin-right:8px}main{min-width:0}
</style><div id="root"></div><script src="/react.js"></script><script src="/react-dom.js"></script><script src="/fixture.js"></script><script src="/primitives.js"></script><script src="/client.js"></script></html>'''
    assets = {
        '/': ('text/html', html.encode()), '/native.css': ('text/css', css),
        '/react.js': ('text/javascript', (vendor / 'react-18.3.1.development.js').read_bytes()),
        '/react-dom.js': ('text/javascript', (vendor / 'react-dom-18.3.1.development.js').read_bytes()),
        '/fixture.js': ('text/javascript', ('window.__labels=' + json.dumps(labels, ensure_ascii=False) + ';\n' + HARNESS).encode()),
        '/primitives.js': ('text/javascript', primitives.encode()), '/client.js': ('text/javascript', client),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            content_type, body = assets.get(self.path, ('text/plain', b'Not found'))
            self.send_response(200 if self.path in assets else 404)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'

    def route_request(route):
        if route.request.url == origin + '/favicon.ico':
            route.fulfill(status=204)
        elif route.request.url.startswith(origin + '/') and route.request.url[len(origin):] in assets:
            route.continue_()
        else:
            REPORT['blocked_requests'].append(route.request.url)
            route.abort()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            context = browser.new_context(viewport={'width': 1200, 'height': 900}, service_workers='block')
            context.route('**/*', route_request)
            page = context.new_page()
            page.on('pageerror', lambda error: REPORT['page_errors'].append(str(error)))
            page.on('console', lambda message: REPORT['console_errors'].append(message.text) if message.type == 'error' else None)
            page.goto(origin, wait_until='networkidle')
            REPORT['checks'].extend(page.evaluate('window.__runChecks()'))
            page.evaluate('window.__showSamples()')
            page.locator('[data-state="ok"] [role="button"]').click()
            assert page.locator('[data-state="ok"] pre').inner_text() == '合成说明正文'
            page.locator('[data-state="ok"] button').click()
            assert page.evaluate('window.__fixture.inspected') == 1
            REPORT['checks'].append('Native row expands instructions and keeps inspect action functional')
            page.screenshot(path=str(OUT / 'desktop.png'), full_page=True)
            for width in [390, 320]:
                page.set_viewport_size({'width': width, 'height': 900})
                measurements = page.evaluate('''() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,items:[...document.querySelectorAll('[data-tool="skill"],.chips [data-ref-chip]')].map(node=>({text:node.textContent,rect:{left:node.getBoundingClientRect().left,right:node.getBoundingClientRect().right},width:node.clientWidth,scroll:node.scrollWidth}))})''')
                assert measurements['document'] <= width, measurements
                assert all(item['rect']['left'] >= 0 and item['rect']['right'] <= width + 1 for item in measurements['items']), measurements
                assert all(item['scroll'] <= item['width'] + 1 for item in measurements['items']), measurements
                REPORT.setdefault('layout', []).append(measurements)
                page.screenshot(path=str(OUT / f'narrow-{width}.png'), full_page=True)
            REPORT['checks'].append('Long Chinese Skill rows and native chips fit 390px and 320px viewports without horizontal overflow')
            assert not REPORT['page_errors'], REPORT['page_errors']
            assert not REPORT['console_errors'], REPORT['console_errors']
            assert not REPORT['blocked_requests'], REPORT['blocked_requests']
            REPORT['status'] = 'passed'
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        REPORT.update(status='failed', error=str(error))
        raise
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        REPORT['artifacts'] = str(OUT)
        (OUT / 'result.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': REPORT['status'], 'checks': len(REPORT['checks']), 'artifacts': str(OUT)}, ensure_ascii=False))
