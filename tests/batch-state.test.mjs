import test from 'node:test';
import assert from 'node:assert/strict';
import {BatchRequests} from '../aeroblade/web/batch-state.js';
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
test('late control after logout cannot repopulate records or exports',async()=>{
 let epoch=0,batch='A',visible=null;const d=deferred(),states=[];const requests=new BatchRequests(()=>epoch,()=>0);
 const work=requests.control({id:'A',selected:()=>batch,request:()=>d.promise,apply:r=>visible=r,refresh:async()=>states.push('refresh'),busy:v=>states.push(v)});
 epoch++;batch=null;d.resolve({id:'A',privateResults:true});await work;
 assert.equal(visible,null);assert.deepEqual(states,[true]);
});
test('late control cannot replace a newly selected batch',async()=>{
 let selected='A',visible='B';const d=deferred();const requests=new BatchRequests(()=>0,()=>0);
 const work=requests.control({id:'A',selected:()=>selected,request:()=>d.promise,apply:r=>visible=r.id,refresh:async()=>{},busy:()=>{}});
 selected='B';d.resolve({id:'A'});await work;assert.equal(visible,'B');
});
test('historical preview A cannot overwrite B or an edited/generated plan',()=>{
 let epoch=0,revision=0;const requests=new BatchRequests(()=>epoch,()=>revision);
 const a=requests.previewTicket(),b=requests.previewTicket();assert.equal(a(),false);assert.equal(b(),true);
 revision++;assert.equal(b(),false);const c=requests.previewTicket();requests.invalidate();assert.equal(c(),false);
 const d=requests.previewTicket();epoch++;assert.equal(d(),false);
});
