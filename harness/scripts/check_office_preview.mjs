// Synthetic fixture conversion only; never reads case material or invokes a model.
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
const payload=resolve(process.argv[2]||'.local/package-updates-0.2.3/workbench');
const {createConverter}=await import(pathToFileURL(join(payload,'node_modules/@deepseek-ai/libreoffice-kit/lib/index.js')).href);
const converter=await createConverter({timeoutMs:120000});
try{
  if(process.argv[3]){
    const input=resolve(process.argv[3]),output=resolve(process.argv[4]);await mkdir(output,{recursive:true});
    for(const ext of ['docx','xlsx','pptx']){
      const source=join(input,`预览测试.${ext}`),target=join(output,`预览测试-${ext}.pdf`);
      const before=await readFile(source);
      const result=await converter.render({inputPath:source,outputPath:target});
      const pdf=await readFile(target);assert.ok(pdf.subarray(0,8).toString().startsWith('%PDF-'));
      assert.deepEqual(await readFile(source),before,'preview must not modify original');
      console.log(JSON.stringify({extension:ext,pdfBytes:pdf.length,backend:result.backend,missingFonts:result.missingFonts}));
    }
  }else console.log('Native Office engine initialization passed');
}finally{await converter.dispose()}
