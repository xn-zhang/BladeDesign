import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validate,analyze} from '../web/geometry.js';
function inspect(input){
const p=validate(input);
if(p.model!=='pritchard-1985')throw Error('Only Pritchard geometry is supported');
const g=analyze(p),round=v=>Math.round(v*1e8)/1e8;
const normalized={points:g.points.map(q=>q.map(v=>round(v/p.axialChord))),pitch:round(g.pitch/p.axialChord)};
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
return {geometry_hash:hash({normalized,scale:round(p.axialChord)}),geometry_group:hash(normalized),pitch:g.pitch,stagger:g.stagger,area:g.area};
}
const input=JSON.parse(readFileSync(0,'utf8'));
if(Array.isArray(input)){
  if(input.length>3000)throw Error('Geometry batch too large');
  console.log(JSON.stringify(input.map(p=>{try{return inspect(p)}catch(e){return {error:String(e.message).slice(0,600)}}})));
}else console.log(JSON.stringify(inspect(input)));
