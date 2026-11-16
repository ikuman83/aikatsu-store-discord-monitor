import assert from 'node:assert/strict';
import test from 'node:test';
import {
  STORES,TACHIKAWA_URL,parseOfficialTimestamp,chooseEvents,formatNotification,
} from '../src/index.mjs';

const checkedAt='2026-11-16T01:00:00.000Z';
const bic=STORES.find(x=>x.name==='ビックカメラ立川店');
const sample={status:'present',machines:[
  {store:bic.name,number:1,label:'5分前',updatedAt:'2026-11-16T00:55:00.000Z'},
]};
test('parses Japan-local official timestamp',()=>{
  assert.equal(parseOfficialTimestamp('2026-11-1610:55:00'),'2026-11-16T01:55:00.000Z');
  assert.throws(()=>parseOfficialTimestamp('2026-02-3010:55:00'));
  assert.throws(()=>parseOfficialTimestamp('yesterday'));
});
test('reappearance notification works even when machine last update is old',()=>{
  const snapshot=new Map([[bic.name,{status:'present',machines:[
    {store:bic.name,number:1,label:'15時間前',updatedAt:'2026-11-15T10:00:00.000Z'},
  ]}]]);
  const state=new Map([[bic.name,{status:'absent',missing_count:2}]]);
  assert.deepEqual(chooseEvents(snapshot,state,new Map(),checkedAt).events,['listing:'+bic.name+':initial']);
});
test('same timestamp is not repeatedly notified',()=>{
  const snapshot=new Map([[bic.name,sample]]);
  const state=new Map([[bic.name,{status:'present',missing_count:0}]]);
  const key=bic.name+'::1';
  assert.deepEqual(chooseEvents(snapshot,state,new Map([[key,'2026-11-15T00:55:00.000Z']]),checkedAt).events,
    ['machine:'+key+':2026-11-16T00:55:00.000Z']);
  assert.equal(chooseEvents(snapshot,state,new Map([[key,sample.machines[0].updatedAt]]),checkedAt).events.length,0);
});
test('unknown store state does not falsely become absent',()=>{
  const result=chooseEvents(new Map([[bic.name,{status:'unknown'}]]),new Map(),new Map(),checkedAt);
  assert.deepEqual(result.nextStores,[]);
});
test('requires two confirmed absent polls to reset presence',()=>{
  const input=new Map([[bic.name,{status:'absent'}]]);
  const first=chooseEvents(input,new Map([[bic.name,{status:'present',missing_count:0}]]),new Map(),checkedAt);
  assert.equal(first.nextStores[0].status,'present');
  const second=chooseEvents(input,new Map([[bic.name,{status:'present',missing_count:1}]]),new Map(),checkedAt);
  assert.equal(second.nextStores[0].status,'absent');
});
test('first listed sighting sends only one listing event',()=>{
  const events=chooseEvents(new Map([[bic.name,sample]]),new Map(),new Map(),checkedAt).events;
  assert.deepEqual(events,['listing:'+bic.name+':initial']);
});
test('notification stays simple, formatted and below Discord character limit',()=>{
  const text=formatNotification(new Map([[bic.name,sample]]),checkedAt,['listing:'+bic.name+':initial']);
  assert.match(text,/取扱店舗に掲載：ビックカメラ立川店/);
  assert.match(text,/ビックカメラ立川店\n1台目【稼働】 5分前/);
  assert.match(text,/確認時間：/);
  assert.ok(!text.includes('**'));
  assert.ok(!text.includes(TACHIKAWA_URL));
  assert.ok(text.length<2000);
});
