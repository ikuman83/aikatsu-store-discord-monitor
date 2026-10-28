import { createPublicKey, verify } from 'node:crypto';
import { waitUntil } from '@vercel/functions';
import * as cheerio from 'cheerio';

const PAGES = [
  { url: 'https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1',
    names: ['タイトーステーション 立川北口店','ビックカメラ立川店','namcoららぽーと立川立飛おまけ横丁店'] },
  { url: 'https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1',
    names: ['タイトーステーション 国分寺店'] }
];
const ORDER = ['タイトーステーション 国分寺店','タイトーステーション 立川北口店','ビックカメラ立川店','namcoららぽーと立川立飛おまけ横丁店'];
const normalize = text => text.normalize('NFKC').replace(/\s+/g, '');
const nowTokyo = () => new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',dateStyle:'short',timeStyle:'medium'}).format(new Date());

function checkSignature(req, body) {
  const key = process.env.DISCORD_PUBLIC_KEY;
  const signature = req.headers['x-signature-ed25519'];
  const timestamp = req.headers['x-signature-timestamp'];
  if (!key || !/^[0-9a-f]{64}$/i.test(key) ||
      !/^[0-9a-f]{128}$/i.test(signature || '') || !timestamp) return false;
  const raw = Buffer.from('302a300506032b6570032100' + key, 'hex');
  return verify(null, Buffer.from(timestamp + body), createPublicKey({key:raw,format:'der',type:'spki'}), Buffer.from(signature,'hex'));
}

async function fetchAll() {
  const machines = [];
  for (const page of PAGES) {
    const r = await fetch(page.url,{headers:{'Cache-Control':'no-cache','User-Agent':'Mozilla/5.0 (compatible; AikatsuStoreMonitor/1.1)'},signal:AbortSignal.timeout(10000)});
    if (!r.ok) throw Error('公式サイトHTTP '+r.status);
    const $ = cheerio.load(await r.text());
    for (const name of page.names) {
      const matching = $('.modalFilterCol').filter((_,el) =>
        normalize($(el).find('.storeInfoRow .storeColName').first().text()) === normalize(name));
      if (matching.length !== 1) throw Error('店舗を読み取れません: '+name);
      const entries = matching.find('li.runningItem').toArray().map(el=>{
        const number = Number($(el).find('.runningItemNum .num').first().text());
        const label = $(el).find('.runningItemTime .timeago').first().text().trim();
        const timestamp = $(el).find('.runningItemTime .timeago').first().attr('title');
        if (!Number.isInteger(number) || number < 1 || !label || !/^\d{4}-\d\d-\d\d\d\d:\d\d:\d\d$/.test(timestamp || '')) throw Error('筐体の情報が不正です: '+name);
        return {name,number,label};
      });
      if (!entries.length) throw Error('筐体情報がありません: '+name);
      machines.push(...entries);
    }
  }
  return machines;
}

function formatStatus(items) {
  const lines=['🎴 **アイカツ！アンコール 現在の稼働情報**',''];
  for (const name of ORDER) {
    const entries=items.filter(i=>i.name===name).sort((a,b)=>a.number-b.number);
    if (!entries.length) throw Error('情報がありません: '+name);
    lines.push('**'+name+'**');
    for (const e of entries) lines.push(e.number+'台目【稼働】 '+e.label);
    lines.push('','');
  }
  lines.push('確認時刻：'+nowTokyo()+'（日本時間）');
  lines.push('立川：'+PAGES[0].url);
  lines.push('国分寺：'+PAGES[1].url);
  return lines.join('\n');
}

async function respondLater(interaction) {
  const appId=interaction.application_id;
  const token=interaction.token;
  // Discord interaction tokens expire after 15 minutes.
  const endpoint='https://discord.com/api/v10/webhooks/'+encodeURIComponent(appId)+'/'+encodeURIComponent(token)+'/messages/@original';
  let content;
  try {
    content=formatStatus(await fetchAll());
  } catch (err) {
    console.error('Unable to fetch store status:',err);
    content='公式サイトから最新情報を取得できませんでした。時間をおいて再度 /状況 を実行してください。';
  }
  const result=await fetch(endpoint,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,allowed_mentions:{parse:[]}})});
  if (!result.ok) console.error('Discord status reply failed:',result.status,await result.text());
}

export const config = { api: { bodyParser: false } };

export default async function handler(req,res) {
  if (req.method !== 'POST') return res.status(405).send('Method Not Allowed');
  const buffers=[];
  for await(const chunk of req) buffers.push(Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk));
  const rawBody=Buffer.concat(buffers).toString('utf8');
  try {
    if (!checkSignature(req,rawBody)) return res.status(401).send('Invalid signature');
    const interaction=JSON.parse(rawBody);
    if (interaction.type===1) return res.status(200).json({type:1});
    if (interaction.type!==2 || interaction.data?.name!=='状況') {
      return res.status(200).json({type:4,data:{content:'未対応のコマンドです。',flags:64}});
    }
    waitUntil(respondLater(interaction));
    return res.status(200).json({type:5});
  } catch(err) {
    console.error('Discord interaction error:',err);
    return res.status(500).send('Internal server error');
  }
}
