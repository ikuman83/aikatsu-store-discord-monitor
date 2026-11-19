import assert from 'node:assert/strict';
import test from 'node:test';
import {
  STORES,TACHIKAWA_URL,parseOfficialTimestamp,isRecentlyUpdated,chooseEvents,formatNotification,
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
  assert.match(text,/取扱店舗への新規掲載を検知：ビックカメラ立川店/);
  assert.match(text,/ビックカメラ立川店\n1台目【稼働】 5分前/);
  assert.match(text,/確認時間：/);
  assert.ok(!text.includes('**'));
  assert.ok(!text.includes(TACHIKAWA_URL));
  assert.ok(text.length<2000);
});

test('old relative updates at 00:15 and 13:15 never trigger an automatic alert',()=>{
  const before='2026-11-19T00:15:00+09:00';
  const after='2026-11-19T13:15:00+09:00';
  const key=bic.name+'::1';
  const prev=new Map([[bic.name,{status:'present',missing_count:0}]]);
  // The stored baseline might be even older than the screen shows.
  const machines=new Map([[key,'2026-11-18T01:00:00.000Z']]);
  const snapshot1=new Map([[bic.name,{status:'present',machines:[
    {store:bic.name,number:1,label:'14時間前',updatedAt:'2026-11-18T01:15:00.000Z'}
  ]}]]);
  const snapshot2=new Map([[bic.name,{status:'present',machines:[
    {store:bic.name,number:1,label:'1日前',updatedAt:'2026-11-18T01:15:00.000Z'}
  ]}]]);
  assert.deepEqual(chooseEvents(snapshot1,prev,machines,before).events,[]);
  assert.deepEqual(chooseEvents(snapshot2,prev,machines,after).events,[]);
});

test('a machine newer than its stored baseline but already hours old must not alert',()=>{
  const previous=new Map([[bic.name,{status:'present',missing_count:0}]]);
  const key=bic.name+'::1';
  const oldMachines=new Map([[key,'2026-11-18T08:00:00.000Z']]);
  const scannedAt='2026-11-19T13:15:00+09:00';
  const m={store:bic.name,number:1,label:'5時間前',updatedAt:'2026-11-19T00:15:00.000Z'};
  const result=chooseEvents(new Map([[bic.name,{status:'present',machines:[m]}]]),
    previous,oldMachines,scannedAt);
  assert.deepEqual(result.events,[]);
  assert.equal(result.nextMachines[0].updatedAt,m.updatedAt); // Baseline still advances.
});

test('visible 2 hours old blocks a future-looking title timestamp from causing alerts',()=>{
  assert.equal(isRecentlyUpdated({
    label:'2時間前',updatedAt:'2026-11-19T04:12:00.000Z'
  },'2026-11-19T04:15:00.000Z'),false);
});

test('only a genuinely recent update notifies and names the triggering machine',()=>{
  const previous=new Map([[bic.name,{status:'present',missing_count:0}]]);
  const m={store:bic.name,number:1,label:'3分前',updatedAt:'2026-11-19T04:12:00.000Z'};
  const snapshot=new Map([[bic.name,{status:'present',machines:[m]}]]);
  const result=chooseEvents(snapshot,previous,
    new Map([[bic.name+'::1','2026-11-18T23:00:00.000Z']]),
    '2026-11-19T04:15:00.000Z');
  assert.deepEqual(result.events,['machine:'+bic.name+'::1:'+m.updatedAt]);
  const formatted=formatNotification(snapshot,'2026-11-19T04:15:00.000Z',result.events);
  assert.match(formatted,/筐体の新しい更新を検知：/);
  assert.match(formatted,/ビックカメラ立川店 1台目（3分前）/);
});

test('time-label freshness is limited to 60 minutes',()=>{
  const checkedAt='2026-11-19T04:15:00.000Z';
  for(const label of ['5分前','59分前','60分前','数分前','30秒前','たった今']){
    assert.equal(isRecentlyUpdated({label,updatedAt:'2026-11-19T04:12:00.000Z'},checkedAt),true,label);
  }
  for(const label of ['2時間前','1時間前','14時間前','2日前']){
    assert.equal(isRecentlyUpdated({label,updatedAt:'2026-11-19T04:12:00.000Z'},checkedAt),false,label);
  }
  assert.equal(isRecentlyUpdated({label:'5分前',updatedAt:'2026-11-18T23:00:00.000Z'},checkedAt),false);
  assert.equal(isRecentlyUpdated({label:'5分前',updatedAt:'2026-11-19T05:12:00.000Z'},checkedAt),false);
});
