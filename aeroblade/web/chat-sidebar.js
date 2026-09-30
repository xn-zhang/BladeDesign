import {currentSession,sessionFetch,captureIdentity,checkIdentity} from './session.js';

export function initChatSidebar(host,{isBusy}) {
  const main=document.createElement('div');main.className='initial-main';
  for(const child of [...host.children])if(child.tagName!=='DIALOG')main.append(child);
  const sidebar=document.createElement('aside');sidebar.className='initial-sidebar';sidebar.id='initial-sidebar';sidebar.setAttribute('aria-label','设计对话导航');
  sidebar.innerHTML=`<div class="initial-sidebar-brand"><span class="initial-brand-mark">A</span><strong>AeroBlade<small>设计对话</small></strong><button type="button" data-collapse aria-label="收起侧栏" title="收起侧栏">◧</button></div>
    <button type="button" class="initial-nav-new" data-new><span>＋</span> 新建对话</button>
    <label class="initial-search"><span aria-hidden="true">⌕</span><input type="search" placeholder="搜索会话名称" aria-label="搜索历史会话"></label>
    <div class="initial-history-heading"><span>已保存会话</span><button type="button" data-refresh aria-label="刷新历史会话" title="刷新历史会话">↻</button></div>
    <div class="initial-history" data-history></div><p class="initial-history-status" data-status role="status"></p>
    <div class="initial-sidebar-bottom"><button type="button" data-save>▤ <span>保存 / 管理对话</span></button><button type="button" data-model>◇ <span>模型配置</span></button><button type="button" data-account>◎ <span>账户设置<small data-user>登录后同步对话</small></span></button></div>`;
  host.prepend(sidebar);host.append(main);
  const toggle=document.createElement('button');toggle.type='button';toggle.id='initial-sidebar-toggle';toggle.textContent='☰';toggle.setAttribute('aria-label','切换对话侧栏');toggle.setAttribute('aria-controls',sidebar.id);main.querySelector('.initial-topbar>div').prepend(toggle);
  const backdrop=document.createElement('button');backdrop.type='button';backdrop.className='initial-sidebar-backdrop';backdrop.setAttribute('aria-label','关闭侧栏');host.append(backdrop);
  let items=[],serial=0,collapsed=matchMedia('(max-width:760px)').matches;
  const restoreDialog=document.createElement('dialog');restoreDialog.className='session-dialog';restoreDialog.innerHTML='<form method="dialog"><h2>继续历史对话</h2><p></p><div class="initial-dialog-actions"><button value="cancel">取消</button><button value="load" class="primary">载入对话</button></div></form>';host.append(restoreDialog);
  function confirmRestore(name){restoreDialog.querySelector('p').textContent=`载入“${name}”会替换当前对话与草稿。请先保存需要保留的内容。`;restoreDialog.returnValue='cancel';restoreDialog.showModal();return new Promise(resolve=>restoreDialog.addEventListener('close',()=>resolve(restoreDialog.returnValue==='load'),{once:true}));}
  function setCollapsed(value){collapsed=value;host.classList.toggle('sidebar-collapsed',value);toggle.setAttribute('aria-expanded',String(!value));}
  toggle.onclick=()=>setCollapsed(!collapsed);sidebar.querySelector('[data-collapse]').onclick=()=>setCollapsed(true);backdrop.onclick=()=>setCollapsed(true);
  host.addEventListener('keydown',event=>{if(event.key==='Escape')setCollapsed(true);});setCollapsed(collapsed);
  const status=sidebar.querySelector('[data-status]');
  async function api(path){const response=await sessionFetch('/api/personal/conversations'+path);const data=await response.json();if(!response.ok)throw Error(data.error||'读取对话失败');return data;}
  function render(){
    const query=sidebar.querySelector('input').value.trim().toLocaleLowerCase(),list=sidebar.querySelector('[data-history]');list.replaceChildren();
    const filtered=items.filter(item=>item.name.toLocaleLowerCase().includes(query));
    for(const item of filtered){
      const button=document.createElement('button');button.type='button';button.className='initial-history-item';button.title=item.name;
      const title=document.createElement('span');title.textContent=item.name;const date=document.createElement('small');date.textContent=new Date(item.updated_at*1000).toLocaleDateString();button.append(title,date);
      button.onclick=async()=>{
        if(isBusy()){status.textContent='请先停止当前生成，再切换会话。';return;}
        const identity=captureIdentity(),id=serial;
        if(!await confirmRestore(item.name))return;button.disabled=true;
        try{checkIdentity(identity);if(id!==serial)return;if(isBusy())throw Error('请先停止当前生成，再切换会话。');const data=await api('/'+item.id);checkIdentity(identity);if(id!==serial)return;host.restoreConversationSnapshot(data.payload);for(const b of list.children)b.classList.remove('active');button.classList.add('active');if(matchMedia('(max-width:760px)').matches)setCollapsed(true);}
        catch(error){if(id===serial)status.textContent=error.message;}finally{button.disabled=false;}
      };list.append(button);
    }
    status.textContent=filtered.length?'':query?'没有匹配的会话。':currentSession()?.authenticated?'保存对话后，可以在这里继续设计。':'登录后查看自己的历史会话。';
  }
  async function refresh(){
    const id=++serial;items=[];render();sidebar.querySelector('[data-user]').textContent=currentSession()?.authenticated?currentSession().username:'登录后同步对话';
    if(!currentSession()?.authenticated)return;status.textContent='正在读取…';
    try{const data=await api('');if(id!==serial)return;items=data.items;render();}catch(error){if(id===serial)status.textContent=error.message;}
  }
  sidebar.querySelector('input').oninput=render;sidebar.querySelector('[data-refresh]').onclick=refresh;
  sidebar.querySelector('[data-new]').onclick=()=>{host.querySelector('#initial-new').click();if(matchMedia('(max-width:760px)').matches)setCollapsed(true);};
  sidebar.querySelector('[data-model]').onclick=()=>host.querySelector('#initial-model-settings').click();
  sidebar.querySelector('[data-account]').onclick=()=>document.querySelector('#account-menu')?.click();
  sidebar.querySelector('[data-save]').onclick=()=>document.querySelector('#personal-conversations')?.click();
  document.addEventListener('aeroblade:sessionchange',()=>{if(restoreDialog.open){restoreDialog.returnValue='cancel';restoreDialog.close();}void refresh();});document.addEventListener('aeroblade:conversationschange',refresh);
  void refresh();return {refresh};
}
