// Pritchard (1985), ASME 85-GT-219, equations 1–16 and Appendix C.
// Explicit mm/degree inputs. No implicit FORTRAN default-value switches.
export const MODEL='pritchard-1985';
export const specs=[['尺寸与叶栅','01',[
 ['radius','截面所在半径 R',30,1000,.1,'mm'],['bladeCount','叶片数 N',10,200,1,''],
 ['axialChord','轴向弦长 Cx',10,100,.1,'mm'],['tangentialChord','周向弦长 Ct',-60,100,.1,'mm'],
 ['throat','几何喉道 O',.5,80,.01,'mm']]],['边缘与角度','02',[
 ['leadingRadius','前缘半径 RLE',.1,6,.01,'mm'],['trailingRadius','尾缘半径 RTE',.05,3,.01,'mm'],
 ['inletAngle','进口叶片角 βin',-60,70,.1,'°'],['outletAngle','出口叶片角 βout',-80,-5,.1,'°'],
 ['inletHalfWedge','进口半楔角 εin',1,25,.1,'°'],['unguidedTurning','无导向转折角 UGT',.1,40,.1,'°']]]];
const rad=Math.PI/180;
const radius=5.5*25.4,bladeCount=51,trailingRadius=.016*25.4;
export const reference={model:MODEL,radius,bladeCount,axialChord:1.102*25.4,tangentialChord:15.0114,
 throat:2*Math.PI*radius/bladeCount*Math.cos(57*rad)-2*trailingRadius,
 leadingRadius:.031*25.4,trailingRadius,inletAngle:35,outletAngle:-57,inletHalfWedge:9,unguidedTurning:6.5,height:60};
export function validateParameters(p){
 if(!p||p.model!==MODEL)throw Error('缺少 Pritchard 模型标识');
 const keys=specs.flatMap(g=>g[2].map(i=>i[0]));
 if(Object.keys(p).some(k=>!['model','height',...keys].includes(k)))throw Error('Pritchard 参数含未知字段');
 for(const [,,items] of specs)for(const [key,label,lo,hi] of items){if(typeof p[key]!=='number'||!Number.isFinite(p[key])||p[key]<lo||p[key]>hi)throw Error(`${label} 必须在 ${lo}–${hi} 范围内`);}
 if(!Number.isInteger(p.bladeCount))throw Error('叶片数必须是整数');
 if(typeof p.height!=='number'||!Number.isFinite(p.height)||p.height<30||p.height>160)throw Error('拉伸展宽必须在30–160 mm');
 return Object.fromEntries(['model',...keys,'height'].map(k=>[k,p[k]]));
}
const normal=b=>[-Math.sin(b),Math.cos(b)];
const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const mix=(a,b,t)=>a+(b-a)*t;
function circle(center,r,a,b,n){return Array.from({length:n+1},(_,i)=>{const t=mix(a,b,i/n);return [center[0]+r*Math.cos(t),center[1]+r*Math.sin(t)];});}
function cubic(A,B,ba,bb,n){
 const h=B[0]-A[0];if(h<=1e-7)throw Error('连接点轴向顺序无效，请调整弦长、喉道或角度');
 const ma=Math.tan(ba),mb=Math.tan(bb);
 const at=t=>[A[0]+h*t,(2*t**3-3*t*t+1)*A[1]+(t**3-2*t*t+t)*h*ma+(-2*t**3+3*t*t)*B[1]+(t**3-t*t)*h*mb];
 return {points:Array.from({length:n+1},(_,i)=>at((1-Math.cos(Math.PI*i/n))/2)),at};
}
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
function intersects(a,b,c,d){
 const eps=1e-10,c1=cross(a,b,c),c2=cross(a,b,d),c3=cross(c,d,a),c4=cross(c,d,b);
 const on=(p,a,b)=>Math.abs(cross(a,b,p))<eps&&p[0]>=Math.min(a[0],b[0])-eps&&p[0]<=Math.max(a[0],b[0])+eps&&p[1]>=Math.min(a[1],b[1])-eps&&p[1]<=Math.max(a[1],b[1])+eps;
 return (c1*c2<0&&c3*c4<0)||on(a,c,d)||on(b,c,d)||on(c,a,b)||on(d,a,b);
}
export function sectionGeometry(input,n=48){
 const p=validateParameters(input),cx=p.axialChord,ct=p.tangentialChord,rl=p.leadingRadius,rt=p.trailingRadius;
 const pitch=2*Math.PI*p.radius/p.bladeCount,u=p.unguidedTurning*rad,bi=p.inletAngle*rad,bo=p.outletAngle*rad,ei=p.inletHalfWedge*rad;
 // Eliminating the uncovered-circle centre gives the same C1 closure equation
 // as Appendix F: s*cos(beta_out-e_out+UGT/2)=(O+2*RTE)*cos(UGT/2).
 const k=(p.throat+2*rt)*Math.cos(u/2)/pitch;
 if(k<=0||k>=1)throw Error('喉道与尾缘厚度超过节距允许范围');
 const eo=bo+u/2+Math.acos(k),b1=bo-eo,b2=b1+u,b3=bi+ei,b4=bi-ei,b5=bo+eo;
 if(eo<=0||eo>=Math.PI/2||[b1,b2,b3,b4,b5].some(b=>Math.abs(b)>=89*rad))throw Error('无法获得可行的尾缘半楔角；请调整喉道、出口角或转折角');
 const P1=[cx-rt*(1+Math.sin(b1)),rt*Math.cos(b1)],P2=[cx-rt+(p.throat+rt)*Math.sin(b2),pitch-(p.throat+rt)*Math.cos(b2)];
 const P3=[rl*(1-Math.sin(b3)),ct+rl*Math.cos(b3)],P4=[rl*(1+Math.sin(b4)),ct-rl*Math.cos(b4)],P5=[cx-rt*(1-Math.sin(b5)),-rt*Math.cos(b5)];
 if(!(0<P3[0]&&P3[0]<P2[0]&&P2[0]<P1[0]&&P1[0]<cx&&0<P4[0]&&P4[0]<P5[0]&&P5[0]<cx))throw Error('五个连接点顺序无效，请调整弦长、半径与喉道');
 const n1=normal(b1),n2=normal(b2),dn=n2.map((v,i)=>v-n1[i]),d=P2.map((v,i)=>v-P1[i]);
 const r0=(d[0]*dn[0]+d[1]*dn[1])/(dn[0]**2+dn[1]**2),center=P1.map((v,i)=>v-r0*n1[i]);
 if(!(r0>0)||Math.abs(distance(center,P2)-r0)>1e-7*cx)throw Error('喉后圆弧闭合失败');
 const suction=cubic(P3,P2,b3,b2,n),pressure=cubic(P4,P5,b4,b5,Math.ceil(n*1.3));
 const segments=[{name:'suction',points:suction.points},{name:'uncovered',points:circle(center,r0,b2+Math.PI/2,b1+Math.PI/2,n)},
 {name:'trailing',points:circle([cx-rt,0],rt,b1+Math.PI/2,b5-Math.PI/2,32)},
 {name:'pressure',points:pressure.points.slice().reverse()},
 {name:'leading',points:circle([rl,ct],rl,b4-Math.PI/2,b3+Math.PI/2-2*Math.PI,32)}];
 const points=segments.flatMap(s=>s.points.slice(0,-1));
 if(points.some(q=>!q.every(Number.isFinite)))throw Error('轮廓包含非有限坐标');
 for(let i=0;i<points.length;i++)for(let j=i+2;j<points.length;j++){
  if(i===0&&j===points.length-1)continue;
  if(intersects(points[i],points[(i+1)%points.length],points[j],points[(j+1)%points.length]))throw Error('轮廓自交，请调整周向弦长或角度');
 }
 // Check periodic copies: an admissible single profile must not intersect its neighbour.
 const shifted=points.map(([x,y])=>[x,y+pitch]);
 for(let i=0;i<points.length;i++)for(let j=0;j<points.length;j++){
  const a=points[i],b=points[(i+1)%points.length],c=shifted[j],d=shifted[(j+1)%points.length];
  if(Math.max(a[0],b[0])<Math.min(c[0],d[0])||Math.max(c[0],d[0])<Math.min(a[0],b[0])||Math.max(a[1],b[1])<Math.min(c[1],d[1])||Math.max(c[1],d[1])<Math.min(a[1],b[1]))continue;
  if(intersects(a,b,c,d))throw Error('相邻叶片相交，请增加节距或调整截面');
 }
 const area=Math.abs(points.reduce((sum,a,i)=>{const b=points[(i+1)%points.length];return sum+a[0]*b[1]-a[1]*b[0];},0))/2;
 if(area<1e-6*cx*cx)throw Error('截面积退化');
 return {points,segments,keyPoints:[P1,P2,P3,P4,P5],angles:[b1,b2,b3,b4,b5],circle:{center,radius:r0},pitch,exitHalfWedge:eo/rad,chord:Math.hypot(cx,ct),stagger:Math.atan2(ct,cx)/rad,solidity:Math.hypot(cx,ct)/pitch,area,throat:p.throat};
}
