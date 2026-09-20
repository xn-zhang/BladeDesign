import {ensureSession,sessionFetch} from './session.js';
export function initModelSettings({host,onChange}) {
  const dialog=document.createElement('dialog');dialog.id='model-settings';dialog.className='model-settings';
  dialog.innerHTML=`<div class="model-settings-heading"><div><span class="model-settings-kicker">MODEL CONNECTION</span><h2>模型配置</h2></div><button type="button" id="model-close" aria-label="关闭模型配置">×</button></div>
    <p class="model-settings-intro">连接兼容 Chat Completions 的服务，通用模型与航发领域模型可分别配置。</p>
    <div class="model-load-row"><span>已登录 · 配置保存到当前平台服务器</span><button type="button" id="model-load">重新读取配置</button></div>
    <form id="model-form"><div class="model-fields"><div><label for="model-provider">配置对象</label><select id="model-provider"><option value="general">通用大模型</option><option value="domain">航发领域大模型</option></select></div><div><label for="model-auth">模型鉴权</label><select id="model-auth"><option value="bearer">Bearer API Key</option><option value="none">无鉴权（自部署服务）</option></select></div></div>
    <label for="model-base">模型 Base URL</label><input id="model-base" type="url" required placeholder="https://你的模型服务/v1" autocomplete="off"><p class="model-field-note">填写 API 基础地址；平台自动追加 /chat/completions。支持 HTTPS，或本机/私有 IP 的 HTTP。</p>
    <div class="model-fields"><div><label for="model-name">模型名称 / Model ID</label><input id="model-name" required maxlength="200" placeholder="服务商提供的模型 ID" autocomplete="off"></div><div><label for="model-key">模型 API Key <span id="model-key-state"></span></label><input id="model-key" type="password" maxlength="4096" placeholder="输入模型服务的 API Key" autocomplete="off"></div></div>
    <div class="model-fields model-options"><div><label for="model-timeout">请求超时（秒）</label><input id="model-timeout" type="number" min="5" max="120" step="1" value="45" required></div><label class="model-check" for="model-json"><input id="model-json" type="checkbox">启用 JSON 模式<span>服务支持 response_format 时开启</span></label></div>
    <p class="model-storage-note">配置保存在服务器私有数据库，重启后自动恢复。密钥不会回显或写入浏览器存储。测试只发送简短连接请求，可能消耗少量额度。</p>
    <div id="model-message" role="status" aria-live="polite">登录后自动读取已有配置，或填写新配置。</div>
    <div class="model-settings-actions"><button type="button" id="model-clear">清除该模型配置</button><div><button type="button" id="model-test">测试连接</button><button type="submit" class="primary" id="model-save">保存并使用</button></div></div></form>
    <div id="model-clear-confirm" hidden><p>确认从服务器删除该模型的地址和密钥？清除后需重新配置。</p><button type="button" id="model-keep">保留配置</button><button type="button" id="model-clear-do">确认清除</button></div>`;
  host.append(dialog);
  const $=s=>dialog.querySelector(s);let configs={},busy=false,controller=null,serial=0;
  const message=(text,error=false)=>{$('#model-message').textContent=text;$('#model-message').classList.toggle('error',error);};
  function setBusy(value){busy=value;for(const node of dialog.querySelectorAll('input,select,button'))if(node.id!=='model-close')node.disabled=value;$('#model-key').disabled=value||$('#model-auth').value==='none';}
  function fill(provider){
    const cfg=configs[provider]||{};
    $('#model-provider').value=provider;$('#model-base').value=cfg.base_url||'';$('#model-name').value=cfg.model||'';
    $('#model-auth').value=cfg.auth||'bearer';$('#model-timeout').value=cfg.timeout||45;$('#model-json').checked=!!cfg.json_mode;
    $('#model-key').value='';$('#model-key-state').textContent=cfg.has_key?'已设置':'';
    $('#model-key').placeholder=cfg.has_key?'留空保留当前地址的密钥':'输入模型服务的 API Key';
    $('#model-key').disabled=$('#model-auth').value==='none';$('#model-clear-confirm').hidden=true;
  }
  async function api(path,body,signal){
    const response=await sessionFetch('/api/design-assistant/'+path,{method:body?'POST':'GET',signal,headers:body?{'Content-Type':'application/json'}:{},...(body?{body:JSON.stringify(body)}:{})});
    if([404,405,501].includes(response.status))throw Error('当前页面未连接新版后端，请检查同源 API 转发。');
    if(response.status===401)throw Error('登录已失效，请重新登录。');
    let data;try{data=await response.json();}catch{throw Error('平台未返回有效 JSON');}
    if(!response.ok)throw Error(typeof data.error==='string'?data.error:'请求失败（HTTP '+response.status+'）');
    return data;
  }
  function draft(){
    if(!$('#model-form').reportValidity())return null;
    return {provider:$('#model-provider').value,base_url:$('#model-base').value.trim(),model:$('#model-name').value.trim(),auth:$('#model-auth').value,api_key:$('#model-key').value,timeout:Number($('#model-timeout').value),json_mode:$('#model-json').checked};
  }
  async function run(action){
    if(busy)return;
    let data;
    if(['test','config'].includes(action)){data=draft();if(!data)return;}
    if(action==='clear')data={provider:$('#model-provider').value};
    const selected=$('#model-provider').value,id=++serial;controller=new AbortController();const signal=controller.signal;
    if(action==='config'||action==='clear')onChange(null);
    setBusy(true);message(action==='test'?'正在测试模型连接…':'正在读取或保存配置…');
    const timeout=setTimeout(()=>controller?.abort(),135000);
    try{
      const result=await api(action==='load'?'config':action,data,signal);
      if(id!==serial)return;
      if(action==='test')message(result.message||'连接成功；草稿尚未保存');
      else{
        configs=result.providers||{};fill(selected);
        message(action==='config'?'配置已保存到服务器，已选择此模型。':action==='clear'?'该模型配置已从服务器清除。':'服务器配置已读取，密钥不会回显。');
        if(action==='config')onChange(selected);else if(action==='clear')onChange(null);
      }
    }catch(err){if(id===serial)message(err.name==='AbortError'?'请求已取消或超时；可重新测试。':err.message,true);}
    finally{clearTimeout(timeout);if(id===serial){controller=null;setBusy(false);}}
  }
  $('#model-load').onclick=()=>void run('load');$('#model-test').onclick=()=>void run('test');
  $('#model-form').onsubmit=e=>{e.preventDefault();void run('config');};
  $('#model-provider').onchange=e=>{fill(e.target.value);message('已切换配置对象，未保存的表单修改不会应用。');};
  $('#model-auth').onchange=()=>{$('#model-key').disabled=$('#model-auth').value==='none';if($('#model-key').disabled)$('#model-key').value='';};
  $('#model-clear').onclick=()=>{$('#model-clear-confirm').hidden=false;$('#model-clear-do').focus();};
  $('#model-keep').onclick=()=>{$('#model-clear-confirm').hidden=true;};$('#model-clear-do').onclick=()=>void run('clear');
  $('#model-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{serial++;controller?.abort();controller=null;setBusy(false);$('#model-key').value='';});
  document.addEventListener('aeroblade:sessionchange',event=>{if(!event.detail.authenticated){configs={};if(dialog.open)dialog.close();}});
  return {
    async open(provider){
      await ensureSession();
      fill(provider==='domain'?'domain':'general');
      message('正在读取服务器配置…');dialog.showModal();
      await run('load');
    },
  };
}
