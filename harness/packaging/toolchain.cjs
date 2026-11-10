const path=require('node:path');
const {createRequire}=require('node:module');
const root=process.env.QX_BUILD_MODULES?path.resolve(process.env.QX_BUILD_MODULES):path.join(__dirname,'node_modules');
const load=createRequire(path.join(root,'__qx_build__.cjs'));
const packageDir=name=>path.dirname(load.resolve(name+'/package.json'));
async function sevenZip(){return load('app-builder-lib/out/toolsets/7zip.js').getPath7za();}
module.exports={load,packageDir,sevenZip};
