// Identity comes from HttpOnly cookies. Never persist passwords or CSRF in browser storage.
import {IdentityEpoch} from './session-state.js';
import {openAdmin} from './account-admin.js';
const epoch=new IdentityEpoch();let state=null,dialog=null,button=null,pending=null,resolveLogin=null,rejectLogin=null,register=false,refreshSerial=0;
export const currentSession=()=>state;
export const captureIdentity=()=>epoch.capture();
export const checkIdentity=value=>epoch.check(value);
const channel=typeof document!=='undefined'&&typeof BroadcastChannel!=='undefined'?new BroadcastChannel('aeroblade-identity'):null;
if(channel)channel.onmessage=async event=>{if(event.data?.userId!==(state?.user_id||null))update({authenticated:false},false);try{await refreshSession(false);}catch{update({authenticated:false},false);}};
function update(next,broadcast=true){
  const previous=state;state=next;const changed=epoch.update(next.authenticated?next.user_id:null);
  if(changed&&broadcast)channel?.postMessage({userId:next.user_id||null});
  if(button)button.textContent=next.authenticated?`账号 · ${next.username}`:'登录 / 注册';
  if(typeof document!=='undefined'&&changed){
    // Always clear the old identity before loading the new one, even A -> B.
    if(previous?.authenticated)document.dispatchEvent(new CustomEvent('aeroblade:sessionchange',{detail:{authenticated:false,userId:null,generation:epoch.capture()}}));
    document.dispatchEvent(new CustomEvent('aeroblade:sessionchange',{detail:{authenticated:!!next.authenticated,userId:next.user_id||null,generation:epoch.capture()}}));
  }
}
async function authRequest(path,options={}){
  const response=await fetch('/api/session'+path,{...options,credentials:'same-origin',redirect:'error',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
  if([404,405,501].includes(response.status))throw Error('当前页面未连接新版登录后端，请检查部署。');
  let data;try{data=await response.json();}catch{throw Error('平台登录服务未返回有效响应。');}
  if(!response.ok)throw Error(data.error||'登录请求失败');return data;
}
export async function refreshSession(broadcast=true){const serial=++refreshSerial,value=epoch.capture();const result=await authRequest('');if(serial!==refreshSerial) return state;epoch.check(value);update(result,broadcast);return result;}
export async function ensureSession(){
  if(pending)return pending;
  const current=await refreshSession();if(current?.authenticated)return current;
  if(!dialog)initSessionUI();
  if(!pending)pending=new Promise((resolve,reject)=>{resolveLogin=resolve;rejectLogin=reject;});
  render();if(!dialog.open)dialog.showModal();return pending;
}
export async function sessionFetch(url,options={}){
  const startingIdentity=epoch.capture(),startedAuthenticated=!!state?.authenticated;
  const current=await ensureSession();if(startedAuthenticated)epoch.check(startingIdentity);const identity=epoch.capture();
  if(options.signal?.aborted)throw new DOMException('请求已停止','AbortError');
  const method=(options.method||'GET').toUpperCase();
  const response=await fetch(url,{...options,credentials:'same-origin',redirect:'error',headers:{...options.headers,...(method!=='GET'?{'X-CSRF-Token':current.csrf}:{})}});
  epoch.check(identity);
  if(response.status===401){update({authenticated:false});return response;}
  const parse=response.json.bind(response);response.json=async()=>{epoch.check(identity);const data=await parse();epoch.check(identity);return data;};
  return response;
}
function render(){
  if(!dialog)return;const $=s=>dialog.querySelector(s),setup=state?.setup_required,auth=!!state?.authenticated,creating=setup||register;
  $('#session-title').textContent=auth?'我的账号':setup?'创建管理员账号':register?'邀请码注册':'登录 AeroBlade';
  $('#session-intro').textContent=auth?`${state.username} · ${state.role==='admin'?'管理员':'普通用户'}。模型配置与个人数据属于当前账号。`:register?'使用管理员提供的邀请码创建自己的账号。':'登录后访问自己的模型配置、设计方案与对话。';
  $('#session-form').hidden=auth||!!(setup&&!state.setup_allowed);$('#session-logout').hidden=!auth;$('#session-password-form').hidden=!auth;
  $('#session-confirm-row').hidden=!creating;$('#session-confirm').required=!!creating;
  $('#session-invite-row').hidden=!register||setup;$('#session-invite').required=register&&!setup;
  $('#session-password').autocomplete=creating?'new-password':'current-password';
  $('#session-submit').textContent=creating?'创建并登录':'登录';
  $('#session-switch').hidden=auth||setup;$('#session-switch').textContent=register?'已有账号，去登录':'持有邀请码？注册账号';
  $('#session-admin').hidden=!auth||state.role!=='admin';
  $('#session-message').textContent=setup&&!state.setup_allowed?'请让部署者初始化管理员账号。':'';
}
export function initSessionUI(){
  if(dialog)return;
  button=document.createElement('button');button.id='account-menu';button.textContent='登录 / 注册';document.querySelector('.header-actions').prepend(button);
  dialog=document.createElement('dialog');dialog.id='session-dialog';dialog.className='session-dialog';
  dialog.innerHTML=`<div class="session-heading"><h2 id="session-title">登录 AeroBlade</h2><button id="session-close" type="button" aria-label="关闭登录窗口">×</button></div><p id="session-intro"></p><form id="session-form"><label for="session-username">用户名</label><input id="session-username" autocomplete="username" required minlength="3" maxlength="64" pattern="[A-Za-z0-9_.-]+" placeholder="字母、数字、点、下划线"><label for="session-password">密码</label><input id="session-password" type="password" autocomplete="current-password" required minlength="12" maxlength="1024" placeholder="至少12个字符"><div id="session-confirm-row" hidden><label for="session-confirm">确认密码</label><input id="session-confirm" type="password" autocomplete="new-password" maxlength="1024"></div><div id="session-invite-row" hidden><label for="session-invite">邀请码</label><input id="session-invite" autocomplete="off" maxlength="100" placeholder="8位邀请码（兼容旧版长码）"></div><button id="session-submit" class="primary" type="submit">登录</button></form><button id="session-switch" type="button">持有邀请码？注册账号</button><button id="session-admin" type="button" hidden>管理用户与邀请码</button><form id="session-password-form" hidden><details><summary>修改我的密码</summary><label for="password-current">当前密码</label><input id="password-current" type="password" autocomplete="current-password" required><label for="password-new">新密码（至少12字符）</label><input id="password-new" type="password" autocomplete="new-password" required minlength="12" maxlength="1024"><button type="submit">修改并重新登录</button></details></form><button id="session-logout" type="button" hidden>退出登录</button><p id="session-message" role="status" aria-live="polite"></p>`;
  document.body.append(dialog);const $=s=>dialog.querySelector(s);
  button.onclick=async()=>{try{await refreshSession();register=false;render();if(!dialog.open)dialog.showModal();}catch(e){render();$('#session-message').textContent=e.message;if(!dialog.open)dialog.showModal();}};
  $('#session-close').onclick=()=>dialog.close();$('#session-switch').onclick=()=>{register=!register;render();};
  $('#session-admin').onclick=async()=>{dialog.close();try{await openAdmin();}catch(e){alert(e.message);}};
  dialog.addEventListener('close',()=>{for(const input of dialog.querySelectorAll('input[type=password]'))input.value='';$('#session-invite').value='';if(rejectLogin)rejectLogin(Error('已取消登录'));pending=null;resolveLogin=null;rejectLogin=null;});
  $('#session-form').onsubmit=async event=>{
    event.preventDefault();const setup=!!state?.setup_required;
    if((setup||register)&&$('#session-password').value!==$('#session-confirm').value){$('#session-message').textContent='两次输入的密码不一致。';return;}
    $('#session-submit').disabled=true;$('#session-switch').disabled=true;$('#session-message').textContent='正在处理…';
    const serial=++refreshSerial;
    try{
      const payload={username:$('#session-username').value.trim(),password:$('#session-password').value};if(register&&!setup)payload.invite=$('#session-invite').value.trim();
      const data=await authRequest(setup?'/setup':register?'/register':'/login',{method:'POST',body:JSON.stringify(payload)});
      if(serial!==refreshSerial)return;update(data);const done=resolveLogin;resolveLogin=null;rejectLogin=null;pending=null;dialog.close();if(done)done(data);
    }catch(e){$('#session-message').textContent=e.message;}finally{$('#session-submit').disabled=false;$('#session-switch').disabled=false;$('#session-password').value='';$('#session-confirm').value='';}
  };
  $('#session-password-form').onsubmit=async event=>{
    event.preventDefault();const submit=event.submitter;submit.disabled=true;
    try{const response=await sessionFetch('/api/session/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:$('#password-current').value,new_password:$('#password-new').value})});const data=await response.json();if(!response.ok)throw Error(data.error);update({authenticated:false});render();$('#session-message').textContent='密码已修改，请重新登录。';}catch(e){$('#session-message').textContent=e.message;}finally{submit.disabled=false;$('#password-current').value='';$('#password-new').value='';}
  };
  $('#session-logout').onclick=async()=>{const identity=epoch.capture();$('#session-logout').disabled=true;try{await authRequest('/logout',{method:'POST',body:'{}',headers:{'X-CSRF-Token':state.csrf}});epoch.check(identity);update({authenticated:false});dialog.close();}catch(e){$('#session-message').textContent=e.message;}finally{$('#session-logout').disabled=false;}};
  refreshSession().catch(()=>{button.title='登录需要可用的平台后端';});
}
