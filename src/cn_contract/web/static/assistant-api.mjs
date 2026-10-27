// Same-origin transport. A failed write may already have reached the server.
export async function request(path, {method='GET', body, form, binary=false}={}) {
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
    if(binary && response.ok) {
      try {return await response.blob();}
      catch {throw Object.assign(new Error('response'),{code:'NETWORK_UNKNOWN',status:response.status});}
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
export const submitBusiness=(id,body)=>request(conversation(id)+'/business',{method:'POST',body});
export const findBusiness=(id,key)=>request(conversation(id)+'/business/by-request/'+encodeURIComponent(key));
export const getBusinessHistory=id=>request(conversation(id)+'/business');
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
export const submitContextPreview=(id,body)=>request(conversation(id)+'/context-preview',{method:'POST',body});
export const submitContextGeneration=(id,body)=>request(conversation(id)+'/context-generations',{method:'POST',body});
export const submitProfilePreview=(id,body)=>request(conversation(id)+'/profile-preview',{method:'POST',body});
export const submitProfileGeneration=(id,body)=>request(conversation(id)+'/profile-generations',{method:'POST',body});
export const getProfile=(id,revision)=>request(conversation(id)+'/profile'+
  (revision===undefined?'':'/revisions/'+encodeURIComponent(revision)));

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

export const submitProfileCommit=(id,body)=>request(conversation(id)+'/profile/commits',{method:'POST',body});
export const findProfileReceipt=(id,key)=>request(conversation(id)+'/profile/receipts/'+encodeURIComponent(key));
export const getIntake=id=>request('/api/intakes/'+encodeURIComponent(id));

export const listOutputs=(id,before)=>request(conversation(id)+'/outputs'+(before?'?before='+encodeURIComponent(JSON.stringify(before)):''));
export const previewOutput=(id,body)=>request(conversation(id)+'/outputs/preview',{method:'POST',body});
export const copyOutput=(id,body)=>request(conversation(id)+'/outputs/copy',{method:'POST',body});
export const downloadOutput=(id,body)=>request(conversation(id)+'/outputs/docx',{method:'POST',body,binary:true});

export const getWorksheet=id=>request(conversation(id)+'/reception-worksheet');
export const commitWorksheet=(id,body)=>request(conversation(id)+'/reception-worksheet/commits',{method:'POST',body});
export const findWorksheetReceipt=(id,key)=>request(conversation(id)+'/reception-worksheet/receipts/'+encodeURIComponent(key));
export const suggestWorksheet=(id,body)=>request(conversation(id)+'/reception-worksheet/suggestions',{method:'POST',body});
export const prepareWorksheet=(id,body)=>request(conversation(id)+'/reception-worksheet/prepare',{method:'POST',body});

export const getEvidence=id=>request(conversation(id)+'/evidence');
export const saveEvidence=(id,body)=>request(conversation(id)+'/evidence/commits',{method:'POST',body});
export const findEvidenceReceipt=(id,key)=>request(conversation(id)+'/evidence/receipts/'+encodeURIComponent(key));
export const getEvidenceVersion=(id,revision)=>request(conversation(id)+'/evidence/revisions/'+encodeURIComponent(revision));

export const getFollowups=id=>request(conversation(id)+'/followups');
export const saveFollowups=(id,body)=>request(conversation(id)+'/followups/commits',{method:'POST',body});
export const findFollowupReceipt=(id,key)=>request(conversation(id)+'/followups/receipts/'+encodeURIComponent(key));
export const getFollowupVersion=(id,revision)=>request(conversation(id)+'/followups/revisions/'+encodeURIComponent(revision));

export const submitMaterialGeneration=(id,body)=>request(conversation(id)+'/material-generations',{method:'POST',body});
