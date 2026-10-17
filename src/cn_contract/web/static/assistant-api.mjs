// Same-origin transport. A failed write may already have reached the server.
export async function request(path, {method='GET', body}={}) {
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
      body:body === undefined ? undefined : JSON.stringify(body)});
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
