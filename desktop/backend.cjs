const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { EventEmitter } = require('node:events');

class Backend extends EventEmitter {
  constructor(executable, args = []) { super(); this.executable = executable; this.args = args; this.closing = false; }
  start(config) {
    if (this.child) return Promise.reject(new Error('BACKEND_ALREADY_STARTED'));
    const nonce = randomBytes(16).toString('hex');
    return new Promise((resolve, reject) => {
      let ready = false, settled = false, buffer = '';
      const fail = code => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error(code)); } };
      const timer = setTimeout(() => { fail('BACKEND_TIMEOUT'); void this.stop(); }, 60000);
      this.child = spawn(this.executable, this.args, { windowsHide:true, stdio:['pipe','pipe','pipe'],
        env:{...process.env, PYTHONIOENCODING:'utf-8'} });
      this.exited = new Promise(done => {
        this.child.once('close', () => {
          clearTimeout(timer); done(); fail('BACKEND_EXITED');
          if (ready && !this.closing) this.emit('failed');
        });
      });
      this.child.once('error', () => fail('BACKEND_START_FAILED'));
      this.child.stdin.on('error', () => fail('BACKEND_PIPE_CLOSED'));
      // Discard stderr without logging it: paths and credentials never reach logs.
      this.child.stderr.resume();
      this.child.stdout.setEncoding('utf8');
      this.child.stdout.on('data', chunk => {
        buffer += chunk;
        if (buffer.length > 8192) { fail('BACKEND_PROTOCOL'); void this.stop(); return; }
        const end = buffer.indexOf('\n');
        if (end < 0) return;
        const line = buffer.slice(0,end); buffer = buffer.slice(end+1);
        if (settled) return;
        try {
          const message = JSON.parse(line);
          if (message.event !== 'ready' || message.nonce !== nonce || !Number.isInteger(message.port)
              || message.port < 1 || message.port > 65535) throw new Error();
          settled = true; ready = true; clearTimeout(timer); resolve(message);
        } catch { fail('BACKEND_PROTOCOL'); void this.stop(); }
      });
      this.child.stdin.write(JSON.stringify({...config, nonce})+'\n');
    });
  }
  async stop() {
    this.closing = true;
    if (!this.child) return;
    this.child.stdin.end();
    let timer;
    await Promise.race([this.exited, new Promise(resolve => {
      timer = setTimeout(() => { this.child.kill(); resolve(); }, 20000);
    })]);
    clearTimeout(timer);
    await this.exited;
  }
}
module.exports = { Backend };
