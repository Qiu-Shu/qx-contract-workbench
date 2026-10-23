const {createHash}=require('node:crypto');
const {canonicalProfileBasis}=require('./profile-basis.cjs');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SCOPE=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const INACTIVE=new Set(['completed','cancelled','failed','interrupted','blocked']);
const exact=(value,fields)=>value!==null && typeof value==='object' && !Array.isArray(value) &&
  Reflect.ownKeys(value).length===fields.length && fields.every(key=>Object.hasOwn(value,key));
const uuid=value=>typeof value==='string' && UUID.test(value);
const count=value=>Number.isSafeInteger(value) && value>=0;
const same=(left,right)=>exact(left,SCOPE) && SCOPE.every(key=>left[key]===right[key]);

function validProfileInput(value) {
  const scope=value?.expected_scope;
  return exact(value,['conversation_id','request_id','expected_scope','expected_composer_revision','project_intake']) &&
    uuid(value.conversation_id) && uuid(value.request_id) && count(value.expected_composer_revision) &&
    typeof value.project_intake==='boolean' && exact(scope,SCOPE) && uuid(scope.workspace_id) &&
    scope.conversation_id===value.conversation_id && ['conversation','intake','matter'].includes(scope.scope_kind) &&
    (scope.scope_kind==='conversation' ? scope.scope_ref===null : uuid(scope.scope_ref)) &&
    count(scope.binding_revision) && scope.binding_revision>0 && count(scope.input_revision) && count(scope.materials_revision);
}

function createProfileSnapshot({tokenFor,csrfCookie,readJSON,postJSON,check,fail}) {
  return async function profileSnapshot(context,input,base,guard,expectedToken) {
    const paths=[base+'?limit=1',base+'/materials',base+'/profile-preview'];
    const token=await tokenFor(context,paths,guard,expectedToken);
    const csrf=await csrfCookie(context,paths[2],guard);
    const [draft,materials]=await Promise.all(paths.slice(0,2).map(path=>readJSON(context.origin,path,token)));
    if(!check(guard) || !same(draft?.scope,input.expected_scope) || !same(materials?.scope,input.expected_scope) ||
        draft.archived_at!==null || draft.composer_revision!==input.expected_composer_revision ||
        !Array.isArray(materials.items) || materials.items.length ||
        !Array.isArray(materials.attachments) || materials.attachments.length ||
        (draft.latest_run!==null && !INACTIVE.has(draft.latest_run?.state)) ||
        typeof draft.draft_input!=='string' || !draft.draft_input.trim() ||
        Buffer.byteLength(draft.draft_input,'utf8')>65536)fail();
    // The preview returns only the server-owned basis; it never supplies permission.
    const basis=canonicalProfileBasis(await postJSON(context.origin,paths[2],token,csrf,{
      request_id:input.request_id,expected_scope:input.expected_scope,
      expected_composer_revision:input.expected_composer_revision,project_intake:input.project_intake}));
    if(!check(guard) || !basis || !same(basis.expected_scope,input.expected_scope) ||
        basis.request_id!==input.request_id || basis.expected_composer_revision!==input.expected_composer_revision ||
        basis.project_intake!==input.project_intake ||
        basis.content_sha256!==createHash('sha256').update(draft.draft_input,'utf8').digest('hex'))fail();
    await tokenFor(context,paths,guard,token);
    return {token,content:draft.draft_input,basis,basisKey:JSON.stringify(basis),paths};
  };
}

module.exports={validProfileInput,createProfileSnapshot};
