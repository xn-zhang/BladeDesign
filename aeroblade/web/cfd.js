import {canConnectService} from './deployment-origin.js';
import {initPersonalWorkspace} from './personal-workspace.js';
import {isPritchard,analyze,validate} from './geometry.js';
import {initFlowView} from './flow-view.js';
import {initEvaluationWorkspace} from './evaluation.js';
import {initBatchWorkflow} from './batch.js';
import {initDesignAssistant} from './design-assistant.js';
import {sessionFetch} from './session.js';
const $ = s => document.querySelector(s);
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {queued:'排队中',preparing:'准备算例',running:'运行中',packaging:'整理结果',completed:'计算结束',failed:'失败',cancelled:'已取消',cancelling:'正在取消',interrupted:'已中断'};
const terminal = new Set(['completed','failed','cancelled','interrupted']);
export function initCFD(getDesign,applyDesign) {
  let connection=null, health=null, selected=null, timer=null, generation=0, busy=false, dirty=false, schedulerBusy=false, schedulerDirty=false, schedulerRevision=-1, refreshSerial=0, pollSerial=0;
  const host = document.createElement('section');host.id='cfd-panel';host.hidden=true;
  host.innerHTML=`<div class="cfd-heading"><div><span class="eyebrow">OPENFOAM COMPUTE</span><h2>CFD 仿真工作台</h2></div><div class="cfd-heading-actions"><span class="cfd-status" id="cfd-status">未连接求解服务</span><button id="cfd-hide">收起</button></div></div>
  <div class="cfd-layout"><div class="cfd-config">
  <h3>01 · 连接计算服务</h3><label for="cfd-url">服务地址</label><input id="cfd-url" type="url" placeholder="https://foam.your-lab.org" autocomplete="off"><label for="cfd-token">独立计算服务令牌 <small>同源连接可留空，使用登录会话</small></label><input id="cfd-token" type="password" placeholder="独立 CFD 服务的令牌；当前平台可留空" autocomplete="off"><div class="cfd-buttons"><button id="cfd-connect" class="primary">连接并检测</button><button id="cfd-disconnect" disabled>断开</button></div>
  <p id="cfd-connection-message" class="cfd-help">网页不直接运行 OpenFOAM。连接已有服务，或下载桥接程序，在你的 Linux 求解机启动。</p><section class="cfd-scheduler" aria-label="并行计算设置"><h3>计算槽位</h3><div class="cfd-scheduler-controls"><label for="cfd-parallel">同时运行</label><select id="cfd-parallel" disabled><option value="2">2 个算例</option></select><button id="cfd-parallel-apply" disabled>应用</button></div><p id="cfd-scheduler-status" role="status">连接后显示运行与排队数量。</p><small>按算例并行；单算例不启用 MPI。</small></section><a class="cfd-download" href="aeroblade.zip" download>下载 AeroBlade 工作台与部署说明 ↗</a>
  <h3>02 · 算例与工况</h3><label for="cfd-case-name">算例名称（可选）</label><input id="cfd-case-name" maxlength="80" placeholder="例如：基准工况 / 高入口总压"><label for="cfd-template">服务器算例模板</label><select id="cfd-template" disabled><option>连接后读取可用模板</option></select><p id="cfd-template-info" class="cfd-help">周期边界、湍流模型、网格尺度和热力学设置由模板确定。</p><button id="cfd-apply-design" disabled>应用模板推荐叶片</button><div id="cfd-inputs"></div><div id="cfd-snapshot" class="cfd-snapshot"></div>
  <div class="cfd-buttons"><button id="cfd-submit" class="primary" disabled>提交真实仿真</button><button id="cfd-request">导出任务请求</button></div><p class="cfd-help">提交时冻结当前叶片和工况；后续编辑不会修改正在计算的任务。</p></div>
  <div class="cfd-monitor"><div class="cfd-task-summary"><div class="cfd-monitor-heading"><h3>03 · 任务监控</h3><button id="cfd-refresh" disabled>刷新任务</button></div><label for="cfd-jobs">计算任务</label><select id="cfd-jobs" disabled><option>暂无任务</option></select>
  <div id="cfd-job-state" class="cfd-empty">连接求解服务后，可提交任务并查看真实运行状态。</div><p id="cfd-dirty" class="cfd-warning" hidden>当前设计已修改。以下结果对应提交时的叶片快照。</p><div class="cfd-buttons"><button id="cfd-cancel" disabled>停止任务</button><button id="cfd-results" disabled>下载场数据与算例 ZIP</button></div>
  </div><div class="cfd-diagnostics"><section class="cfd-history"><div class="cfd-chart-heading"><h3>残差历史</h3><span>Initial residual · log₁₀</span></div><svg id="cfd-residuals" viewBox="0 0 640 235" role="img" aria-label="OpenFOAM 实际初始残差历史"></svg><div id="cfd-legend" class="cfd-legend"></div><p id="cfd-convergence" class="cfd-help">尚无求解数据。进程完成不等于物理收敛。</p>
  <div class="cfd-monitor-heading"><h3>求解日志</h3><span>尾部 24 KB</span></div><pre id="cfd-log" tabindex="0" aria-label="OpenFOAM 实时日志">等待连接…</pre></section><section id="cfd-flow" class="cfd-flow"></section></div>
  </div></div><div id="cfd-message" role="status" aria-live="polite"></div>`;
  $('footer').before(host);
  const config=$('.cfd-config'),configActions=$('#cfd-submit').parentElement,configScroll=document.createElement('div'),configFooter=document.createElement('div');configScroll.className='cfd-config-scroll';configFooter.className='cfd-config-actions';configActions.remove();while(config.firstChild)configScroll.append(config.firstChild);configFooter.append(configActions);config.append(configScroll,configFooter);
  const flowView=initFlowView($('#cfd-flow'),id=>api('/jobs/'+id+'/flow'));
  const trigger=document.createElement('button');trigger.id='open-cfd';trigger.textContent='CFD 仿真';
  const designTab=document.createElement('button');designTab.id='open-design';designTab.textContent='参数化设计';
  const {evaluationPanel,aiPanel,showTraining,buildBatchDataset,getConditions,applyConditions}=initEvaluationWorkspace({getDesign,applyDesign,openDesign:()=>workspace('design'),openAI:()=>workspace('ai'),openEvaluation:()=>workspace('evaluation'),openAssistant:()=>workspace('initial'),openModelSettings:()=>{workspace('initial');$('#initial-model-settings').click();}});
  const aiTab=document.createElement('button');aiTab.id='open-ai';aiTab.textContent='AI 推理';
  const evaluationTab=document.createElement('button');evaluationTab.id='open-evaluation';evaluationTab.textContent='评估与优化';
  const tabs=document.createElement('nav');tabs.className='workspace-tabs';tabs.setAttribute('aria-label','工作区切换');tabs.setAttribute('role','tablist');tabs.append(designTab,trigger,aiTab,evaluationTab);$('.header-actions').before(tabs);
  const design=$('main'),title=$('.workspace-title');design.id='design-workspace';design.setAttribute('role','tabpanel');design.setAttribute('aria-labelledby','open-design');host.setAttribute('role','tabpanel');host.setAttribute('aria-labelledby','open-cfd');
  const initialPanel=initDesignAssistant({applyDesign,openDesign:()=>{workspace('design');designTab.focus();}}),initialTab=document.createElement('button');initialTab.id='open-initial';initialTab.textContent='初始设计';tabs.prepend(initialTab);
  initPersonalWorkspace({getDesign,applyDesign,getConditions,applyConditions,assistant:initialPanel,openDesign:()=>workspace('design')});
  document.addEventListener('aeroblade:sessionchange',e=>{if(!e.detail.authenticated){resetConnection();$('#cfd-token').value='';$('#cfd-jobs').replaceChildren();$('#cfd-template').replaceChildren();applyConditions({inletTotalPressure:100200,inletTotalTemperature:300,outletStaticPressure:100000,iterations:3000});}});
  const workspaces=[['initial',initialTab,initialPanel],['design',designTab,design],['cfd',trigger,host],['ai',aiTab,aiPanel],['evaluation',evaluationTab,evaluationPanel]];
  for(const [,tab,panel] of workspaces){tab.setAttribute('role','tab');tab.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);}
  function workspace(mode){document.body.dataset.workspace=mode;title.hidden=mode!=='design';for(const [id,tab,panel] of workspaces){const active=id===mode;panel.hidden=!active;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;}window.scrollTo(0,0);if(mode==='cfd')snapshot();}
  trigger.onclick=()=>workspace('cfd');designTab.onclick=()=>workspace('design');$('#cfd-hide').textContent='返回设计';$('#cfd-hide').onclick=()=>{workspace('design');designTab.focus();};
  aiTab.onclick=()=>workspace('ai');
  evaluationTab.onclick=()=>workspace('evaluation');
  initialTab.onclick=()=>workspace('initial');
  tabs.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const current=workspaces.findIndex(([id])=>id===document.body.dataset.workspace);const index=e.key==='Home'?0:e.key==='End'?workspaces.length-1:(current+(e.key==='ArrowRight'?1:-1)+workspaces.length)%workspaces.length;workspace(workspaces[index][0]);workspaces[index][1].focus();}});
  workspace('initial');
  initBatchWorkflow({getDesign,applyDesign,initialPanel,cfdPanel:host,aiPanel,openCFD:()=>workspace('cfd'),openAI:()=>workspace('ai'),showTraining,buildBatchDataset});
  $('#cfd-url').value=location.origin;
  function message(text,error=false){$('#cfd-message').textContent=text;$('#cfd-message').className=error?'error':'';}
  function snapshot(){const p=getDesign();$('#cfd-snapshot').textContent=isPritchard(p)?`Pritchard 1985 · 轴向弦长 ${p.axialChord.toFixed(3)} mm · 节距 ${analyze(p).pitch.toFixed(3)} mm · 拉伸展宽 ${p.height} mm`:`旧模型 · 弦长 ${p.chord} mm · 叶高 ${p.height} mm · 扭转 ${p.twist}°`;
    dirty=!!selected&&(Object.keys(selected.parameters||{}).length!==Object.keys(p).length||Object.keys(p).some(k=>selected.parameters?.[k]!==p[k]));$('#cfd-dirty').hidden=!dirty;}
  document.addEventListener('aeroblade:designchange',snapshot);
  function drawResiduals(rows=[]){
    const svg=$('#cfd-residuals');if(!rows.length){svg.innerHTML='<text x="320" y="120" text-anchor="middle" fill="#526780" font-size="14">等待 OpenFOAM 残差输出</text>';$('#cfd-legend').textContent='';return;}
    const fields=[...new Set(rows.map(r=>r.field))].slice(0,10),colors=['#4585ef','#1baf99','#ed9b38','#9b78df','#d96677','#428aa6','#957553','#a8a531','#aa68a2','#667ba7'];
    const valid=rows.filter(r=>Number.isFinite(r.initial)&&r.initial>0&&Number.isFinite(r.iteration));if(!valid.length){svg.innerHTML='<text x="320" y="120" text-anchor="middle" fill="#526780" font-size="14">残差为零或无有效正值</text>';return;}
    const xmin=Math.min(...valid.map(r=>r.iteration)),xmax=Math.max(xmin+1,...valid.map(r=>r.iteration));const ymin=Math.min(-6,Math.floor(Math.min(...valid.map(r=>Math.log10(r.initial))))),ymax=Math.max(0,Math.ceil(Math.max(...valid.map(r=>Math.log10(r.initial)))));const x=v=>55+(v-xmin)/(xmax-xmin)*560,y=v=>190-(Math.log10(v)-ymin)/(ymax-ymin)*165;
    let html='';for(let i=0;i<=4;i++){const yy=25+i*41.25,exp=ymax-(ymax-ymin)*i/4;html+=`<line x1="55" y1="${yy}" x2="615" y2="${yy}" stroke="#e5ebf3"/><text x="45" y="${yy+4}" fill="#526780" text-anchor="end" font-size="22">1e${exp.toFixed(1)}</text>`;const xv=xmin+(xmax-xmin)*i/4;html+=`<text x="${55+i*140}" y="217" fill="#526780" text-anchor="middle" font-size="22">${xv.toFixed(0)}</text>`;}
    fields.forEach((f,i)=>{const series=valid.filter(r=>r.field===f);html+=`<polyline fill="none" stroke="${colors[i]}" stroke-width="1.6" points="${series.map(r=>`${x(r.iteration)},${y(r.initial)}`).join(' ')}"/>`;});svg.innerHTML=html;
    $('#cfd-legend').innerHTML=fields.map((f,i)=>`<span><i style="background:${colors[i]}"></i>${escapeHTML(f)}</span>`).join('');
  }
  async function api(path,opts={},session=connection){
    if(!session)throw Error('请先连接求解服务');
    const ctrl=new AbortController(),timeout=setTimeout(()=>ctrl.abort(),path.endsWith('/artifacts')?120000:15000);
    try {const res=await (session.cookie?sessionFetch:fetch)(session.url+'/api'+path,{...opts,headers:{...(!session.cookie?{Authorization:'Bearer '+session.token}:{}),...(opts.body?{'Content-Type':'application/json'}:{}),...opts.headers},signal:ctrl.signal,redirect:'error'});
      if(!res.ok){let detail;try{detail=(await res.json()).error}catch{detail='HTTP '+res.status}throw Error(detail||'服务请求失败');}
      return path.endsWith('/artifacts')?await res.blob():await res.json();
    }catch(e){if(e.name==='AbortError')throw Error('连接超时，请检查服务地址、HTTPS 和网络');if(e instanceof TypeError)throw Error('无法访问服务，请检查 HTTPS、允许的网页来源和网络连接');throw e;}finally{clearTimeout(timeout);}
  }
  function renderScheduler(data){
    if(!data||!Number.isInteger(data.max_parallel))return;
    if((data.revision??0)<schedulerRevision)return;schedulerRevision=data.revision??0;
    const select=$('#cfd-parallel'),limit=Math.min(64,data.max_parallel_limit||data.max_parallel);
    if(select.options.length!==limit)select.innerHTML=Array.from({length:limit},(_,i)=>`<option value="${i+1}">${i+1} 个算例</option>`).join('');
    if(!schedulerDirty&&!schedulerBusy)select.value=String(data.max_parallel);
    select.disabled=!connection||schedulerBusy;$('#cfd-parallel-apply').disabled=!connection||schedulerBusy;
    $('#cfd-scheduler-status').textContent=`运行 ${data.running_jobs??0} / ${data.max_parallel} · 排队 ${data.queued_jobs??0} · 任务上限 ${data.max_pending??'—'}`+(data.running_jobs>data.max_parallel?'；降低的并发上限将在已有任务结束后生效。':'');
  }
  $('#cfd-parallel').onchange=()=>{schedulerDirty=true;};
  $('#cfd-parallel-apply').onclick=async()=>{if(schedulerBusy||!connection)return;const gen=generation;schedulerBusy=true;$('#cfd-parallel').disabled=true;$('#cfd-parallel-apply').disabled=true;
    try{const data=await api('/scheduler',{method:'POST',body:JSON.stringify({max_parallel:Number($('#cfd-parallel').value)})});if(gen!==generation)return;schedulerDirty=false;schedulerBusy=false;renderScheduler(data);message('并发上限已更新；已运行的算例继续执行。');}
    catch(e){if(gen===generation)message(e.message,true);}
    finally{if(gen===generation){schedulerBusy=false;$('#cfd-parallel').disabled=!connection;$('#cfd-parallel-apply').disabled=!connection;}}
  };
  function scheduleRefresh(){clearTimeout(timer);if(connection)timer=setTimeout(()=>refreshJobs().catch(e=>{message(e.message,true);scheduleRefresh();}),2500);}
  function resetConnection(){flowView.clear();busy=false;schedulerBusy=false;schedulerRevision=-1;schedulerDirty=false;$('#cfd-parallel').disabled=true;$('#cfd-parallel-apply').disabled=true;$('#cfd-scheduler-status').textContent='连接后显示运行与排队数量。';generation++;clearTimeout(timer);connection=null;health=null;selected=null;$('#cfd-disconnect').disabled=true;$('#cfd-connect').disabled=false;$('#cfd-template').disabled=true;$('#cfd-jobs').disabled=true;$('#cfd-refresh').disabled=true;$('#cfd-submit').disabled=true;$('#cfd-cancel').disabled=true;$('#cfd-results').disabled=true;$('#cfd-status').textContent='未连接求解服务';$('#cfd-status').classList.remove('connected');$('#cfd-job-state').textContent='未连接。已有服务器任务不会因断开页面而停止。';$('#cfd-log').textContent='等待连接…';$('#cfd-dirty').hidden=true;drawResiduals();}
  $('#cfd-disconnect').onclick=()=>{resetConnection();$('#cfd-token').value='';message('已清除页面中的连接令牌；计算任务未停止。');};
  $('#cfd-connect').onclick=async()=>{
    resetConnection();const gen=generation;$('#cfd-connect').disabled=true;message('正在检测真实求解环境…');
    try {const url=new URL($('#cfd-url').value.trim());if(url.username||url.password||url.search||url.hash)throw Error('请填写不含凭据、查询参数或片段的服务地址');
      if(!canConnectService(url,location.protocol))throw Error('HTTPS 页面需要 HTTPS 求解地址；HTTP 工作台也支持内网 IP 或本机 HTTP 服务');
      const token=$('#cfd-token').value.trim(),cookie=url.origin===location.origin&&!token;if(!cookie&&token.length<24)throw Error('独立 CFD 服务需要至少24个字符的服务令牌；同源服务可留空并使用登录会话');
      const session={url:url.href.replace(/\/$/,''),token,cookie};const data=await api('/health',{},session);if(gen!==generation)return;
      if(data.model_only)throw Error('当前后端仅提供模型服务，请填写独立 CFD 服务器地址及其服务令牌');
      if(data.api!=='aeroblade-openfoam-v1'||!Array.isArray(data.templates))throw Error('服务不是兼容的 AeroBlade OpenFOAM 桥接端');
      connection=session;health=data;renderScheduler(data);$('#cfd-token').value='';$('#cfd-status').textContent=data.ready?'求解服务已就绪':'已连接 · 环境待配置';$('#cfd-status').classList.add('connected');$('#cfd-disconnect').disabled=false;$('#cfd-refresh').disabled=false;
      $('#cfd-connection-message').textContent=`OpenFOAM ${data.openfoam_version} · ${data.templates.length} 个模板 · 多算例调度`;
      $('#cfd-template').innerHTML=data.templates.length?data.templates.map(t=>`<option value="${escapeHTML(t.id)}">${escapeHTML(t.name||t.id)}</option>`).join(''):'<option>服务器未安装算例模板</option>';$('#cfd-template').disabled=!data.templates.length;const matching=data.templates.find(t=>(t.geometry_model||'legacy')===(getDesign().model||'legacy'));if(matching)$('#cfd-template').value=matching.id;renderInputs();await refreshJobs();
      if(gen!==generation)return;message(data.ready?'已连接真实求解服务。选择模板并核对工况后即可提交。':['服务已连接，但尚不能求解。',...(!data.templates.length?['请在求解机安装已验证的叶栅算例模板。']:[]),...(data.missing_commands?.length?['缺少命令：'+data.missing_commands.join(', ')]:[]),...(data.template_errors||[])].join(' '),!data.ready);
    }catch(e){if(gen===generation){resetConnection();message(e.message,true);}}finally{if(gen===generation)$('#cfd-connect').disabled=false;}
  };
  document.addEventListener('aeroblade:sessionchange',event=>{if(!event.detail.authenticated&&connection?.cookie){resetConnection();message('已退出平台登录；服务器计算任务不受影响。');}});
  function template(){return health?.templates.find(t=>t.id===$('#cfd-template').value)}
  function renderInputs(){const t=template();$('#cfd-apply-design').disabled=!t?.recommended_parameters||!applyDesign;$('#cfd-inputs').innerHTML='';$('#cfd-submit').disabled=!health?.ready||!t||busy;
    $('#cfd-template-info').textContent=t?`${t.solver} · ${t.description||t.name||t.id}`:'模板尚未配置。请在求解机安装已有的叶栅算例后重新连接。';
    if(!t)return;$('#cfd-inputs').innerHTML=t.inputs.map(i=>`<div><label for="cfd-param-${escapeHTML(i.key)}">${escapeHTML(i.label||i.key)} <small>${escapeHTML(i.unit)}</small></label><input id="cfd-param-${escapeHTML(i.key)}" data-condition="${escapeHTML(i.key)}" type="number" min="${i.min}" max="${i.max}" step="${i.integer?'1':'any'}" value="${i.default}" required><small class="cfd-range">${i.min} – ${i.max}</small></div>`).join('');
  }
  $('#cfd-template').onchange=renderInputs;
  $('#cfd-apply-design').onclick=()=>{const t=template();if(t?.recommended_parameters&&applyDesign){try{applyDesign(structuredClone(t.recommended_parameters));snapshot();message('已应用模板推荐叶片。提交时会再次检查几何约束。');}catch(e){message(e.message,true);}}};
  function payload(requireTemplate=true){const t=template();const design=validate(getDesign());if(t&&(t.geometry_model||'legacy')!==(design.model||'legacy'))throw Error('叶片模型与模板不匹配，请切换模板或应用模板推荐叶片');if(isPritchard(design))analyze(design);if(requireTemplate&&!t)throw Error('请先连接服务并选择算例模板');const conditions={};if(t)for(const i of t.inputs){const input=$('#cfd-param-'+i.key);if(!input.reportValidity())throw Error('请检查工况数值：'+i.label);conditions[i.key]=Number(input.value);}
    for(const c of t?.constraints||[]){const a=conditions[c.left],b=conditions[c.right];if(!({'>':a>b,'>=':a>=b,'<':a<b,'<=':a<=b})[c.op])throw Error(`工况约束：${c.left} ${c.op} ${c.right}`);}
    return {schema:'aeroblade-cfd-v1',name:$('#cfd-case-name').value.trim(),template_id:t?.id||null,parameters:structuredClone(design),geometry_model:design.model||'legacy',conditions,design_units:'mm',geometry_export_units:'m'};
  }
  function saveBlob(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}
  $('#cfd-request').onclick=()=>{try{const data=payload(false);saveBlob(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'aeroblade-cfd-request.json');message(data.template_id?'已导出叶片快照与模板工况。':'已导出叶片请求。尚未指定模板和工况，不能直接用于求解。');}catch(e){message(e.message,true)}};
  async function refreshJobs(prefer){
    if(!connection)return;const gen=generation,serial=++refreshSerial;clearTimeout(timer);
    const data=await api('/jobs');if(gen!==generation||serial!==refreshSerial)return;
    renderScheduler(data.scheduler);const current=$('#cfd-jobs').value,list=data.jobs||[];
    $('#cfd-jobs').innerHTML=list.length?list.map(j=>`<option value="${j.id}">${escapeHTML(j.name||j.id.slice(0,8))} · ${escapeHTML(labels[j.status]||j.status)} · ${escapeHTML(j.stage||j.solver)}</option>`).join(''):'<option>暂无任务</option>';
    $('#cfd-jobs').disabled=!list.length;
    if(list.length){$('#cfd-jobs').value=list.some(j=>j.id===prefer)?prefer:list.some(j=>j.id===current)?current:list.some(j=>j.id===selected?.id)?selected.id:list[0].id;await poll();}
    else scheduleRefresh();
  }
  $('#cfd-refresh').onclick=()=>refreshJobs().catch(e=>message(e.message,true));$('#cfd-jobs').onchange=()=>poll().catch(e=>message(e.message,true));
  async function poll(){clearTimeout(timer);if(!connection||$('#cfd-jobs').disabled)return;const gen=generation,id=$('#cfd-jobs').value,serial=++pollSerial;
    try{const j=await api('/jobs/'+id);if(gen!==generation||serial!==pollSerial||id!==$('#cfd-jobs').value)return;selected=j;renderJob(j);scheduleRefresh();}
    catch(e){if(gen===generation){message(e.message+'；可点击刷新任务重试。',true);scheduleRefresh();}}
  }
  function renderJob(j){flowView.setJob(j);const params=j.parameters;$('#cfd-job-state').innerHTML=`<div><strong>${escapeHTML(labels[j.status]||j.status)}</strong><span>${escapeHTML(j.stage)}</span></div><p>${escapeHTML(j.message)}</p><small title="${escapeHTML(j.name||'未命名算例')}">${escapeHTML(j.name||'未命名算例')} · 任务 ${escapeHTML(j.id.slice(0,8))} · ${escapeHTML(j.template_id)}${params?` · ${params.model==='pritchard-1985'?'Pritchard / 轴向弦长 '+params.axialChord:'旧模型 / 弦长 '+params.chord} mm`:''}</small>`;
    $('#cfd-cancel').disabled=terminal.has(j.status)||j.status==='cancelling';$('#cfd-results').disabled=!j.artifact_ready||j.status!=='completed';$('#cfd-log').textContent=j.log_tail||'任务尚未输出日志。';drawResiduals(j.residuals||[]);$('#cfd-convergence').textContent=j.convergence==='solver_reported'?'求解器报告满足其收敛判据；仍需检查质量守恒、工程指标及网格独立性。':j.status==='completed'?'进程正常结束，但未确认残差收敛。请审核日志和场数据。':'仅显示求解器真实残差；不生成示意流场或预测效率。';snapshot();const opt=[...$('#cfd-jobs').options].find(o=>o.value===j.id);if(opt)opt.textContent=`${j.name||j.id.slice(0,8)} · ${labels[j.status]||j.status} · ${j.stage||j.solver}`;
  }
  $('#cfd-submit').onclick=async()=>{if(busy)return;const gen=generation;try{const data=payload();busy=true;$('#cfd-submit').disabled=true;message('正在提交叶片快照与工况…');const j=await api('/jobs',{method:'POST',body:JSON.stringify(data)});if(gen!==generation)return;await refreshJobs(j.id);if(gen===generation)message('任务已提交到真实求解队列。');}catch(e){if(gen===generation)message(e.message,true)}finally{if(gen===generation){busy=false;$('#cfd-submit').disabled=!health?.ready||!template();}}};
  $('#cfd-cancel').onclick=async()=>{if(!selected)return;const gen=generation,id=selected.id;$('#cfd-cancel').disabled=true;try{await api('/jobs/'+id+'/cancel',{method:'POST'});if(gen===generation)await poll();}catch(e){if(gen===generation){message(e.message,true);$('#cfd-cancel').disabled=false;}}};
  $('#cfd-results').onclick=async()=>{if(!selected)return;const id=selected.id,gen=generation;$('#cfd-results').disabled=true;message('正在下载真实算例与结果…');try{const blob=await api('/jobs/'+id+'/artifacts');if(gen!==generation)return;saveBlob(blob,'aeroblade-'+id.slice(0,8)+'-results.zip');message('已下载结果。可使用 ParaView 打开 case 中的 VTK 场数据。');}catch(e){if(gen===generation)message(e.message,true)}finally{if(gen===generation)$('#cfd-results').disabled=false;}};
  drawResiduals();snapshot();
}
