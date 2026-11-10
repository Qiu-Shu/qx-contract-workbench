import {createRequire} from 'node:module';
import {realpathSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const harness=createRequire(realpathSync(new URL('../../node_modules/@deepseek-ai/dsh/package.json',import.meta.url)));
const require=createRequire(harness.resolve('@deepseek-ai/dsh-mcp-client'));
let sdk;
export function loadMcpSdk(){
  return sdk??={...require('@modelcontextprotocol/client'),...require('@modelcontextprotocol/client/stdio')};
}
export const {scrubbedParentEnv}=harness('@deepseek-ai/dsh-subprocess');
export const {scopeOf}=harness('@deepseek-ai/dsh-scope');
export const bridge=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-mcp-client')));
