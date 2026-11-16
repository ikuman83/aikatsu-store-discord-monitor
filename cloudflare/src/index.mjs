import {handleDiscordInteraction} from './discord.mjs';

/**
 * アイカツ！アンコール 取扱店舗監視 - Cloudflare Workers + D1.
 * Every minute, fetch only the two official pages and compare changes.
 */
export const TACHIKAWA_URL = 'https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1';
export const KOKUBUNJI_URL = 'https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1';
export const STORES = [
  {name:'タイトーステーション 国分寺店', url:KOKUBUNJI_URL},
  {name:'タイトーステーション 立川北口店', url:TACHIKAWA_URL},
  {name:'ビックカメラ立川店', url:TACHIKAWA_URL},
  {name:'namcoららぽーと立川立飛おまけ横丁店', url:TACHIKAWA_URL},
];
const normalize = text => String(text || '').normalize('NFKC').replace(/\s+/g,'');
const isoDate = now => new Date(now).toISOString();
const tokyoFormat = now => new Intl.DateTimeFormat('ja-JP', {
  timeZone:'Asia/Tokyo', year:'numeric', month:'2-digit', day:'2-digit',
  hour:'2-digit', minute:'2-digit', hour12:false,
}).format(new Date(now));

export function parseOfficialTimestamp(raw) {
  const match = String(raw || '').replace(/\s+/g,'').match(/^(\d{4})-(\d\d)-(\d\d)(\d\d):(\d\d):(\d\d)$/);
  if (!match) throw Error('Invalid official timestamp');
  const [, year, month, day, hour, minute, second] = match;
  const value = new Date(year+'-'+month+'-'+day+'T'+hour+':'+minute+':'+second+'+09:00');
  const local = Number.isFinite(value.getTime())
    ? new Date(value.getTime()+9*3600_000).toISOString().slice(0,19)
    : '';
  if(local !== year+'-'+month+'-'+day+'T'+hour+':'+minute+':'+second) throw Error('Invalid calendar timestamp');
  return value.toISOString();
}

/** HTMLRewriter is Cloudflare native, avoiding heavy JS DOM dependencies. */
export async function parseOfficialPage(html, url, checkedAt, Rewriter=globalThis.HTMLRewriter) {
  if (!Rewriter) throw Error('Cloudflare HTMLRewriter required');
  const modals=[]; let modal=null; let machine=null; let title='';
  const rewrite=new Rewriter()
    .on('title', {text(t){title+=t.text;}})
    .on('div.modalFilterCol', {element(e){
      const m={name:'',machines:[]}; modals.push(m); modal=m;
      e.onEndTag(()=>{modal=null;machine=null;});
    }})
    .on('.modalFilterCol .storeInfoRow .storeColName', {text(t){if(modal)modal.name+=t.text;}})
    .on('.modalFilterCol li.runningItem', {element(e){
      if(!modal)return;
      const m={number:'',label:'',timestamp:''};modal.machines.push(m);machine=m;
      e.onEndTag(()=>{machine=null;});
    }})
    .on('.modalFilterCol li.runningItem .runningItemNum .num', {text(t){if(machine)machine.number+=t.text;}})
    .on('.modalFilterCol li.runningItem .runningItemTime .timeago', {
      element(e){if(machine)machine.timestamp=e.getAttribute('title')||'';},
      text(t){if(machine)machine.label+=t.text;},
    });
  await rewrite.transform(new Response(html,{headers:{'content-type':'text/html; charset=utf-8'}})).arrayBuffer();
  if(!title.includes('取扱店舗')) throw Error('Official page title changed');
  const actual=modals.filter(m=>m.name.trim());
  const empty=html.includes('指定された条件のお店は見つかりませんでした。');
  if(!actual.length&&!empty)throw Error('Search results could not be verified');
  const snapshot=new Map();
  for(const store of STORES.filter(s=>s.url===url)){
    const matches=actual.filter(m=>normalize(m.name)===normalize(store.name));
    if(matches.length>1){snapshot.set(store.name,{status:'unknown'});continue;}
    if(matches.length===0){snapshot.set(store.name,{status:'absent'});continue;}
    const entries=[];const seen=new Set();let corrupt=false;
    for(const item of matches[0].machines){
      const number=Number(normalize(item.number));
      let updatedAt;
      try{updatedAt=parseOfficialTimestamp(item.timestamp);}catch{corrupt=true;break;}
      const delta=new Date(checkedAt).getTime()-new Date(updatedAt).getTime();
      if(!Number.isInteger(number)||number<1||seen.has(number)||!item.label.trim()||delta< -120000){
        corrupt=true;break;
      }
      entries.push({store:store.name,number,label:item.label.trim(),updatedAt});seen.add(number);
    }
    snapshot.set(store.name,{status:'present',machines:corrupt||!entries.length?null:entries});
  }
  return snapshot;
}

export function chooseEvents(snapshot,oldStores,oldMachines,checkedAt){
  const events=[];const nextStores=[];const nextMachines=[];
  const checked=new Date(checkedAt).getTime();
  for(const store of STORES){
    const item=snapshot.get(store.name);
    if(!item||item.status==='unknown')continue;
    const old=oldStores.get(store.name);
    if(item.status==='absent'){
      const missing=(old?.missing_count||0)+1;
      // Two consecutive trustworthy absences to prevent flapping.
      nextStores.push({name:store.name,status:missing>=2?'absent':(old?.status||'absent'),missing});
      continue;
    }
    if(old?.status!=='present')events.push('listing:'+store.name+':'+(old?.checked_at||'initial'));
    nextStores.push({name:store.name,status:'present',missing:0});
    for(const m of item.machines||[]){
      const key=store.name+'::'+m.number;
      const previous=oldMachines.get(key);
      const fresh=checked-new Date(m.updatedAt).getTime()<=3600000;
      if(previous&&m.updatedAt>previous)events.push('machine:'+key+':'+m.updatedAt);
      else if(!previous&&old?.status==='present'&&fresh)events.push('machine-new:'+key+':'+m.updatedAt);
      if(!previous||m.updatedAt>previous)nextMachines.push({key,store:store.name,updatedAt:m.updatedAt});
    }
  }
  return {events,nextStores,nextMachines};
}

export function formatNotification(snapshot,checkedAt,events=[]){
  const lines=[];
  const listing=events.filter(e=>e.startsWith('listing:')).map(e=>e.slice(8).split(':')[0]);
  if(listing.length)lines.push('取扱店舗に掲載：'+listing.join('、'),'');
  for(const store of STORES){
    lines.push(store.name);
    const s=snapshot.get(store.name);
    if(!s||s.status==='unknown'||(s.status==='present'&&!s.machines))lines.push('情報取得不可');
    else if(s.status==='absent')lines.push('取扱店舗への掲載なし');
    else for(const m of s.machines.slice().sort((a,b)=>a.number-b.number))
      lines.push(m.number+'台目【稼働】 '+m.label);
    lines.push('');
  }
  lines.push('確認時間：'+tokyoFormat(checkedAt)+' JST');
  return lines.join('\n');
}

async function fetchOfficial(url){
  const r=await fetch(url,{
    headers:{'User-Agent':'AikatsuEncoreMonitor/1.0','Cache-Control':'no-cache',Pragma:'no-cache'},
    cf:{cacheTtl:0},signal:AbortSignal.timeout(12000),
  });
  if(!r.ok)throw Error('Official page HTTP '+r.status);
  const age=r.headers.get('age');
  if(age&&Number(age)>30)throw Error('Stale cached official page');
  const html=await r.text();
  if(html.length<1000||html.length>2000000)throw Error('Unexpected official page size');
  return html;
}

async function deliverPending(env){
  // No delayed stale notifications. 10 minute retry window.
  const rows=await env.DB.prepare(
    'SELECT id,content FROM notifications WHERE sent_at IS NULL AND created_at >= ? ORDER BY created_at LIMIT 10'
  ).bind(isoDate(Date.now()-600000)).all();
  for(const row of rows.results||[]){
    const response=await fetch(env.DISCORD_WEBHOOK_URL,{
      method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({content:row.content,allowed_mentions:{parse:[]}}),
      signal:AbortSignal.timeout(10000),
    });
    if(!response.ok)throw Error('Discord HTTP '+response.status);
    await env.DB.prepare('UPDATE notifications SET sent_at=? WHERE id=? AND sent_at IS NULL')
      .bind(isoDate(Date.now()),row.id).run();
    console.log('Discord notification delivered',row.id);
  }
}

async function withLease(env,callback){
  const now=Date.now();const token=crypto.randomUUID();
  const lock=await env.DB.prepare(
    "INSERT INTO scan_lease (key,token,expires_at) VALUES ('scan',?,?) "+
    "ON CONFLICT(key) DO UPDATE SET token=excluded.token,expires_at=excluded.expires_at "+
    "WHERE scan_lease.expires_at<?"
  ).bind(token,now+150000,now).run();
  if((lock.meta?.changes||0)!==1){console.log('Concurrent scan skipped');return;}
  try{return await callback();}
  finally{await env.DB.prepare("DELETE FROM scan_lease WHERE key='scan' AND token=?").bind(token).run();}
}

export async function scan(env,checkedAt=new Date().toISOString()){
  if(!env.DB||!env.DISCORD_WEBHOOK_URL)throw Error('Missing D1 or Discord secret');
  return withLease(env,async()=>{
    const snapshot=new Map();
    const urls=[TACHIKAWA_URL,KOKUBUNJI_URL];
    const fetched=await Promise.allSettled(urls.map(async url=>{
      return parseOfficialPage(await fetchOfficial(url),url,checkedAt);
    }));
    for(let i=0;i<fetched.length;i++){
      if(fetched[i].status==='fulfilled')for(const [name,item] of fetched[i].value)snapshot.set(name,item);
      else console.warn('Official search fetch failed',urls[i],String(fetched[i].reason));
    }
    const [stores,machines]=await Promise.all([
      env.DB.prepare('SELECT name,status,missing_count,checked_at FROM store_state').all(),
      env.DB.prepare('SELECT id,updated_at FROM machine_state').all(),
    ]);
    const prevStores=new Map((stores.results||[]).map(r=>[r.name,r]));
    const prevMachines=new Map((machines.results||[]).map(r=>[r.id,r.updated_at]));
    const changes=chooseEvents(snapshot,prevStores,prevMachines,checkedAt);
    if(changes.events.length){
      const message=formatNotification(snapshot,checkedAt,changes.events);
      if(message.length>1900)throw Error('Notification exceeds Discord limit');
      const hash=await crypto.subtle.digest('SHA-256',
        new TextEncoder().encode(changes.events.slice().sort().join('\n')));
      const id=Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('');
      await env.DB.prepare(
        'INSERT OR IGNORE INTO notifications (id,content,created_at) VALUES (?,?,?)'
      ).bind(id,message,checkedAt).run();
    }
    // Save each verified state so that subsequent scans only detect changes.
    for(const s of changes.nextStores)await env.DB.prepare(
      'INSERT INTO store_state (name,status,missing_count,checked_at) VALUES (?,?,?,?) '+
      'ON CONFLICT(name) DO UPDATE SET status=excluded.status,missing_count=excluded.missing_count,checked_at=excluded.checked_at'
    ).bind(s.name,s.status,s.missing,checkedAt).run();
    for(const m of changes.nextMachines)await env.DB.prepare(
      'INSERT INTO machine_state (id,store,updated_at) VALUES (?,?,?) '+
      'ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at'
    ).bind(m.key,m.store,m.updatedAt).run();
    const status=snapshot.size===STORES.length?'complete':snapshot.size?'partial':'unavailable';
    await env.DB.prepare("INSERT INTO health (key,value) VALUES ('last_scan',?) "+
      'ON CONFLICT(key) DO UPDATE SET value=excluded.value'
    ).bind(JSON.stringify({at:checkedAt,status})).run();
    await deliverPending(env);
    console.log('Checked',checkedAt,status,'changes',changes.events.length);
  });
}

/**
 * Read current official data independently of the one-minute monitor.
 * A user-triggered /aikatsu never changes stored state or creates update alerts.
 */
export async function readLiveStoreStatus() {
  const checkedAt = new Date().toISOString();
  const pages = [TACHIKAWA_URL, KOKUBUNJI_URL];
  const results = await Promise.allSettled(pages.map(async url =>
    parseOfficialPage(await fetchOfficial(url), url, checkedAt)
  ));
  const snapshot = new Map();
  let goodPages = 0;
  for (let i = 0; i < results.length; i++) {
    if (results[i].status === 'fulfilled') {
      goodPages++;
      for (const [name, entry] of results[i].value) snapshot.set(name, entry);
    } else {
      console.warn('Status command could not fetch official page:',pages[i],
        String(results[i].reason));
    }
  }
  if (!goodPages) throw Error('Both official store search pages failed');
  let formatted = formatNotification(snapshot, checkedAt);
  if (goodPages < pages.length)
    formatted += '\n※一部店舗の最新情報を取得できませんでした。';
  return formatted;
}

export default {
  async scheduled(_controller,env,ctx){ctx.waitUntil(scan(env));},
  async fetch(request,env,ctx){
    if(new URL(request.url).pathname === '/discord')
      return handleDiscordInteraction(request, env, ctx, readLiveStoreStatus);
    if(request.method!=='GET'||new URL(request.url).pathname!=='/health')
      return new Response('Not found',{status:404});
    if(!env.DB)return Response.json({status:'configuration_missing'},{status:503});
    const row=await env.DB.prepare("SELECT value FROM health WHERE key='last_scan'").first();
    if(!row)return Response.json({status:'not_started'},{status:503});
    const entry=JSON.parse(row.value);
    const current=Date.now()-new Date(entry.at).getTime()>=180000?'stale':entry.status==='unavailable'?'unavailable':'ok';
    return Response.json({status:current,last_scan:entry.at,scan_status:entry.status},
      {status:current==='ok'?200:503,headers:{'cache-control':'no-store'}});
  },
};
