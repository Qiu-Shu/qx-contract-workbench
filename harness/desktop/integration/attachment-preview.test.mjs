import {test} from 'node:test';
import assert from 'node:assert/strict';
import {attachmentPreviewPath} from './attachment-preview.mjs';
const reference={attachmentId:'sha256:'+'a'.repeat(64),name:'合同 审查（甲方）.docx',bytes:42};
test('resolves a stored upload by its opaque reference without treating display name as a path',()=>{
  let received;
  const result=attachmentPreviewPath({fileHostPath:ref=>{received=ref;return 'C:/资料/inbox/'+ref.name}},reference);
  assert.equal(result,'C:/资料/inbox/'+reference.name);assert.deepEqual(received,reference);
});
test('refuses traversal, malformed identifiers, forged paths and invalid byte counts before provider lookup',()=>{
  let called=0;const provider={fileHostPath:()=>{called++;return 'C:/private'}};
  for(const patch of [{name:'../secret.docx'},{name:'C:\\secret.docx'},{name:'..'},{name:'a\0.docx'},
    {attachmentId:'../outside'},{bytes:-1},{bytes:Infinity},{path:'C:/private'}]){
    assert.throws(()=>attachmentPreviewPath(provider,{...reference,...patch}),/Invalid attachment/);
  }
  assert.equal(called,0);
});
test('same filename with different content retains distinct storage identity',()=>{
  const provider={fileHostPath:ref=>'C:/uploads/'+ref.attachmentId.slice(7)+'/'+ref.name};
  assert.notEqual(attachmentPreviewPath(provider,reference),attachmentPreviewPath(provider,{...reference,attachmentId:'sha256:'+'b'.repeat(64)}));
});
test('unavailable storage reports failure instead of inventing a disk path',()=>{
  assert.throws(()=>attachmentPreviewPath({},reference),/unavailable/);
  assert.throws(()=>attachmentPreviewPath({fileHostPath:()=>undefined},reference),/unavailable/);
});
