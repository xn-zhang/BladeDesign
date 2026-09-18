import fs from 'node:fs';
import {build,stl,validate,isPritchard,analyze} from '../web/geometry.js';
const [input,output]=process.argv.slice(2);
const {parameters}=JSON.parse(fs.readFileSync(input,'utf8'));
const mesh=build(validate(parameters));
mesh.vertices=mesh.vertices.map(p=>p.map(x=>x*.001));
fs.writeFileSync(output,stl(mesh));
const bounds=[0,1].map(side=>[0,1,2].map(axis=>Math[side?'max':'min'](...mesh.vertices.map(p=>p[axis]))));
console.log(JSON.stringify({bounds_m:bounds,volume_m3:mesh.volume*1e-9,vertices:mesh.vertices.length,faces:mesh.faces.length,units:'m',geometry_model:parameters.model||'legacy',...(isPritchard(parameters)?{pitch_m:analyze(parameters).pitch*.001,exit_half_wedge_deg:analyze(parameters).exitHalfWedge}:{} )}));
