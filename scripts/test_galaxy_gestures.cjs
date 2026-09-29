const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createGalaxyGestures,createGalaxyTouchMode}=require(process.argv[2]||'../ui/assets/law_galaxy_gestures.js');
function setup(options={}){
 const events={},envEvents={},captured=new Set(),rotations=[],taps=[],activity=[],hovers=[],leaves=[];let zoom=1;
 const canvas={addEventListener:(k,v)=>events[k]=v,removeEventListener:k=>delete events[k],
  getBoundingClientRect:()=>({left:20,top:40}),setPointerCapture:id=>captured.add(id),
  hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id)};
 const env={addEventListener:(k,v)=>envEvents[k]=v,removeEventListener:k=>delete envEvents[k]};
 const api=createGalaxyGestures({canvas,env,getZoom:()=>zoom,onZoom:z=>zoom=z,
  onRotate:(x,y)=>rotations.push([x,y]),onTap:(x,y)=>taps.push([x,y]),onActive:a=>activity.push(a),onHover:(x,y)=>hovers.push([x,y]),onLeave:()=>leaves.push(true),...options});
 const send=(type,id,x,y,extra={})=>events[type]({pointerId:id,clientX:x+20,clientY:y+40,pointerType:'touch',button:0,...extra});
 return{send,events,envEvents,api,rotations,taps,activity,hovers,leaves,captured,get zoom(){return zoom}};
}
test('two fingers zoom in and out without rotating or selecting',()=>{
 const s=setup();s.send('pointerdown',1,0,0);s.send('pointerdown',2,100,0);
 s.send('pointermove',2,200,0);assert.equal(s.zoom,2);
 s.send('pointermove',2,50,0);assert.equal(s.zoom,.5);
 s.send('pointerup',2,50,0);s.send('pointerup',1,0,0);
 assert.deepEqual(s.rotations,[]);assert.deepEqual(s.taps,[]);assert.equal(s.activity.at(-1),false);
});
test('one-finger rotation continues smoothly after pinch ends',()=>{
 const s=setup();s.send('pointerdown',1,10,10);s.send('pointermove',1,15,20);
 s.send('pointerdown',2,115,20);s.send('pointermove',1,20,20);s.send('pointerup',2,115,20);
 s.send('pointermove',1,23,24);s.send('pointerup',1,23,24);
 assert.deepEqual(s.rotations,[[5,10],[3,4]]);assert.deepEqual(s.taps,[]);
});
test('a tap selects; dragging out and back does not',()=>{
 const s=setup();s.send('pointerdown',1,15,20);s.send('pointerup',1,15,20);
 s.send('pointerdown',2,30,30);s.send('pointermove',2,80,30);s.send('pointermove',2,30,30);s.send('pointerup',2,30,30);
 assert.deepEqual(s.taps,[[15,20]]);
});
test('third finger changes do not jump and never select',()=>{
 const s=setup();s.send('pointerdown',1,0,0);s.send('pointerdown',2,100,0);s.send('pointerdown',3,300,0);
 s.send('pointermove',3,400,0);assert.equal(s.zoom,1);s.send('pointerup',1,0,0);
 s.send('pointermove',3,550,0);assert.equal(s.zoom,1.5);
 s.send('pointerup',2,100,0);s.send('pointerup',3,550,0);assert.deepEqual(s.taps,[]);
});
test('cancel and lost capture leave no stuck gesture or accidental tap',()=>{
 for(const type of ['pointercancel','lostpointercapture']){
  const s=setup();s.send('pointerdown',1,0,0);s.send(type,1,0,0);s.send('pointerup',1,0,0);
  assert.deepEqual(s.taps,[]);assert.equal(s.activity.at(-1),false);assert.equal(s.captured.size,0);
 }
});
test('pinch and wheel clamp zoom; reversing at a limit responds immediately',()=>{
 const s=setup();s.send('pointerdown',1,0,0);s.send('pointerdown',2,100,0);s.send('pointermove',2,1000,0);
 assert.equal(s.zoom,2.8);s.send('pointermove',2,500,0);assert.equal(s.zoom,1.4);
 let prevented=false;s.events.wheel({deltaY:100000,preventDefault:()=>prevented=true});assert.equal(s.zoom,.4);assert.equal(prevented,true);
});
test('mouse drag, tap and right-click remain distinct',()=>{
 const s=setup(),mouse={pointerType:'mouse'};
 s.send('pointerdown',1,0,0,{...mouse,button:2});s.send('pointerup',1,0,0,mouse);assert.equal(s.taps.length,0);
 s.send('pointerdown',1,0,0,mouse);s.send('pointermove',1,20,10,mouse);s.send('pointerup',1,20,10,mouse);
 assert.deepEqual(s.rotations,[[20,10]]);assert.equal(s.taps.length,0);
});
test('blur and disposal release pointers and remove listeners',()=>{
 const s=setup();s.send('pointerdown',1,10,20);s.envEvents.blur();assert.equal(s.captured.size,0);assert.equal(s.activity.at(-1),false);
 s.api.dispose();assert.equal(Object.keys(s.events).length,0);assert.equal(Object.keys(s.envEvents).length,0);
});

test('initially disabled gestures do not capture, rotate, zoom, tap or hover',()=>{
 const s=setup({enabled:false});
 s.send('pointerdown',1,10,10);s.send('pointerdown',2,110,10);s.send('pointermove',2,210,10);
 s.send('pointerup',2,210,10);s.send('pointerup',1,10,10);
 s.send('pointermove',3,20,20,{pointerType:'mouse'});s.events.pointerleave();
 assert.equal(s.captured.size,0);assert.equal(s.zoom,1);
 for(const values of [s.rotations,s.taps,s.hovers,s.activity,s.leaves])assert.deepEqual(values,[]);
});

test('disabled wheel keeps native scrolling and enabling restores wheel zoom',()=>{
 const s=setup({enabled:false});let prevented=0;
 const wheel={deltaY:-100,preventDefault:()=>prevented++};
 s.events.wheel(wheel);assert.equal(prevented,0);assert.equal(s.zoom,1);
 s.api.setEnabled(true);s.events.wheel(wheel);assert.equal(prevented,1);assert.ok(s.zoom>1);
 s.api.setEnabled(false);const zoom=s.zoom;s.events.wheel(wheel);
 assert.equal(prevented,1);assert.equal(s.zoom,zoom);
});

test('disabling releases a pending tap and re-enabling ignores its leftover pointerup',()=>{
 const s=setup();s.send('pointerdown',1,10,10);assert.equal(s.captured.size,1);
 const leaves=s.leaves.length;s.api.setEnabled(false);
 assert.equal(s.captured.size,0);assert.equal(s.activity.at(-1),false);assert.equal(s.leaves.length,leaves+1);
 s.api.setEnabled(true);s.send('pointerup',1,10,10);assert.deepEqual(s.taps,[]);
 s.send('pointerdown',2,30,40);s.send('pointerup',2,30,40);assert.deepEqual(s.taps,[[30,40]]);
 s.send('pointermove',3,70,80,{pointerType:'mouse'});assert.deepEqual(s.hovers,[[70,80]]);
});

test('disabling during pinch releases both fingers and no residual movement survives',()=>{
 const s=setup();s.send('pointerdown',1,0,0);s.send('pointerdown',2,100,0);
 s.send('pointermove',2,150,0);assert.equal(s.zoom,1.5);
 s.api.setEnabled(false);assert.equal(s.captured.size,0);assert.equal(s.activity.at(-1),false);
 s.send('pointermove',2,250,0);s.api.setEnabled(true);
 s.send('pointermove',1,10,10);s.send('pointerup',1,10,10);s.send('pointerup',2,250,0);
 assert.equal(s.zoom,1.5);assert.deepEqual(s.rotations,[]);assert.deepEqual(s.taps,[]);
 s.send('pointerdown',3,0,0);s.send('pointermove',3,5,7);s.send('pointerup',3,5,7);
 assert.deepEqual(s.rotations,[[5,7]]);
});

test('clear releases pointers without disabling future gestures or creating a tap',()=>{
 const s=setup();s.send('pointerdown',1,10,10);s.api.clear();
 assert.equal(s.captured.size,0);assert.equal(s.activity.at(-1),false);
 s.send('lostpointercapture',1,10,10);s.send('pointerup',1,10,10);assert.deepEqual(s.taps,[]);
 s.send('pointerdown',2,50,50);s.send('pointerup',2,50,50);assert.deepEqual(s.taps,[[50,50]]);
});

function eventTarget(){
 const handlers=new Map(),attrs={};
 return {handlers,attrs,addEventListener(type,fn,options){
   const list=handlers.get(type)||[];list.push({fn,options});handlers.set(type,list);
  },removeEventListener(type,fn,options){
   handlers.set(type,(handlers.get(type)||[]).filter(h=>h.fn!==fn||h.options!==options));
  },setAttribute(name,value){attrs[name]=value},focus(){this.focused=true},
  fire(type,value={}){
   const event={...value,prevented:false,stopped:false,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};
   for(const {fn} of [...(handlers.get(type)||[])].sort((a,b)=>Number(!!b.options)-Number(!!a.options))){fn(event);if(event.stopped)break;}
   return event;
  },listeners(){return [...handlers.values()].reduce((n,list)=>n+list.length,0)}};
}

function modeSetup({coarse=true,legacyMedia=false,observer=true}={}){
 const root={dataset:{}},canvas=eventTarget(),button=eventTarget(),hint={},media=eventTarget(),env=eventTarget(),doc=eventTarget();
 media.matches=coarse;doc.hidden=false;env.document=doc;env.matchMedia=query=>{assert.equal(query,'(pointer: coarse)');return media};
 if(legacyMedia){
  const changes=[];media.addListener=fn=>changes.push(fn);media.removeListener=fn=>changes.splice(changes.indexOf(fn),1);
  media.fire=()=>{for(const fn of [...changes])fn()};media.listeners=()=>changes.length;
  delete media.addEventListener;delete media.removeEventListener;
 }
 let observerInstance;
 if(observer)env.IntersectionObserver=class{
  constructor(callback,options){this.callback=callback;this.options=options;observerInstance=this;}
  observe(target){this.target=target;}
  disconnect(){this.disconnected=true;}
 };
 const gestures={enabled:true,clears:0,setEnabled(value){this.enabled=value;if(!value)this.clear()},clear(){this.clears++}};
 const api=createGalaxyTouchMode({root,canvas,button,hint,gestures,env,doc});
 const see=(ratio,target=button)=>observerInstance.callback([{target,isIntersecting:ratio>0,intersectionRatio:ratio}]);
 return {root,canvas,button,hint,media,env,doc,gestures,api,see,get observer(){return observerInstance}};
}

test('coarse touch starts in scroll mode and an explicit button toggles interaction',()=>{
 const s=modeSetup();assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.gestures.enabled,false);
 assert.equal(s.button.hidden,false);assert.equal(s.button.textContent,'지도 조작');assert.equal(s.button.attrs['aria-pressed'],'false');
 assert.equal(s.canvas.tabIndex,-1);assert.match(s.canvas.attrs['aria-label'],/밀어 스크롤/);
 assert.equal(s.hint.textContent,'화면을 밀어 스크롤 · 지도를 움직이려면 지도 조작');
 s.button.fire('click');assert.equal(s.root.dataset.touchMode,'interact');assert.equal(s.gestures.enabled,true);
 assert.equal(s.button.textContent,'스크롤로 돌아가기');assert.equal(s.button.attrs['aria-pressed'],'true');
 assert.equal(s.canvas.tabIndex,0);assert.equal(s.hint.textContent,'지도 조작 중 · 한 손가락 회전, 두 손가락 확대');
 s.button.fire('click');assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.gestures.enabled,false);
});

test('desktop retains ordinary gestures while input-device changes reset touch interaction',()=>{
 const s=modeSetup({coarse:false});assert.equal(s.root.dataset.touchMode,'desktop');assert.equal(s.gestures.enabled,true);
 assert.equal(s.button.hidden,true);assert.equal(s.hint.hidden,true);assert.equal(s.canvas.tabIndex,0);
 s.button.fire('click');assert.equal(s.root.dataset.touchMode,'desktop');
 s.media.matches=true;s.media.fire('change');assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.gestures.enabled,false);
 s.button.fire('click');s.media.matches=false;s.media.fire('change');assert.equal(s.root.dataset.touchMode,'desktop');assert.equal(s.gestures.enabled,true);
 s.media.matches=true;s.media.fire('change');assert.equal(s.root.dataset.touchMode,'scroll');
});

test('Escape exits interaction before other keyboard actions and restores button focus',()=>{
 const s=modeSetup();let other=0;s.doc.addEventListener('keydown',()=>other++);
 const inactive=s.doc.fire('keydown',{key:'Escape'});assert.equal(inactive.prevented,false);assert.equal(other,1);
 s.button.fire('click');const active=s.doc.fire('keydown',{key:'Escape'});
 assert.equal(active.prevented,true);assert.equal(active.stopped,true);assert.equal(other,1);
 assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.button.focused,true);
 assert.equal(s.doc.handlers.get('keydown')[0].options,true);
 const desktop=modeSetup({coarse:false});assert.equal(desktop.doc.fire('keydown',{key:'Escape'}).prevented,false);
});

test('blur, pagehide, page hiding and both fullscreen transitions return to scroll mode',()=>{
 const s=modeSetup();
 for(const transition of ['blur','pagehide','hidden','fullscreen-enter','fullscreen-exit']){
  s.doc.hidden=false;s.button.fire('click');assert.equal(s.root.dataset.touchMode,'interact');
  const before=s.gestures.clears;
  if(transition==='blur')s.env.fire('blur');
  else if(transition==='pagehide')s.env.fire('pagehide',{persisted:true});
  else if(transition==='hidden'){s.doc.hidden=true;s.doc.fire('visibilitychange');}
  else{s.doc.fullscreenElement=transition==='fullscreen-enter'?s.root:null;s.doc.fire('fullscreenchange');}
  assert.equal(s.root.dataset.touchMode,'scroll',transition);assert.equal(s.gestures.enabled,false);assert.ok(s.gestures.clears>before);
 }
 s.doc.hidden=false;s.button.fire('click');s.doc.fire('visibilitychange');assert.equal(s.root.dataset.touchMode,'interact');
});

test('losing the visible exit button disables interaction at the specified threshold',()=>{
 const s=modeSetup();assert.equal(s.observer.target,s.button);assert.deepEqual(s.observer.options.threshold,[0,.75,1]);
 s.button.fire('click');s.see(.75);assert.equal(s.root.dataset.touchMode,'interact');
 s.see(.74);assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.gestures.enabled,false);
 s.button.fire('click');assert.equal(s.root.dataset.touchMode,'scroll');
 s.see(1);s.button.fire('click');s.see(0,{});assert.equal(s.root.dataset.touchMode,'interact');
 s.see(0);assert.equal(s.root.dataset.touchMode,'scroll');
});

test('mode disposal removes listeners and observer, and legacy media listeners are cleaned up',()=>{
 for(const legacyMedia of [false,true]){
  const s=modeSetup({legacyMedia});s.button.fire('click');s.api.dispose();
  assert.equal(s.gestures.enabled,false);assert.equal(s.root.dataset.touchMode,'scroll');assert.equal(s.observer.disconnected,true);
  for(const target of [s.button,s.media,s.env,s.doc])assert.equal(target.listeners(),0);
  const before=s.gestures.clears;s.api.dispose();s.button.fire('click');s.see(1);assert.equal(s.gestures.clears,before);
 }
 const noObserver=modeSetup({observer:false});noObserver.button.fire('click');assert.equal(noObserver.root.dataset.touchMode,'interact');noObserver.api.dispose();
});
