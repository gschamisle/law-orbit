import test from 'node:test';
import assert from 'node:assert/strict';
import {counterURL,mountPageviews} from '../web/pageviews.mjs';

test('only canonical public app counts; previews, exports and other hosts never do',()=>{
 assert.ok(counterURL('https://gschamisle.github.io/law-orbit/'));
 for(const href of ['http://127.0.0.1:8544/','http://localhost:8544/law-orbit/','file:///C:/law-orbit/index.html','https://gitlab.aigov.go.kr/gslee0819/law-orbit/','https://gschamisle.github.io/law-orbit/introduction.html','https://gschamisle.github.io/law-orbit/renderer.html','https://gschamisle.github.io.evil.test/law-orbit/'])assert.equal(counterURL(href),'');
 assert.equal(counterURL('https://gschamisle.github.io/law-orbit/',{online:false}),'');
 assert.equal(counterURL('https://gschamisle.github.io/law-orbit/',{topLevel:false}),'');
});

test('query and fragment never leave the app and aliases share one counter',()=>{
 assert.equal(counterURL('https://gschamisle.github.io/law-orbit/?q=private#article'),counterURL('https://gschamisle.github.io/law-orbit/index.html'));
 assert.ok(!counterURL('https://gschamisle.github.io/law-orbit/').includes('extraCount'));
});

test('mount issues one request, preserves app on failure and never invents a count',()=>{
 const requests=[];const badge={set src(value){requests.push(value);this.onerror();}};
 const container={ownerDocument:{createElement:()=>badge},textContent:'',replaceChildren(){throw Error('Failed badge must not appear');}};
 const options={href:'https://gschamisle.github.io/law-orbit/',online:true,topLevel:true};
 mountPageviews(container,options);mountPageviews(container,options);
 assert.equal(requests.length,1);assert.equal(badge.referrerPolicy,'no-referrer');assert.match(container.textContent,/집계 연결 안 됨/);
});
