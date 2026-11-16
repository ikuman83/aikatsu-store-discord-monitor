/**
 * Discord slash-command interaction receiver for the existing Cloudflare Worker.
 * All requests are verified using the Discord application's Ed25519 public key.
 */
const enc = new TextEncoder();

function hexBytes(value, length) {
  if (typeof value !== 'string' || value.length !== length * 2 ||
      !/^[a-f0-9]+$/i.test(value)) throw Error('Invalid hex-encoded key/signature');
  return Uint8Array.from(value.match(/../g), part => parseInt(part, 16));
}

export async function verifyDiscordRequest(request, publicKey, raw, now = Date.now()) {
  const signature = request.headers.get('x-signature-ed25519');
  const timestamp = request.headers.get('x-signature-timestamp');
  if (!publicKey || !signature || !timestamp || !/^\d{10}$/.test(timestamp)) return false;
  if (Math.abs(now - Number(timestamp) * 1000) > 5 * 60 * 1000) return false;
  try {
    const key = await crypto.subtle.importKey(
      'raw', hexBytes(publicKey, 32), {name:'Ed25519'}, false, ['verify']
    );
    return await crypto.subtle.verify(
      'Ed25519', key, hexBytes(signature, 64), enc.encode(timestamp + raw)
    );
  } catch {
    return false;
  }
}

function message(content, ephemeral = false) {
  return Response.json({type:4,data:{
    content:content.slice(0,1950),
    allowed_mentions:{parse:[]},
    ...(ephemeral ? {flags:64} : {})
  }},{headers:{'Cache-Control':'no-store'}});
}

async function editDeferredReply(interaction, content, fetchFn) {
  const applicationId = interaction.application_id;
  const token = interaction.token;
  if (!/^\d{15,25}$/.test(String(applicationId)) ||
      !/^[A-Za-z0-9._-]{20,300}$/.test(String(token))) {
    throw Error('Invalid interaction continuation identifier');
  }
  const url = 'https://discord.com/api/v10/webhooks/' + applicationId +
    '/' + encodeURIComponent(token) + '/messages/@original';
  const result = await fetchFn(url, {
    method:'PATCH', headers:{'content-type':'application/json'},
    body:JSON.stringify({content:content.slice(0,1950),allowed_mentions:{parse:[]}}),
    signal:AbortSignal.timeout(10000),
  });
  if (!result.ok) throw Error('Discord reply failed with HTTP '+result.status);
}

export async function handleDiscordInteraction(request, env, ctx, getStatus, fetchFn = fetch) {
  if (request.method !== 'POST') return new Response('Method Not Allowed',{status:405});
  if (!env.DISCORD_PUBLIC_KEY) return new Response('Discord integration not configured',{status:503});
  const raw = await request.text();
  if (!(await verifyDiscordRequest(request, env.DISCORD_PUBLIC_KEY, raw)))
    return new Response('Invalid signature',{status:401});
  let interaction;
  try {interaction=JSON.parse(raw);} catch {return new Response('Bad JSON',{status:400});}
  if (interaction.type === 1) return Response.json({type:1});
  if (interaction.type !== 2 || interaction.data?.name !== '状況')
    return message('このコマンドには対応していません。',true);
  if (!ctx?.waitUntil) return new Response('Execution context unavailable',{status:503});
  ctx.waitUntil((async () => {
    let content;
    try {
      content = await getStatus();
    } catch (err) {
      console.error('Current official store status could not be obtained:',String(err));
      content = '公式サイトから最新情報を取得できませんでした。時間を置いて再度 /状況 を実行してください。';
    }
    try {
      await editDeferredReply(interaction,content,fetchFn);
    } catch (err) {
      // Tokens are never logged.
      console.error('Failed to update Discord interaction response:',String(err));
    }
  })());
  return Response.json({type:5},{headers:{'Cache-Control':'no-store'}});
}
