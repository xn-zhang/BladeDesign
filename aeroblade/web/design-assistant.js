import {currentSession} from './session.js';
import {PARAMETER_FIELDS, demoReply, requestAssistant, validateProposal} from './design-assistant-client.js';
import {initModelSettings} from './model-settings.js';

const STORAGE_KEY = 'aeroblade-initial-design-v1';
const MAX_MESSAGES = 60;
const providerNames = {demo:'参考演示',general:'通用大模型',domain:'航发领域大模型'};
const prompts = [
  ['从总体要求开始','我计划设计一组涡轮叶片。请先帮我梳理流量、功率、效率目标和边界条件，缺少的信息逐项向我确认。'],
  ['已有平均线结果','我已有平均线设计结果，希望根据速度三角形初始化 Pritchard 11 参数。请先确认气流角的坐标约定、转/静子类型和截面半径。'],
  ['从参考叶型出发','我希望从相似工况的参考叶型开始设计。请帮我确认参考来源、适用工况和参数映射，再整理初始方案。'],
];
function element(tag, className, text) {
  const node=document.createElement(tag);
  if(className)node.className=className;
  if(text!==undefined)node.textContent=text;
  return node;
}

export function initDesignAssistant({applyDesign,openDesign}) {
  let storageOwner=currentSession()?.user_id||'anonymous';
  const host=element('section','initial-workspace');host.id='initial-panel';host.hidden=true;
  host.innerHTML=`
    <div class="initial-topbar"><div><span class="initial-dot"></span><strong>总师智能体</strong><span class="initial-context">初始设计</span></div><div><button id="initial-model-settings">模型配置</button><button id="initial-new">新建对话</button><button id="initial-skip" class="initial-manual">跳过对话，手动设计 ↗</button></div></div>
    <div class="initial-scroll" id="initial-scroll">
      <div class="initial-welcome" id="initial-welcome"><div class="initial-emblem" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none"><path d="M42 8C19 11 12 26 14 49c8-14 21-9 30-22 5-7 5-13 4-18l-6-1Z" fill="currentColor" opacity=".14"/><path d="M44 9C22 11 15 25 14 49c9-14 22-10 30-22 4-6 5-12 4-18M19 42c4-15 12-24 25-29" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></div><span class="initial-kicker">AEROBLADE · INITIAL DESIGN</span><h2>从一个设计目标开始</h2><p>与总师智能体梳理总体要求，逐步形成关键气动参数<br class="initial-break">与 Pritchard 初始叶型方案。</p>
      <div class="initial-path" aria-label="设计流程"><span>01 明确需求</span><i>→</i><span>02 形成初设</span><i>→</i><span>03 参数化设计</span></div>
      <div class="initial-prompts" id="initial-prompts"></div></div>
      <div class="initial-messages" id="initial-messages" role="log" aria-label="初始设计对话" aria-live="polite" aria-relevant="additions"></div>
      <div class="initial-pending" id="initial-pending" role="status" hidden><span class="initial-dot"></span> 正在整理回复…</div>
      <div class="initial-error" id="initial-error" role="alert" hidden><span></span><button id="initial-retry">重试</button></div>
    </div>
    <div class="initial-bottom"><div class="initial-composer"><form id="initial-form"><label class="initial-sr" for="initial-input">输入总体设计要求或补充条件</label><textarea id="initial-input" rows="3" maxlength="6000" placeholder="描述你的设计目标，例如：设计对象、流量、功率、效率与工况要求…"></textarea><div class="initial-composer-actions"><div><label class="initial-sr" for="initial-provider">模型来源</label><select id="initial-provider"><option value="demo">参考演示 · 无需连接</option><option value="general">通用大模型</option><option value="domain">航发领域大模型</option></select><button type="button" id="initial-reference">载入参考方案</button></div><div><span id="initial-count">0 / 6000</span><button type="button" id="initial-stop" hidden>停止</button><button type="submit" id="initial-send" class="primary" disabled>发送 ↑</button></div></div></form></div>
      <div class="initial-footnote"><span id="initial-mode-note">参考演示仅展示交互与预设，未接入模型推理。</span><span>Enter 发送 · Shift + Enter 换行</span></div><p id="initial-storage-note" role="status" hidden></p>
    </div>
    <dialog id="initial-clear-dialog"><form method="dialog"><h2>开始新的初始设计？</h2><p>将清除本页对话、草稿与待确认方案，参数化设计工作区中的参数保持不变。</p><div class="initial-dialog-actions"><button value="cancel">保留对话</button><button value="clear" class="primary">开始新对话</button></div></form></dialog>`;
  document.querySelector('footer').before(host);
  const $=selector=>host.querySelector(selector), input=$('#initial-input'),messagesNode=$('#initial-messages');
  let messages=[],provider='demo',candidate=null,version=0,revision=0,busy=false,controller=null,requestId=0,lastRequest=null,error='',applied=false;
  const settings=initModelSettings({host,onChange:selected=>{
    if(selected){provider=selected;$('#initial-provider').value=provider;}
    candidate=null;revision++;lastRequest=null;error='';applied=false;renderMessages();updateControls();persist();
  }});

  function persist() {
    try { sessionStorage.setItem(STORAGE_KEY+':'+storageOwner,JSON.stringify({schema:1,messages,provider,candidate,version,revision,draft:input.value,lastRequest})); }
    catch { $('#initial-storage-note').hidden=false;$('#initial-storage-note').textContent='当前浏览器无法保存会话；离开或刷新页面后，本页对话可能丢失。'; }
  }
  function restore() {
    try {
      const saved=sessionStorage.getItem(STORAGE_KEY+':'+storageOwner);if(!saved)return;
      if(saved.length>2000000)throw Error('会话过大');
      const data=JSON.parse(saved);
      if(data.schema!==1 || !providerNames[data.provider] || !Array.isArray(data.messages) || data.messages.length>MAX_MESSAGES)throw Error('会话格式错误');
      if(!data.messages.every(m=>['user','assistant'].includes(m.role)&&typeof m.content==='string'&&m.content.length<=12000))throw Error('消息格式错误');
      messages=data.messages;provider=data.provider;revision=Number.isSafeInteger(data.revision)?data.revision:0;version=Number.isSafeInteger(data.version)?data.version:0;
      input.value=typeof data.draft==='string'?data.draft.slice(0,6000):'';
      if(data.candidate && data.candidate.revision===revision && data.candidate.provider===provider)candidate={...data.candidate,proposal:validateProposal(data.candidate.proposal)};
      if(data.lastRequest && messages.at(-1)?.role==='user') {lastRequest={provider,text:messages.at(-1).content};error='上次请求未完成，可重试或继续补充要求。';}
    } catch {error='之前的会话无法完整恢复，请新建对话或继续输入。';candidate=null;}
  }
  function updateControls() {
    $('#initial-send').disabled=busy || !input.value.trim() || messages.length>=MAX_MESSAGES-1;
    $('#initial-stop').hidden=!busy;$('#initial-send').hidden=busy;
    $('#initial-pending').hidden=!busy;$('#initial-provider').disabled=busy;
    $('#initial-model-settings').disabled=busy;
    $('#initial-reference').hidden=provider!=='demo';$('#initial-reference').disabled=busy||messages.length>=MAX_MESSAGES-1;
    $('#initial-count').textContent=`${input.value.length} / 6000`;
    $('#initial-mode-note').textContent=provider==='demo'?'参考演示仅展示交互与预设，未接入模型推理。':'通过已配置的模型服务生成建议；采用前请审阅来源与假设。';
    $('#initial-error').hidden=!error;$('#initial-error span').textContent=error;
    $('#initial-retry').hidden=!lastRequest;$('#initial-retry').disabled=busy;
    if(messages.length>=MAX_MESSAGES-1)$('#initial-mode-note').textContent='本次会话已达到消息上限，请新建对话；最后一次失败请求仍可重试。';
  }
  function scrollLatest() {const scroller=$('#initial-scroll');requestAnimationFrame(()=>scroller.scrollTo({top:scroller.scrollHeight,behavior:'auto'}));}
  function renderCandidate() {
    if(!candidate || candidate.revision!==revision || candidate.provider!==provider)return;
    const p=candidate.proposal,card=element('section','initial-proposal');card.setAttribute('aria-label','待确认的初始方案');
    const heading=element('div','initial-proposal-heading');heading.append(element('div','',`初始方案 · V${candidate.version}`),element('span','initial-valid','几何校验通过'));card.append(heading);
    card.append(element('p','initial-proposal-source',`${providerNames[candidate.provider]} · ${candidate.provider==='demo'?'图19参考截面，未匹配当前设计要求':'初设建议，待气动评估'} · mm / deg`));
    const aero=element('div','initial-aero');aero.append(element('h3','','关键气动参数'));
    if(!p.aerodynamic.length)aero.append(element('p','','尚未计算。接入平均线工具后，由模型提供带来源的气动初设结果。'));
    for(const item of p.aerodynamic)aero.append(element('p','',`${item.label}：${item.value} ${item.unit} · ${item.source}`));
    card.append(aero);
    const details=element('details','initial-parameters');details.open=true;details.append(element('summary','','Pritchard 11 参数'));
    const wrap=element('div','initial-table-wrap'),table=element('table');table.innerHTML='<caption class="initial-sr">Pritchard 初始几何参数与来源</caption><thead><tr><th scope="col">参数</th><th scope="col">初始值</th><th scope="col">来源</th></tr></thead>';
    const body=element('tbody');for(const [key,label,,,,unit] of PARAMETER_FIELDS){const row=element('tr');const name=element('th','',label);name.scope='row';row.append(name,element('td','',`${Number(p.parameters[key].toFixed(5))} ${unit}`),element('td','',p.sources[key]));body.append(row);}table.append(body);wrap.append(table);details.append(wrap);card.append(details);
    card.append(element('p','initial-span-note',`拉伸展示展宽 ${p.parameters.height} mm · 独立设置，不计入11参数`));
    for(const [title,items] of [['方案假设',p.assumptions],['后续验证',p.warnings]]){if(items.length){const block=element('div','initial-evidence');block.append(element('h3','',title));const list=element('ul');items.forEach(text=>list.append(element('li','',text)));block.append(list);card.append(block);}}
    const actions=element('div','initial-proposal-actions'),button=element('button','primary',applied?'再次采用并进入参数化设计 →':'采用此方案并进入参数化设计 →');button.disabled=busy;
    button.onclick=()=>{
      try { const verified=validateProposal(candidate.proposal);applyDesign(verified.parameters);applied=true;renderMessages();openDesign(); }
      catch(err){error=`方案未应用：${err.message}`;updateControls();scrollLatest();}
    };
    actions.append(element('span','','将替换设计页当前参数；可继续对话修改方案。'),button);card.append(actions);messagesNode.append(card);
  }
  function renderMessages() {
    messagesNode.replaceChildren();$('#initial-welcome').hidden=messages.length>0;
    for(const message of messages){const item=element('article',`initial-message initial-${message.role}`);item.append(element('div','initial-message-author',message.role==='user'?'你':`总师智能体 · ${providerNames[message.provider]||providerNames[provider]}`),element('p','',message.content));messagesNode.append(item);}
    renderCandidate();
  }
  function cancelRequest(showError=true) {
    requestId++;controller?.abort();controller=null;busy=false;
    if(showError){error='已停止生成。可重试当前请求，或继续输入。';updateControls();persist();}
  }
  async function send(text,retry=false) {
    text=text.trim();if(busy||!text||text.length>6000)return;
    if(!retry&&messages.length>=MAX_MESSAGES-1)return;
    revision++;candidate=null;applied=false;error='';
    if(!retry){messages.push({role:'user',content:text});input.value='';}
    lastRequest={text,provider};busy=true;controller=new AbortController();const signal=controller.signal,id=++requestId;
    renderMessages();updateControls();scrollLatest();persist();
    let timeout;
    try {
      timeout=setTimeout(()=>{if(id===requestId){cancelRequest(false);error='请求超时（135秒），请重试或检查模型服务。';updateControls();persist();}},135000);
      let reply;
      if(provider==='demo'){
        await new Promise((resolve,reject)=>{const timer=setTimeout(resolve,450);signal.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('已停止','AbortError'));},{once:true});});
        reply=demoReply(text);
      } else {
        reply=await requestAssistant({provider,messages:messages.map(({role,content})=>({role,content})),signal});
      }
      if(id!==requestId)return;
      const verified=reply.proposal?validateProposal(reply.proposal):null;
      messages.push({role:'assistant',content:reply.message,provider});
      if(verified)candidate={proposal:verified,provider,revision,version:++version};
      lastRequest=null;
    }catch(err){if(id!==requestId)return;error=err.name==='AbortError'?'已停止生成。':`未能生成回复：${err.message}`;}
    finally {clearTimeout(timeout);if(id===requestId){busy=false;controller=null;renderMessages();updateControls();persist();scrollLatest();input.focus();}}
  }
  for(const [title,prompt] of prompts){const button=element('button','initial-prompt');button.type='button';button.append(element('strong','',title),element('span','',prompt),element('i','','↗'));button.onclick=()=>{input.value=prompt;updateControls();persist();input.focus();};$('#initial-prompts').append(button);}
  $('#initial-form').onsubmit=e=>{e.preventDefault();void send(input.value);};
  input.oninput=()=>{updateControls();persist();};
  input.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();void send(input.value);}};
  $('#initial-reference').onclick=()=>void send('载入参考方案');
  $('#initial-stop').onclick=()=>cancelRequest();
  $('#initial-retry').onclick=()=>{if(lastRequest)void send(lastRequest.text,true);};
  $('#initial-skip').onclick=()=>openDesign();
  $('#initial-model-settings').onclick=async()=>{try{await settings.open(provider);}catch(err){error=err.message;updateControls();}};
  document.addEventListener('aeroblade:sessionchange',e=>{cancelRequest(false);messages=[];candidate=null;version=0;revision++;lastRequest=null;error='';applied=false;provider='demo';input.value='';storageOwner=e.detail.userId||'anonymous';if(e.detail.authenticated)restore();$('#initial-provider').value=provider;renderMessages();updateControls();});
  $('#initial-provider').onchange=e=>{provider=e.target.value;candidate=null;revision++;lastRequest=null;error='';applied=false;renderMessages();updateControls();persist();};
  $('#initial-new').onclick=()=>{if(!messages.length&&!input.value)return;$('#initial-clear-dialog').showModal();};
  $('#initial-clear-dialog').addEventListener('close',()=>{
    if($('#initial-clear-dialog').returnValue!=='clear')return;
    cancelRequest(false);messages=[];candidate=null;version=0;revision=0;lastRequest=null;error='';applied=false;input.value='';renderMessages();updateControls();persist();input.focus();
  });
  restore();$('#initial-provider').value=provider;renderMessages();updateControls();scrollLatest();
  host.getBatchBaseline=()=>candidate&&!busy&&candidate.revision===revision?{parameters:structuredClone(candidate.proposal.parameters),provenance:{source:'initial-proposal',provider:candidate.provider,version:candidate.version,sources:structuredClone(candidate.proposal.sources)}}:null;
  host.getConversationSnapshot=()=>({schema:'aeroblade-saved-conversation-v1',messages:messages.map(({role,content})=>({role,content})),provider,candidate:candidate?.proposal||null,draft:input.value});
  host.restoreConversationSnapshot=snapshot=>{
    if(snapshot.schema!=='aeroblade-saved-conversation-v1')throw Error('对话格式无效');
    const proposal=snapshot.candidate?validateProposal(snapshot.candidate):null;
    cancelRequest(false);messages=structuredClone(snapshot.messages);provider=snapshot.provider;revision++;candidate=proposal?{proposal,provider,revision,version:++version}:null;lastRequest=null;error='';applied=false;input.value=snapshot.draft;$('#initial-provider').value=provider;renderMessages();updateControls();persist();scrollLatest();document.querySelector('#open-initial')?.click();
  };
  return host;
}
