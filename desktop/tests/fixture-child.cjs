let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.includes('\n')) {
    const config = JSON.parse(input.trim());
    process.stdout.write(JSON.stringify({event:'ready',port:19022,nonce:config.bad ? 'wrong' : config.nonce})+'\n');
    input = '';
  }
});
process.stdin.on('end', () => process.exit(0));
