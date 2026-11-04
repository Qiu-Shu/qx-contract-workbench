const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {createRequire}=require('node:module');
const dsh=createRequire(require.resolve('@deepseek-ai/dsh/package.json'));
const web=createRequire(dsh.resolve('@deepseek-ai/dsh-web-app/package.json'));
const source=fs.readFileSync(web.resolve('@deepseek-ai/dsh-client-ui-chat/client'),'utf8');
const start=source.indexOf('function assistantText('),end=source.indexOf('//#endregion',start);
assert.ok(start>=0&&end>start);
const copied=vm.runInNewContext(source.slice(start,end)+';assistantText');
test('native copy excludes internal notes even when model adds a preamble',()=>{
  const text='好的，下面可直接发送：\n【可发送回复】\n您好，请发来合同。\n【律师参考】\n内部策略，请勿发给客户。';
  assert.equal(copied([{kind:'reasoning',text:'思考过程'},{kind:'text',text}]),'您好，请发来合同。');
});
test('ordinary legal answers and incomplete markers keep their original text',()=>{
  for(const text of ['普通法律分析。','【可发送回复】格式不完整'])assert.equal(copied([{kind:'text',text}]),text);
});
