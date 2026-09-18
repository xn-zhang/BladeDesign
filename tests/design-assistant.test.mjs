import test from 'node:test';
import assert from 'node:assert/strict';
import {reference} from '../openfoam-bridge/web/pritchard.js';
import {validateProposal, validateReply, requestAssistant, demoReply} from '../openfoam-bridge/web/design-assistant-client.js';

const proposal = () => ({schema:'aeroblade-initial-proposal-v1', units:{length:'mm',angle:'deg'}, parameters:{...reference}, sources:Object.fromEntries(Object.keys(reference).filter(k=>!['model','height'].includes(k)).map(k=>[k,'图19参考算例'])), aerodynamic:[], assumptions:['参考尺寸'], missing:[], warnings:['尚未进行气动评估']});
test('complete proposals preserve all eleven parameters and provenance', () => {
  const input=proposal(), result=validateProposal(input);
  assert.deepEqual(result.parameters,input.parameters);
  assert.equal(Object.keys(result.sources).length,11);
  assert.notEqual(result.parameters,input.parameters);
});
test('invalid units, missing sources, malformed values and infeasible geometry are rejected', () => {
  for(const mutate of [p=>p.units.angle='rad',p=>delete p.parameters.throat,p=>p.parameters.radius='139.7',p=>p.parameters.bladeCount=51.5,p=>p.parameters.throat=79,p=>delete p.sources.throat,p=>p.missing=['入口工况'],p=>p.aerodynamic=[{label:'效率',value:Infinity,unit:'',source:'模型'}]]){
    const p=proposal();mutate(p);assert.throws(()=>validateProposal(p));
  }
});
test('clarification replies are accepted without a proposal; malformed proposal cannot enter design', () => {
  assert.equal(validateReply({message:'请提供转速。',proposal:null}).proposal,null);
  assert.throws(()=>validateReply({message:'完成',proposal:{parameters:reference}}));
  assert.throws(()=>validateReply({message:'',proposal:null}));
});
test('demo asks for data without pretending to derive parameters; explicit reference action returns labeled proposal', () => {
  assert.equal(demoReply('设计一个效率90%的叶片').proposal,null);
  const reply=demoReply('载入参考方案');
  assert.match(reply.message,/参考/);
  assert.deepEqual(validateProposal(reply.proposal).parameters,reference);
  assert.equal(reply.proposal.aerodynamic.length,0);
});
test('API request uses the chosen provider, conversation and abort signal', async () => {
  const controller=new AbortController();let captured;
  const reply=await requestAssistant({provider:'domain',messages:[{role:'user',content:'设计要求'}],signal:controller.signal,fetchImpl:async (url,options)=>{
    captured={url,options};return {ok:true,json:async()=>({schema:'aeroblade-assistant-reply-v1',message:'请补充工况',proposal:null})};
  }});
  assert.equal(reply.message,'请补充工况');
  assert.equal(captured.url,'/api/design-assistant/chat');
  assert.equal(JSON.parse(captured.options.body).provider,'domain');
  assert.equal(captured.options.signal,controller.signal);
});
test('unconnected API and malformed reply surface actionable errors', async () => {
  await assert.rejects(requestAssistant({provider:'general',messages:[],fetchImpl:async()=>({ok:false,status:404})}),/尚未接入/);
  await assert.rejects(requestAssistant({provider:'general',messages:[],fetchImpl:async()=>({ok:true,json:async()=>({message:'错误',proposal:proposal() , schema:'bad'})})}),/协议/);
});
