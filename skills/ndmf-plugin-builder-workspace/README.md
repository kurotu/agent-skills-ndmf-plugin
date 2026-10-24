# ndmf-plugin-builder トリガー評価ハーネス

`skills/ndmf-plugin-builder` の frontmatter description が正しく発火するかを
検証するための開発用ツールです。**配布物には含まれません**(skills.sh は
SKILL.md を含むフォルダのみをスキルとして認識します)。

評価セットは skill-creator の慣例に従いスキル側に置いています:
`../ndmf-plugin-builder/evals/trigger-eval.json`(発火すべき14件+
紛らわしい非発火14件)。

## 使い方

description を変更したら:

```powershell
$env:PYTHONUTF8 = "1"
python run_eval_serial.py --model haiku    # 現行 description を28クエリ×3回で評価
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
- モデルの基準値(2026-10-24 時点、972字の description、28件): sonnet 28/28、
  haiku 24/28。haiku で 22/28 を下回るようなら変更を疑ってください。
  haiku の失敗は「NDMF」と明記した日本語のデバッグ相談の未発火に偏っており、
  description の不足というよりモデルの傾向です。旧 description(794字)も
  元の20件で 19/20(2026-07-14)→ 17/20(2026-10-24)と、description を
  変えていないのに下がりました。haiku の数字だけで回帰と判断しないでください。
- description の上限は1024字(skill-creator の `quick_validate.py`)。
  972字なので、キーワードを足すなら何かを削る必要があります。

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
- スクリプトは skill-creator プラグインのスクリプトを import します。
  キャッシュのパスはプラグイン更新のたびに変わるので、
  `~/.claude/plugins/installed_plugins.json` から都度解決しています。
- 評価セッションは常にホームディレクトリで動きます。このリポジトリ内で
  動かすと CLAUDE.md やスキル本体のファイルが見えてしまい、実際の
  ユーザー環境とずれるためです。
- 評価は `~/.claude/commands/` に一時コマンドファイルを作って行われます。
  異常終了時に `ndmf-plugin-builder-skill-*.md` が残ることがあるので、
  見つけたら削除してください。
