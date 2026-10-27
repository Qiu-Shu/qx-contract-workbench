const {TextDecoder} = require('node:util');
const {validMaterialBasis}=require('./material-basis.cjs');
const {validProfileBasis} = require('./profile-basis.cjs');

const PROTOCOL = 'qx-model-control-v1';
const JUDGE_PROTOCOL = 'qx-judge-control-v1';
const JUDGE_AUTH_PROTOCOL = 'qx-judge-authorization-v1';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const CODES = new Set(['BLOCKED_LIVE','VERSION_CONFLICT','STATE_CONFLICT',
  'BUDGET_EXCEEDED','CROSS_MATTER_DENIED']);
const STATUSES = {configure:['configured'],disable:['disabled'],
  authorize:['authorized','existing'],revoke:['revoked'],configure_judge:['configured'],disable_judge:['disabled'],
  authorize_judge:['authorized','existing'],revoke_judge:['revoked'],authorize_context:['authorized','existing'],
  authorize_profile:['authorized','existing'],authorize_material:['authorized','existing']};
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const keys = (value, expected) => object(value) && Object.keys(value).length === expected.length &&
  expected.every(key => Object.hasOwn(value,key));
const blocked = () => ({ok:false,code:'BLOCKED_LIVE'});

function validContextBasis(basis) {
  if (!keys(basis,['input_format','template_version','request_id','expected_scope',
      'expected_composer_revision','system_sha256','manifest_sha256','source_bindings',
      'config_sha256','wire_sha256']) || basis.input_format!=='library-context-v1' ||
      basis.template_version!=='saved-library-context-system-v1' ||
      typeof basis.request_id!=='string' || !UUID.test(basis.request_id) ||
      !object(basis.expected_scope) ||
      !Number.isSafeInteger(basis.expected_composer_revision) || basis.expected_composer_revision<0) return false;
  for (const digest of ['system_sha256','manifest_sha256','config_sha256','wire_sha256'])
    if (typeof basis[digest]!=='string' || !SHA256.test(basis[digest])) return false;
  if (!Array.isArray(basis.source_bindings) || basis.source_bindings.length<1 ||
      basis.source_bindings.length>8) return false;
  const seen=new Set();
  for (const binding of basis.source_bindings) {
    if (!keys(binding,['saved_citation_id','citation_sha256']) ||
        typeof binding.saved_citation_id!=='string' || !UUID.test(binding.saved_citation_id) ||
        typeof binding.citation_sha256!=='string' || !SHA256.test(binding.citation_sha256) ||
        seen.has(binding.saved_citation_id)) return false;
    seen.add(binding.saved_citation_id);
  }
  return true;
}

function validPayload(operation, payload) {
  if (operation === 'disable' || operation === 'disable_judge') return keys(payload,[]);
  if (operation === 'configure' || operation === 'configure_judge') return keys(payload,['config','secret']) && object(payload.config) &&
    typeof payload.secret === 'string' && /^[\x20-\x7e]{16,1024}$/.test(payload.secret) &&
    payload.secret.trim().length >= 16 && payload.secret.trim().length <= 512;
  const token = value => typeof value === 'string' && /^[\x21-\x7e]{1,256}$/.test(value);
  if (operation === 'revoke' || operation === 'revoke_judge') return keys(payload,['session_token']) && token(payload.session_token);
  if (operation === 'authorize_profile' || operation === 'authorize_material')
    return keys(payload,['session_token','expected_config_version','basis','max_total_usd','valid_for_seconds']) &&
      token(payload.session_token) && typeof payload.expected_config_version === 'string' &&
      UUID.test(payload.expected_config_version) && (operation==='authorize_material'?validMaterialBasis(payload.basis):validProfileBasis(payload.basis)) &&
      typeof payload.max_total_usd === 'string' && payload.max_total_usd.length <= 64 &&
      Number.isSafeInteger(payload.valid_for_seconds) && payload.valid_for_seconds >= 1 && payload.valid_for_seconds <= 900;
  if (operation === 'authorize_context')
    return keys(payload,['session_token','expected_config_version','basis','max_total_usd',
      'valid_for_seconds','max_rounds']) && token(payload.session_token) &&
      typeof payload.expected_config_version === 'string' && UUID.test(payload.expected_config_version) &&
      validContextBasis(payload.basis) && payload.max_rounds === 1 &&
      typeof payload.max_total_usd === 'string' && payload.max_total_usd.length <= 64 &&
      Number.isSafeInteger(payload.valid_for_seconds) && payload.valid_for_seconds >= 1 &&
      payload.valid_for_seconds <= 900;
  const judge = operation === 'authorize_judge';
  if ((!judge && operation !== 'authorize') || !keys(payload,['session_token','expected_config_version',
    'basis','max_total_usd','valid_for_seconds'])) return false;
  const basis = payload.basis;
  return token(payload.session_token) && typeof payload.expected_config_version === 'string' &&
    UUID.test(payload.expected_config_version) && keys(basis,['request_id','expected_scope',
      'expected_composer_revision','content_sha256',...(judge?['purpose']:[])]) &&
    (!judge || basis.purpose === 'primary_intent') && typeof basis.request_id === 'string' &&
    UUID.test(basis.request_id) && object(basis.expected_scope) &&
    Number.isSafeInteger(basis.expected_composer_revision) && basis.expected_composer_revision >= 0 &&
    typeof basis.content_sha256 === 'string' && SHA256.test(basis.content_sha256) &&
    typeof payload.max_total_usd === 'string' && payload.max_total_usd.length <= 64 &&
    Number.isSafeInteger(payload.valid_for_seconds) && payload.valid_for_seconds >= 1 &&
    payload.valid_for_seconds <= 900;
}

class ModelControl {
  constructor({nonce,write,onReady,onFatal,timeoutMs=10000}) {
    this.nonce=nonce; this.write=write; this.onReady=onReady; this.onFatal=onFatal;
    this.timeoutMs=timeoutMs; this.sequence=0; this.buffer=Buffer.alloc(0);
    this.ready=false; this.enabled=false; this.judgeEnabled=false; this.judgeAuthorizationEnabled=false;
    this.closed=false; this.failed=false; this.pending=null;
  }
  _finish(error, result) {
    const pending=this.pending;
    if (!pending) return;
    this.pending=null; clearTimeout(pending.timer);
    if (error) pending.reject(error); else pending.resolve(result);
  }
  fail(code='BACKEND_PROTOCOL') {
    if (this.closed || this.failed) return;
    this.failed=true; this.buffer=Buffer.alloc(0);
    this._finish(new Error(code));
    this.onFatal(code);
  }
  close() {
    this.closed=true; this.buffer=Buffer.alloc(0);
    this._finish(new Error('BACKEND_STOPPED'));
  }
  end() {
    this.fail(this.buffer.length ? 'BACKEND_PROTOCOL' : 'BACKEND_EXITED');
  }
  feed(chunk) {
    if (this.closed || this.failed) return;
    if (!Buffer.isBuffer(chunk)) return this.fail();
    let offset=0;
    while (offset < chunk.length && !this.closed && !this.failed) {
      const end=chunk.indexOf(10,offset);
      const part=chunk.subarray(offset,end < 0 ? chunk.length : end);
      if (this.buffer.length+part.length+(end < 0 ? 0 : 1) > 8192) return this.fail();
      this.buffer=Buffer.concat([this.buffer,part]);
      if (end < 0) return;
      const line=this.buffer; this.buffer=Buffer.alloc(0);
      this._line(line); offset=end+1;
    }
  }
  _line(bytes) {
    try {
      const line=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
      const value=JSON.parse(line);
      if (JSON.stringify(value) !== line || !object(value)) throw new Error();
      if (value.event === 'error') {
        if (!keys(value,['event','code']) || typeof value.code !== 'string') throw new Error();
        return this.fail('BACKEND_REJECTED');
      }
      if (!this.ready) {
        const fields=['event','port','nonce'];
        const hasMain=Object.hasOwn(value,'control_protocol'),hasJudge=Object.hasOwn(value,'judge_control_protocol');
        const hasJudgeAuthorization=Object.hasOwn(value,'judge_authorization_protocol');
        if (hasMain) fields.push('control_protocol');
        if (hasJudge) fields.push('judge_control_protocol');
        if (hasJudgeAuthorization) fields.push('judge_authorization_protocol');
        if (!keys(value,fields) || value.event !== 'ready' || value.nonce !== this.nonce ||
            !Number.isSafeInteger(value.port) || value.port < 1 || value.port > 65535 ||
            (hasMain && value.control_protocol !== PROTOCOL) ||
            (hasJudge && (!hasMain || value.judge_control_protocol !== JUDGE_PROTOCOL)) ||
            (hasJudgeAuthorization && (!hasJudge || value.judge_authorization_protocol !== JUDGE_AUTH_PROTOCOL))) throw new Error();
        this.ready=true; this.enabled=hasMain; this.judgeEnabled=hasJudge;
        this.judgeAuthorizationEnabled=hasJudgeAuthorization;
        this.onReady(value); return;
      }
      if (!this.pending || value.event !== 'model-control-result' || value.protocol !== PROTOCOL ||
          value.nonce !== this.nonce || !Number.isSafeInteger(value.sequence) ||
          value.sequence !== this.pending.sequence) throw new Error();
      const base=['event','protocol','nonce','sequence','ok'];
      let result;
      if (value.ok === false) {
        if (!keys(value,[...base,'code']) || typeof value.code !== 'string') throw new Error();
        result={ok:false,code:CODES.has(value.code) ? value.code : 'BLOCKED_LIVE'};
      } else if (value.ok === true && STATUSES[this.pending.operation].includes(value.status)) {
        const fields=[...base,'status'];
        if (value.status === 'configured') fields.push('config_sha256','config_version');
        if (!keys(value,fields)) throw new Error();
        result={ok:true,status:value.status};
        if (value.status === 'configured') {
          if (typeof value.config_sha256 !== 'string' || !SHA256.test(value.config_sha256) ||
              typeof value.config_version !== 'string' || !UUID.test(value.config_version)) throw new Error();
          result.config_sha256=value.config_sha256; result.config_version=value.config_version;
        }
      } else throw new Error();
      this._finish(null,result);
    } catch { this.fail(); }
  }
  request(operation,payload) {
    if (this.closed || this.failed || !this.ready || !this.enabled) return Promise.resolve(blocked());
    if ((operation === 'configure_judge' || operation === 'disable_judge') && !this.judgeEnabled) return Promise.resolve(blocked());
    if ((operation === 'authorize_judge' || operation === 'revoke_judge') && !this.judgeAuthorizationEnabled) return Promise.resolve(blocked());
    if (this.pending) return Promise.resolve({ok:false,code:'STATE_CONFLICT'});
    let line;
    const sequence=this.sequence+1;
    try {
      if (!Number.isSafeInteger(sequence) || !validPayload(operation,payload)) return Promise.resolve(blocked());
      line=JSON.stringify({event:'model-control',protocol:PROTOCOL,nonce:this.nonce,sequence,operation,payload})+'\n';
      if (Buffer.byteLength(line,'utf8') > (operation==='authorize_material'?524288:32768)) return Promise.resolve(blocked());
    } catch { return Promise.resolve(blocked()); }
    this.sequence=sequence;
    return new Promise((resolve,reject) => {
      this.pending={sequence,operation,resolve,reject,
        timer:setTimeout(() => this.fail('BACKEND_CONTROL_TIMEOUT'),this.timeoutMs)};
      try { this.write(line); } catch { this.fail('BACKEND_PIPE_CLOSED'); }
    });
  }
}

module.exports={ModelControl};
