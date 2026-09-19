'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {createGalaxySound} = require('../ui/assets/law_galaxy_sound.js');

class Target {
  constructor() { this.listeners = new Map(); this.attrs = {}; }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  removeEventListener(name, fn) { if (this.listeners.get(name) === fn) this.listeners.delete(name); }
  setAttribute(key, value) { this.attrs[key] = value; }
  fire(name, event) { return this.listeners.get(name)?.(event); }
  focus() { this.focused=true; }
}
function fixture({deferResume = false, noAudio = false} = {}) {
  const doc = new Target(); doc.hidden = false;
  const root = {ownerDocument:doc, dataset:{}};
  const button = new Target(), slider = new Target(), readout = {}, volumeButton = new Target();
  slider.value = '12'; slider.parentElement = {hidden:true};
  const contexts = [], timers = new Map(), oscillators = [];
  let clock = 0, seq = 0, observer, finishResume;
  const parameter = () => ({value:0, setValueAtTime(v){this.value=v;}, exponentialRampToValueAtTime(v){this.value=v;}, setTargetAtTime(v){this.value=v;}, cancelScheduledValues(){}});
  const node = () => Object.assign({connect(){}, disconnect(){}}, Object.fromEntries(['gain','pan','frequency','threshold','knee','ratio','attack','release','delayTime'].map(k=>[k,parameter()])));
  class Context {
    constructor(){ this.state='suspended'; this.currentTime=0; this.destination=node(); this.gains=[]; contexts.push(this); }
    createGain(){ const n=node();this.gains.push(n);return n; }
    createBiquadFilter(){return node();}
    createDynamicsCompressor(){return node();}
    createDelay(){return node();}
    createStereoPanner(){return node();}
    createOscillator(){ const n=node(); n.started=false; n.start=()=>{n.started=true;}; n.stop=at=>{n.stoppedAt=at;};oscillators.push(n);return n; }
    async resume(){if(deferResume) await new Promise(resolve=>{finishResume=resolve;});this.state='running';}
    async suspend(){this.state='suspended';}
    async close(){this.state='closed';}
  }
  const env = new Target();
  Object.assign(env, {AudioContext:noAudio ? undefined:Context, performance:{now:()=>clock},
    setTimeout(fn, ms){const id=++seq;timers.set(id,{fn,ms});return id;},
    clearTimeout(id){timers.delete(id);},
    IntersectionObserver:class {
      constructor(callback){this.callback=callback;observer=this;}
      observe(){} disconnect(){this.disconnected=true;}
    }});
  const sound = createGalaxySound({root,button,slider,readout,volumeButton,env});
  const settle = async()=>{await Promise.resolve();await Promise.resolve();};
  return {root,button,slider,readout,volumeButton,doc,env,contexts,timers,oscillators,sound,
    tick:ms=>{clock+=ms;},
    async visible(value){observer.callback([{isIntersecting:value,intersectionRatio:value?1:0}]);await settle();},
    async visibility(value){doc.hidden=!value;await doc.fire('visibilitychange');await settle();},
    async runTimers(ms){for(const [id,t] of [...timers]) if(t.ms===ms){timers.delete(id);t.fn();}await settle();},
    endVoices(){oscillators.forEach(o=>o.onended?.());},
    resolveResume:async()=>{finishResume();await settle();},
    observer:()=>observer};
}

test('starts silent; explicit activation uses low default volume', async()=>{
  const f=fixture(); assert.equal(f.contexts.length,0);assert.equal(f.root.dataset.soundState,'off');
  f.sound.hover('a');assert.equal(f.oscillators.length,0);
  await f.button.fire('click');assert.equal(f.root.dataset.soundState,'playing');
  assert.equal(f.contexts[0].gains[0].gain.value,.12);assert.equal(f.slider.parentElement.hidden,false);
  assert.equal(f.button.attrs['aria-pressed'],'true');f.sound.dispose();
});
test('hover deduplication, rate limit, and simultaneous voice limit', async()=>{
  const f=fixture();await f.button.fire('click');f.sound.hover('a');
  const count=f.oscillators.length;f.sound.hover('a');f.sound.hover('b');assert.equal(f.oscillators.length,count);
  for(let i=0;i<20;i++){f.tick(250);f.sound.hover(`node-${i}`);}
  assert.equal(f.oscillators.length,16,'eight voices, two oscillators per voice');
  f.endVoices();f.tick(250);f.sound.hover('new');assert.equal(f.oscillators.length,20);f.sound.dispose();
});
test('background trail is sparse and ignores tiny pointer movements', async()=>{
  const f=fixture();await f.button.fire('click');f.sound.trail(.5,.5);
  const count=f.oscillators.length;f.sound.trail(.9,.9);f.tick(1500);f.sound.trail(.51,.51);
  assert.equal(f.oscillators.length,count);f.sound.trail(.9,.9);assert.equal(f.oscillators.length,count+2);f.sound.dispose();
});
test('volume clamps to 30 percent and zero produces no new voices', async()=>{
  const f=fixture();await f.button.fire('click');f.slider.value='100';f.slider.fire('input');
  assert.equal(f.readout.textContent,'30%');assert.equal(f.contexts[0].gains[0].gain.value,.3);
  f.slider.value='0';f.slider.fire('input');const count=f.oscillators.length;
  f.sound.hover('a');assert.equal(f.oscillators.length,count);f.sound.dispose();
});
test('leaving the galaxy stops ambience and suspends audio; returning resumes', async()=>{
  const f=fixture();await f.button.fire('click');await f.visible(false);
  assert.equal(f.root.dataset.soundState,'paused');assert.ok(![...f.timers.values()].some(t=>t.ms===9000));
  await f.runTimers(240);assert.equal(f.contexts[0].state,'suspended');
  await f.visible(true);assert.equal(f.root.dataset.soundState,'playing');
  await f.visibility(false);assert.equal(f.root.dataset.soundState,'paused');
  await f.visibility(true);assert.equal(f.root.dataset.soundState,'playing');f.sound.dispose();
});
test('switching off stays off after hiding and showing; disposal closes resources', async()=>{
  const f=fixture();await f.button.fire('click');await f.button.fire('click');
  const count=f.oscillators.length;await f.visible(false);await f.visible(true);f.sound.hover('a');
  assert.equal(f.root.dataset.soundState,'off');assert.equal(f.oscillators.length,count);
  assert.equal(f.slider.parentElement.hidden,true);f.sound.dispose();
  assert.equal(f.contexts[0].state,'closed');assert.equal(f.timers.size,0);assert.equal(f.button.listeners.size,0);assert.equal(f.observer().disconnected,true);
});
test('hiding while audio activation is pending cannot start ambience', async()=>{
  const f=fixture({deferResume:true});const activation=f.button.fire('click');await f.visible(false);
  await f.resolveResume();await activation;assert.equal(f.root.dataset.soundState,'paused');
  assert.equal(f.oscillators.length,0);await f.runTimers(240);assert.equal(f.contexts[0].state,'suspended');f.sound.dispose();
});
test('unsupported audio is reported without throwing or playing', async()=>{
  const f=fixture({noAudio:true});await f.button.fire('click');assert.equal(f.root.dataset.soundState,'unavailable');
  assert.equal(f.button.attrs['aria-pressed'],'false');assert.equal(f.oscillators.length,0);f.sound.dispose();
});

test('volume popover closes after three seconds while sound keeps playing',async()=>{
 const f=fixture();await f.button.fire('click');assert.equal(f.slider.parentElement.hidden,false);
 await f.runTimers(3000);assert.equal(f.slider.parentElement.hidden,true);
 assert.equal(f.root.dataset.soundState,'playing');assert.equal(f.volumeButton.attrs['aria-expanded'],'false');
 f.volumeButton.fire('click');assert.equal(f.slider.parentElement.hidden,false);f.sound.dispose();
});
test('volume interaction restarts timeout and dragging does not disappear mid-gesture',async()=>{
 const f=fixture();await f.button.fire('click');
 const old=[...f.timers].find(([id,t])=>t.ms===3000)[0];f.slider.fire('input');assert.ok(!f.timers.has(old));
 f.slider.fire('pointerdown');await f.runTimers(3000);assert.equal(f.slider.parentElement.hidden,false);
 f.env.fire('pointerup');await f.runTimers(3000);assert.equal(f.slider.parentElement.hidden,true);f.sound.dispose();
});
test('escape closes volume and restores keyboard focus; off hides the reopen control',async()=>{
 const f=fixture();await f.button.fire('click');f.doc.activeElement=f.slider;
 f.slider.fire('keydown',{key:'Escape',preventDefault(){}});
 assert.equal(f.slider.parentElement.hidden,true);assert.equal(f.volumeButton.focused,true);
 await f.button.fire('click');assert.equal(f.volumeButton.hidden,true);assert.equal(f.timers.size,1);f.sound.dispose();
});
