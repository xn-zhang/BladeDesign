import test from 'node:test';import assert from 'node:assert/strict';
test('cross-tab identity changes clear stale UI without rebroadcast loops',async()=>{
 const oldDocument=globalThis.document,oldChannel=globalThis.BroadcastChannel,oldFetch=globalThis.fetch;let channel;const messages=[],events=[];
 try{
  globalThis.document={dispatchEvent:e=>events.push(e.detail)};
  globalThis.BroadcastChannel=class{constructor(){channel=this;}postMessage(m){messages.push(m);}};
  const {refreshSession,currentSession}=await import('../aeroblade/web/session.js');
  globalThis.fetch=async()=>new Response(JSON.stringify({authenticated:true,user_id:'a',username:'alice',csrf:'a'}));await refreshSession();assert.equal(messages.at(-1).userId,'a');
  globalThis.fetch=async()=>new Response(JSON.stringify({authenticated:true,user_id:'b',username:'bob',csrf:'b'}));const count=messages.length;await channel.onmessage({data:{userId:'b'}});
  assert.equal(currentSession().user_id,'b');assert.equal(messages.length,count);assert.ok(events.some(e=>!e.authenticated));
 }finally{globalThis.document=oldDocument;globalThis.BroadcastChannel=oldChannel;globalThis.fetch=oldFetch;}
});
