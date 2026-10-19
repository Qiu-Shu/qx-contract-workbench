// Synthetic owned child: stdin and stdout only, no service or network.
const readline = require('node:readline');
const input = readline.createInterface({ input: process.stdin });
const protocol = 'qx-model-control-v1';
const version = '11111111-2222-4333-8444-555555555555';
const mode = process.argv[2] || 'normal';
let config;
let sequence=0;
function write(value) {
  const line=JSON.stringify(value)+'\n';
  if (mode === 'fragmented') {
    let index=0;
    const next=() => { process.stdout.write(line[index++]); if (index < line.length) setImmediate(next); };
    next();
  } else process.stdout.write(line);
}
input.on('line', line => {
  const message = JSON.parse(line);
  if (!config) {
    config = message;
    const ready={event:'ready',port:19022,nonce:config.nonce};
    if (mode !== 'legacy') ready.control_protocol=protocol;
    if (mode === 'extra-ready-frame') process.stdout.write(JSON.stringify(ready)+'\n{"event":"unexpected"}\n');
    else write(ready);
    return;
  }
  if (JSON.stringify(message) !== line || message.event !== 'model-control' || message.protocol !== protocol ||
      message.nonce !== config.nonce || message.sequence !== ++sequence ||
      Object.keys(message).sort().join(',') !== 'event,nonce,operation,payload,protocol,sequence') process.exit(4);
  if (mode === 'hang') return;
  const result = {event:'model-control-result',protocol,nonce:config.nonce,
    sequence:message.sequence,ok:true,status:{configure:'configured',disable:'disabled',
      authorize:'authorized',revoke:'revoked'}[message.operation]};
  if (message.operation === 'configure') Object.assign(result,
    {config_sha256:'a'.repeat(64),config_version:version});
  if (mode === 'bad-nonce') result.nonce='wrong';
  if (mode === 'partial-result') {
    process.stdout.write('{"event":"model-control-result"',() => process.exit(0)); return;
  }
  write(result);
});
input.on('close', () => {
  if (mode === 'bad-nonce') setInterval(() => {},1000); else process.exit(0);
});
