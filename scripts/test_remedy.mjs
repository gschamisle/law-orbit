import assert from 'node:assert/strict';
import { test } from 'node:test';
import { matchingRemedyNotes } from '../web/remedy.mjs';
import { validateBridge, bridgeLabel, loadBridgeGroup } from '../web/cross-domain.mjs';

test('mixed exclusion and selected incorporation survive; changed wording hides notes', () => {
  const quote='① 행정심판법을 적용하지 아니한다. 다만, 제15조를 준용한다.';
  const r={law:'국세기본법',jo:'56',quote,labels:['적용 제외','일부 준용']};
  const guide={kind:'editorial-remedy-guide',schema:1,is_citation:false,entries:[r]};
  const a={jo:'56',text:'제56조(다른 법률과의 관계)\n'+quote+'\n② 다음 항'};
  assert.deepEqual(matchingRemedyNotes(guide,r.law,a),[r]);
  assert.deepEqual(matchingRemedyNotes(guide,r.law,{...a,text:a.text.replace('아니한다','한다')}),[]);
  assert.deepEqual(matchingRemedyNotes(guide,'관세법',a),[]);
  assert.deepEqual(matchingRemedyNotes({...guide,is_citation:true},r.law,a),[]);
  assert.deepEqual(matchingRemedyNotes(undefined,r.law,a),[]);
});

test('only selected remedy peers and matching snapshot dates are accepted', async () => {
  for (const peer of ['tax','customs','local_tax','labor','medical','privacy','public_institutions','ftc','housing','state_property']) {
    const b={kind:`remedy-${peer}-bridge`,schema:1,domain:peer,peer:'remedy',editions:{[peer]:'old',remedy:'new'},entries:[],laws:{},broad:{}};
    const manifest={domains:[{id:peer,built_at:'old'},{id:'remedy',built_at:'new'}]};
    const catalog={built_at:'old',laws:[]};
    assert.equal(validateBridge(b,peer,manifest,catalog),b);
    assert.throws(()=>validateBridge({...b,editions:{[peer]:'old',remedy:'other'}},peer,manifest,catalog));
    const group={kind:'domain-bridge-set',schema:1,domain:peer,bridges:['one','one']};
    await assert.rejects(loadBridgeGroup(group,peer,manifest,catalog,async()=>b));
  }
  assert.match(bridgeLabel({cross_domain:true,neighbor_domain:'remedy'}),/행정구제/);
  assert.throws(()=>validateBridge({kind:'remedy-fsc-bridge',schema:1,domain:'fsc',peer:'remedy'},'fsc',{},{}));
});

test('full-article notes cannot carry an old explanation into added exceptions', () => {
  const quote='제36조(처분에 대한 이의신청)\n③ 심판을 제기할 수 있다.\n⑧ 적용 제외';
  const row={law:'행정기본법',jo:'36',quote,full_article:true};
  const guide={kind:'editorial-remedy-guide',schema:1,is_citation:false,entries:[row]};
  assert.deepEqual(matchingRemedyNotes(guide,row.law,{jo:'36',text:quote}),[row]);
  assert.deepEqual(matchingRemedyNotes(guide,row.law,{jo:'36',text:quote+'\n⑨ 새로운 특례'}),[]);
});
