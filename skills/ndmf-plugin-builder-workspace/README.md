# ndmf-plugin-builder トリガー評価ハーネス

`skills/ndmf-plugin-builder` の frontmatter description が正しく発火するかを
検証するための開発用ツールです。**配布物には含まれません**(skills.sh は
SKILL.md を含むフォルダのみをスキルとして認識します)。

評価セットは skill-creator の慣例に従いスキル側に置いています:
`../ndmf-plugin-builder/evals/trigger-eval.json`(発火すべき10件+
紛らわしい非発火10件)。

## 使い方

description を変更したら:

```powershell
$env:PYTHONUTF8 = "1"
python run_eval_serial.py --model haiku    # 現行 description を20クエリ×3回で評価
python run_eval_serial.py --model haiku --status   # 進捗確認のみ
```

description の自動最適化ループ(評価→改善→再評価、最大5周):

```powershell
$env:PYTHONUTF8 = "1"
python run_opt.py            # 開始 or 再開
python run_opt.py --status   # 進捗確認のみ
```

- どちらも直列実行で、**1クエリごとにチェックポイント保存**します。
  中断したら同じコマンドの再実行で続きから再開します。
- `run_eval_serial.py` は description が変わると該当ラベルの状態を自動リセット
  します。`run_opt.py` は不整合を検出したら停止するので、その場合は
  `opt-serial-state.json` を削除してください。
- モデルの基準値(2026-07-14 時点、794字の description): sonnet 20/20、
  haiku 19/20。haiku で 17/20 を下回るようなら変更を疑ってください。

## ファイル構成

- `win_fix.py` — クエリ1件を `claude -p` で実行し発火を判定するランナー。
  skill-creator 同梱の `run_eval.py` は `select.select()` をパイプに使うため
  **Windows では全クエリが偽の未発火になる**(WinError 10038)。その修正版。
  APIエラー(レート制限・障害)は「未発火」と区別して例外を投げます —
  区別しないと障害の時間帯が全滅として集計されます(実際に一度起きました)。
- `run_eval_serial.py` — 現行 description(+旧 description があれば比較)の
  発火テスト。結果は `eval-serial-result-<model>.json`。
- `run_opt.py` — skill-creator の run_loop.py 相当(train/test 6:4 分割、
  test スコアで最良を選定)のチェックポイント対応版。
  `draft-description.txt` を置くとそれを起点に、なければ現行 description を
  起点に最適化します。
- 状態・ログ・結果ファイルは .gitignore 済み(このマシンにのみ残ります)。

## 注意

- `PYTHONUTF8=1` 必須。ないと日本語クエリの JSON 読み込みが cp932 で落ちます。
- スクリプトは skill-creator プラグインのキャッシュパス
  (`~/.claude/plugins/cache/claude-plugins-official/skill-creator/...`)を
  参照します。プラグイン更新でパスが変わったら追従が必要です。
- 評価は `~/.claude/commands/` に一時コマンドファイルを作って行われます。
  異常終了時に `ndmf-plugin-builder-skill-*.md` が残ることがあるので、
  見つけたら削除してください。
