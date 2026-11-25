# Cloudflare Workers版：1分ごとの「アイカツ！アンコール」監視

公式「取扱店舗」の立川3店舗・国分寺1店舗を、24時間・毎分チェックします。既存のDiscord Webhookに通知します。

## 本番デプロイ手順

1. https://dash.cloudflare.com/ でCloudflareアカウントを用意し、Account IDを確認。
2. https://dash.cloudflare.com/profile/api-tokens で、対象アカウントに Workers Scripts: Edit と D1: Edit の権限を持つ最小権限のAPIトークンを作成。
3. https://github.com/ikuman83/aikatsu-store-discord-monitor/settings/secrets/actions に以下の2つのGitHub Secretを登録：
   - CLOUDFLARE_API_TOKEN：作成したAPIトークン
   - CLOUDFLARE_ACCOUNT_ID：CloudflareのAccount ID
   - 既存の DISCORD_WEBHOOK_URL は変更不要。トークンとWebhook URLはチャットへ送らない。
4. https://github.com/ikuman83/aikatsu-store-discord-monitor/actions/workflows/deploy-cloudflare.yml を開き、Run workflowを一度実行。D1 DB作成、テーブル初期化、Worker公開、Discordシークレット登録を自動実行します。
5. デプロイログのworkers.dev URLに /health を付けて開きます。Cron開始後に status: ok が表示され、実行時刻を確認できます。Cron反映には最大15分程度かかることがあります。
6. CloudflareのCronとDiscord通知が本番で正常に動くことを確認してから、旧GitHub Actions監視を停止してください。公開確認前には停止しません。

## Discordへの実送信テスト（旧監視を止める前に実施）

[GitHub Actions: Test Cloudflare Discord delivery](https://github.com/ikuman83/aikatsu-store-discord-monitor/actions/workflows/test-cloudflare-delivery.yml) で Run workflow を一度実行してください。

このワークフローは次を検証します。

1. Workerの /health が ok / complete である
2. D1に1件のテスト通知を投入できる
3. 次のCloudflare Cron実行が通知をDiscordへ送り、送信済みをD1に記録する

テスト成功時にはGitHub Actionsで緑色のチェックが表示され、Discordに「🧪 Cloudflare Workersからのテスト通知です。」というメッセージが届きます。

**このテストは実店舗の更新検出ではなく、Cloudflare→D1→Discordの送信経路の検証**です。成功を確認できるまでは旧GitHub監視を停止しないでください。

## Discordから手動確認する `/aikatsu` コマンド

Cloudflare Workerの `/discord` エンドポイントは、署名が正しいDiscordリクエストのみを受信します。`/aikatsu` で公式「取扱店舗」の2ページを再取得し、監視対象4店舗の一覧と確認時間をDiscordに返信します。定期監視の履歴や通知判定は変更しません。

### 初回セットアップ

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを作成（Webhookだけではスラッシュコマンドを受信できません）。
2. アプリの General Information で **Application ID** と **Public Key** を確認し、Bot ページで **Bot Token** を取得します。Bot Token は公開しないでください。スクリーンショットにも写さないこと。
3. [GitHubのActions Secrets](https://github.com/ikuman83/aikatsu-store-discord-monitor/settings/secrets/actions)に次の3つを追加します。
   - `DISCORD_APPLICATION_ID`：Application ID
   - `DISCORD_PUBLIC_KEY`：Public Key（64桁の16進数）
   - `DISCORD_BOT_TOKEN`：Bot Token
   - 任意で `DISCORD_GUILD_ID`（特定サーバーにのみコマンドを登録したい場合）
4. [Configure Discord /aikatsu command](https://github.com/ikuman83/aikatsu-store-discord-monitor/actions/workflows/configure-discord-aikatsu.yml) の **Run workflow** を実行します。既存のCloudflare Workerを再デプロイして公開鍵を登録し、Discord APIへ `aikatsu` コマンドを登録します。既存のCronは維持します。
5. Discord Developer Portal の **General Information → Interactions Endpoint URL** に、次のURLを設定し、検証・保存します。
   `https://aikatsu-encore-monitor.ikuman83.workers.dev/discord`
6. 同アプリの Installation 設定でサーバーへのインストール（`applications.commands` 権限）を許可し、目的のDiscordサーバーへ追加します。GitHubの登録ログにもインストールURLが表示されます。
7. Discordで `/aikatsu` を入力し、公式サイトの最新情報が返信されることを確認してください。

注意：本番での `/aikatsu` 応答はまだ確認できていません。GitHubのテストは、Discord署名検証・遅延返信・従来コマンドを受け付けない動作まで検証します。GitHub SecretsやBot Tokenをこのチャットに貼らないでください。

## 通知仕様（2026年11月26日：公式オンライン／オフライン方式に対応）

公式サイトが筐体の「最終更新時間」を表示しなくなったため、古い分単位の更新時刻による通知判定は廃止しました。

- 公式「取扱店舗」への新規掲載・再掲載：前回の確定した掲載なしから掲載ありに変わったときだけ通知します。
- 各筐体について **オフライン → オンライン** への切り替わりを確認したときに通知します。逆方向（オンライン → オフライン）は状態を記録するのみで、通知しません。
- 初回導入時の筐体状態は比較する履歴がないため、まず基準として保存し、初回のオンライン状態だけでは通知しません。
- D1の `machine_online_state` に台ごとの前回状態を保存。正常に解析できた状態のみ上書きし、同じ状態が続けば通知しません。
- `/aikatsu` はその時点で公式ページを取得し、各筐体を `【オンライン】`／`【オフライン】` と表示します。確認時間も表示します。
- 不明な表記・公式ページの取得失敗は「情報取得不可」と表示し、オンラインと断定したり、古い値で通知したりしません。
- 通知では変化した店舗・何台目かを明示し、4店舗の状態一覧を添えます。1分間隔のCronと既存Discordコマンド設定は維持します。

注意：実際の電源・遊べる状態を直接計測するものではなく、公式ページの「オンライン／オフライン」を監視します。公式側が情報を一定間隔で更新しているため、状態表示に遅れが生じる可能性があります。

## 運用・制限

Cronは 1分ごと（UTCの * * * * *）。厳密な即時通知保証ではありません。公式サイトへの通信は約2,880回/日（2ページ×1,440回）です。Cloudflare Workers Free枠は100,000リクエスト/日、Cron CPU 10ms/実行などの制限があります。D1無料枠にも日次読み書き上限があります。公式サイトの利用条件・レート制限は尊重します。

Cloudflareアカウント固有のDB IDはGitHub Actionsの実行時に設定されます。データベースを毎回作り直さないため通知履歴は維持されます。初期店舗履歴は2026年11月中旬のGitHub確認結果を参照します。

健康状態は公開URLの /health から確認できます。staleまたはunavailableならCloudflareのLogsを確認してください。WorkersのCron自体が停止した場合は、このWorker自身が停止を通知できません。

ローカル単体テスト：cloudflareディレクトリで npm test 。本番の公式サイト取得とDiscordへの通知はデプロイ後に確認してください。
