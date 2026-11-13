import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir,rm,stat,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {prepareContentWatch,componentAsset} from './prepare-content-watch.mjs';

const bytes=Buffer.from('synthetic executable, never run');
const asset={name:'synthetic',url:'https://github.com/xpzouying/xiaohongshu-mcp/releases/download/v2.7.2/synthetic',
  sha256:createHash('sha256').update(bytes).digest('hex'),size:bytes.length};
async function fixture(t){const stateDir=await mkdtemp(join(tmpdir(),'qx-xhs-prepare-'));t.after(()=>rm(stateDir,{recursive:true,force:true}));return stateDir;}
test('supported release assets have fixed checksums and unsupported hosts stop before a download',async t=>{
  assert.equal(componentAsset('win32','x64').name,'xiaohongshu-mcp-windows-amd64.exe');
  assert.match(componentAsset('darwin','arm64').sha256,/^[a-f0-9]{64}$/);
  assert.throws(()=>componentAsset('linux','arm64'),/暂不支持/);
  const stateDir=await fixture(t);let requests=0;
  await assert.rejects(prepareContentWatch({stateDir,platform:'unsupported',fetchImpl:async()=>{requests++;}}),/暂不支持/);
  assert.equal(requests,0);
});
test('an explicit prepare downloads, verifies and stores a component without changing saved account state',async t=>{
  const stateDir=await fixture(t);await mkdir(join(stateDir,'auth'));await writeFile(join(stateDir,'auth/cookies.json'),'synthetic existing session');
  let requests=0;
  const options={stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>{requests++;return new Response(bytes);}};
  const result=await prepareContentWatch(options);
  assert.equal(result.ready,true);assert.equal(result.version,'v2.7.2');
  assert.deepEqual(await readFile(result.executable),bytes);
  assert.equal(await readFile(join(stateDir,'auth/cookies.json'),'utf8'),'synthetic existing session');
  if(process.platform!=='win32')assert.equal((await stat(result.executable)).mode&0o777,0o700);
  assert.match(await readFile(join(stateDir,'runtime/LICENSE.xiaohongshu-mcp.txt'),'utf8'),/Apache License/);
  assert.equal((await prepareContentWatch(options)).executable,result.executable);assert.equal(requests,1);
});
test('a checksum failure preserves the previous binary and account state',async t=>{
  const stateDir=await fixture(t),runtime=join(stateDir,'runtime');await mkdir(runtime);
  const executable=join(runtime,'xiaohongshu-mcp');await writeFile(executable,'previous application component');
  await assert.rejects(prepareContentWatch({stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>new Response(Buffer.alloc(bytes.length,1))}),/校验/);
  assert.equal(await readFile(executable,'utf8'),'previous application component');
});
test('an oversized or failed download never produces a ready component',async t=>{
  const stateDir=await fixture(t);
  await assert.rejects(prepareContentWatch({stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>new Response(Buffer.alloc(bytes.length+1))}),/大小/);
  await assert.rejects(prepareContentWatch({stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>new Response('missing',{status:404})}),/下载/);
});
test('concurrent prepare actions share a single verified download',async t=>{
  const stateDir=await fixture(t);let requests=0;
  const options={stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>{requests++;return new Response(bytes);}};
  const [first,second]=await Promise.all([prepareContentWatch(options),prepareContentWatch(options)]);
  assert.equal(first.executable,second.executable);assert.equal(requests,1);
});
test('a linked component directory is refused before download or modification',async t=>{
  const stateDir=await fixture(t),outside=await fixture(t);await symlink(outside,join(stateDir,'runtime'),'dir');
  let requests=0;
  await assert.rejects(prepareContentWatch({stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>{requests++;return new Response(bytes);}}),/符号链接/);
  assert.equal(requests,0);
});
test('an interrupted response explains the download failure without exposing transport details',async t=>{
  const stateDir=await fixture(t);
  const stream=new ReadableStream({start(controller){controller.error(new Error('transport-url?token=synthetic-secret'));}});
  await assert.rejects(prepareContentWatch({stateDir,platform:'darwin',arch:'arm64',asset,fetchImpl:async()=>new Response(stream)}),error=>{
    assert.match(error.message,/下载/);assert.ok(!error.message.includes('synthetic-secret'));return true;
  });
});
