import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createContext,runInContext} from 'node:vm';

const source=readFileSync(new URL('../web/sw.js',import.meta.url),'utf8');
const scope='https://example.test/law-orbit/';
const oldShell='law-orbit-shell-compact-map-controls-v1';
const dataCache='law-galaxy-data-v1',manifestCache='law-galaxy-manifest-v1';

function worker({claimError,keysError,installError,offline=false,failOpen=[],failRead=[],failDelete=[]}={}){
 const listeners=new Map(),saved=new Map(),operations=[];
 const key=value=>new URL(typeof value==='string'?value:value.url||String(value),scope).href;
 const seed=(name,entries)=>saved.set(name,new Map(entries.map(([url,text])=>[key(url),new Response(text)])));
 const caches={
  async keys(){if(keysError)throw keysError;return [...saved.keys()];},
  async open(name){
   if(failOpen.includes(name))throw Error('open unavailable');
   if(!saved.has(name))saved.set(name,new Map());
   const entries=saved.get(name);
   return {
    async addAll(urls){
     operations.push(['install',name]);
     if(installError)throw installError;
     for(const url of urls)entries.set(key(url),new Response(`installed ${url}`));
    },
    async keys(){if(failRead.includes(name))throw Error('read unavailable');return [...entries.keys()].map(url=>({url}));},
    async match(url){if(failRead.includes(name))throw Error('read unavailable');return entries.get(key(url))?.clone();},
    async put(url,response){entries.set(key(url),response.clone());},
   };
  },
  async delete(name){operations.push(['delete',name]);if(failDelete.includes(name))throw Error('delete unavailable');return saved.delete(name);},
 };
 const context=createContext({caches,URL,Response,location:{origin:new URL(scope).origin},fetch:async()=>{if(offline)throw Error('offline');return new Response('network');},self:{
  registration:{scope},
  clients:{async claim(){operations.push(['claim']);if(claimError)throw claimError;}},
  addEventListener(type,callback){listeners.set(type,callback);},
 }});
 runInContext(source,context);
 const shell=runInContext('SHELL',context);
 const assets=Array.from(runInContext('ASSETS',context));
 const lifecycle=async type=>{
  let work;listeners.get(type)({waitUntil(value){work=value;}});
  await work;
 };
 const request=url=>{
  let response;listeners.get('fetch')({request:{url:key(url),method:'GET',mode:'navigate'},respondWith(value){response=value;}});
  return response;
 };
 return {saved,operations,seed,shell,assets,lifecycle,request,key};
}

function seedProtected(w){
 w.seed(dataCache,[['data/saved.json.gz','saved law text']]);
 w.seed(manifestCache,[['manifest.json','offline manifest']]);
 w.seed('another-app-cache-v1',[['../other-app/index.html','other app']]);
 // A reused shell prefix still does not authorize deleting another app's files.
 w.seed('law-orbit-shell-sibling-v1',[['../other-app/index.html','sibling app']]);
}

test('installation saves the shell including the annex-link module for offline use',async()=>{
 const w=worker();await w.lifecycle('install');
 assert.notEqual(w.shell,oldShell);
 assert(w.saved.get(w.shell).has(w.key('annex-links.mjs')));
 assert(w.saved.get(w.shell).has(w.key('./')));
 assert(w.saved.get(w.shell).has(w.key('renderer.html')));
 assert(w.saved.get(w.shell).has(w.key('fonts/MaruBuri-LICENSE.txt')));
 assert(w.saved.get(w.shell).has(w.key('fonts/Pretendard-LICENSE.txt')));
});

test('activation deletes only obsolete shells belonging to this app after claiming clients',async()=>{
 const w=worker();seedProtected(w);
 w.seed(oldShell,[['index.html','old shell']]);
 w.seed('law-galaxy-shell-v1',[['./','initial shell']]);
 w.seed('law-orbit-shell-empty-v1',[]);
 await w.lifecycle('install');
 const protectedNames=[dataCache,manifestCache,'another-app-cache-v1','law-orbit-shell-sibling-v1'];
 const protectedEntries=protectedNames.map(name=>w.saved.get(name));
 await w.lifecycle('activate');
 assert.equal(w.saved.has(oldShell),false);
 assert.equal(w.saved.has('law-galaxy-shell-v1'),false);
 assert.equal(w.saved.has('law-orbit-shell-empty-v1'),false);
 assert(w.saved.has(w.shell));
 protectedNames.forEach((name,index)=>assert.equal(w.saved.get(name),protectedEntries[index]));
 assert.deepEqual(w.operations.filter(([op])=>op!=='install').map(([op])=>op),['claim','delete','delete','delete']);
 assert.equal(await w.saved.get(dataCache).get(w.key('data/saved.json.gz')).text(),'saved law text');
 assert.equal(await w.saved.get(manifestCache).get(w.key('manifest.json')).text(),'offline manifest');
});

test('failed client claim leaves all old caches intact',async()=>{
 const w=worker({claimError:Error('claim failed')});w.seed(oldShell,[['./','old']]);seedProtected(w);
 await w.lifecycle('install');
 await assert.rejects(w.lifecycle('activate'),/claim failed/);
 assert(w.saved.has(oldShell));
 assert.equal(w.operations.some(([op])=>op==='delete'),false);
});

test('failed installation leaves the prior offline shell and saved data intact',async()=>{
 const w=worker({installError:Error('precache failed')});w.seed(oldShell,[['./','old']]);seedProtected(w);
 await assert.rejects(w.lifecycle('install'),/precache failed/);
 assert(w.saved.has(oldShell));assert(w.saved.has(dataCache));assert(w.saved.has(manifestCache));
 assert.equal(w.operations.some(([op])=>op==='claim'||op==='delete'),false);
});

test('missing or incomplete new shell retains every old shell',async()=>{
 for(const incomplete of [false,true]){
  const w=worker();w.seed(oldShell,[['./','old']]);
  if(incomplete){await w.lifecycle('install');w.saved.get(w.shell).delete(w.key('index.html'));}
  await w.lifecycle('activate');
  assert(w.saved.has(oldShell));
  assert.equal(w.operations.some(([op])=>op==='delete'),false);
 }
});

test('unavailable cache inventory or replacement shell does not block activation or delete old data',async()=>{
 for(const options of [{keysError:Error('inventory unavailable')},{failOpen:[]},{failRead:[]}]){
  const w=worker(options);w.seed(oldShell,[['./','old']]);seedProtected(w);
  await w.lifecycle('install');
  // Fail the actual replacement cache only during activation. A release may
  // rename SHELL; a stale literal would silently stop injecting the failure.
  (options.failOpen||options.failRead)?.push(w.shell);
  await w.lifecycle('activate');
  assert(w.saved.has(oldShell));assert(w.saved.has(dataCache));assert(w.saved.has(manifestCache));
  assert(w.saved.has(w.shell));
  assert.equal(w.operations.filter(([op])=>op==='claim').length,1);
  assert.equal(w.operations.some(([op])=>op==='delete'),false);
 }
});

test('one inaccessible or undeletable old shell does not block cleanup of other obsolete shells',async()=>{
 for(const option of ['failOpen','failRead','failDelete']){
  const w=worker({[option]:[oldShell]});w.seed(oldShell,[['./','old']]);seedProtected(w);
  w.seed('law-galaxy-shell-v1',[['./','initial']]);
  await w.lifecycle('install');await w.lifecycle('activate');
  assert(w.saved.has(oldShell));assert.equal(w.saved.has('law-galaxy-shell-v1'),false);
  assert(w.saved.has(dataCache));assert(w.saved.has(manifestCache));
 }
});

test('mixed-scope and foreign-origin shell caches are retained',async()=>{
 const w=worker();
 for(const url of ['../law-orbit-other/index.html','https://elsewhere.test/law-orbit/index.html']){
  w.seed(oldShell,[['./','local'],[url,'not owned']]);
  await w.lifecycle('install');await w.lifecycle('activate');
  assert(w.saved.has(oldShell));
 }
});

test('the new offline shell remains readable while data and manifest requests stay outside the worker',async()=>{
 const w=worker({offline:true});w.seed(oldShell,[['./','old']]);seedProtected(w);
 await w.lifecycle('install');await w.lifecycle('activate');
 assert.equal(await (await w.request('annex-links.mjs')).text(),'installed annex-links.mjs');
 assert.equal(await (await w.request('some-offline-page')).text(),'installed ./');
 assert.equal(w.request('data/saved.json.gz'),undefined);
 assert.equal(w.request('manifest.json'),undefined);
 assert.equal(w.request('https://elsewhere.test/index.html'),undefined);
});
