const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createGalaxyGestures}=require(process.argv[2]||'../ui/assets/law_galaxy_gestures.js');
function setup(){
 const events={},envEvents={},captured=new Set(),rotations=[],taps=[],activity=[];let zoom=1;
 const canvas={addEventListener:(k,v)=>events[k]=v,removeEventListener:k=>delete events[k],
  getBoundingClientRect:()=>({left:20,top:40}),setPointerCapture:id=>captured.add(id),
  hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id)};
 const env={addEventListener:(k,v)=>envEvents[k]=v,removeEventListener:k=>delete envEvents[k]};
 const api=createGalaxyGestures({canvas,env,getZoom:()=>zoom,onZoom:z=>zoom=z,
  onRotate:(x,y)=>rotations.push([x,y]),onTap:(x,y)=>taps.push([x,y]),onActive:a=>activity.push(a),onHover:()=>{},onLeave:()=>{}});
 const send=(type,id,x,y,extra={})=>events[type]({pointerId:id,clientX:x+20,clientY:y+40,pointerType:'touch',button:0,...extra});
 return{send,events,envEvents,api,rotations,taps,activity,captured,get zoom(){return zoom}};
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
