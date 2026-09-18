const fmt=v=>Number(v).toLocaleString('zh-CN',{maximumSignificantDigits:7});
const stops=[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]];
function colour(t){const u=Math.max(0,Math.min(1,t))*4,i=Math.min(3,Math.floor(u)),f=u-i;return `rgb(${stops[i].map((v,k)=>Math.round(v+(stops[i+1][k]-v)*f)).join(',')})`;}
function inside(x,y,ids,points){let hit=false;for(let i=0,j=ids.length-1;i<ids.length;j=i++){const a=points[ids[i]],b=points[ids[j]];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])hit=!hit;}return hit;}
export function initFlowView(host,fetchFlow){
  host.innerHTML=`<div class="cfd-monitor-heading"><h3>流场可视化</h3><span>真实单元场 · XY</span></div>
    <p class="flow-meta">选择已完成任务以读取真实场数据</p>
    <div class="flow-toolbar"><label>物理量<select class="flow-field" disabled><option>等待场数据</option></select></label><label class="flow-mesh"><input type="checkbox" disabled>显示网格</label><button class="flow-reset" disabled>重置视图</button></div>
    <div class="flow-viewport"><canvas class="flow-canvas" aria-label="真实 CFD 二维单元云图：滚轮缩放，拖动平移" tabindex="0"></canvas><div class="flow-empty" role="status">完成计算后，显示对应任务的真实速度、压力与温度场。</div></div>
    <div class="flow-legend" hidden><div class="flow-legend-heading"><span class="flow-quantity"></span><span>单元值 · 无插值</span></div><div class="flow-ramp"></div><div class="flow-range"><span></span><span></span></div></div>
    <p class="flow-probe">悬停读取单元值 · 滚轮缩放 · 拖动平移</p><p class="flow-note cfd-help">无场数据区域不着色。当前仅支持二维结果；三维结果请下载 VTK。</p>`;
  const q=s=>host.querySelector(s),canvas=q('canvas'),ctx=canvas.getContext('2d'),select=q('.flow-field'),mesh=q('.flow-mesh input'),reset=q('.flow-reset');
  let data=null,boxes=[],sequence=0,key='',zoom=1,pan=[0,0],drag=null,w=1,h=1,dpr=1,transform=null;
  function controls(on){select.disabled=mesh.disabled=reset.disabled=!on;}
  function empty(message){data=null;boxes=[];drag=null;q('.flow-empty').hidden=false;q('.flow-empty').textContent=message;q('.flow-legend').hidden=true;controls(false);q('.flow-probe').textContent='悬停读取单元值 · 滚轮缩放 · 拖动平移';draw();}
  function clear(){sequence++;key='';empty('完成计算后，显示对应任务的真实速度、压力与温度场。');q('.flow-meta').textContent='选择已完成任务以读取真实场数据';q('.flow-note').textContent='无场数据区域不着色。当前仅支持二维结果；三维结果请下载 VTK。';}
  function draw(){
    w=Math.max(1,canvas.clientWidth);h=Math.max(1,canvas.clientHeight);dpr=Math.min(2,window.devicePixelRatio||1);
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.fillStyle='#f9fbfe';ctx.fillRect(0,0,w,h);if(!data)return;
    const [lo,hi]=data.bounds,s=Math.min((w-88)/(hi[0]-lo[0]),(h-72)/(hi[1]-lo[1]))*zoom,cx=(lo[0]+hi[0])/2,cy=(lo[1]+hi[1])/2;
    const vx=w/2+18,vy=h/2-12,tx=vx+pan[0]-cx*s,ty=vy+pan[1]+cy*s;transform={s,tx,ty,vx,vy};const X=x=>x*s+tx,Y=y=>ty-y*s,field=data.fields[select.value];
    if(!field)return;ctx.save();ctx.beginPath();ctx.rect(54,16,w-72,h-56);ctx.clip();
    for(let i=0;i<data.cells.length;i++){
      const ids=data.cells[i];ctx.beginPath();ids.forEach((id,n)=>{const p=data.points[id];if(n)ctx.lineTo(X(p[0]),Y(p[1]));else ctx.moveTo(X(p[0]),Y(p[1]));});ctx.closePath();
      const c=colour(field.max===field.min ? .5 : (field.values[i]-field.min)/(field.max-field.min));ctx.fillStyle=c;ctx.fill();ctx.strokeStyle=mesh.checked?'rgba(18,35,49,.36)':c;ctx.lineWidth=mesh.checked ? .5 : .35;ctx.stroke();
    }
    ctx.restore();ctx.strokeStyle='#c8d4e2';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(54,16);ctx.lineTo(54,h-40);ctx.lineTo(w-18,h-40);ctx.stroke();
    ctx.fillStyle='#61758c';ctx.font='12px system-ui';ctx.textAlign='center';
    for(let i=0;i<=4;i++){const x=54+(w-72)*i/4;ctx.textAlign=i===0?'left':i===4?'right':'center';ctx.fillText(String(Number(((x-tx)/s*1000).toFixed(1))),x,h-23);}
    ctx.textAlign='right';for(let i=0;i<=4;i++){const y=20+(h-64)*i/4;ctx.fillText(String(Number(((ty-y)/s*1000).toFixed(1))),49,y+3);}
    ctx.textAlign='center';ctx.fillText('x / mm',w/2,h-5);ctx.save();ctx.translate(10,h/2);ctx.rotate(-Math.PI/2);ctx.fillText('y / mm',0,0);ctx.restore();
  }
  function legend(){if(!data)return;const f=data.fields[select.value];q('.flow-quantity').textContent=f.label+' / '+f.unit;const labels=q('.flow-range').children;labels[0].textContent=fmt(f.min);labels[1].textContent=fmt(f.max);q('.flow-probe').textContent='悬停读取单元值 · 滚轮缩放 · 拖动平移';draw();}
  async function setJob(job){
    const next=job.id+':'+job.status;if(key===next)return;key=next;const seq=++sequence;
    empty(job.status==='completed'?'正在读取实际网格和场数据…':'此任务尚未完成；完成后显示对应真实流场。');
    q('.flow-meta').textContent='任务 '+job.id.slice(0,8);
    q('.flow-note').textContent=job.convergence==='solver_reported'?'求解器报告收敛；云图不代表网格独立性或工程精度验证。':'尚未确认收敛；请结合残差及网格检查评估结果。';
    if(job.status!=='completed')return;
    try{
      const result=await fetchFlow(job.id);if(seq!==sequence)return;
      if(result.schema!=='aeroblade-flow-v1'||result.job_id!==job.id||!result.cells?.length)throw Error('流场数据与所选任务不匹配');
      data=result;boxes=data.cells.map(ids=>{const ps=ids.map(i=>data.points[i]);return [Math.min(...ps.map(p=>p[0])),Math.min(...ps.map(p=>p[1])),Math.max(...ps.map(p=>p[0])),Math.max(...ps.map(p=>p[1]))];});
      select.replaceChildren(...Object.entries(data.fields).map(([id,f])=>{const opt=document.createElement('option');opt.value=id;opt.textContent=f.label+' ('+f.unit+')';return opt;}));
      select.value='speed';zoom=1;pan=[0,0];q('.flow-empty').hidden=true;q('.flow-legend').hidden=false;controls(true);
      q('.flow-meta').textContent=`任务 ${job.id.slice(0,8)} · 结果步 ${data.time} · ${data.cell_count.toLocaleString()} 个单元`;
      legend();
    }catch(error){if(seq===sequence){key='';empty(error.message);}}
  }
  select.addEventListener('change',legend);mesh.addEventListener('change',draw);
  reset.onclick=()=>{zoom=1;pan=[0,0];draw();};
  canvas.addEventListener('wheel',event=>{if(!data)return;event.preventDefault();const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,old=zoom;zoom=Math.max(.5,Math.min(16,zoom*Math.exp(-event.deltaY*.001)));const ratio=zoom/old;pan=[x-transform.vx-(x-transform.vx-pan[0])*ratio,y-transform.vy-(y-transform.vy-pan[1])*ratio];draw();},{passive:false});
  canvas.addEventListener('pointerdown',event=>{if(!data)return;drag={x:event.clientX,y:event.clientY,pan:[...pan]};canvas.setPointerCapture(event.pointerId);canvas.style.cursor='grabbing';});
  canvas.addEventListener('pointerup',()=>{drag=null;canvas.style.cursor='crosshair';});canvas.addEventListener('pointercancel',()=>{drag=null;canvas.style.cursor='crosshair';});
  canvas.addEventListener('pointermove',event=>{
    if(!data||!transform)return;if(drag){pan=[drag.pan[0]+event.clientX-drag.x,drag.pan[1]+event.clientY-drag.y];draw();return;}
    const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left-transform.tx)/transform.s,y=(transform.ty-(event.clientY-rect.top))/transform.s;
    const i=boxes.findIndex((b,i)=>x>=b[0]&&x<=b[2]&&y>=b[1]&&y<=b[3]&&inside(x,y,data.cells[i],data.points));
    if(i<0){q('.flow-probe').textContent='此处没有流体单元场数据';return;}const f=data.fields[select.value];
    q('.flow-probe').textContent=`单元 ${data.cell_ids[i]} · x ${fmt(x*1000)} / y ${fmt(y*1000)} mm · ${f.label} ${fmt(f.values[i])} ${f.unit}`;
  });
  canvas.addEventListener('keydown',event=>{if(event.key==='0'){zoom=1;pan=[0,0];draw();}});
  new ResizeObserver(draw).observe(canvas);clear();return {setJob,clear};
}
