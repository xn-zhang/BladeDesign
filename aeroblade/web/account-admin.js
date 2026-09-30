import {sessionFetch,currentSession,ensureSession} from './session.js';
let dialog,serial=0,busy=false,modelConfigs={},policy={};
const names={general:'通用大模型',domain:'航发领域大模型'};
const actions={'invite.create':'生成邀请码','invite.update':'修改邀请码','invite.revoke':'撤销邀请码','user.disable':'禁用用户','user.enable':'恢复用户','user.logout':'强制退出','public_model.configure':'保存公共模型','public_model.clear':'清除公共模型','public_model.policy':'修改模型策略'};
const date=value=>new Date(value*1000).toLocaleString('zh-CN',{hour12:false});
const localDate=value=>{const d=new Date(value*1000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);};
const $=selector=>dialog.querySelector(selector);
function el(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
async function api(path,data){const response=await sessionFetch('/api/admin/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'操作失败');return result;}
function message(value,error=false){$('[data-message]').textContent=value;$('[data-message]').classList.toggle('error',error);}
function setBusy(value){busy=value;for(const node of dialog.querySelectorAll('input,select,button'))if(!node.matches('[data-close]'))node.disabled=value;syncAuth();}
function syncAuth(){if(dialog)$('[data-key]').disabled=busy||$('[data-auth]').value==='none';}
function tab(name){for(const button of dialog.querySelectorAll('[data-tab]'))button.setAttribute('aria-selected',String(button.dataset.tab===name));for(const panel of dialog.querySelectorAll('[data-panel]'))panel.hidden=panel.dataset.panel!==name;}
export async function openAdmin(){
  await ensureSession();if(currentSession()?.role!=='admin')throw Error('需要管理员权限');
  if(!dialog){
    dialog=el('dialog',undefined,'session-dialog account-admin');dialog.setAttribute('aria-label','管理员控制台');
    dialog.innerHTML=`<div class="session-heading"><div><span class="admin-kicker">PLATFORM ADMINISTRATION</span><h2>管理员控制台</h2></div><button data-close aria-label="关闭管理员控制台">×</button></div>
      <p class="admin-intro">管理平台访问、公共模型与用户权限。</p>
      <div class="admin-tabs" role="tablist" aria-label="管理功能"><button id="admin-tab-invites" role="tab" data-tab="invites" aria-controls="admin-invites" aria-selected="true">邀请码管理</button><button id="admin-tab-models" role="tab" data-tab="models" aria-controls="admin-models" aria-selected="false">公共模型管理</button><button id="admin-tab-users" role="tab" data-tab="users" aria-controls="admin-users" aria-selected="false">用户管理</button></div>
      <p data-message role="status" aria-live="polite"></p>
      <section id="admin-invites" role="tabpanel" aria-labelledby="admin-tab-invites" data-panel="invites">
        <form data-invite-form class="admin-card"><h3>生成邀请码</h3><div class="admin-fields"><label>有效期<select data-duration aria-label="邀请码有效期"><option value="3600">1 小时</option><option value="86400">1 天</option><option value="604800" selected>7 天</option><option value="2592000">30 天</option><option value="7776000">90 天</option><option value="custom">指定到期时间</option></select></label><label>最多注册账号数<input data-max-uses aria-label="邀请码使用次数" type="number" min="1" max="1000" value="10" required></label></div><label data-custom-expiry hidden>到期时间<input data-create-expiry type="datetime-local" aria-label="新邀请码到期时间"></label><button type="submit" class="primary">生成邀请码</button>
        <div data-code hidden><label>新邀请码（仅此次显示）<input readonly autocomplete="off" aria-label="新邀请码"></label><button type="button" data-copy>复制邀请码</button><small data-code-note></small></div></form>
        <div class="admin-section-title"><h3>邀请码记录</h3><button data-refresh>刷新</button></div><p class="admin-help">可修改到期时间和使用上限；撤销后不能重新启用。列表显示最近 200 条，时间按当前设备时区显示。</p><div data-invites></div>
      </section>
      <section id="admin-models" role="tabpanel" aria-labelledby="admin-tab-models" data-panel="models" hidden>
        <form data-model-form class="admin-card"><h3>公共模型连接</h3><p>用户无需填写密钥即可使用。个人模型保存后优先使用个人配置。</p><div class="admin-fields"><label>配置对象<select data-provider aria-label="公共模型类型"><option value="general">通用大模型</option><option value="domain">航发领域大模型</option></select></label><label>鉴权方式<select data-auth aria-label="公共模型鉴权"><option value="bearer">Bearer API Key</option><option value="none">无鉴权（自部署）</option></select></label></div>
        <label>Base URL<input data-base aria-label="公共模型 Base URL" type="url" required placeholder="https://模型服务/v1" autocomplete="off"></label><div class="admin-fields"><label>Model ID<input data-model aria-label="公共模型 Model ID" maxlength="200" required autocomplete="off"></label><label>API Key <span data-key-state></span><input data-key aria-label="公共模型 API Key" type="password" maxlength="4096" autocomplete="off"></label></div>
        <div class="admin-fields"><label>超时（秒）<input data-timeout aria-label="公共模型超时" type="number" min="5" max="120" value="45" required></label><label class="admin-check"><input data-json type="checkbox">启用 JSON 模式</label></div>
        <p class="admin-help">密钥只保存在服务器，不会回显。测试连接会发送简短请求，可能消耗模型额度。保存连接后，请在下方策略中启用。</p>
        <div class="admin-actions"><button type="button" data-clear-model>清除当前公共模型</button><div><button type="button" data-test-model>测试连接</button><button type="submit" class="primary">保存公共模型</button></div></div></form>
        <form data-policy-form class="admin-card"><h3>可用模型与调用限额</h3><div data-model-summary class="admin-model-summary"></div><label class="admin-check"><input data-enabled="general" type="checkbox">向所有用户开放通用大模型</label><label class="admin-check"><input data-enabled="domain" type="checkbox">向所有用户开放航发领域大模型</label><div class="admin-fields"><label>默认模型<select data-default aria-label="默认公共模型"><option value="general">通用大模型</option><option value="domain">航发领域大模型</option></select></label><label>每用户每日公共模型调用上限<input data-limit aria-label="每日公共模型限额" type="number" min="1" max="10000" value="50" required></label></div><p class="admin-help">每日按北京时间 00:00 重置。发送到公共模型的请求计数，失败请求也计入；个人模型调用不占此限额。新对话默认选择已启用的公共模型。</p><button type="submit" class="primary">保存开放策略</button></form>
      </section>
      <section id="admin-users" role="tabpanel" aria-labelledby="admin-tab-users" data-panel="users" hidden><div class="admin-section-title"><h3>平台用户 <span data-user-count></span></h3><button data-refresh>刷新</button></div><input data-search type="search" aria-label="搜索用户" placeholder="搜索用户名"><p class="admin-help">禁用会阻止登录并撤销会话；强制退出只撤销会话，用户仍可重新登录。</p><div data-users></div></section>
      <details class="admin-logs"><summary>管理员操作日志 · 最近 200 条</summary><p class="admin-help">记录配置与权限变更，不记录密码、API Key 或邀请码原文。</p><div data-logs></div></details>
      <div data-confirm hidden class="admin-confirm"><p data-confirm-text></p><div><button data-confirm-cancel>取消</button><button data-confirm-yes class="primary">确认操作</button></div></div>`;
    document.body.append(dialog);
    $('[data-close]').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{serial++;busy=false;$('[data-code] input').value='';$('[data-code]').hidden=true;$('[data-key]').value='';$('[data-confirm]').hidden=true;});
    document.addEventListener('aeroblade:sessionchange',()=>{if(dialog.open)dialog.close();});
    for(const b of dialog.querySelectorAll('[data-tab]'))b.onclick=()=>tab(b.dataset.tab);
    for(const b of dialog.querySelectorAll('[data-refresh]'))b.onclick=()=>void load();
    $('[data-search]').oninput=filterUsers;
    $('[data-duration]').onchange=()=>{$('[data-custom-expiry]').hidden=$('[data-duration]').value!=='custom';};
    $('[data-provider]').onchange=()=>fillModel();$('[data-auth]').onchange=()=>{syncAuth();if($('[data-auth]').value==='none')$('[data-key]').value='';};
    $('[data-copy]').onclick=async()=>{try{await navigator.clipboard.writeText($('[data-code] input').value);message('邀请码已复制。');}catch{message('请选中邀请码手动复制。');}};
    $('[data-invite-form]').onsubmit=e=>{e.preventDefault();const expires=$('[data-duration]').value==='custom'?Math.floor(new Date($('[data-create-expiry]').value).getTime()/1000-Date.now()/1000):Number($('[data-duration]').value);if(!Number.isFinite(expires)||expires<60||expires>7776000){message('请选择未来1分钟至90天内的到期时间。',true);return;}void run(async()=>{const id=serial;const invite=await api('invites',{expires_in:expires,max_uses:Number($('[data-max-uses]').value)});if(id!==serial||!dialog.open)return;$('[data-code]').hidden=false;$('[data-code] input').value=invite.code;$('[data-code-note]').textContent=`最多 ${invite.max_uses} 个账号 · 到期 ${date(invite.expires_at)}`;return '邀请码已生成，请及时复制。';});};
    $('[data-model-form]').onsubmit=e=>{e.preventDefault();void run(async()=>{await api('models',modelDraft());return '公共模型连接已保存，请确认下方开放策略。';});};
    $('[data-test-model]').onclick=()=>{if(!$('[data-model-form]').reportValidity())return;void run(async()=>{const result=await api('models/test',modelDraft());return result.message;},false);};
    $('[data-clear-model]').onclick=()=>confirmAction('清除这个公共模型的连接和密钥？当前依赖此模型的用户将无法继续调用。',()=>run(async()=>{await api('models/clear',{provider:$('[data-provider]').value});return '公共模型连接已清除。';}));
    $('[data-policy-form]').onsubmit=e=>{e.preventDefault();void run(async()=>{await api('model-policy',{enabled:Object.fromEntries(['general','domain'].map(p=>[p,$(`[data-enabled="${p}"]`).checked])),default_provider:$('[data-default]').value,daily_limit:Number($('[data-limit]').value)});document.dispatchEvent(new CustomEvent('aeroblade:modelpolicychange'));return '公共模型开放策略与限额已保存。';});};
    $('[data-confirm-cancel]').onclick=()=>{$('[data-confirm]').hidden=true;};
  }
  tab('invites');setBusy(false);message('正在读取管理数据…');dialog.showModal();await load();
}
function confirmAction(text,callback){$('[data-confirm-text]').textContent=text;$('[data-confirm]').hidden=false;$('[data-confirm-yes]').onclick=()=>{$('[data-confirm]').hidden=true;void callback();};$('[data-confirm]').scrollIntoView({block:'nearest'});$('[data-confirm-yes]').focus();}
function modelDraft(){return {provider:$('[data-provider]').value,base_url:$('[data-base]').value.trim(),model:$('[data-model]').value.trim(),auth:$('[data-auth]').value,api_key:$('[data-key]').value,timeout:Number($('[data-timeout]').value),json_mode:$('[data-json]').checked};}
function fillModel(){const cfg=modelConfigs[$('[data-provider]').value]||{};$('[data-base]').value=cfg.base_url||'';$('[data-model]').value=cfg.model||'';$('[data-auth]').value=cfg.auth||'bearer';$('[data-key]').value='';$('[data-key-state]').textContent=cfg.has_key?'（已设置）':'';$('[data-key]').placeholder=cfg.has_key?'留空保留当前地址的密钥':'输入服务商 API Key';$('[data-timeout]').value=cfg.timeout||45;$('[data-json]').checked=!!cfg.json_mode;syncAuth();}
async function run(action,reload=true){
  if(busy)return;let id=serial;setBusy(true);message('正在处理…');
  try{const result=await action();if(id!==serial||!dialog.open)return;if(reload){id=serial+1;if(!await load())return;}if(id===serial&&dialog.open)message(result||'操作完成。');}
  catch(e){if(id===serial&&dialog.open)message(e.message,true);}
  finally{if(id===serial&&dialog.open)setBusy(false);}
}
async function load(){
  const id=++serial;setBusy(true);
  try{
    const [invites,users,models,logs]=await Promise.all([api('invites'),api('users'),api('models'),api('logs')]);if(id!==serial||!dialog.open)return;
    renderInvites(invites.invites);renderUsers(users.users);renderLogs(logs.logs);modelConfigs=models.providers;policy=models.policy;fillModel();
    for(const p of ['general','domain'])$(`[data-enabled="${p}"]`).checked=policy.enabled[p];$('[data-default]').value=policy.default_provider;$('[data-limit]').value=policy.daily_limit;
    $('[data-model-summary]').replaceChildren(...['general','domain'].map(p=>el('div',`${names[p]} · ${modelConfigs[p]?.configured?modelConfigs[p].model:'未配置'} · ${policy.enabled[p]&&modelConfigs[p]?.configured?'已开放':'未开放'}`)));
    message('管理数据已更新。');return true;
  }catch(e){if(id===serial&&dialog.open)message(e.message,true);}
  finally{if(id===serial&&dialog.open)setBusy(false);}
}
function renderInvites(invites){
  const group=$('[data-invites]');group.replaceChildren();if(!invites.length){group.append(el('p','暂无邀请码。','admin-empty'));return;}
  for(const i of invites){
    const row=el('div',undefined,'admin-record'),head=el('div',undefined,'admin-record-head'),status=i.revoked?'已撤销':i.expires_at*1000<Date.now()?'已过期':i.used_count>=i.max_uses?'次数已满':'可使用';
    head.append(el('strong',`邀请码 ${i.id.slice(0,8)}`),el('span',status,'admin-badge'));row.append(head,el('p',`已用 ${i.used_count} / ${i.max_uses} · 剩余 ${Math.max(0,i.max_uses-i.used_count)}`),el('small',`创建 ${date(i.created_at)} · 到期 ${date(i.expires_at)} · 修改 ${date(i.updated_at||i.created_at)}`));
    if(!i.revoked){const controls=el('div',undefined,'admin-actions'),edit=el('button','修改时间 / 次数'),revoke=el('button','撤销');controls.append(edit,revoke);row.append(controls);const form=el('form',undefined,'admin-inline-form');form.hidden=true;const expiry=el('input'),uses=el('input');expiry.type='datetime-local';expiry.value=localDate(i.expires_at);expiry.required=true;expiry.setAttribute('aria-label',`邀请码 ${i.id.slice(0,8)} 到期时间`);uses.type='number';uses.min=Math.max(1,i.used_count);uses.max=1000;uses.value=i.max_uses;uses.required=true;uses.setAttribute('aria-label',`邀请码 ${i.id.slice(0,8)} 使用上限`);const expiryLabel=el('label','到期时间'),usesLabel=el('label','使用上限');expiryLabel.append(expiry);usesLabel.append(uses);form.append(expiryLabel,usesLabel);const save=el('button','保存修改');save.type='submit';save.className='primary';form.append(save);row.append(form);edit.onclick=()=>{form.hidden=!form.hidden;};form.onsubmit=e=>{e.preventDefault();void run(async()=>{await api('invites/'+i.id+'/update',{expires_at:Math.floor(new Date(expiry.value).getTime()/1000),max_uses:Number(uses.value)});return '邀请码已更新。';});};revoke.onclick=()=>confirmAction(`撤销邀请码 ${i.id.slice(0,8)}？撤销后不能恢复。`,()=>run(async()=>{await api('invites/'+i.id+'/revoke',{});return '邀请码已撤销。';}));}
    group.append(row);
  }
}
function renderUsers(users){
  const group=$('[data-users]');group.replaceChildren();$('[data-user-count]').textContent=`(${users.length})`;
  for(const u of users){const row=el('div',undefined,'admin-record');row.dataset.username=u.username.toLowerCase();const head=el('div',undefined,'admin-record-head');head.append(el('strong',u.username),el('span',u.role==='admin'?'管理员':u.disabled?'已禁用':'普通用户','admin-badge'));row.append(head,el('p',`注册时间 ${date(u.created_at)}`));if(u.public_usage)row.append(el('small',`今日公共模型调用 ${u.public_usage.used} / ${u.public_usage.limit} · ${u.public_usage.day}（北京时间）`));if(u.role!=='admin'){const controls=el('div',undefined,'admin-actions'),status=el('button',u.disabled?'恢复账号':'禁用账号'),logout=el('button','强制退出登录');controls.append(status,logout);row.append(controls);status.onclick=()=>confirmAction(`${u.disabled?'恢复':'禁用'}用户 ${u.username}？`,()=>run(async()=>{await api('users/'+u.id+'/status',{disabled:!u.disabled});return '用户状态已更新。';}));logout.onclick=()=>confirmAction(`撤销 ${u.username} 的全部登录会话？用户可以重新登录。`,()=>run(async()=>{await api('users/'+u.id+'/logout',{});return '该用户的全部会话已退出。';}));}group.append(row);}filterUsers();
}
function filterUsers(){const query=$('[data-search]').value.trim().toLowerCase();for(const row of $('[data-users]').children)row.hidden=!row.dataset.username.includes(query);}
function renderLogs(logs){const group=$('[data-logs]');group.replaceChildren();if(!logs.length){group.append(el('p','暂无管理员操作记录。'));return;}for(const l of logs){const row=el('div',undefined,'admin-log');row.append(el('strong',actions[l.action]||l.action),el('span',`${l.actor||'管理员'} · ${date(l.created_at)} · ${names[l.target]||l.target.slice(0,8)}`));const detail=l.detail;if(detail.expires_at)row.append(el('small',`到期 ${date(detail.expires_at)} · 使用上限 ${detail.max_uses}`));if(detail.model)row.append(el('small',`Model ID：${detail.model}`));if(detail.daily_limit)row.append(el('small',`默认 ${names[detail.default_provider]} · 日限额 ${detail.daily_limit}`));group.append(row);}}
