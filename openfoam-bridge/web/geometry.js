import * as legacy from './legacy-geometry.js';
import {MODEL,specs as pritchardSpecs,reference,validateParameters,sectionGeometry} from './pritchard.js';
export {MODEL,reference,pritchardSpecs};
export const isPritchard=p=>p?.model===MODEL;
export const specs=pritchardSpecs;
export const presets={baseline:{...reference},slender:{...reference,axialChord:32},wide:{...reference,inletHalfWedge:12}};
export const getSpecs=p=>isPritchard(p)?pritchardSpecs:legacy.specs;
export const getPresets=p=>isPritchard(p)?presets:legacy.presets;
let cachedKey='',cachedGeometry;
export function analyze(p){const key=JSON.stringify(p);if(key!==cachedKey){cachedGeometry=sectionGeometry(p);cachedKey=key;}return cachedGeometry;}
export function frame(p){return isPritchard(p)?{chord:p.axialChord,height:p.height,taper:1,twist:0,stagger:0,sweep:0,lean:0}:p;}
export function validate(p){
 if(p?.model&&p.model!==MODEL)throw Error('未知几何模型');
 return isPritchard(p)?validateParameters(p):legacy.validate(p);
}
export function section(p,z){return legacy.section(frame(p),z);}
export function profile(p){return isPritchard(p)?analyze(p).points.map(([x,y])=>[x/p.axialChord,(y-p.tangentialChord/2)/p.axialChord]):legacy.profile(p);}
export function build(p,n=64,layers=24){validate(p);return isPritchard(p)?legacy.build(frame(p),n,layers,profile(p)):legacy.build(p,n,layers);}
export const stl=legacy.stl;
export const camber=legacy.camber;
export const thick=legacy.thick;
