import {readFileSync} from 'node:fs';
import {deliverProviderResponse} from './verified-delivery-harness.mjs';
const input=JSON.parse(readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(await deliverProviderResponse(input.messages,input.result,input.workspace)));
