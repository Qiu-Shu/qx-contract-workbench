const form=document.querySelector('form'),key=document.querySelector('#api-key'),status=document.querySelector('#status'),submit=document.querySelector('#submit');
document.querySelector('#reveal').onclick=event=>{
  const visible=key.type==='password';key.type=visible?'text':'password';
  event.target.textContent=visible?'隐藏':'显示';event.target.setAttribute('aria-pressed',String(visible));
};
document.querySelector('#get-key').onclick=()=>window.setup.openKeys();
form.onsubmit=async event=>{
  event.preventDefault();submit.disabled=true;key.disabled=true;status.textContent='正在验证账户并启动工作台…';
  try{const result=await window.setup.save(key.value);status.textContent=result.message||'';if(result.ok)key.value='';}
  catch{status.textContent='配置未完成，请重新打开工作台后重试。';}
  finally{submit.disabled=false;key.disabled=false;}
};
