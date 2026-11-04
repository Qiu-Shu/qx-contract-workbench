// Deterministic transport/artifact checks only. Legal quality requires separate review.
function assessFunctional({scenario,completed,actual,rounds}){
 const succeeded=rounds.flatMap(r=>r.toolResults||[]).filter(t=>t.result?.executed===true&&t.result.is_error===false&&t.result.result?.saved!==false&&t.result.result?.error===undefined);
 const names=succeeded.map(t=>t.name),drafts=actual?.drafts||[];
 const genericSavedIds=new Set(succeeded.filter(t=>t.name==='record_case_note').map(t=>t.result.result?.id).filter(Boolean));
 const outputs=succeeded.flatMap(t=>{const r=t.result.result||{};return [['path','sha256'],['word_path','word_sha256'],['internal_path','internal_sha256']].filter(([key])=>typeof r[key]==='string'&&/\.docx$/i.test(r[key])).map(([key,digest])=>({path:r[key],sha256:r[digest]}));});
 const readable=output=>drafts.some(d=>d.path===output.path&&typeof d.text==='string'&&d.text.trim()&&typeof d.sha256==='string'&&(!output.sha256||output.sha256===d.sha256));
 const functionalChecks={modelFinished:completed===true,finalized:actual?.finalized===true,
  sourceUnchanged:actual?.source_unchanged===true,completeNoteReadback:actual?.notes_complete===true,
  requiredToolsUsed:scenario.required_tools.every(name=>names.includes(name)),
  wordProduced:outputs.length>0&&outputs.every(readable),
  noteSaved:!scenario.expected_kind||(actual?.case?.notes||[]).some(n=>(n.kind===scenario.expected_kind||genericSavedIds.has(n.id))&&typeof n.content==='string'&&n.content.trim())};
 return {functionalChecks,functionalPassed:Object.values(functionalChecks).every(Boolean),qualityStatus:'not_reviewed',qualityPassed:null,
  observedNoteKinds:[...new Set((actual?.case?.notes||[]).map(n=>n.kind))],
  qualityNotice:'Transport completion and file persistence are not semantic/legal quality approval. Review actual note and Word text against the scenario.'};
}
module.exports={assessFunctional};
