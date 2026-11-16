# アイカツ！アンコール：公式「取扱店舗」監視

**現在稼働中：Cloudflare Workers + D1、24時間・原則1分間隔。**
公式サイトの取扱店舗検索（立川・国分寺）で4店舗を監視し、掲載や筐体の最終更新日時に変化があればDiscordに通知します。

- タイトーステーション 国分寺店
- タイトーステーション 立川北口店
- ビックカメラ立川店
- namcoららぽーと立川立飛おまけ横丁店

### 稼働状況

[Cloudflare Worker /health](https://aikatsu-encore-monitor.ikuman83.workers.dev/health)

### 定期監視

新しい掲載・更新日時の変化を検出し、D1で前回状態と通知履歴を保持します。GitHub Actions旧監視の自動実行は停止済みです（手動実行だけ可能）。

### Discordコマンド：`/aikatsu`

Cloudflare Workerに、`/aikatsu` で4店舗の最新情報を返信するコードを追加しました。**Discordアプリの作成・署名公開鍵の登録・コマンド登録が終わるまで、Discord上では利用できません。** 旧コマンド名 `/状況` は使用しません。

設定手順：[cloudflare/README.md](./cloudflare/README.md)

- [Discord Developer Portal](https://discord.com/developers/applications)
- [GitHubでDiscordコマンドを設定](https://github.com/ikuman83/aikatsu-store-discord-monitor/actions/workflows/configure-discord-aikatsu.yml)
- Discord Interactions Endpoint URL：`https://aikatsu-encore-monitor.ikuman83.workers.dev/discord`

Cloudflare Workerは `cloudflare/src/index.mjs`、Discord署名検証は `cloudflare/src/discord.mjs` にあります。ルートの `api/discord.js` は使用していない旧Vercel用の試作コードです。

### セキュリティ

Discord Bot Token、Webhook URL、Cloudflare API TokenはGitHub SecretsとCloudflare Secretsで保護し、リポジトリやチャットには貼り付けないでください。
