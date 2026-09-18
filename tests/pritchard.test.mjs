import test from 'node:test';
import assert from 'node:assert/strict';
import {reference,sectionGeometry} from '../aeroblade/web/pritchard.js';
import {build,validate} from '../aeroblade/web/geometry.js';
const near=(a,b,eps=1e-8)=>assert.ok(Math.abs(a-b)<eps,`${a} != ${b}`),dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
test('Figure 19 pitch, throat and printed 3.31 degree exit half-wedge',()=>{
 const g=sectionGeometry(reference);near(g.pitch/25.4,.67759841548,1e-10);near(g.throat/25.4,.337,5e-4);near(g.exitHalfWedge,3.31,.005);
 assert.equal(g.segments.length,5);assert.equal(g.keyPoints.length,5);
 near(dist(g.keyPoints[1],[reference.axialChord-reference.trailingRadius,g.pitch])-reference.trailingRadius,reference.throat);
});
test('Curve joins preserve position and tangent direction',()=>{
 const g=sectionGeometry(reference,240);
 for(let i=0;i<5;i++){const a=g.segments[i].points,b=g.segments[(i+1)%5].points;near(dist(a.at(-1),b[0]),0);
 const u=a.at(-1).map((x,j)=>x-a.at(-2)[j]),v=b[1].map((x,j)=>x-b[0][j]);assert.ok((u[0]*v[0]+u[1]*v[1])/(Math.hypot(...u)*Math.hypot(...v))>.998,`join ${i}`);}
});
test('Specified leading, trailing and uncovered radii',()=>{
 const g=sectionGeometry(reference);
 for(const [name,c,r] of [['leading',[reference.leadingRadius,reference.tangentialChord],reference.leadingRadius],['trailing',[reference.axialChord-reference.trailingRadius,0],reference.trailingRadius],['uncovered',g.circle.center,g.circle.radius]])for(const p of g.segments.find(s=>s.name===name).points)near(dist(p,c),r);
});
test('Length scaling and R/N invariance',()=>{
 const p={...reference};for(const k of ['radius','axialChord','tangentialChord','throat','leadingRadius','trailingRadius','height'])p[k]*=1.5;
 const a=sectionGeometry(reference),b=sectionGeometry(p),c=sectionGeometry({...reference,radius:reference.radius*2,bladeCount:reference.bladeCount*2});a.points.forEach((q,i)=>q.forEach((v,j)=>{near(b.points[i][j],v*1.5);near(c.points[i][j],v);}));
});
test('Closed mesh is manifold and volume matches section area times height',()=>{
 const g=sectionGeometry(reference),m=build(reference),edges=new Map();near(m.volume,g.area*reference.height,1e-6);
 for(const f of m.faces)for(let i=0;i<3;i++){const a=f[i],b=f[(i+1)%3],k=[Math.min(a,b),Math.max(a,b)].join(':');const e=edges.get(k)||[0,0];e[0]++;e[1]+=a<b?1:-1;edges.set(k,e);}assert.ok([...edges.values()].every(([count,orientation])=>count===2&&orientation===0));
});
test('Reject infeasible geometry, unknown fields and fractional blade counts',()=>{
 for(const p of [{...reference,throat:80},{...reference,bladeCount:51.5},{...reference,inletAngle:Infinity},{...reference,stagger:0},{...reference,axialChord:10}])assert.throws(()=>sectionGeometry(p));assert.throws(()=>validate({...reference,model:'unknown'}));
});
test('Legacy parameters remain on the historical engine',()=>{
 const p={chord:40,thickness:12,position:35,inlet:10,outlet:-5,stagger:0,height:60,taper:1,twist:0,sweep:0,lean:0};assert.equal(validate(p).model,undefined);assert.equal(build(p).vertices.length,3225);
});
