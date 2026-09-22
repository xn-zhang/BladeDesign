import {ensureSession,sessionFetch,captureIdentity,checkIdentity,currentSession} from './session.js';
import {validate,build} from './geometry.js';
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
export function initPersonalWorkspace({getDesign,applyDesign,getConditions,applyConditions,assistant,openDesign}){
  const trigger=node('button','我的数据');trigger.id='personal-open';document.querySelector('.header-actions').append(trigger);
  const dialog=node('dialog');dialog.className='session-dialog personal-workspace';dialog.id='personal-dialog';
  dialog.innerHTML='<div class="session-heading"><h2>我的数据</h2><button data-close aria-label="关闭个人数据">×</button></div><p data-owner></p><div class="personal-tabs"><button data-kind="designs">设计方案</button><button data-kind="conversations">设计对话</button></div><form data-save><label for="personal-name">保存名称</label><input id="personal-name" required maxlength="120" placeholder="给当前方案或对话命名"><label for="personal-notes" data-notes-label>设计备注</label><textarea id="personal-notes" maxlength="4000" rows="3"></textarea><button class="primary" type="submit" data-save-button>保存当前设计</button></form><p data-message role="status"></p><div data-list></div>';
  document.body.append(dialog);
  const question=node('dialog');question.className='session-dialog';question.innerHTML='<form method="dialog"><p data-question></p><input data-answer maxlength="120" hidden><div><button value="cancel">取消</button><button value="accept" class="primary">确认</button></div></form>';document.body.append(question);
  function ask(text,value=null){question.querySelector('[data-question]').textContent=text;const input=question.querySelector('[data-answer]');input.hidden=value===null;input.value=value||'';question.returnValue='cancel';question.showModal();return new Promise(resolve=>question.addEventListener('close',()=>resolve(question.returnValue==='accept'?(value===null?true:input.value):null),{once:true}));}
  const $=s=>dialog.querySelector(s);let kind='designs',serial=0;
  async function api(path,data){const response=await sessionFetch('/api/personal/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'操作失败');return result;}
  const message=t=>{$('[data-message]').textContent=t;};
  async function load(){const id=++serial,selectedKind=kind;message('正在读取…');try{const data=await api(selectedKind);if(id!==serial)return;const list=$('[data-list]');list.replaceChildren();for(const item of data.items){const row=node('div');row.className='personal-row';const label=node('div');label.append(node('strong',item.name),node('small',new Date(item.updated_at*1000).toLocaleString()));row.append(label);for(const [action,title] of [['load','载入'],['rename','重命名'],['delete','删除']]){const b=node('button',title);b.onclick=()=>operate(action,item,selectedKind);row.append(b);}list.append(row);}message(data.items.length?`已保存 ${data.items.length} 份${kind==='designs'?'设计':'对话'}`:'还没有保存记录。');}catch(e){if(id===serial)message(e.message);}}
  async function operate(action,item,selectedKind){
    const id=serial,identity=captureIdentity();
    try{
      if(action==='load'){
        if(!await ask(`载入“${item.name}”将替换当前${selectedKind==='designs'?'设计与工况':'对话草稿'}，是否继续？`))return;
        checkIdentity(identity);const data=await api(selectedKind+'/'+item.id);checkIdentity(identity);if(id!==serial)return;
        if(selectedKind==='designs'){const parameters=validate(data.payload.parameters);build(parameters);applyConditions(data.payload.conditions);applyDesign(parameters);$('#personal-notes').value=data.payload.notes;openDesign();}
        else assistant.restoreConversationSnapshot(data.payload);
        dialog.close();
      }else if(action==='rename'){
        const name=await ask('新的名称',item.name);if(name===null)return;checkIdentity(identity);await api(selectedKind+'/'+item.id+'/rename',{name});if(id===serial)await load();
      }else if(await ask(`删除“${item.name}”？`)){checkIdentity(identity);await api(selectedKind+'/'+item.id+'/delete',{});if(id===serial)await load();}
    }catch(e){if(id===serial)message(e.message);}
  }
  async function open(selected='designs'){try{await ensureSession();kind=selected;$('#personal-name').value='';render();if(!dialog.open)dialog.showModal();await load();}catch(e){alert(e.message);}}
  function render(){serial++;$('[data-list]').replaceChildren();$('[data-owner]').textContent=`当前账号：${currentSession()?.username||''} · 仅自己可见`;$('[data-save-button]').textContent=kind==='designs'?'保存当前设计与工况':'保存当前对话';$('#personal-notes').hidden=kind!=='designs';$('[data-notes-label]').hidden=kind!=='designs';for(const b of dialog.querySelectorAll('[data-kind]'))b.setAttribute('aria-pressed',String(b.dataset.kind===kind));}
  for(const b of dialog.querySelectorAll('[data-kind]'))b.onclick=()=>{kind=b.dataset.kind;render();void load();};
  $('[data-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{serial++;});trigger.onclick=()=>open();
  $('[data-save]').onsubmit=async e=>{e.preventDefault();const button=$('[data-save-button]'),selected=kind,id=serial;button.disabled=true;try{const payload=selected==='designs'?{schema:'aeroblade-saved-design-v1',parameters:structuredClone(getDesign()),conditions:getConditions(),notes:$('#personal-notes').value}:assistant.getConversationSnapshot();await api(selected,{name:$('#personal-name').value,payload});if(id===serial){await load();message('保存成功，可在其他浏览器登录后恢复。');}}catch(err){if(id===serial)message(err.message);}finally{button.disabled=false;}};
  document.addEventListener('aeroblade:sessionchange',()=>{serial++;if(question.open){question.returnValue='cancel';question.close();}if(dialog.open)dialog.close();$('#personal-name').value='';$('#personal-notes').value='';$('[data-list]').replaceChildren();message('');});
  const conversationButton=node('button','保存 / 打开对话');conversationButton.id='personal-conversations';conversationButton.onclick=()=>open('conversations');assistant.querySelector('.initial-bottom').prepend(conversationButton);
  return {open};
}
