const {evaluate}=require('./checks.cjs');
module.exports=(output,context)=>{
 const spec=require('./cases.cjs').find(c=>c.id===context.vars.caseId);
 try{return evaluate(JSON.parse(output),spec);}catch(error){return {pass:false,score:0,reason:error.message};}
};
