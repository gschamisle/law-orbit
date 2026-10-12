import test from 'node:test';
import assert from 'node:assert/strict';
import { createRendererChannel } from '../web/renderer-channel.mjs';
const origin='https://example.test';
function fixture() {
  const calls=[];
  const frame={contentWindow:{postMessage:(...args)=>calls.push(args)}};
  const channel=createRendererChannel(origin);
  const payload={mode:'spotlight',nodes:[{id:'real-article'}]};
  const event={origin,source:frame.contentWindow,data:{type:'galaxy-ready'}};
  return {calls,frame,channel,payload,event};
}
test('mounting never sends data through an iframe load callback',()=>{
  const s=fixture();s.channel.use(s.frame,s.payload);assert.deepEqual(s.calls,[]);
});
test('the current same-origin renderer receives the exact map only after ready',()=>{
  const s=fixture();s.channel.use(s.frame,s.payload);
  assert.equal(s.channel.ready(s.event,s.frame),true);
  assert.deepEqual(s.calls,[[{type:'galaxy-data',data:s.payload},origin]]);
});
test('foreign origin, sibling sender and unknown message are rejected',()=>{
  for(const bad of [{origin:'https://foreign.test'},{source:{}},{source:null},{data:{type:'galaxy-select'}},{data:null}]){
    const s=fixture();s.channel.use(s.frame,s.payload);
    assert.equal(s.channel.ready({...s.event,...bad},s.frame),false);assert.deepEqual(s.calls,[]);
    assert.equal(s.channel.ready(s.event,s.frame),true);
  }
});
test('an unmounted or replaced renderer cannot receive stale map data',()=>{
  const s=fixture();assert.equal(s.channel.ready(s.event,s.frame),false);
  s.channel.use(s.frame,s.payload);
  assert.equal(s.channel.ready(s.event,null),false);
  assert.equal(s.channel.ready(s.event,{contentWindow:s.frame.contentWindow}),false);
  const next={contentWindow:{postMessage:()=>assert.fail('stale event must not reach next frame')}};
  s.channel.use(next,{nodes:[]});assert.equal(s.channel.ready(s.event,next),false);
  assert.deepEqual(s.calls,[]);
});
test('a renderer reload can ask again without relaxing source validation',()=>{
  const s=fixture();s.channel.use(s.frame,s.payload);
  assert.equal(s.channel.ready(s.event,s.frame),true);
  assert.equal(s.channel.ready(s.event,s.frame),true);
  assert.equal(s.calls.length,2);
});
