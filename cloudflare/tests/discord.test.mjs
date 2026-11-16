import assert from 'node:assert/strict';
import test from 'node:test';
import { generateKeyPairSync, sign } from 'node:crypto';
import {handleDiscordInteraction, verifyDiscordRequest} from '../src/discord.mjs';

const pair = generateKeyPairSync('ed25519');
const publicHex = pair.publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('hex');
const applicationId = '123456789012345678';
const token = 'test_Interaction_token_1234567890_ABCDEF';

function signedRequest(data, options={}) {
  const raw = JSON.stringify(data);
  const timestamp = Math.floor(Date.now()/1000).toString();
  const signature = sign(null,Buffer.from(timestamp+raw),pair.privateKey).toString('hex');
  return new Request('https://example.workers.dev/discord', {
    method:'POST',headers:{
      'x-signature-ed25519':options.invalidSignature?'00'.repeat(64):signature,
      'x-signature-timestamp':options.timestamp||timestamp,
      'content-type':'application/json',
    },body:raw,
  });
}

function context(){
  const pending=[];
  return {waitUntil(p){pending.push(p);},pending};
}

test('Discord validates signed requests and rejects invalid signatures', async()=>{
  const valid=signedRequest({type:1});
  assert.equal(await verifyDiscordRequest(valid,publicHex,JSON.stringify({type:1})),true);
  const invalid=signedRequest({type:1},{invalidSignature:true});
  const res=await handleDiscordInteraction(invalid,{DISCORD_PUBLIC_KEY:publicHex},
    context(), async()=>{throw Error('should not execute');});
  assert.equal(res.status,401);
});

test('Discord Ping verification returns PONG', async()=>{
  const res=await handleDiscordInteraction(
    signedRequest({type:1}),{DISCORD_PUBLIC_KEY:publicHex},context(),
    async()=>{throw Error('should not fetch');});
  assert.deepEqual(await res.json(),{type:1});
});

test('correct /aikatsu command defers, fetches, and replies to original message',async()=>{
  const ctx=context();
  const calls=[];
  const res=await handleDiscordInteraction(
    signedRequest({type:2,data:{name:'aikatsu'},application_id:applicationId,token}),
    {DISCORD_PUBLIC_KEY:publicHex},ctx,async()=>'タイトーステーション立川北口店\n1台目【稼働】 5分前',
    async(url,options)=>{calls.push({url,options});return new Response('{}',{status:200});});
  assert.deepEqual(await res.json(),{type:5});
  assert.equal(ctx.pending.length,1);
  await Promise.all(ctx.pending);
  assert.equal(calls.length,1);
  assert.match(calls[0].url,/\/messages\/@original$/);
  assert.equal(calls[0].options.method,'PATCH');
  assert.match(JSON.parse(calls[0].options.body).content,/1台目【稼働】 5分前/);
});

test('legacy /状況 command is not accepted',async()=>{
  const ctx=context();
  const res=await handleDiscordInteraction(
    signedRequest({type:2,data:{name:'状況'},application_id:applicationId,token}),
    {DISCORD_PUBLIC_KEY:publicHex},ctx, async()=>{throw Error('must not fetch');});
  assert.equal((await res.json()).type,4);
  assert.equal(ctx.pending.length,0);
});

test('site fetch failure generates an explanatory /aikatsu response',async()=>{
  const ctx=context(),calls=[];
  const res=await handleDiscordInteraction(
    signedRequest({type:2,data:{name:'aikatsu'},application_id:applicationId,token}),
    {DISCORD_PUBLIC_KEY:publicHex},ctx,async()=>{throw Error('site is down');},
    async(_url,options)=>{calls.push(JSON.parse(options.body));return new Response('{}',{status:200});});
  assert.equal((await res.json()).type,5);
  await Promise.all(ctx.pending);
  assert.match(calls[0].content,/再度 \/aikatsu を実行してください/);
});

test('Discord rejects expired signed requests',async()=>{
  const timestamp=String(Math.floor(Date.now()/1000)-601);
  const req=signedRequest({type:1},{timestamp});
  assert.equal(await handleDiscordInteraction(req,{DISCORD_PUBLIC_KEY:publicHex},
    context(),async()=>{}).then(x=>x.status),401);
});
