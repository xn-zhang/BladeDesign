// Authentication secrets are carried only by HttpOnly cookies, never browser storage.
let state=null,dialog=null,button=null,pending=null,resolveLogin=null,rejectLogin=null;
function update(next){
  const previous=state;state=next;
  if(button)button.textContent=next.authenticated?`账号 · ${next.username}`:'登录';
  if(typeof document!=='undefined'&&previous?.authenticated!==next.authenticated)
    document.dispatchEvent(new CustomEvent('aeroblade:sessionchange',{detail:{authenticated:next.authenticated}}));
}
async function authRequest(path,options={}){
  const response=await fetch('/api/session'+path,{...options,credentials:'same-origin',redirect:'error',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
  if([404,405,501].includes(response.status))throw Error('当前页面未连接登录后端，请启动新版平台服务或配置同源 API 转发。');
  let data;try{data=await response.json();}catch{throw Error('平台登录服务未返回有效响应。');}
  if(!response.ok)throw Error(data.error||'登录请求失败');
  return data;
}
export async function refreshSession(){const result=await authRequest('');update(result);return result;}

export async function ensureSession(){
  if(pending)return pending;
  const current=await refreshSession();if(current.authenticated)return current;
  if(!dialog)initSessionUI();
  if(!pending)pending=new Promise((resolve,reject)=>{resolveLogin=resolve;rejectLogin=reject;});
  render();if(!dialog.open)dialog.showModal();return pending;
}

export async function sessionFetch(url,options={}){
  const current=await ensureSession();
  if(options.signal?.aborted)throw new DOMException('请求已停止','AbortError');
  const method=(options.method||'GET').toUpperCase();
  const response=await fetch(url,{...options,credentials:'same-origin',redirect:'error',headers:{...options.headers,...(method!=='GET'?{'X-CSRF-Token':current.csrf}:{})}});
  if(response.status===401)update({authenticated:false});
  return response;
}

function render(){
  if(!dialog)return;
  const setup=state?.setup_required;
  dialog.querySelector('#session-title').textContent=state?.authenticated?'平台账号':setup?'创建管理员账号':'登录 AeroBlade';
  dialog.querySelector('#session-intro').textContent=state?.authenticated?`当前登录：${state.username}`:setup?'首次使用，请创建管理员账号。以后在这台或其他电脑上使用同一账号登录。':'登录后即可管理模型配置和使用真实模型，无需填写平台令牌。';
  dialog.querySelector('#session-form').hidden=!!state?.authenticated||!!(setup&&!state.setup_allowed);
  dialog.querySelector('#session-logout').hidden=!state?.authenticated;
  dialog.querySelector('#session-confirm-row').hidden=!setup;
  dialog.querySelector('#session-confirm').required=!!setup;
  dialog.querySelector('#session-submit').textContent=setup?'创建并登录':'登录';
  dialog.querySelector('#session-message').textContent=setup&&!state.setup_allowed?'管理员尚未初始化，请让部署者在后端配置管理员账号后重启服务。':'';
}

export function initSessionUI(){
  if(dialog)return;
  button=document.createElement('button');button.id='account-menu';button.textContent='登录';document.querySelector('.header-actions').prepend(button);
  dialog=document.createElement('dialog');dialog.id='session-dialog';dialog.className='session-dialog';
  dialog.innerHTML=`<div class="session-heading"><h2 id="session-title">登录 AeroBlade</h2><button id="session-close" type="button" aria-label="关闭登录窗口">×</button></div><p id="session-intro"></p><form id="session-form"><label for="session-username">用户名</label><input id="session-username" autocomplete="username" required minlength="3" maxlength="64" pattern="[A-Za-z0-9_.-]+" value="admin"><label for="session-password">登录密码</label><input id="session-password" type="password" autocomplete="current-password" required minlength="12" maxlength="1024" placeholder="至少12个字符"><div id="session-confirm-row" hidden><label for="session-confirm">确认密码</label><input id="session-confirm" type="password" autocomplete="new-password" maxlength="1024"></div><button id="session-submit" class="primary" type="submit">登录</button></form><button id="session-logout" type="button" hidden>退出登录</button><p id="session-message" role="status" aria-live="polite"></p>`;
  document.body.append(dialog);
  const $=selector=>dialog.querySelector(selector);
  button.onclick=async()=>{try{await refreshSession();render();dialog.showModal();}catch(e){render();$('#session-message').textContent=e.message;if(!dialog.open)dialog.showModal();}};
  $('#session-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{
    $('#session-password').value='';$('#session-confirm').value='';
    if(rejectLogin)rejectLogin(new Error('已取消登录'));
    pending=null;resolveLogin=null;rejectLogin=null;
  });
  $('#session-form').onsubmit=async event=>{
    event.preventDefault();const setup=!!state?.setup_required;
    if(setup&&$('#session-password').value!==$('#session-confirm').value){$('#session-message').textContent='两次输入的密码不一致。';return;}
    $('#session-submit').disabled=true;$('#session-message').textContent='正在登录…';
    try{
      const data=await authRequest(setup?'/setup':'/login',{method:'POST',body:JSON.stringify({username:$('#session-username').value.trim(),password:$('#session-password').value})});
      update(data);const done=resolveLogin;resolveLogin=null;rejectLogin=null;pending=null;dialog.close();if(done)done(data);
    }catch(e){$('#session-message').textContent=e.message;}
    finally{$('#session-submit').disabled=false;$('#session-password').value='';$('#session-confirm').value='';}
  };
  $('#session-logout').onclick=async()=>{
    $('#session-logout').disabled=true;
    try{await authRequest('/logout',{method:'POST',body:'{}',headers:{'X-CSRF-Token':state.csrf}});update({authenticated:false});dialog.close();}
    catch(e){$('#session-message').textContent=e.message;}finally{$('#session-logout').disabled=false;}
  };
  refreshSession().catch(()=>{button.title='登录需要可用的平台后端';});
}
