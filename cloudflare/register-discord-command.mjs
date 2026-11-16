/** Safely register the /aikatsu slash command with Discord over HTTPS. */
const appId=process.env.DISCORD_APPLICATION_ID;
const botToken=process.env.DISCORD_BOT_TOKEN;
const guildId=process.env.DISCORD_GUILD_ID?.trim();
if(!/^\d{15,25}$/.test(appId||''))throw Error('DISCORD_APPLICATION_ID GitHub Secret is missing or invalid');
if(!botToken||botToken.length<30)throw Error('DISCORD_BOT_TOKEN GitHub Secret is missing');
if(guildId&&!/^\d{15,25}$/.test(guildId))throw Error('Invalid optional DISCORD_GUILD_ID');
const path='/applications/'+appId+(guildId?'/guilds/'+guildId:'')+'/commands';
const response=await fetch('https://discord.com/api/v10'+path,{
  method:'POST',
  headers:{'Authorization':'Bot '+botToken,'Content-Type':'application/json'},
  body:JSON.stringify({
    name:'aikatsu',
    description:'アイカツ！アンコールの指定4店舗の最新稼働状況を表示します',
    type:1
  }),
});
if(!response.ok){
  const detail=await response.text();
  throw Error('Discord command registration failed: HTTP '+response.status+' '+detail.slice(0,600));
}
const command=await response.json();
if(command.name!=='aikatsu'||!command.id)throw Error('Unexpected Discord command registration response');
console.log('Registered Discord slash command /aikatsu, ID '+command.id);
console.log('Install application to a server (applications.commands scope): '+
  'https://discord.com/oauth2/authorize?client_id='+appId+'&scope=applications.commands');
