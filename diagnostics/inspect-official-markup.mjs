/** Diagnose official storefront markup without exposing full page HTML.
 * No state writes, no Discord, and no deployment.
 */
const targets=[
  ['立川','https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1'],
  ['国分寺','https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1']
];
for(const [area,url] of targets){
  const r=await fetch(url,{headers:{'Cache-Control':'no-cache','User-Agent':'Mozilla/5.0'},signal:AbortSignal.timeout(15000)});
  if(!r.ok)throw Error(area+' HTTP '+r.status);
  const html=await r.text();
  console.log('AREA',area,'HTTP',r.status,'htmlChars',html.length);
  console.log('FLAGS',JSON.stringify({
    modalFilterCol:(html.match(/modalFilterCol/g)||[]).length,
    runningItem:(html.match(/runningItem/g)||[]).length,
    timeago:(html.match(/timeago/g)||[]).length,
    online:(html.match(/オンライン/g)||[]).length,
    offline:(html.match(/オフライン/g)||[]).length
  }));
  const terms=['オンライン','オフライン','タイトーステーション','ビックカメラ','namcoららぽーと'];
  for(const term of terms){
    const idx=html.indexOf(term);
    if(idx<0)continue;
    console.log('EXCERPT',term,html.slice(Math.max(0,idx-850),Math.min(html.length,idx+1250))
      .replace(/\s+/g,' ').slice(0,2050));
  }
  const listStart=html.indexOf('modalFilterCol');
  if(listStart>=0){
    console.log('FIRST MODAL',html.slice(Math.max(0,listStart-80),listStart+6500)
      .replace(/\s+/g,' ').slice(0,6580));
  }
}
