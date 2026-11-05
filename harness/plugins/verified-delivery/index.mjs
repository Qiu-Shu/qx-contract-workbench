import {createRequire} from 'node:module';
import {realpathSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {guardStream} from './core.mjs';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const local=createRequire(join(root,'package.json'));
const dsh=createRequire(realpathSync(local.resolve('@deepseek-ai/dsh/package.json')));
const base=createRequire(dsh.resolve('@deepseek-ai/dsh-base/package.json'));
const {isAgentLoopRequest}=await import(pathToFileURL(base.resolve('@deepseek-ai/dsh-llm')).href);
export const name='qx-verified-delivery';
export const inject=['llm'];
export function apply(ctx,config={}){
 if(!config.workspace)throw Error('受约束交付需要当前工作区。');
 ctx.on('llm/stream',(options,next)=>isAgentLoopRequest(options)?guardStream(options,next,config.workspace):next());
}
