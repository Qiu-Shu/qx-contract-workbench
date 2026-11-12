const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const mapping=/\t\tconst qxToolLabels = (\{[\s\S]*?\});/g;
const summary='const summary = [titleKey === "tool.title.generic" ? toolName : "", base].filter(Boolean).join(" · ");';
const localizedSummary='const summary = [titleKey === "tool.title.generic" && !qxToolLabel(toolName) ? toolName : "", base].filter(Boolean).join(" · ");';
function transform(source,labels){
  if(!labels||Array.isArray(labels)||typeof labels!=='object'||!Object.keys(labels).length||
    !Object.entries(labels).every(([id,label])=>/^[A-Za-z0-9_-]+$/.test(id)&&typeof label==='string'&&label.trim()&&/[\u3400-\u9fff]/u.test(label)))throw Error('Invalid Tool label catalog');
  const declaration='\t\tconst qxToolLabels = '+JSON.stringify(labels,null,2).replace(/\n/g,'\n\t\t')+';';
  const matches=[...source.matchAll(mapping)];
  function once(old,next){
    if(source.split(old).length!==2)throw Error('Source differs from the pinned Tool UI');
    source=source.replace(old,()=>next);
  }
  if(matches.length){
    if(matches.length!==1||!source.includes(localizedSummary)||!source.includes('title: qxToolLabel(toolName) ?? t(model.titleKey),'))throw Error('Source differs from the pinned Tool UI');
    return source.replace(mapping,()=>declaration);
  }
  const anchor='\t\tconst VARIANT_TITLE_KEYS = {';
  once(anchor,'\t\t// Display labels only; dispatch, persisted names and inspection keep the original IDs.\n'+declaration+'\n\t\tconst qxToolLabel = name => Object.hasOwn(qxToolLabels, name) ? qxToolLabels[name] : undefined;\n'+anchor);
  once(summary,localizedSummary);
  // Restrict the title change to the generic card; preserve native specialized tool views.
  const start=source.indexOf('function GenericToolCard('),end=source.indexOf('\n\t\t//#endregion',start);
  if(start<0||end<0)throw Error('Source differs from the pinned Tool UI');
  const card=source.slice(start,end),title='title: t(model.titleKey),';
  if(card.split(title).length!==2)throw Error('Source differs from the pinned Tool UI');
  source=source.slice(0,start)+card.replace(title,'title: qxToolLabel(toolName) ?? t(model.titleKey),')+source.slice(end);
  return source;
}
function stageToolLabels(root,payload,manifest){
  const relative='node_modules/@deepseek-ai/dsh-client-ui-tool/lib/client.js';
  const source=path.join(root,'config/tool-labels.zh-CN.json'),catalog=JSON.parse(fs.readFileSync(source,'utf8'));
  if(catalog.version!==1)throw Error('Invalid Tool label catalog');
  const file=path.join(payload,relative),updated=transform(fs.readFileSync(file,'utf8'),catalog.labels);
  fs.mkdirSync(path.join(payload,'config'),{recursive:true});
  fs.copyFileSync(source,path.join(payload,'config/tool-labels.zh-CN.json'));
  manifest.push({source:'config/tool-labels.zh-CN.json',target:'resources/workbench/config/tool-labels.zh-CN.json',sha256:crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex')});
  fs.writeFileSync(file,updated);
  return {target:'resources/workbench/'+relative,sha256:crypto.createHash('sha256').update(updated).digest('hex')};
}
if(require.main===module){
  if(!process.argv[2])throw Error('Usage: node scripts/tool-labels.cjs <pnpm-patch-directory>');
  const target=path.resolve(process.argv[2],'lib/client.js'),catalog=require('../config/tool-labels.zh-CN.json');
  fs.writeFileSync(target,transform(fs.readFileSync(target,'utf8'),catalog.labels));
  console.log(JSON.stringify({labels:Object.keys(catalog.labels).length,file:target}));
}
module.exports={transform,stageToolLabels};
