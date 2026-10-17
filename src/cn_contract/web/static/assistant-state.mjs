// This controller stores only the current page in memory; the server owns revisions.
const scopeKeys = ['workspace_id', 'conversation_id', 'scope_kind', 'scope_ref',
  'binding_revision', 'input_revision', 'materials_revision'];
const sameScope = (left, right) => scopeKeys.every(key => left?.[key] === right?.[key]);
const unique = messages => [...new Map(messages.map(message => [message.id, message])).values()];
const activeRuns = new Set(['queued', 'preparing', 'routing', 'retrieving', 'generating',
  'persisting', 'awaiting_input']);

export function createDraftController(api, {
  onChange = () => {}, onConversation = () => {}, uuid = () => crypto.randomUUID(), readonly = false,
} = {}) {
  const state = {id: null, view: null, text: '', savedText: '', skill: null,
    status: readonly ? 'readonly' : 'idle', error: null, conflict: null, dirty: false, loading: false,
    materials: null, materialAction: null};
  let epoch = 0, closed = false, channel = null, creating = null, pending = null, materialPending = null;
  let reading = false, paging = false, cancelling = false;

  function notify() {
    state.materialAction = materialPending?.kind || null;
    state.dirty = Boolean(creating || pending || materialPending || state.conflict ||
      (state.id ? state.text !== state.savedText : state.text.trim()));
    onChange(state);
  }
  const current = token => !closed && token === epoch;
  function identity(id) {
    if (state.id !== id) { state.id = id; onConversation(id); }
  }
  function reset() {
    creating = pending = materialPending = null;
    reading = paging = cancelling = false;
    state.view = null; state.text = state.savedText = ''; state.skill = null;
    state.conflict = state.error = null; state.loading = false;
    state.materials = null; state.materialAction = null;
    state.status = readonly ? 'readonly' : 'idle';
  }
  function fail(error, token) {
    if (!current(token)) return false;
    if (error.status === 401 || error.status === 403) {
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
    if (!previous || !sameScope(previous.scope, view.scope) || !previous.messages.length) return view;
    const ids = new Set(previous.messages.map(message => message.id));
    // A disjoint latest page may hide a gap: restart its cursor instead of skipping that gap.
    if (view.messages.length && !view.messages.some(message => ids.has(message.id))) return view;
    return {...view, messages: unique([...previous.messages, ...view.messages]),
      next_before: previous.next_before};
  }
  function baseline(view, keepText = true) {
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
      baseline(view); return true;
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
  function save(explicit = false) {
    if (closed || state.loading || state.status === 'revoked' || state.conflict) return Promise.resolve(false);
    if (readonly) return Promise.resolve(!state.dirty);
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
    if (closed || readonly || state.loading || state.status === 'revoked' || materialPending || state.conflict || channel) {
      return Promise.resolve(false);
    }
    // Pending text writes share this drain; a file never sends an old draft back.
    materialPending = {kind,input,file,attachment,body:null,unknown:false,done:null};
    notify(); return save(true);
  }
  async function open(id) {
    if (closed) return false;
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
  async function refresh() {
    if (closed || !state.id || state.loading || channel || pending || creating || reading) return false;
    const token = epoch, id = state.id, baselineAtStart = state.view, marker = {};
    reading = marker;
    try {
      const view = checked(await api.getConversation(id), id);
      const materials = await materialsFor(view);
      if (!current(token)) return false;
      if (channel || pending || state.view !== baselineAtStart) return false;
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
    try {
      await api.cancelRun(run.id, {request_id: uuid()});
      if (!current(token)) return false;
      return await refresh();
    } catch (error) { return fail(error, token); }
    finally { if (cancelling === marker) cancelling = false; }
  }
  return {
    state,
    edit(text) {
      if (closed || readonly || state.loading || state.status === 'revoked') return;
      state.text = text;
      if (state.conflict) state.conflict.local = text;
      if (state.status === 'saved') state.status = 'idle';
      notify();
    },
    selectSkill(skill) {
      if (closed || readonly || state.loading || state.status === 'revoked') return;
      state.skill = skill; notify();
    },
    open, save: () => save(), retry: () => save(true), refresh, loadEarlier, cancel,
    upload: (file,policy) => file ? material('upload',{original_name:file.name,mime:file.type,policy},{file}) : Promise.resolve(false),
    parse: (attachment,baseline_view=null) => material('parse',{baseline_view},{attachment}),
    selectMaterials: items => material('selection',{items}),
    revoke(error) {
      return error?.status === 401 || error?.status === 403 ? fail(error, epoch) : false;
    },
    async newConversation() {
      if (closed || (!state.loading && (state.dirty || channel) && !await save())) return false;
      epoch += 1; reset(); identity(null); notify(); return true;
    },
    async resolveConflict(choice) {
      if (closed || readonly || !state.conflict || !['local', 'server'].includes(choice)) return false;
      if (choice === 'server') state.text = state.savedText;
      state.conflict = null; state.status = 'idle'; state.error = null; notify();
      return choice === 'local' || materialPending ? save(true) : true;
    },
    canLeave: () => closed || (!state.dirty && !state.loading && !channel && !reading && !paging && !cancelling),
    close() { closed = true; epoch += 1; reset(); state.id = null; notify(); },
  };
}
