// Keep the native textarea and its selection; composition Enter is never send.
export function bindComposer({input, form, onEdit, onSend, beforeSend=()=>true}) {
  let composing = false, suppressUntil = 0, sending=false;
  const send=async()=>{
    if(sending)return false;
    sending=true;
    try{if(await beforeSend())return await onSend();return false;}
    finally{sending=false;}
  };
  const start = ()=>{ composing = true; };
  const end = ()=>{ composing = false; suppressUntil = performance.now()+150; onEdit(input.value); };
  const edit = ()=>{ if (!composing) onEdit(input.value); };
  const keydown = event=>{
    if (event.key !== 'Enter') return;
    if (composing || event.isComposing || event.keyCode === 229) return;
    if (event.shiftKey) return;
    event.preventDefault();
    if (event.repeat || performance.now() < suppressUntil) return;
    return send();
  };
  const submit = event=>{ event.preventDefault(); if (!composing) return send(); };
  input.addEventListener('compositionstart',start);
  input.addEventListener('compositionend',end);
  input.addEventListener('input',edit);
  input.addEventListener('keydown',keydown);
  form.addEventListener('submit',submit);
  return {
    isComposing:()=>composing,
    dispose() {
      input.removeEventListener('compositionstart',start);
      input.removeEventListener('compositionend',end);
      input.removeEventListener('input',edit);
      input.removeEventListener('keydown',keydown);
      form.removeEventListener('submit',submit);
    },
  };
}
