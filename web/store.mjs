const memory=new Map();const pending=new Map();
export const DATA_CACHE='law-galaxy-data-v1';
async function cache(){try{return await caches.open(DATA_CACHE);}catch{return null;}}
export async function cached(ref){const c=await cache();return !!(c&&await c.match(new URL(ref.url,location.href)));}
export async function data(ref){
 if(memory.has(ref.url)){const value=memory.get(ref.url);memory.delete(ref.url);memory.set(ref.url,value);return value;}
 if(pending.has(ref.url))return pending.get(ref.url);
 const task=(async()=>{
  const url=new URL(ref.url,location.href);if(url.origin!==location.origin||!url.pathname.endsWith('/'+ref.sha256+'.json.gz'))throw Error('자료 경로가 올바르지 않습니다.');
  const c=await cache();let response=c&&await c.match(url),bytes;
  if(response)bytes=await response.arrayBuffer();
  else{response=await fetch(url);if(!response.ok)throw Error('자료를 받지 못했습니다. 인터넷 연결을 확인하세요.');bytes=await response.arrayBuffer();}
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==ref.sha256){if(c)await c.delete(url);throw Error('자료 검증에 실패했습니다. 다시 받아 주세요.');}
  if(!('DecompressionStream'in window))throw Error('자료 압축 해제를 지원하는 최신 브라우저로 열어 주세요.');
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const value=await new Response(stream).json();
  if(c){try{await c.put(url,new Response(bytes,{headers:{'Content-Type':'application/gzip'}}));}catch{/* Quota or private mode: online reading remains available. */}}
  memory.set(ref.url,value);while(memory.size>10)memory.delete(memory.keys().next().value);
  return value;
 })();pending.set(ref.url,task);try{return await task;}finally{pending.delete(ref.url);}
}
export async function clearSaved(){memory.clear();return caches.delete(DATA_CACHE);}
export async function saveAll(refs,progress,signal){let i=0;for(const ref of refs){if(signal?.aborted)break;await data(ref);progress(++i,refs.length);}return i;}
