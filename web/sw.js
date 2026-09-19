const SHELL='law-orbit-shell-v2';
const ASSETS=['./','index.html','style.css?v=orbit-1','fonts.css','app.mjs?v=orbit-1','store.mjs','reading.mjs','query.mjs','renderer.html','app.webmanifest?v=orbit-1','icon.svg','fonts/MaruBuri-Regular.woff2','fonts/MaruBuri-SemiBold.woff2','fonts/MaruBuri-Bold.woff2','fonts/Pretendard-SemiBold.woff2'];
self.addEventListener('install',event=>event.waitUntil(caches.open(SHELL).then(c=>c.addAll(ASSETS))));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);if(url.origin!==location.origin||event.request.method!=='GET'||url.pathname.endsWith('.json.gz')||url.pathname.endsWith('manifest.json'))return;
 event.respondWith((async()=>{const cache=await caches.open(SHELL);try{const response=await fetch(event.request);if(response.ok)await cache.put(event.request,response.clone());return response;}catch{const cached=await cache.match(event.request);if(cached)return cached;if(event.request.mode==='navigate')return cache.match(new URL('./',self.registration.scope));return new Response('Offline resource unavailable',{status:503});}})());
});
