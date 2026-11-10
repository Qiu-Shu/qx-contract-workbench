import {createRequire} from 'node:module';
import {realpathSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createDeliveryPaths} from './paths.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const local = createRequire(join(root, 'package.json'));
const dsh = createRequire(realpathSync(local.resolve('@deepseek-ai/dsh/package.json')));
const native = await import(pathToFileURL(dsh.resolve('@deepseek-ai/dsh-tool-present')).href);
export const name = 'qx-present';
export const inject = [...native.inject, 'sessionQuery'];

export function apply(ctx, config = {}) {
  const resolveFiles = createDeliveryPaths(ctx, config.workspace);
  native.apply({
    fs: ctx.fs, agents: ctx.agents, workingDirectory: ctx.workingDirectory,
    on: ctx.on.bind(ctx),
    tools: {register(tool) {
      const parameters = structuredClone(tool.parameters);
      parameters.properties.files.items.properties.path.description = 'Path of an existing regular file. Relative paths may refer to files generated in this Session; otherwise they use the Session working directory. Ambiguous names require a full path.';
      ctx.tools.register({...tool,
        parameters,
        async execute(args, exec) {
          if (!Array.isArray(args?.files) || !args.files.every(file => typeof file?.path === 'string')) return tool.execute(args, exec);
          const files = await resolveFiles(args.files, exec);
          return tool.execute({...args, files}, exec);
        },
      });
    }},
  }, {maxFiles: config.maxFiles ?? 8});
}
