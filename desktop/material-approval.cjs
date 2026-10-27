const {validMaterialBasis}=require('./material-basis.cjs');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const keys=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const same=(a,b)=>keys.every(k=>a?.[k]===b?.[k]);
function validMaterialInput(v){
  return v&&typeof v==='object'&&Object.keys(v).length===5&&
    ['conversation_id','request_id','expected_scope','expected_composer_revision','parent_business_run_id'].every(k=>Object.hasOwn(v,k))&&
    [v.conversation_id,v.request_id,v.parent_business_run_id].every(x=>typeof x==='string'&&UUID.test(x))&&
    v.expected_scope?.conversation_id===v.conversation_id&&Number.isSafeInteger(v.expected_composer_revision)&&v.expected_composer_revision>=0;
}
function createMaterialSnapshot({tokenFor,csrfCookie,readJSON,postJSON,check,fail}){
  return async(context,input,base,guard,expectedToken)=>{
    const paths=[base+'?limit=1',base+'/material-preview'];
    const token=await tokenFor(context,paths,guard,expectedToken),csrf=await csrfCookie(context,paths[1],guard);
    const draft=await readJSON(context.origin,paths[0],token);
    if(!check(guard)||!same(draft?.scope,input.expected_scope)||draft.archived_at!==null||draft.composer_revision!==input.expected_composer_revision)fail();
    const {conversation_id,...selection}=input;
    const basis=await postJSON(context.origin,paths[1],token,csrf,selection);
    if(!check(guard)||!validMaterialBasis(basis)||!same(basis.expected_scope,input.expected_scope)||
        basis.request_id!==input.request_id||basis.expected_composer_revision!==input.expected_composer_revision||
        basis.parent_business_run_id!==input.parent_business_run_id)fail();
    await tokenFor(context,paths,guard,token);
    return {token,content:basis.manifest.question,basis,basisKey:JSON.stringify(basis),paths};
  };
}
module.exports={validMaterialInput,createMaterialSnapshot};
