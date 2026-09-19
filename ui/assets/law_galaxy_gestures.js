'use strict';
// Shared by the embedded galaxy and the self-contained HTML download.
function createGalaxyGestures({canvas,getZoom,onZoom,onRotate,onTap,onHover,onLeave,onActive,env=globalThis}) {
  const points=new Map();
  let distance=null, multiple=false;
  const clamp=value=>Math.max(.4,Math.min(2.8,value));
  const local=e=>{const r=canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top}};
  const separation=()=>{const [a,b]=points.values();return a&&b?Math.hypot(a.x-b.x,a.y-b.y):null};
  function down(e){
    if(e.pointerType==='mouse'&&e.button!==0)return;
    const p=local(e);
    points.set(e.pointerId,{...p,ox:p.x,oy:p.y,moved:false});
    canvas.setPointerCapture(e.pointerId);
    if(points.size>1)multiple=true;
    distance=separation();onActive(true);onLeave();
  }
  function move(e){
    const next=local(e),p=points.get(e.pointerId);
    if(!p){if(e.pointerType!=='touch'&&!points.size)onHover(next.x,next.y);return;}
    const dx=next.x-p.x,dy=next.y-p.y;
    Object.assign(p,next);p.moved ||= Math.hypot(p.x-p.ox,p.y-p.oy)>=6;
    if(points.size>1){
      const current=separation();
      if(distance>0&&current>0)onZoom(clamp(getZoom()*current/distance));
      distance=current;
    }else onRotate(dx,dy);
  }
  function end(e,cancelled=false){
    const p=points.get(e.pointerId);if(!p)return;
    const next=local(e);
    const tap=!cancelled&&!multiple&&!p.moved&&Math.hypot(next.x-p.ox,next.y-p.oy)<6;
    points.delete(e.pointerId);
    if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
    distance=separation();
    if(!points.size){multiple=false;onActive(false);}
    if(tap)onTap(next.x,next.y);
  }
  const up=e=>end(e),cancel=e=>end(e,true);
  function clear(){
    const ids=[...points.keys()];points.clear();distance=null;multiple=false;
    for(const id of ids)if(canvas.hasPointerCapture(id))canvas.releasePointerCapture(id);
    onActive(false);onLeave();
  }
  const wheel=e=>{e.preventDefault();onZoom(clamp(getZoom()*Math.exp(-e.deltaY*.001)))};
  const events={pointerdown:down,pointermove:move,pointerup:up,pointercancel:cancel,lostpointercapture:cancel,pointerleave:onLeave,wheel};
  for(const [type,handler] of Object.entries(events))canvas.addEventListener(type,handler,type==='wheel'?{passive:false}:undefined);
  env.addEventListener('blur',clear);
  return {dispose(){clear();for(const [type,handler] of Object.entries(events))canvas.removeEventListener(type,handler);env.removeEventListener('blur',clear)}};
}
if(typeof module!=='undefined'&&module.exports)module.exports={createGalaxyGestures};
