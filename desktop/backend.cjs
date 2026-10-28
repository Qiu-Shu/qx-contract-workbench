const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { EventEmitter } = require('node:events');
const { ModelControl } = require('./model-control.cjs');

class Backend extends EventEmitter {
  constructor(executable, args = []) { super(); this.executable = executable; this.args = args; this.closing = false; }
  start(config) {
    if (this.closing) return Promise.reject(new Error('BACKEND_STOPPED'));
    if (this.child) return Promise.reject(new Error('BACKEND_ALREADY_STARTED'));
    const nonce = randomBytes(16).toString('hex');
    return new Promise((resolve, reject) => {
      let ready = false, settled = false, reported = false;
      const fail = code => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error(code)); } };
      const report = () => { if (ready && !this.closing && !reported) { reported=true; this.emit('failed'); } };
      const abort = code => {
        fail(code);
        if (this.child) this.child.kill();
        report();
      };
      const timer = setTimeout(() => this.control.fail('BACKEND_TIMEOUT'), 60000);
      this.control = new ModelControl({nonce,
        write: line => this.child.stdin.write(line,error => { if (error) this.control.fail('BACKEND_PIPE_CLOSED'); }),
        onReady: message => {
          ready=true; clearTimeout(timer);
          // Finish parsing this stdout chunk before publishing startup success.
          queueMicrotask(() => { if (!settled && !this.closing) { settled=true; resolve(message); } });
        },
        onFatal: abort});
      try {
        this.child = spawn(this.executable, this.args, { windowsHide:true, stdio:['pipe','pipe','pipe'],
          env:{...process.env, PYTHONIOENCODING:'utf-8'} });
      } catch { this.control.fail('BACKEND_START_FAILED'); return; }
      this.exited = new Promise(done => {
        this.child.once('close', () => {
          clearTimeout(timer); done(); fail('BACKEND_EXITED');
          this.control.end(); report();
        });
      });
      this.child.once('error', () => this.control.fail('BACKEND_START_FAILED'));
      this.child.stdin.on('error', () => this.control.fail('BACKEND_PIPE_CLOSED'));
      this.child.stdout.on('error', () => this.control.fail('BACKEND_PIPE_CLOSED'));
      this.child.stderr.on('error', () => this.control.fail('BACKEND_PIPE_CLOSED'));
      // Discard stderr without logging it: paths and credentials never reach logs.
      this.child.stderr.resume();
      this.child.stdout.on('data', chunk => this.control.feed(chunk));
      this.child.stdout.on('end', () => this.control.end());
      try { this.child.stdin.write(JSON.stringify({...config, nonce})+'\n'); }
      catch { this.control.fail('BACKEND_PIPE_CLOSED'); }
    });
  }
  configureJudge(payload) { return this._model('configure_judge',payload); }
  disableJudge() { return this._model('disable_judge',{}); }
  authorizeJudge(payload) { return this._model('authorize_judge',payload); }
  revokeJudge(payload) { return this._model('revoke_judge',payload); }
  configureModel(payload) { return this._model('configure',payload); }
  disableModel() { return this._model('disable',{}); }
  authorizeModel(payload) { return this._model('authorize',payload); }
  revokeModel(payload) { return this._model('revoke',payload); }
  authorizeContextModel(payload) { return this._model('authorize_context',payload); }
  authorizeMaterialModel(payload) { return this._model('authorize_material',payload); }
  authorizeProfileModel(payload) { return this._model('authorize_profile',payload); }
  startPersonalWeixin(payload) { return this._model('start_personal_weixin',payload); }
  disablePersonalWeixin() { return this._model('disable_personal_weixin',{}); }
  verifyPersonalWeixin(payload) { return this._model('verify_personal_weixin',payload); }
  _model(operation,payload) {
    return this.control ? this.control.request(operation,payload) : Promise.resolve({ok:false,code:'BLOCKED_LIVE'});
  }
  async stop() {
    this.closing = true;
    this.control?.close();
    if (!this.child) return;
    if (!this.stopping) this.stopping=(async () => {
      this.child.stdin.end();
      const timer=setTimeout(() => this.child.kill(),20000);
      try { await this.exited; } finally { clearTimeout(timer); }
    })();
    await this.stopping;
  }
}
module.exports = { Backend };
