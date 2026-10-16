const form = document.querySelector('#setup');
const retry = document.querySelector('#retry');
let current;
function render(state) {
  if (!state) return;
  current = state;
  form.hidden = state.mode !== 'setup';
  retry.hidden = state.mode !== 'error';
  document.querySelector('#status').textContent = state.message || '';
  document.querySelector('#library-path').textContent = state.library || '尚未连接。已有案例、法规库可直接选择目录。';
  document.querySelector('#data-path').textContent = state.dataParent || '';
  for (const button of document.querySelectorAll('button')) button.disabled = state.mode === 'loading';
}
window.desktopSetup.onState(render);
window.desktopSetup.state().then(render);
document.querySelector('#library').addEventListener('click',()=>window.desktopSetup.chooseLibrary());
retry.addEventListener('click',()=>window.desktopSetup.start());
form.addEventListener('submit',async event=>{
  event.preventDefault();
  const error = document.querySelector('#validation');
  const username = document.querySelector('#username').value;
  const password = document.querySelector('#password').value;
  if (username !== username.trim() || !username || /[\p{Cc}\p{Cf}]/u.test(username)) {
    error.hidden = false; error.textContent = '用户名不能有首尾空格或控制字符。'; return;
  }
  if (password !== document.querySelector('#confirm').value) {
    error.hidden = false; error.textContent = '两次密码不一致，请重新输入。'; document.querySelector('#confirm').focus(); return;
  }
  error.hidden = true;
  const pending = window.desktopSetup.start({username,password});
  document.querySelector('#password').value = ''; document.querySelector('#confirm').value = '';
  render({...current,mode:'loading',message:'正在建立账户…'});
  await pending;
});
