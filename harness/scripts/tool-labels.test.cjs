const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const sourcePath=path.join(process.env.QX_TEST_APP||root,'node_modules/@deepseek-ai/dsh-client-ui-tool/lib/client.js');
const upstream=fs.readFileSync(sourcePath,'utf8');
const transformFile=path.join(__dirname,'tool-labels.cjs');
const {transform,stageToolLabels}=require(transformFile);
const sample={'mcp__qx_materials__read_material':'读取材料正文','mcp__qx_legal__calculate_calendar_date':'计算日期'};
function load(source){
  let ui;
  const jsx=(type,props)=>({type,props});
  vm.runInNewContext(source.replace('exports.apply = apply;','exports.probe = {toolRowModel, GenericToolCard, label: typeof qxToolLabel === "undefined" ? () => undefined : qxToolLabel};\n\t\texports.apply = apply;'),{
    TextEncoder,TextDecoder,
    window:{__ModuleLoader__:{load({factory}){ui=factory(name=>name==='react'?{memo:f=>f,forwardRef:f=>f}:name==='react/jsx-runtime'?{jsx,jsxs:jsx}:{});}}},
  });
  return ui.probe;
}
function block(phase){
  const call={name:'mcp__qx_materials__read_material',argsRaw:'{"path":"合成合同.txt"}'};
  return phase==='preparing'?{phase,callId:'synthetic-call'}:phase==='running'?{...call,phase:'start',callId:'synthetic-call'}:
    {kind:'tool',callId:'synthetic-call',call,isError:phase==='error',...(phase==='stopped'?{isError:true,error:{code:'interrupted'}}:{}),content:[{type:'text',text:phase==='error'?'合成失败':'合成正文'}]};
}
test('specific Chinese tool names render for preparing, running, results, errors and interrupted history without changing calls',()=>{
  const ui=load(transform(upstream,sample));
  for(const phase of ['preparing','running','ok','error','stopped']){
    const input={...block(phase),args:{text:()=>undefined,complete:()=>false}},before=JSON.stringify({...block(phase),args:{text:()=>undefined,complete:()=>false}});
    const row=ui.GenericToolCard({toolName:'mcp__qx_materials__read_material',block:input,t:key=>key});
    assert.equal(row.props.title,'读取材料正文');
    assert.equal(row.props.toolName,'mcp__qx_materials__read_material');
    assert.ok(!row.props.summary.includes('mcp__'));
    assert.equal(row.props.state,phase);
    assert.equal(JSON.stringify(input),before);
    if(phase==='error')assert.equal(row.props.errorSummary,'合成失败');
  }
});
test('unknown tools retain exact original names, arguments and results',()=>{
  const original=load(upstream),translated=load(transform(upstream,sample));
  for(const name of ['mcp__other__read_material','new_external_tool','pwsh']){
    const input={...block('ok'),args:{text:()=>undefined,complete:()=>false}};
    const props=ui=>ui.GenericToolCard({toolName:name,block:input,t:key=>key}).props;
    assert.deepEqual(JSON.parse(JSON.stringify(props(translated))),JSON.parse(JSON.stringify(props(original))));
  }
});
test('a repeated preparation updates labels once and fails clearly if the pinned UI changed',()=>{
  const once=transform(upstream,sample);
  assert.equal(transform(once,sample),once);
  const updated=transform(once,{...sample,'mcp__qx_materials__read_material':'读取文档正文'});
  assert.equal(load(updated).GenericToolCard({toolName:'mcp__qx_materials__read_material',block:{...block('ok'),args:{text:()=>undefined,complete:()=>false}},t:key=>key}).props.title,'读取文档正文');
  assert.throws(()=>transform('changed upstream',sample),/pinned Tool UI/);
});
test('every bundled MCP tool has its own Chinese name and unknown names are not guessed',()=>{
  const labels=require('../config/tool-labels.zh-CN.json').labels;
  const ui=load(transform(upstream,labels));let count=0;
  for(const file of fs.readdirSync(path.join(root,'plugins/lazy-mcp/catalogs'))){
    const catalog=JSON.parse(fs.readFileSync(path.join(root,'plugins/lazy-mcp/catalogs',file)));
    for(const tool of catalog.tools){
      const name=`mcp__${catalog.serverName}__${tool.name}`;
      assert.ok(name.length<=64&&/^[A-Za-z0-9_-]+$/.test(name));
      assert.match(labels[name]||'',/[\u3400-\u9fff]/u,name);
      const row=ui.GenericToolCard({toolName:name,block:{...block('ok'),args:{text:()=>undefined}},t:key=>key});
      assert.equal(row.props.title,labels[name]);assert.equal(row.props.toolName,name);count++;
    }
  }
  for(const name of ['toString','constructor','__proto__','mcp__unknown__read_material'])assert.equal(ui.label(name),undefined);
  assert.ok(count>150);console.log('Bundled MCP tool labels verified: '+count);
});
test('packaging writes the same translated client and records both catalog and output hashes',t=>{
  const os=require('node:os'),crypto=require('node:crypto');
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-tool-labels-'));t.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
  const relative='node_modules/@deepseek-ai/dsh-client-ui-tool/lib/client.js',file=path.join(temp,relative),manifest=[];
  fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,upstream);
  const generated=stageToolLabels(root,temp,manifest),labels=require('../config/tool-labels.zh-CN.json').labels;
  assert.equal(fs.readFileSync(file,'utf8'),transform(upstream,labels));
  assert.equal(generated.target,'resources/workbench/'+relative);
  assert.equal(generated.sha256,crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'));
  assert.equal(manifest[0].source,'config/tool-labels.zh-CN.json');
  assert.equal(manifest[0].sha256,crypto.createHash('sha256').update(fs.readFileSync(path.join(temp,'config/tool-labels.zh-CN.json'))).digest('hex'));
  assert.throws(()=>transform(upstream,{tool:' ' }),/Invalid Tool label catalog/);
});
test('development patch, lockfile and installer use the same label catalog',()=>{
  const crypto=require('node:crypto'),relative='patches/@deepseek-ai__dsh-client-ui-tool@0.2.2-alpha.2.patch';
  const patch=fs.readFileSync(path.join(root,relative),'utf8'),hash=crypto.createHash('sha256').update(patch).digest('hex');
  const additions=patch.split('\n').filter(line=>line.startsWith('+')&&!line.startsWith('+++')).map(line=>line.slice(1)).join('\n');
  const embedded=additions.match(/const qxToolLabels = (\{[\s\S]*?\});/);
  assert.ok(embedded);assert.deepEqual(JSON.parse(embedded[1]),require('../config/tool-labels.zh-CN.json').labels);
  assert.ok(fs.readFileSync(path.join(root,'pnpm-workspace.yaml'),'utf8').includes(relative));
  const lock=fs.readFileSync(path.join(root,'pnpm-lock.yaml'),'utf8');
  assert.ok(lock.includes("'@deepseek-ai/dsh-client-ui-tool@0.2.2-alpha.2': "+hash));
  assert.ok(lock.includes("'@deepseek-ai/dsh-client-ui-tool@0.2.2-alpha.2(patch_hash="+hash+")"));
  assert.ok(lock.includes("'@deepseek-ai/dsh-client-ui-tool': 0.2.2-alpha.2(patch_hash="+hash+")"));
});
