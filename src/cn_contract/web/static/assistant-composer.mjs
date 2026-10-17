// Keep the native textarea and its selection; composition Enter is never send.
export function bindComposer({input, form, onEdit, onSend}) {
  let composing = false, suppressUntil = 0;
  const start = ()=>{ composing = true; };
  const end = ()=>{ composing = false; suppressUntil = performance.now()+150; onEdit(input.value); };
  const edit = ()=>{ if (!composing) onEdit(input.value); };
  const keydown = event=>{
    if (event.key !== 'Enter') return;
    if (composing || event.isComposing || event.keyCode === 229) return;
    if (event.shiftKey) return;
    event.preventDefault();
    if (event.repeat || performance.now() < suppressUntil) return;
    onSend();
  };
  const submit = event=>{ event.preventDefault(); if (!composing) onSend(); };
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
