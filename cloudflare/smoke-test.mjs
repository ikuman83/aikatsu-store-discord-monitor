/** Test live Cloudflare Cron -> D1 outbox -> Discord Webhook.
 * This tool neither stores nor prints the Discord URL.
 */
import { readFileSync } from "node:fs";

const account = process.env.CLOUDFLARE_ACCOUNT_ID;
const token = process.env.CLOUDFLARE_API_TOKEN;
if (!account || !token) throw Error("Cloudflare GitHub Secrets are missing");

const toml = readFileSync("wrangler.runtime.toml", "utf8");
const uuid = toml.match(/database_id\s*=\s*"([0-9a-f-]{36})"/i)?.[1];
if (!uuid) throw Error("Cannot find Cloudflare D1 database ID");

const url = "https://api.cloudflare.com/client/v4/accounts/" +
  encodeURIComponent(account) + "/d1/database/" + uuid + "/query";

async function sql(statement, params = []) {
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + token,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sql: statement, params }),
  });
  const data = await r.json();
  if (!r.ok || !data.success || data.result?.[0]?.success === false) {
    const message = data.errors?.map(e => e.message).join("; ") || "D1 query error";
    throw Error("Cloudflare D1 API returned " + r.status + ": " + message);
  }
  return data.result?.[0]?.results ?? [];
}

const healthUrl = "https://aikatsu-encore-monitor.ikuman83.workers.dev/health";
const h = await fetch(healthUrl, { headers: { "Cache-Control": "no-cache" } });
const health = await h.json();
if (health.status !== "ok" || health.scan_status !== "complete") {
  throw Error("Live Cloudflare monitoring is not healthy: " + JSON.stringify(health));
}
console.log("Live Cloudflare Cron monitoring: ok / complete");

const id = "smoke-" + (process.env.GITHUB_RUN_ID || crypto.randomUUID());
const when = new Date().toISOString();
await sql("INSERT INTO notifications(id,content,created_at) VALUES(?,?,?)", [
  id,
  "🧪 Cloudflare Workersからのテスト通知です。1分間隔の監視とDiscord連携を確認しています。",
  when,
]);
console.log("Queued a single smoke-test notification.");

for (let attempt = 0; attempt < 12; attempt++) {
  await new Promise(resolve => setTimeout(resolve, 10000));
  const rows = await sql("SELECT sent_at FROM notifications WHERE id = ?", [id]);
  if (rows[0]?.sent_at) {
    console.log("Cloudflare Worker delivered the test to Discord successfully.");
    process.exit(0);
  }
}
throw Error("No Discord delivery acknowledgement after 120 seconds. Inspect Cloudflare Workers Logs.");
