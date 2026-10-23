const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256=/^[0-9a-f]{64}$/;
const FIELDS=['input_format','template_version','purpose','handler_id','handler_version','request_id',
  'expected_scope','expected_composer_revision','content_sha256','base_profile_revision',
  'expected_intake_id','expected_intake_revision','project_intake','system_sha256','config_sha256',
  'wire_sha256','wire_bytes'];
const SCOPE=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const exact=(value,fields)=>value!==null && typeof value==='object' && !Array.isArray(value) &&
  Reflect.ownKeys(value).length===fields.length && fields.every(field=>Object.hasOwn(value,field));
const uuid=value=>typeof value==='string' && UUID.test(value);
const integer=(value,min=0)=>Number.isSafeInteger(value) && value>=min;

function canonicalProfileBasis(value){
  try{
    if(!exact(value,FIELDS) || !exact(value.expected_scope,SCOPE))return null;
    const basis=structuredClone(value),scope=basis.expected_scope;
    if(basis.input_format!=='profile-text-v1' || basis.template_version!=='profile-text-system-v1' ||
        basis.purpose!=='reply_and_profile_draft' || basis.handler_id!=='profile.save' || basis.handler_version!=='1' ||
        !uuid(basis.request_id) || !integer(basis.expected_composer_revision) || !integer(basis.base_profile_revision) ||
        typeof basis.project_intake!=='boolean' || !integer(basis.wire_bytes,1) || basis.wire_bytes>262144 ||
        !uuid(scope.workspace_id) || !uuid(scope.conversation_id) ||
        !['conversation','intake','matter'].includes(scope.scope_kind) ||
        (scope.scope_kind==='conversation' ? scope.scope_ref!==null : !uuid(scope.scope_ref)) ||
        !integer(scope.binding_revision,1) || !integer(scope.input_revision) || !integer(scope.materials_revision))return null;
    for(const field of ['content_sha256','system_sha256','config_sha256','wire_sha256'])
      if(typeof basis[field]!=='string' || !SHA256.test(basis[field]))return null;
    if(basis.expected_intake_id===null ? basis.expected_intake_revision!==null :
        !uuid(basis.expected_intake_id) || !integer(basis.expected_intake_revision,1))return null;
    if(scope.scope_kind==='intake' && basis.expected_intake_id!==scope.scope_ref)return null;
    const result=Object.fromEntries(FIELDS.map(field=>[field,basis[field]]));
    result.expected_scope=Object.fromEntries(SCOPE.map(field=>[field,scope[field]]));
    return result;
  }catch{return null;}
}

const validProfileBasis=value=>canonicalProfileBasis(value)!==null;
module.exports={validProfileBasis,canonicalProfileBasis};
