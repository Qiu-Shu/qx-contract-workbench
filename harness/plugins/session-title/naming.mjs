export const providerId = 'qx-first-content-title';
const eligible = event => event.type === 'user/message' && event.data.source.kind === 'user' &&
  event.data.content.some(part => part.type === 'file' || part.type === 'image' || (part.type === 'text' && part.text.trim()));
const uploaded = event => eligible(event) && event.data.content.some(part=>part.type==='file'||part.type==='image');
const pinned = (title,first) => title?.source.kind === 'user' || (title?.source.kind === 'provider' &&
  (!uploaded(first) || (title.source.provider===providerId && title.messageSeqs.includes(first.seq))));

// Work is keyed by the actual Session, never by the selected desktop tab.
export function installNaming(ctx, generate) {
  const active = new Map();
  const inFlight = new Set();
  let stopped = false;
  function schedule(session) {
    if (stopped) return;
    const events=session.snapshotEvents();
    const first = events.find(uploaded) || events.find(eligible);
    if (!first || pinned(ctx.sessionTitle.get(session),first) || !session.requestHeader()?.config) return;
    const previous=active.get(session);
    if(previous?.firstSeq===first.seq)return;
    previous?.controller.abort();
    const controller = new AbortController();
    const job = {controller,firstSeq:first.seq}; active.set(session, job);inFlight.add(job);
    job.promise = Promise.resolve().then(async () => {
      const title = await generate(session, first, controller.signal);
      if (stopped || controller.signal.aborted || ctx.sessions.get(session.id) !== session || pinned(ctx.sessionTitle.get(session),first)) return;
      if (!title?.trim()) throw Error('empty title');
      session.append('session/title', {title, messageSeqs:[first.seq], source:{kind:'provider',provider:providerId}});
    }).catch(error => {
      if (!controller.signal.aborted) ctx.logger.warn('群兴：首次内容命名暂未完成，保留原名称；下次仍只使用首次内容。');
    }).finally(() => {if(active.get(session)===job)active.delete(session);inFlight.delete(job)});
  }
  ctx.on('session/event', (session,event) => {
    if (eligible(event) || event.type === 'request/header') schedule(session);
    if (event.type === 'session/title' && event.data.source.kind === 'user') active.get(session)?.controller.abort();
  });
  ctx.on('session/disposed', session => active.get(session)?.controller.abort());
  ctx.effect(() => async () => {
    stopped=true;
    for(const job of inFlight)job.controller.abort();
    await Promise.allSettled([...inFlight].map(job=>job.promise));
  });
}

function bounded(text, bytes) {
  let result='', used=0;
  for(const char of text){const size=Buffer.byteLength(char);if(used+size>bytes)break;result+=char;used+=size}
  return result;
}

export async function titleInput(first, attachments, readExcerpts) {
  const parts=first.data.content;
  const text=parts.filter(p=>p.type==='text').map(p=>p.text).join('\n');
  const files=parts.filter(p=>p.type==='file'||p.type==='image');
  const names=files.map(p=>p.attachment.name || (p.type==='image'?'上传图片':'上传文件'));
  const locations=files.slice(0,3).map(p=>({type:p.type,path:p.type==='file'?attachments.fileHostPath(p.attachment):attachments.imageHostPath(p.attachment)})).filter(p=>p.path);
  const excerpts=locations.length?await readExcerpts(locations.map(p=>p.path),locations.filter(p=>p.type==='image').map(p=>p.path)):[];
  // Keep room for document text even when the accompanying instruction is long.
  return bounded(JSON.stringify({首次文字:bounded(text,files.length?6000:18000),
    首次附件:names.slice(0,30).map(n=>bounded(n,240)),
    正文摘录:excerpts.map(p=>bounded(p.text||'',5000))}),24000);
}
