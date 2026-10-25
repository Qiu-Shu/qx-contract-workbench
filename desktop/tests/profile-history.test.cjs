const {test}=require('node:test');
const assert=require('node:assert/strict');
const {canonicalProfileBasis}=require('../profile-basis.cjs');
const id=n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
const basis=()=>({input_format:'profile-text-v1',template_version:'profile-text-system-v2',
 purpose:'reply_and_profile_draft',handler_id:'profile.save',handler_version:'1',request_id:id(1),
 expected_scope:{workspace_id:id(2),conversation_id:id(3),scope_kind:'conversation',scope_ref:null,
 binding_revision:1,input_revision:1,materials_revision:0},expected_composer_revision:2,
 content_sha256:'a'.repeat(64),base_profile_revision:0,expected_intake_id:null,expected_intake_revision:null,
 project_intake:false,system_sha256:'b'.repeat(64),config_sha256:'c'.repeat(64),wire_sha256:'d'.repeat(64),wire_bytes:2000,
 conversation_history:[{message_id:id(4),role:'user',source_revision:1,content:'借款35000元。'},
 {message_id:id(5),role:'assistant',source_revision:1,content:'请核对还款日期。'}]});
test('profile v2 canonicalizes exactly the visible prior conversation',()=>{
 const input=basis(),value=canonicalProfileBasis(input);assert.deepEqual(value,input);
 input.conversation_history[0].content='网页改写';assert.notEqual(value.conversation_history[0].content,input.conversation_history[0].content);
});
test('history rejects unknown fields, wrong role, ordering and version mismatch',()=>{
 for(const change of [v=>v.conversation_history[0].role='system',v=>v.conversation_history.reverse(),
 v=>v.conversation_history[0].extra=true,v=>v.template_version='profile-text-system-v1',
 v=>v.conversation_history=[]]){const value=basis();change(value);assert.equal(canonicalProfileBasis(value),null);}
});
