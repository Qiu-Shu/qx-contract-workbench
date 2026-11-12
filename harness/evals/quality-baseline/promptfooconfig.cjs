const path=require('node:path');
module.exports={description:'24 synthetic cases through the installed Harness agent and real MCP tools',
 prompts:['Execute repository-owned synthetic case {{caseId}}'],
 providers:[{id:'file://provider.cjs',config:{mode:process.env.QX_EVAL_MODE||'scripted'}}],
 // Promptfoo 0.125.1 assertion loader treats a Windows drive colon as an export separator.
 tests:require('./cases.cjs').map(c=>({description:c.id,vars:{caseId:c.id},assert:[{type:'javascript',value:'file://assertions.js'}]})),
 evaluateOptions:{maxConcurrency:1,cache:false},sharing:false};
