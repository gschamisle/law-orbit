const SHELL='law-orbit-shell-tax-license-v2';
const ASSETS=['./','index.html','notices.html','notices.css','style.css?v=orbit-procurement-structure-v1','fonts.css','app.mjs?v=orbit-procurement-structure-v1','procurement-pdf.mjs','feedback.mjs','store.mjs','reading.mjs','annex.mjs','annex-links.mjs','pageviews.mjs','cross-domain.mjs','special.mjs','public-scope.mjs','delegation.css?v=orbit-procurement-structure-v1','delegation.mjs','delegation-ui.mjs','query.mjs','renderer.html','app.webmanifest?v=orbit-1','icon.svg','fonts/MaruBuri-Regular.woff2','fonts/MaruBuri-SemiBold.woff2','fonts/MaruBuri-Bold.woff2','fonts/Pretendard-SemiBold.woff2','fonts/MaruBuri-LICENSE.txt','fonts/Pretendard-LICENSE.txt'];
self.addEventListener('install',event=>event.waitUntil(caches.open(SHELL).then(c=>c.addAll(ASSETS))));
async function cleanupOldShells(){
 // CacheStorage belongs to the whole origin. Never clear saved law data,
 // the offline manifest, or a sibling application's cache.
 try{
  const names=await caches.keys();
  if(!names.includes(SHELL))return;
  const current=await caches.open(SHELL),scope=new URL(self.registration.scope);
  for(const asset of ASSETS){if(!(await current.match(new URL(asset,scope)))?.ok)return;}
  for(const name of names){
   if(name===SHELL||!(name.startsWith('law-orbit-shell-')||name==='law-galaxy-shell-v1'))continue;
   try{
    const old=await caches.open(name),requests=await old.keys();
    if(requests.every(request=>{const url=new URL(request.url);return url.origin===scope.origin&&url.pathname.startsWith(scope.pathname);})){await caches.delete(name);}
   }catch{/* A failed cleanup must not prevent the new worker from activating. */}
  }
 }catch{/* Retain old caches when cache availability cannot be established. */}
}
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 await self.clients.claim();
 await cleanupOldShells();
})()));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);if(url.origin!==location.origin||event.request.method!=='GET'||url.pathname.endsWith('.json.gz')||url.pathname.endsWith('manifest.json'))return;
 event.respondWith((async()=>{const cache=await caches.open(SHELL);try{const response=await fetch(event.request);if(response.ok)await cache.put(event.request,response.clone());return response;}catch{const cached=await cache.match(event.request);if(cached)return cached;if(event.request.mode==='navigate')return cache.match(new URL('./',self.registration.scope));return new Response('Offline resource unavailable',{status:503});}})());
});
