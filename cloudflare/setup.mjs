/** Create/reuse a Cloudflare D1 database, then write an ephemeral Wrangler config. */
import {readFileSync,writeFileSync} from 'node:fs';
const account=process.env.CLOUDFLARE_ACCOUNT_ID;
const token=process.env.CLOUDFLARE_API_TOKEN;
if(!account||!token)throw Error('CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN GitHub Secrets required');
const name='aikatsu-encore-monitor-state';
const base='https://api.cloudflare.com/client/v4/accounts/'+encodeURIComponent(account)+'/d1/database';
async function api(method,url,body){
  const response=await fetch(url,{
    method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:body?JSON.stringify(body):undefined,
  });
  const result=await response.json();
  if(!response.ok||!result.success)
    throw Error('Cloudflare API '+response.status+': '+JSON.stringify(result.errors||[]).slice(0,600));
  return result.result;
}
const list=await api('GET',base+'?name='+encodeURIComponent(name)+'&per_page=100');
let db=list.find(x=>x.name===name);
if(!db){db=await api('POST',base,{name,primary_location_hint:'apac'});console.log('Created D1 database');}
else console.log('Reusing existing D1 database');
if(!/^[0-9a-f-]{36}$/i.test(db.uuid))throw Error('Invalid database UUID');
writeFileSync('wrangler.runtime.toml',readFileSync('wrangler.toml','utf8').replace('REPLACE_WITH_YOUR_D1_UUID',db.uuid));
console.log('Wrangler configuration ready.');
