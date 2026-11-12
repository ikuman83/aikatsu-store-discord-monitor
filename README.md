# アイカツ！アンコール：取扱店舗・筐体更新Discord監視

公式サイトの **「取扱店舗」** 検索ページを確認します。旧「遊べるお店」の検索ページは監視に使用しません。店舗掲載の確認と「最終更新60分以内」の判定には同じページを使用します。

- 立川（タイトーステーション立川北口店、ビックカメラ立川店、namcoららぽーと立川立飛おまけ横丁店）
- 国分寺（タイトーステーション国分寺店）

毎時 **05分・35分（日本時間）** に GitHub Actions が監視を試みます。GitHub側の遅延・スキップがあり、正確な30分間隔の実行は保証されません。

Discord通知条件：

1. 取扱店舗に最初に掲載されたこと、または前回「掲載なし」と確認された店舗が再掲載されたことを検知したとき（履歴により重複防止）
2. 掲載中の筐体の最終更新が **60分以内** であり、その更新をまだ通知していないとき（履歴により重複防止）

通知時は取得できた全店舗・全筐体の状況と確認時刻を表示します。公式サイトで掲載の有無を判定できない場合には推測しません。旧名称に依存する解析や、検索結果のないページから更新時刻を推測することはありません。

## 導入・テスト

1. **Settings → Secrets and variables → Actions** に、名前 `DISCORD_WEBHOOK_URL` で新しいDiscord Webhook URLを登録。URLはソースコードに保存しない。
2. **Actions → Aikatsu Encore Store Monitor → Run workflow** で `send_test` にチェックし、Discordへのテスト通知を確認する。
3. `send_test` を外して手動実行すると実ページをチェックする。**Actionsの実行ログ** で対象店舗・筐体の解析結果を必ず確認する。

## 注意事項

- GitHub Actionsのスケジュール実行は遅延・スキップする場合があり、30分ちょうどの動作は保証されません。
- 対象サイトからHTMLを取得できることが前提です。画面構造が変わると解析に失敗します。取得・解析失敗時は推測で通知しません。
- `data/state.json` に通知履歴を保存するため、Workflowの `contents: write` 権限を使用します。ログで `git push` が拒否される場合はSettings → Actions → General → Workflow permissionsを確認してください。
- GitHubの公開リポジトリでは標準ランナーのActions利用は通常無料です。Discord Webhook URLはSecretとして非公開に保存してください。
- GPT Plusの契約とは独立して動きます。

## 参照先

- 立川: https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1
- 国分寺: https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1

## Discordスラッシュコマンド `/状況`（セットアップ待ち）

`api/discord.js` にDiscord署名検証（Ed25519）と公式サイトから全9台をリアルタイム取得して返信する処理を用意しました。**GitHubにコードを置いただけではDiscordで使えるようになりません。**

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリケーションを作成し、General Informationの **Application ID** と **Public Key** を確認します（この2つは公開情報です）。BotのトークンやWebhookのURLはチャットに貼らないでください。
2. GitHubのこのリポジトリをVercelにインポートし、VercelのEnvironment Variablesに `DISCORD_PUBLIC_KEY` をPublic Keyの値で登録します。GitHub Actionsとは独立しています。
3. デプロイ後のURL `https://<Vercelのドメイン>/api/discord` をDiscord Developer Portalの **General Information → Interactions Endpoint URL** に登録します。Discordの検証で200応答が出る必要があります。
4. Discord Developer Portalのコマンド登録手段（Discord REST API `PUT /applications/{application.id}/commands` 等）を使い、名前 `状況`、説明 `4店舗の稼働情報を表示` のCHAT_INPUTコマンドを登録します。登録にはBot Tokenが必要ですが、これは安全な管理画面やローカル環境でのみ使用してください。
5. Developer PortalのInstallationから適切なスコープ（`applications.commands`、必要な場合`bot`）でアプリをサーバーに追加し、Discordの `/状況` を実行してください。

コマンドはDiscordから応答を遅延確定（defer）した後、Vercelで公式サイトを取得して元の応答を編集します。エラー時は更新情報を推測せず、失敗した旨を表示します。通常の30分ごとのGitHub Actions監視は継続します。
