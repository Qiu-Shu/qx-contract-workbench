// Read-only provenance checks; runtime behavior is tested by the existing preview suite.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const [rootArg,payloadArg,upstreamArg,outputArg]=process.argv.slice(2);
assert.ok([rootArg,payloadArg,upstreamArg,outputArg].every(x=>x&&path.isAbsolute(x)),'Supply absolute harness, payload, upstream evidence and new output paths');
const root=path.resolve(rootArg),payload=path.resolve(payloadArg);
assert.ok(!fs.existsSync(outputArg),'Keep prior evidence; use a new output path');
const upstream=JSON.parse(fs.readFileSync(upstreamArg,'utf8'));
const digest=data=>crypto.createHash('sha256').update(data).digest('hex');
const normalize=text=>text.replace(/\s+/g,' ').trim();
const read=relative=>fs.readFileSync(path.join(payload,relative),'utf8');
const diffRoot='node_modules/diff/';
const diffPackage=JSON.parse(read(diffRoot+'package.json'));
assert.equal(diffPackage.version,'9.0.0');
assert.equal(diffPackage.license,'BSD-3-Clause');
assert.equal(JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).dependencies.diff,'9.0.0');
assert.equal(normalize(read(diffRoot+'LICENSE')),normalize(upstream.jsdiff.license.content));
const previewRoot='node_modules/@deepseek-ai/dsh-client-ui-sidebar-documentpreview/';
const previewPackage=JSON.parse(read(previewRoot+'package.json'));
assert.equal(previewPackage.version,'0.2.2-alpha.2');
assert.equal(previewPackage.devDependencies['pdfjs-dist'],'6.3.289');
const client=read(previewRoot+'lib/client.pdf.js');
assert.ok(client.includes('apiVersion: "6.3.289"'));
assert.ok(client.includes('pdfjs-dist@6.3.289'));
const notice=client.slice(0,client.indexOf('window.__ModuleLoader__.load')).replace(/^\/\/ ?/gm,'');
assert.ok(normalize(notice).includes(normalize(upstream.pdf.license.content)),'Bundled PDF.js notice must include the complete pinned upstream license');
assert.ok(client.includes('"data-pdf-text": true'));
assert.ok(client.includes('"data-pdf-page": page'));
assert.ok(client.includes('getViewport({ scale: 96 / 72 })'));
const files=[diffRoot+'package.json',diffRoot+'LICENSE',previewRoot+'package.json',previewRoot+'lib/client.pdf.js'];
const report={passed:true,readOnly:true,checkedAt:new Date().toISOString(),payload,
  diff:{version:diffPackage.version,directDependency:true,licenseMatchesPinnedSource:true},
  pdf:{alreadyEmbedded:true,version:'6.3.289',containerVersion:previewPackage.version,
    fullLicenseIncluded:true,textLayerAndPageNodesPresent:true,latestObserved:upstream.pdf.latestObserved.tag,
    latestVersionNotInstalledOrExecutedByThisProbe:true},
  files:files.map(file=>{const bytes=fs.readFileSync(path.join(payload,file));return {file,bytes:bytes.length,sha256:digest(bytes)};}),
  verifierSha256:digest(fs.readFileSync(__filename)),upstreamEvidenceSha256:digest(fs.readFileSync(upstreamArg)),
  limits:['Provenance assertions are not renderer execution or a comprehensive vulnerability/dependency-license audit','OCR coordinate highlighting and PDF.js 6.5.438 integration are not verified here']};
fs.mkdirSync(path.dirname(outputArg),{recursive:true});fs.writeFileSync(outputArg,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
