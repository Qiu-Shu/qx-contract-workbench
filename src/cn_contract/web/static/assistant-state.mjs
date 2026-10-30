import {createMaterialGenerationController} from './assistant-material-generation.mjs';
import {createGenerationController,isAuthorizationError} from './assistant-generation.mjs';
import {createResearchController} from './assistant-research.mjs';
import {createContextController} from './assistant-context.mjs';
import {createBusinessController} from './assistant-business.mjs';

// This controller stores only the current page in memory; the server owns revisions.
const scopeKeys = ['workspace_id', 'conversation_id', 'scope_kind', 'scope_ref',
  'binding_revision', 'input_revision', 'materials_revision'];
const sameScope = (left, right) => scopeKeys.every(key => left?.[key] === right?.[key]);
const sameContext = (left,right) => scopeKeys.slice(0,5).every(key=>left?.[key]===right?.[key]);
const unique = messages => [...new Map(messages.map(message => [message.id, message])).values()];
const activeRuns = new Set(['queued', 'preparing', 'routing', 'retrieving', 'generating',
  'persisting', 'awaiting_input']);

export function createDraftController(api, {
  onChange = () => {}, onConversation = () => {}, uuid = () => crypto.randomUUID(), readonly = false,
  nativeAuthorization = null, nativeContextAuthorization = null, nativeProfileAuthorization = null, nativeMaterialAuthorization = null,
  autoReadMaterials = false,
} = {}) {
  const state = {id: null, view: null, text: '', savedText: '', skill: null,
    status: readonly ? 'readonly' : 'idle', error: null, conflict: null, dirty: false, loading: false,
    materials: null, materialAction: null, desktopModel: null};
  let epoch = 0, closed = false, channel = null, creating = null, pending = null, materialPending = null;
  let reading = false, paging = false, cancelling = false, generation = null, research = null, context = null, business = null, materialGeneration = null;
  const stoppedRuns=new Set();
  const isRunStopped=id=>stoppedRuns.has(id)||(state.view?.latest_run?.id===id&&
    (state.view.latest_run.cancel_requested||state.view.latest_run.state==='cancelled'));

  function notify() {
    state.materialAction = materialPending?.kind || null;
    state.dirty = Boolean(creating || pending || materialPending || state.conflict ||
      (state.id ? state.text !== state.savedText : state.text.trim()));
    generation?.sync(); research?.sync(); context?.sync(); business?.sync(); onChange(state);
  }
  const current = token => !closed && token === epoch;
  function identity(id) {
    if (state.id !== id) { state.id = id; onConversation(id); }
  }
  function reset() {
    generation?.reset();research?.reset();context?.reset();business?.reset();materialGeneration?.reset();
    creating = pending = materialPending = null;
    reading = paging = cancelling = false;
    stoppedRuns.clear();
    state.view = null; state.text = state.savedText = ''; state.skill = null;
    state.conflict = state.error = null; state.loading = false;
    state.materials = null; state.materialAction = null;
    state.status = readonly ? 'readonly' : 'idle';
  }
  function fail(error, token) {
    if (!current(token)) return false;
    if (isAuthorizationError(error)) {
      epoch += 1; reset(); state.status = 'revoked'; identity(null);
    } else state.status = 'error';
    state.error = {code: error.code || 'REQUEST_FAILED', status: error.status || 0};
    notify(); return false;
  }
  function checked(view, id) {
    if (!view?.scope?.conversation_id || (id && view.scope.conversation_id !== id)) {
      throw Object.assign(new Error('Invalid conversation response'), {code: 'INVALID_RESPONSE'});
    }
    return view;
  }
  function merged(view) {
    const previous = state.view;
    if (!previous || !sameContext(previous.scope, view.scope) || !previous.messages.length) return view;
    const ids = new Set(previous.messages.map(message => message.id));
    // A disjoint latest page may hide a gap: restart its cursor instead of skipping that gap.
    if (view.messages.length && !view.messages.some(message => ids.has(message.id))) return view;
    return {...view, messages: unique([...previous.messages, ...view.messages]),
      next_before: previous.next_before};
  }
  function baseline(view, keepText = true) {
    if(state.view && !sameContext(state.view.scope,view.scope)){generation?.reset();research?.reset();context?.reset();}
    state.view = merged(view); state.savedText = view.draft_input;
    if (!keepText) state.text = view.draft_input;
  }
  function conflict(view) {
    baseline(view);
    state.conflict = {local: state.text, server: view.draft_input};
    pending = null; state.status = 'conflict'; state.error = null; notify(); return false;
  }
  function committed(view, body) {
    return sameScope(view.scope, body.expected_scope) &&
      view.composer_revision === body.expected_composer_revision + 1 && view.draft_input === body.content;
  }
  async function reconcile(token) {
    const write = pending;
    const view = checked(await api.getConversation(state.id), state.id);
    if (!current(token)) return false;
    const body = write.body;
    if (committed(view, body)) {
      baseline(view); pending = null; return true;
    }
    if (sameScope(view.scope, body.expected_scope) &&
        view.composer_revision === body.expected_composer_revision && view.draft_input === write.baseline) {
      return true;
    }
    return conflict(view);
  }
  async function writeDraft(token) {
    try {
      const view = checked(await api.saveDraft(state.id, pending.body), state.id);
      if (!current(token)) return false;
      baseline(view); pending = null; return true;
    } catch (error) {
      if (!current(token)) return false;
      if (error.status === 409 && error.code === 'VERSION_CONFLICT') {
        try {
          const view = checked(await api.getConversation(state.id), state.id);
          if (!current(token)) return false;
          if (committed(view, pending.body)) { baseline(view); pending = null; return true; }
          return conflict(view);
        } catch (readError) { return fail(readError, token); }
      }
      // A definite input rejection did not commit. Transport/server failures remain unknown.
      if (error.status >= 400 && error.status < 500) pending = null;
      return fail(error, token);
    }
  }
  async function materialsFor(view) {
    if (!api.getMaterials) return null;
    const materials = await api.getMaterials(view.scope.conversation_id);
    if (!sameScope(materials.scope, view.scope)) {
      throw Object.assign(new Error('Material revision changed'), {code:'VERSION_CONFLICT',status:409});
    }
    return materials;
  }
  async function writeMaterial(token) {
    const action = materialPending, id = state.id;
    action.body ||= {request_id:uuid(),expected_scope:{...state.view.scope},...action.input};
    const body = action.body;
    try {
      if (!action.done && action.unknown) {
        action.done = action.kind === 'upload'
          ? await api.findAttachmentRequest(id,body.request_id)
          : action.kind === 'parse' ? await api.findParseRequest(id,action.attachment,body.request_id)
            : await api.findMaterialRequest(id,body.request_id);
        if (!current(token)) return false;
      }
      if (!action.done) {
        action.unknown = true;
        action.done = action.kind === 'upload' ? await api.uploadAttachment(id,body,action.file)
          : action.kind === 'parse' ? await api.parseAttachment(id,action.attachment,body)
            : await api.selectMaterials(id,body);
        if (!current(token)) return false;
      }
      const view = checked(await api.getConversation(id),id);
      const materials = await materialsFor(view);
      if (!current(token)) return false;
      materialPending = null; state.materials = materials;
      if (view.composer_revision !== state.view.composer_revision || view.draft_input !== state.savedText) {
        return conflict(view);
      }
      baseline(view);
      const uploaded=action.kind==='upload'?action.done?.attachment:null;
      if(autoReadMaterials&&uploaded&&api.parseAttachment&&['application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document'].includes(uploaded.mime)){
        materialPending={kind:'parse',input:{baseline_view:null},attachment:uploaded.id,body:null,unknown:false,done:null};
        notify();return writeMaterial(token);
      }
      return true;
    } catch(error) {
      if (!current(token)) return false;
      if (error.status === 409 && error.code === 'VERSION_CONFLICT') {
        if (!action.done) { action.body = null; action.unknown = false; }
        try {
          const view = checked(await api.getConversation(id),id);
          const materials = await materialsFor(view);
          if (!current(token)) return false;
          state.materials = materials;
          if (action.done) materialPending = null;
          return conflict(view);
        } catch(readError) { return fail(readError,token); }
      }
      if (error.status >= 400 && error.status < 500 && !action.done) materialPending = null;
      return fail(error,token);
    }
  }
  async function drain(explicit) {
    const token = epoch;
    try {
      if (pending) {
        if (!explicit || !await reconcile(token)) return false;
        if (pending && !await writeDraft(token)) return false;
      }
      if (!state.id && (creating || state.text.trim() || materialPending)) {
        creating ||= {request_id: uuid()};
        const view = checked(await api.createConversation(creating));
        if (!current(token)) return false;
        identity(view.scope.conversation_id); baseline(view); creating = null;
        if (view.draft_input && view.draft_input !== state.text) return conflict(view);
      }
      if (materialPending && !await writeMaterial(token)) return false;
      while (current(token) && state.id && state.text !== state.savedText) {
        pending = {body: {expected_scope: {...state.view.scope},
          expected_composer_revision: state.view.composer_revision, content: state.text},
          baseline: state.savedText};
        if (!await writeDraft(token)) return false;
        notify();
      }
      if (!current(token)) return false;
      state.error = null; state.status = readonly ? 'readonly' : (state.id ? 'saved' : 'idle');
      return true;
    } catch (error) { return fail(error, token); }
  }
  function save(explicit = false, fromGeneration = false) {
    if (closed || state.loading || state.status === 'revoked' || state.conflict) return Promise.resolve(false);
    if (readonly) return Promise.resolve(!state.dirty);
    const active=materialGeneration?.blocked()?materialGeneration:business?.blocked()?business:generation?.blocked()?generation:research?.blocked()?research:context?.blocked()?context:null;
    if(!fromGeneration && active) {
      if(!active.busy())return Promise.resolve(false);
      const token=epoch;
      return active.wait().then(()=>current(token) && !active.unknown() ? save(explicit) : false);
    }
    if (channel) return channel;
    if (!state.dirty) return Promise.resolve(true);
    if (state.status === 'error' && !explicit) return Promise.resolve(false);
    state.status = 'saving'; state.error = null;
    const token = epoch;
    channel = Promise.resolve().then(() => drain(explicit)).finally(() => {
      channel = null;
      if (current(token)) notify();
    });
    notify(); return channel;
  }
  function material(kind,input,{file,attachment}={}) {
    if (closed || readonly || state.loading || state.status === 'revoked' || materialPending || state.conflict || channel || generation?.blocked() || research?.blocked() || (business?.blocked() || materialGeneration?.blocked())) {
      return Promise.resolve(false);
    }
    // Pending text writes share this drain; a file never sends an old draft back.
    materialPending = {kind,input,file,attachment,body:null,unknown:false,done:null};
    notify(); return save(true);
  }
  async function open(id) {
    if (closed) return false;
    if((business?.blocked() || materialGeneration?.blocked()))return false;
    if (id === state.id && state.view) return refresh();
    if (!state.loading && (state.dirty || channel) && !await save()) return false;
    const token = ++epoch;
    reset(); state.id = null; state.loading = true; state.status = 'loading'; notify();
    try {
      const view = checked(await api.getConversation(id), id);
      const materials = await materialsFor(view);
      if (!current(token)) return false;
      identity(id); baseline(view, false); state.materials = materials; state.loading = false;
      state.status = readonly ? 'readonly' : 'saved'; notify(); return true;
    } catch (error) {
      if (current(token)) state.loading = false;
      return fail(error, token);
    }
  }
  async function refresh(fromGeneration = false, canApply = () => true) {
    if (closed || !state.id || state.loading || channel || pending || creating || reading ||
        (!fromGeneration && (generation?.unknown() || research?.unknown() || business?.unknown() || context?.unknown() || materialGeneration?.unknown()))) return false;
    const token = epoch, id = state.id, baselineAtStart = state.view, marker = {};
    reading = marker;
    try {
      const view = checked(await api.getConversation(id), id);
      const materials = await materialsFor(view);
      if (!current(token)) return false;
      if (channel || pending || state.view !== baselineAtStart || !canApply()) return false;
      const previous = state.view;
      if (state.conflict || (state.dirty && (!sameScope(view.scope, previous.scope) ||
          view.composer_revision !== previous.composer_revision || view.draft_input !== state.savedText))) {
        return conflict(view);
      }
      baseline(view, state.dirty); state.materials = materials; state.error = null;
      state.status = readonly ? 'readonly' : (state.dirty ? 'idle' : 'saved'); notify(); return true;
    } catch (error) { return fail(error, token); }
    finally { if (reading === marker) reading = false; }
  }
  async function loadEarlier() {
    if (closed || state.loading || paging || !state.view?.next_before) return false;
    const token = epoch, id = state.id, before = state.view.next_before, marker = {};
    paging = marker;
    try {
      const view = checked(await api.getConversation(id, before), id);
      if (!current(token) || state.view.next_before !== before) return false;
      state.view = {...state.view, messages: unique([...view.messages, ...state.view.messages]), next_before: view.next_before};
      notify(); return true;
    } catch (error) { return fail(error, token); }
    finally { if (paging === marker) paging = false; }
  }
  async function cancel() {
    const run = state.view?.latest_run;
    if (closed || readonly || state.loading || channel || cancelling || !run ||
        !activeRuns.has(run.state) || run.cancel_requested) return false;
    const token = epoch, marker = {};
    cancelling = marker;
    // The user's stop intent takes effect before an in-flight authorization resolves.
    stoppedRuns.add(run.id);
    try {
      await api.cancelRun(run.id, {request_id: uuid()});
      if (!current(token)) return false;
      if(!await refresh())return false;
      await refreshWorkflows();return current(token);
    } catch (error) { return fail(error, token); }
    finally { if (cancelling === marker) cancelling = false; }
  }
  const workflowHost={state,readonly,uuid,notify,nativeAuthorization,nativeContextAuthorization,nativeProfileAuthorization,nativeMaterialAuthorization,
    token:()=>epoch,current,fail,isRunStopped,
    blocked:()=>Boolean((pending || creating) && !channel || materialPending || state.status==='error'),
    busy:()=>Boolean(channel || pending || creating || materialPending || reading),
    saveDraft:()=>save(false,true),refreshDraft:()=>refresh(true),
    accept(body,attempt,clearText) {
      state.view={...state.view,scope:{...attempt.scope},composer_revision:body.expected_composer_revision+1,draft_input:''};
      state.savedText='';if(clearText)state.text='';
      state.error=null;state.status=state.text?'idle':'saved';notify();
    },
    async readConflict() {
      const token=epoch,id=state.id;
      try {
        const view=checked(await api.getConversation(id),id),materials=await materialsFor(view);
        if(!current(token))return false;
        state.materials=materials;return conflict(view);
      } catch(error) {return fail(error,token);}
    },
  };
  generation=createGenerationController(api,{...workflowHost,
    blocked:()=>workflowHost.blocked() || research?.blocked() || context?.blocked() || (business?.blocked() || materialGeneration?.blocked())});
  research=createResearchController(api,{...workflowHost,
    blocked:()=>workflowHost.blocked() || generation?.blocked() || context?.blocked() || (business?.blocked() || materialGeneration?.blocked())});
  context=createContextController(api,{...workflowHost,
    blocked:()=>workflowHost.blocked() || generation?.blocked() || research?.blocked() || (business?.blocked() || materialGeneration?.blocked())});
  business=createBusinessController(api,{...workflowHost,
    blocked:()=>workflowHost.blocked() || generation?.blocked() || research?.blocked() || context?.blocked()});
  materialGeneration=createMaterialGenerationController(api,{...workflowHost,
    blocked:()=>workflowHost.blocked() || generation?.blocked() || research?.blocked() || context?.blocked() || business?.blocked(),
    refreshHistory:()=>generation.refresh()});
  async function sendBusiness(){
    const token=epoch;
    if(!await business.send()||!current(token))return false;
    const receipt=business.lastAccepted();
    // Only an acknowledged user send may start analysis. History reads never send.
    // New typing and explicit collection instructions stay in the user's control.
    if(!receipt?.task_id||!receipt.workflow||isRunStopped(receipt.run_id)||!state.materialGeneration.available||state.text.trim()||
        /稍等|等我|先别|先不要|暂不|上传完再|发完再/.test(business.lastAcceptedContent()))return true;
    if(receipt.workflow!=='sales'&&!state.materials?.items?.length)return true;
    return materialGeneration.send(receipt.run_id);
  }
  function refreshWorkflows(){
    if(materialGeneration.unknown())return materialGeneration.refresh();
    if(business.unknown())return business.refresh();
    // An unacknowledged write must be resolved before any competing history read.
    if(research.blocked())return research.refresh();
    if(context.blocked())return context.refresh();
    if(generation.blocked() || !api.getResearchHistory)return generation.refresh();
    const token=epoch;
    return generation.refresh().then(async generated=>{
      if(!current(token))return false;
      const researched=await research.refresh();
      if(current(token) && state.context?.phase==='tracking')await context.refresh();
      if(current(token))await business.refresh();
      return researched && (generated || !api.getGenerationCapability);
    });
  }
  return {
    state,
    edit(text) {
      if (closed || readonly || state.loading || state.status === 'revoked') return;
      state.text = text; generation.changed();research.changed();context.changed();
      if (state.conflict) state.conflict.local = text;
      if (state.status === 'saved') state.status = 'idle';
      notify();
    },
    selectSkill(skill) {
      if (closed || readonly || state.loading || state.status === 'revoked') return;
      if(skill!==state.skill){
        const last=state.business?.items?.at(-1);
        if(!state.text.trim()&&last&&!last.task_id){
          const message=state.view?.messages?.find(message=>message.id===last.message_id);
          if(message)state.text=message.content;
        }
        state.business.selectedTask=null;
      }
      state.skill = skill; generation.changed();research.changed();context.changed(); notify();
    },
    open, async ensureConversation() {
      if(closed || readonly || state.loading || state.conflict || state.status==='revoked' || state.status==='error')return false;
      if(!state.id){creating ||= {request_id:uuid()};notify();}
      return await save() && Boolean(state.id);
    }, save: () => save(), retry: () => save(true), refresh, loadEarlier, cancel,
    send:()=>materialGeneration.unknown()?materialGeneration.refresh():business.unknown()?sendBusiness():research.unknown()?research.send():generation.unknown()?generation.send():
      context.unknown()?context.send():
      business.handles()?sendBusiness():
      state.skill==='legal_research'?research.send():
      !state.skill && state.context?.selected.length?context.send():generation.send(),
    generateMaterial:id=>materialGeneration.send(id),
    previewContext:()=>context.preview(),
    selectBusinessTask:id=>business.select(id),
    toggleContextCitation(id){
      const selected=state.context.selected.join(',');context.toggle(id);
      if(selected!==state.context.selected.join(',')){generation.changed();notify();}
    },
    refreshGeneration:refreshWorkflows,
    upload: (file,policy) => file ? material('upload',{original_name:file.name,mime:file.type,policy},{file}) : Promise.resolve(false),
    parse: (attachment,baseline_view=null) => material('parse',{baseline_view},{attachment}),
    selectMaterials: items => material('selection',{items}),
    revoke(error) {
      return isAuthorizationError(error) ? fail(error, epoch) : false;
    },
    async newConversation() {
      if(business.blocked() || materialGeneration.blocked())return false;
      if (closed || (!state.loading && (state.dirty || channel) && !await save())) return false;
      epoch += 1; reset(); identity(null); notify(); return true;
    },
    async resolveConflict(choice) {
      if (closed || readonly || !state.conflict || !['local', 'server'].includes(choice)) return false;
      if (choice === 'server') state.text = state.savedText;
      state.conflict = null; state.status = 'idle'; state.error = null; notify();
      return choice === 'local' || materialPending ? save(true) : true;
    },
    canLeave: () => closed || (!state.dirty && !state.loading && !channel && !reading && !paging && !cancelling && !generation.blocked() && !research.blocked() && !context.blocked() && !business.blocked() && !materialGeneration.blocked()),
    close() { closed = true; epoch += 1; reset(); state.id = null; notify(); },
  };
}
