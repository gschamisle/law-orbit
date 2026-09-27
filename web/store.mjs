const memory=new Map(),pending=new Map(),packMemory=new Map(),packPending=new Map();
let packing=null;
export const DATA_CACHE='law-galaxy-data-v1';
async function cache(){try{return await caches.open(DATA_CACHE);}catch{return null;}}
function address(ref){
 if(!ref||!/^[a-f0-9]{64}$/.test(ref.sha256)||ref.url!==`data/${ref.sha256}.json.gz`||!Number.isSafeInteger(ref.bytes)||ref.bytes<1||ref.bytes>25*1024*1024)throw Error('자료 경로 또는 크기가 올바르지 않습니다.');
 return new URL(ref.url,location.href);
}
export function configureStorage(config){
 if(config&&(config.schema!==1||config.threshold!==8192||config.prefix_chars!==2||!config.buckets||Object.keys(config.buckets).some(k=>!/^[a-f0-9]{2}$/.test(k))))throw Error('자료 묶음 형식이 맞지 않습니다. 새 판본을 확인해 주세요.');
 if(config)Object.values(config.buckets).forEach(address);
 packing=config||null;packMemory.clear();
}
async function verify(bytes,ref){
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
 if(bytes.byteLength!==ref.bytes||digest!==ref.sha256)throw Error('자료 검증에 실패했습니다. 다시 받아 주세요.');
 return bytes;
}
async function decode(bytes){
 if(typeof DecompressionStream!=='function')throw Error('자료 압축 해제를 지원하는 최신 브라우저로 열어 주세요.');
 return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
}
async function physical(ref){
 const url=address(ref),c=await cache();let response=c&&await c.match(url);
 if(!response){response=await fetch(url);if(!response.ok)throw Error('자료를 받지 못했습니다. 인터넷 연결을 확인하세요.');}
 try{const bytes=await verify(await response.arrayBuffer(),ref);if(c){try{await c.put(url,new Response(bytes,{headers:{'Content-Type':'application/gzip'}}));}catch{}}return bytes;}
 catch(error){if(c)await c.delete(url);throw error;}
}
function packFor(ref){
 if(!packing||ref.bytes>packing.threshold)return null;
 const pack=packing.buckets[ref.sha256.slice(0,2)];if(!pack)throw Error('필요한 자료 묶음이 없습니다. 새 판본을 확인해 주세요.');return pack;
}
async function loadPack(ref){
 if(packMemory.has(ref.url)){const value=packMemory.get(ref.url);packMemory.delete(ref.url);packMemory.set(ref.url,value);return value;}
 if(packPending.has(ref.url))return packPending.get(ref.url);
 const task=(async()=>{const value=await decode(await physical(ref));if(value.kind!=='law-orbit-small-files'||value.schema!==1||!value.entries||typeof value.entries!=='object'||Array.isArray(value.entries))throw Error('자료 묶음의 내용이 올바르지 않습니다.');packMemory.set(ref.url,value.entries);while(packMemory.size>4)packMemory.delete(packMemory.keys().next().value);return value.entries;})();
 packPending.set(ref.url,task);try{return await task;}finally{packPending.delete(ref.url);}
}
export async function cached(ref){const url=address(ref),c=await cache();if(!c)return false;if(await c.match(url))return true;const pack=packFor(ref);return !!(pack&&await c.match(address(pack)));}
export async function data(ref){
 address(ref);const key=ref.url+'|'+ref.bytes;
 if(memory.has(key)){const value=memory.get(key);memory.delete(key);memory.set(key,value);return value;}
 if(pending.has(key))return pending.get(key);
 const task=(async()=>{
  const pack=packFor(ref);let bytes;
  if(pack){
   // Reuse verified legacy caches after upgrading, without another download.
   const c=await cache(),old=c&&await c.match(address(ref));
   if(old){try{bytes=await verify(await old.arrayBuffer(),ref);}catch(error){await c.delete(address(ref));throw error;}}
   else{const entries=await loadPack(pack),encoded=entries[ref.sha256];if(typeof encoded!=='string'||!/^[A-Za-z0-9+/]+={0,2}$/.test(encoded))throw Error('자료 묶음에 요청한 항목이 없습니다.');bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));await verify(bytes,ref);}
  }else bytes=await physical(ref);
  const value=await decode(bytes);memory.set(key,value);while(memory.size>10)memory.delete(memory.keys().next().value);return value;
 })();pending.set(key,task);try{return await task;}finally{pending.delete(key);}
}
export async function clearSaved(){memory.clear();packMemory.clear();return caches.delete(DATA_CACHE);}
export async function saveAll(refs,progress,signal){let i=0;for(const ref of refs){if(signal?.aborted)break;await data(ref);progress(++i,refs.length);}return i;}
