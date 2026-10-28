# アイカツ！アンコール：店舗更新Discord監視

公式「データカードダス アイカツ！アンコール」の立川3店舗・国分寺1店舗を、GitHub Actionsで毎時 **5分・25分・45分（日本時間）** にチェックします。

監視対象：
- タイトーステーション 立川北口店
- ビックカメラ立川店
- namcoららぽーと立川立飛おまけ横丁店
- タイトーステーション 国分寺店

筐体ごとに「最終更新」が60分未満の場合、新しい更新に限ってDiscordに通知します。「1時間前」は実際には60分以上の場合があるため通知しません。

## 導入・テスト

1. **Settings → Secrets and variables → Actions** に、名前 `DISCORD_WEBHOOK_URL` で新しいDiscord Webhook URLを登録。URLはソースコードに保存しない。
2. **Actions → Aikatsu Encore Store Monitor → Run workflow** で `send_test` にチェックし、Discordへのテスト通知を確認する。
3. `send_test` を外して手動実行すると実ページをチェックする。**Actionsの実行ログ** で対象店舗・筐体の解析結果を必ず確認する。

## 注意事項

- GitHub Actionsのスケジュール実行は遅延・スキップする場合があり、20分ちょうどの動作は保証されません。
- 対象サイトからHTMLを取得できることが前提です。画面構造が変わると解析に失敗します。取得・解析失敗時は推測で通知しません。
- `data/state.json` に通知履歴を保存するため、Workflowの `contents: write` 権限を使用します。ログで `git push` が拒否される場合はSettings → Actions → General → Workflow permissionsを確認してください。
- GitHubの公開リポジトリでは標準ランナーのActions利用は通常無料です。Discord Webhook URLはSecretとして非公開に保存してください。
- GPT Plusの契約とは独立して動きます。

## 参照先

- 立川: https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1
- 国分寺: https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1
