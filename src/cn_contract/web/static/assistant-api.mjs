// Same-origin transport. A failed write may already have reached the server.
export async function request(path, {method='GET', body, form}={}) {
  const headers = {};
  if (method !== 'GET') {
    const cookie = document.cookie.split('; ').find(value=>value.startsWith('qx_csrf='));
    headers['X-CSRF-Token'] = cookie ? decodeURIComponent(cookie.slice(8)) : '';
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(),15000);
  try {
    let response;
    try {
      response = await fetch(path, {method, headers, signal:controller.signal, credentials:'same-origin', cache:'no-store',
      body:form || (body === undefined ? undefined : JSON.stringify(body))});
    } catch {
      throw Object.assign(new Error('network'), {code:'NETWORK_UNKNOWN', status:0});
    }
    let data;
    try { data = await response.json(); }
    catch { throw Object.assign(new Error('response'), {code:'NETWORK_UNKNOWN', status:response.status}); }
    if (!response.ok) throw Object.assign(new Error('request'), {code:data.code || 'REQUEST_FAILED', status:response.status});
    return data;
  } finally { clearTimeout(timer); }
}

const conversation = id=>'/api/assistant/conversations/'+encodeURIComponent(id);
export const getConversation = (id,before)=>request(conversation(id)+(before?'?before='+encodeURIComponent(before):''));
export const createConversation = body=>request('/api/assistant/conversations',{method:'POST',body});
export const saveDraft = (id,body)=>request(conversation(id)+'/draft',{method:'PUT',body});
export const listConversations = cursor=>request('/api/assistant/conversations'+(cursor?'?cursor='+encodeURIComponent(cursor):''));
export const skills = ()=>request('/api/assistant/skills');
export const session = ()=>request('/api/session');
export const cancelRun = (id,body)=>request('/api/assistant/runs/'+encodeURIComponent(id)+'/cancel',{method:'POST',body});
export const getGenerationCapability=id=>request(conversation(id)+'/generation-capability');
export const submitGeneration=(id,body)=>request(conversation(id)+'/generations',{method:'POST',body});
export const findGenerationRequest=(id,key)=>request(conversation(id)+'/generations/by-request/'+encodeURIComponent(key));
export const getGenerationAttempt=id=>request('/api/assistant/attempts/'+encodeURIComponent(id));
export const getGenerationHistory=(id,ids)=>request(conversation(id)+'/generation-history?'+
  new URLSearchParams(ids.map(value=>['message_id',value])));
export const submitResearch=(id,body)=>request(conversation(id)+'/researches',{method:'POST',body});
export const findResearchRequest=(id,key)=>request(conversation(id)+'/researches/by-request/'+encodeURIComponent(key));
export const getResearchHistory=(id,ids)=>request(conversation(id)+'/research-history?'+
  new URLSearchParams(ids.map(value=>['message_id',value])));
export const getSavedCitation=id=>request('/api/assistant/library-citations/'+encodeURIComponent(id));

const attachment=(id,file)=>conversation(id)+'/attachments/'+encodeURIComponent(file);
export const getMaterials=id=>request(conversation(id)+'/materials');
export const findAttachmentRequest=(id,key)=>request(conversation(id)+'/attachments/by-request/'+encodeURIComponent(key));
export const findMaterialRequest=(id,key)=>request(conversation(id)+'/materials/by-request/'+encodeURIComponent(key));
export const uploadAttachment=(id,body,file)=>{
  const form=new FormData();form.append('metadata',JSON.stringify(body));form.append('file',file,file.name);
  return request(conversation(id)+'/attachments',{method:'POST',form});
};
export const parseAttachment=(id,file,body)=>request(attachment(id,file)+'/parses',{method:'POST',body});
export const findParseRequest=(id,file,key)=>request(attachment(id,file)+'/parses/by-request/'+encodeURIComponent(key));
export const getParse=(id,file,revision)=>request(attachment(id,file)+'/parses/'+encodeURIComponent(revision));
export const selectMaterials=(id,body)=>request(conversation(id)+'/materials',{method:'PUT',body});
export const originalUrl=(id,file)=>attachment(id,file)+'/original';
