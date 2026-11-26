import assert from 'node:assert/strict';
import test from 'node:test';
import {
  STORES,TACHIKAWA_URL,parseOfficialTimestamp,classifyMachineCard,chooseEvents,formatNotification,
} from '../src/index.mjs';

const checkedAt='2026-11-26T00:00:00.000Z';
const bic=STORES.find(x=>x.name==='ビックカメラ立川店');
const online=(number=1)=>({store:bic.name,number,status:'online'});
const offline=(number=1)=>({store:bic.name,number,status:'offline'});
const snapshot=machines=>new Map([[bic.name,{status:'present',machines}]]);
const present=new Map([[bic.name,{status:'present',missing_count:0}]]);
const offlineState=new Map([[bic.name+'::1','offline']]);
const onlineState=new Map([[bic.name+'::1','online']]);

test('official new offline markup is recognized',()=>{
  assert.equal(classifyMachineCard('オフライン','runningCard stopped'),'offline');
  assert.equal(classifyMachineCard(' オフライン ','runningCard stopped'),'offline');
  assert.equal(classifyMachineCard('オンライン','runningCard'),'online');
  assert.equal(classifyMachineCard('オンライン','runningCard online'),'online');
  assert.equal(classifyMachineCard('カード切れ停止中','runningCard stopped'),'card_empty');
  assert.equal(classifyMachineCard(' カード切れ停止中 ','runningCard stopped'),'card_empty');
});
test('known series/card metadata in active runningCard is online',()=>{
  assert.equal(classifyMachineCard('1弾','runningCard'),'online');
  assert.equal(classifyMachineCard('カード 1弾','runningCard'),'online');
});
test('unknown or malformed card is never assumed online',()=>{
  assert.equal(classifyMachineCard('','runningCard'),null);
  assert.equal(classifyMachineCard('謎の状況','runningCard'),null);
  assert.equal(classifyMachineCard('謎の状況','runningCard stopped'),null);
});
test('offline to online transition notifies exactly once',()=>{
  const first=chooseEvents(snapshot([online()]),present,offlineState,checkedAt);
  assert.deepEqual(first.events,['machine-online:'+bic.name+'::1:'+checkedAt]);
  assert.deepEqual(first.nextMachines,[{key:bic.name+'::1',store:bic.name,status:'online'}]);
  assert.deepEqual(chooseEvents(snapshot([online()]),present,onlineState,checkedAt).events,[]);
});
test('card-empty to online transition notifies exactly once',()=>{
  const cards=new Map([[bic.name+'::1','card_empty']]);
  const first=chooseEvents(snapshot([online()]),present,cards,checkedAt);
  assert.deepEqual(first.events,['machine-online:'+bic.name+'::1:'+checkedAt]);
  assert.deepEqual(chooseEvents(snapshot([online()]),present,onlineState,checkedAt).events,[]);
});
test('offline to card-empty transition updates DB without notification',()=>{
  const first=chooseEvents(snapshot([{store:bic.name,number:1,status:'card_empty'}]),present,offlineState,checkedAt);
  assert.deepEqual(first.events,[]);
  assert.equal(first.nextMachines[0].status,'card_empty');
});
test('card-empty to offline transition never notifies',()=>{
  const prev=new Map([[bic.name+'::1','card_empty']]);
  const first=chooseEvents(snapshot([offline()]),present,prev,checkedAt);
  assert.deepEqual(first.events,[]);
});
test('new listing with online machines is also silent until a known offline/card-empty to online transition',()=>{
  const previous=new Map([[bic.name,{status:'absent',missing_count:2,checked_at:'2026-11-25T20:00:00Z'}]]);
  assert.deepEqual(chooseEvents(snapshot([online()]),previous,new Map(),checkedAt).events,[]);
});
test('online to offline transition does not send a notification',()=>{
  const result=chooseEvents(snapshot([offline()]),present,onlineState,checkedAt);
  assert.deepEqual(result.events,[]);
  assert.equal(result.nextMachines[0].status,'offline');
});
test('first successful observation sets baseline without an alert',()=>{
  assert.deepEqual(chooseEvents(snapshot([online()]),present,new Map(),checkedAt).events,[]);
  assert.deepEqual(chooseEvents(snapshot([offline()]),present,new Map(),checkedAt).events,[]);
});
test('new listing with offline machines does not notify',()=>{
  const previous=new Map([[bic.name,{status:'absent',missing_count:2,checked_at:'2026-11-25T20:00:00Z'}]]);
  const result=chooseEvents(snapshot([offline()]),previous,new Map(),checkedAt);
  assert.deepEqual(result.events,[]);
});
test('first observation with missing store history does not fake a re-listing',()=>{
  assert.deepEqual(chooseEvents(snapshot([online()]),new Map(),new Map(),checkedAt).events,[]);
});
test('two verified absent polls are needed before marking a store absent',()=>{
  const absent=new Map([[bic.name,{status:'absent'}]]);
  assert.equal(chooseEvents(absent,present,new Map(),checkedAt).nextStores[0].status,'present');
  const previous=new Map([[bic.name,{status:'present',missing_count:1}]]);
  assert.equal(chooseEvents(absent,previous,new Map(),checkedAt).nextStores[0].status,'absent');
});
test('unknown page data never changes status or sends alerts',()=>{
  const result=chooseEvents(new Map([[bic.name,{status:'unknown'}]]),present,offlineState,checkedAt);
  assert.deepEqual(result.events,[]);
  assert.deepEqual(result.nextMachines,[]);
  assert.deepEqual(result.nextStores,[]);
});
test('new format /aikatsu response shows online/offline, not old times',()=>{
  const content=formatNotification(snapshot([offline(1),online(2)]),checkedAt);
  assert.match(content,/ビックカメラ立川店\n1台目【オフライン】\n2台目【オンライン】/);
  assert.doesNotMatch(content,/分前|時間前|最終更新/);
  assert.match(content,/確認時間/);
});
test('Discord full status distinguishes offline from card-empty',()=>{
  const machines=[online(1),offline(2),{store:bic.name,number:3,status:'card_empty'}];
  const message=formatNotification(snapshot(machines),checkedAt);
  assert.match(message,/1台目【オンライン】/);
  assert.match(message,/2台目【オフライン】/);
  assert.match(message,/3台目【カード切れ停止中】/);
});
test('automatic alert states online transition and which cabinet changed',()=>{
  const events=chooseEvents(snapshot([online()]),present,offlineState,checkedAt).events;
  const content=formatNotification(snapshot([online()]),checkedAt,events);
  assert.match(content,/オンラインへの切り替わりを検知/);
  assert.match(content,/ビックカメラ立川店 1台目/);
});
test('offline-only snapshot does not generate notifications',()=>{
  assert.deepEqual(chooseEvents(snapshot([offline(1),offline(2)]),
    present,new Map([[bic.name+'::1','offline'],[bic.name+'::2','offline']]),checkedAt).events,[]);
});
test('partial missing pages are displayed as unavailable, not offline',()=>{
  const content=formatNotification(new Map(),checkedAt);
  assert.match(content,/情報取得不可/);
  assert.doesNotMatch(content,/【オフライン】/);
});
test('timestamp utility remains strict for legacy data',()=>{
  assert.equal(parseOfficialTimestamp('2026-11-1610:55:00'),'2026-11-16T01:55:00.000Z');
  assert.throws(()=>parseOfficialTimestamp('2026-02-3010:55:00'));
});
test('Discord format below message limit and no unwanted URL',()=>{
  const content=formatNotification(snapshot([offline(1),online(2)]),checkedAt);
  assert.ok(content.length<1900);
  assert.ok(!content.includes('**'));
  assert.ok(!content.includes(TACHIKAWA_URL));
});
