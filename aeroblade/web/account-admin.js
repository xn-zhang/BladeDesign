import {sessionFetch,currentSession,ensureSession} from './session.js';
let dialog,serial=0;
async function api(path,data){const response=await sessionFetch('/api/admin/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'操作失败');return result;}
function el(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
export async function openAdmin(){
  await ensureSession();if(currentSession()?.role!=='admin')throw Error('需要管理员权限');
  if(!dialog){
    dialog=el('dialog');dialog.className='session-dialog account-admin';dialog.innerHTML='<div class="session-heading"><h2>用户与邀请码</h2><button data-close aria-label="关闭">×</button></div><button data-create class="primary">生成邀请码</button><p>邀请码有效期7天，最多注册10个账号。</p><div data-code hidden><label>新邀请码（仅此次显示）<input readonly autocomplete="off"></label><button data-copy>复制邀请码</button></div><p data-message role="status"></p><h3>邀请码</h3><div data-invites></div><h3>用户</h3><div data-users></div>';document.body.append(dialog);
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{serial++;dialog.querySelector('[data-code] input').value='';dialog.querySelector('[data-code]').hidden=true;});
    document.addEventListener('aeroblade:sessionchange',()=>{if(dialog.open)dialog.close();});
    dialog.querySelector('[data-copy]').onclick=async()=>{try{await navigator.clipboard.writeText(dialog.querySelector('[data-code] input').value);message('已复制，可分享给最多10名测试者。');}catch{message('请选中邀请码手动复制。');}};
    dialog.querySelector('[data-create]').onclick=async event=>{const id=serial;event.target.disabled=true;try{const invite=await api('invites',{});if(id!==serial)return;dialog.querySelector('[data-code]').hidden=false;dialog.querySelector('[data-code] input').value=invite.code;await load();}catch(e){message(e.message);}finally{event.target.disabled=false;}};
  }
  dialog.showModal();await load();
}
function message(value){if(dialog)dialog.querySelector('[data-message]').textContent=value;}
async function load(){
  const id=++serial;
  try{
    const [invites,users]=await Promise.all([api('invites'),api('users')]);if(id!==serial||!dialog.open)return;
    const group=dialog.querySelector('[data-invites]');group.replaceChildren();
    for(const i of invites.invites){const row=el('div');row.className='account-row';row.append(el('span',`${i.id.slice(0,8)} · ${i.revoked?'已撤销':i.expires_at*1000<Date.now()?'已过期':i.used_count>=i.max_uses?'次数已满':'可使用'} · 已用 ${i.used_count}/${i.max_uses}`));if(i.used_count<i.max_uses&&!i.revoked&&i.expires_at*1000>Date.now()){const b=el('button','撤销');b.onclick=()=>act(b,'invites/'+i.id+'/revoke',{});row.append(b);}group.append(row);}
    const people=dialog.querySelector('[data-users]');people.replaceChildren();
    for(const u of users.users){const row=el('div');row.className='account-row';row.append(el('span',`${u.username} · ${u.role==='admin'?'管理员':u.disabled?'已禁用':'普通用户'}`));if(u.role!=='admin'){const b=el('button',u.disabled?'恢复':'禁用');b.onclick=()=>act(b,'users/'+u.id+'/status',{disabled:!u.disabled});row.append(b);}people.append(row);}
  }catch(e){if(id===serial)message(e.message);}
}
async function act(button,path,data){button.disabled=true;try{await api(path,data);await load();}catch(e){message(e.message);}finally{button.disabled=false;}}
