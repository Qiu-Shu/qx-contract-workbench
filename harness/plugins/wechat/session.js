/** QX patch of dsh-wechat-media (MIT): preserve the requested durable identity. */
export function isSessionExistsError(error) {
  return /already\s*exists|already\s*owned|SessionAlreadyExists|SessionAlreadyOwned/i.test(`${error?.name ?? ''} ${error?.message ?? ''}`);
}
export function describeError(error) { return String(error?.message ?? error ?? 'unknown error'); }
export async function openSessionAgent({agents,sessionId,meta,agentOptions,setup,isMissingSession=()=>false}={}) {
  if (!sessionId || !agents?.resume || !agents?.create) throw new Error('session identity and agents service required');
  const common={meta,...(agentOptions?{agentOptions}:{}),...(setup?{setup}:{})};
  try { return {handle:await agents.resume({resumeSessionId:sessionId,...common}),sessionId}; }
  catch(error) {
    if (!isMissingSession(error)) throw new Error(`无法恢复会话 ${sessionId}：${describeError(error)}。已保留原会话，没有新建空白会话。`,{cause:error});
  }
  return {handle:await agents.create({sessionId,...common}),sessionId};
}
