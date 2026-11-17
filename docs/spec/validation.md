# 検証系サブコマンド仕様（checkgen / checkverify / validate / explain）

> [仕様書トップ](../md_merge_spec.md) — 共通オプション・入力/出力指定・ログ・JSON・dry-run の各仕様はトップを参照。

---

## checkgen

### 概要

`procedure` の `insertmd` が参照する各 MD ファイルの**コンテンツ・フィンガープリント**を算出し、レシピとは別の YAML ファイル（`output.checkfilename`）に書き出す。スライド単位の挿入では、元コンテンツのページ追加・削除で番号がズレて意図しない結果になりやすいため、レシピ作成時点の各 MD の状態を記録しておき、`merge` 実行時に現在の内容と照合して**大きな変化があれば警告**する用途に使う。

**insertmd** のフィンガープリントは以下を含む（言語非依存。日本語にも対応）。

| 項目 | 内容 |
| ---- | ---- |
| `tokens` | 正規化後のトークン数（ASCII 英数字の連続＋それ以外の非空白文字を1トークンとして数える） |
| `headings` | Markdown 見出し（`#`〜`######`）テキストの順序付きリスト。コードフェンス内は除外 |
| `idmarkers` | `{{#id:...}}` マーカーの個数 |
| `sha8` | 正規化テキストの SHA-256 先頭 8 桁（完全一致の高速判定用） |
| `simhash` | トークン集合の 64bit SimHash（16進）。類似度（Hamming 距離）判定用 |

**insertpptx** のフィンガープリントは以下を含む（python-pptx でスライドを読む）。

| 項目 | 内容 |
| ---- | ---- |
| `slidecount` | 総スライド数 |
| `titles` | 全スライドのタイトル枠テキストの順序付きリスト（タイトルが無いスライドは空文字） |

### 使用例

```bash
pptmdmerge checkgen recipe.yaml            # チェックデータを生成
pptmdmerge checkgen recipe.yaml --force    # 既存を上書き
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存のチェックデータを上書きする | 任意 |

### 出力ファイル

`output.checkfilename`（省略時は `output.targetbasefilename` から `{base}_check.yaml` を自動生成）。`output.outputdir` 配下に書き出す。同一 `mdfilename` / `pptxfilename` が複数回参照される場合は 1 件にまとめる。insertmd は `entries`、insertpptx は `pptx_entries` に格納する。

```yaml
schema_version: 1
kind: insert_check
generated:
  by: md-merge
  at: 2026-06-26T09:24:33+09:00
source:
  config_yaml: recipe.yaml
entries:
  - mdfilename: a.md
    tokens: 46
    headings: ["はじめに"]
    idmarkers: 1
    sha8: f5d59fd7
    simhash: cd6ea5077e769ba0
pptx_entries:
  - pptxfilename: deck.pptx
    slidecount: 12
    titles: ["表紙", "目次", "本編1", "..."]
```

### pptmerge 実行時の照合（insertpptx 整合性チェック）

`output.checkfilename` の `pptx_entries` が存在する場合、`pptmerge` は各 insertpptx の現在の `slidecount` と `titles` を算出して照合し、**スライド数の変化**または**タイトル列の変化**を検出すると warning を出力する（`--no-check` でスキップ）。スライド単位の `slides:` 範囲指定が、元 pptx のページ追加・削除でズレるのを結合前に気づくための仕組み。チェックデータに無い insertpptx（スタンプ後に追加されたもの）は照合をスキップする。

### merge 実行時の照合（insertmd 整合性チェック）

`output.checkfilename` が存在する場合、`merge` は各 insertmd ファイルの現在のフィンガープリントを算出してチェックデータと比較し、**大きな変化**を検出すると warning を出力する（`--no-check` でスキップ）。判定ルール:

| 条件 | 判定 |
| ---- | ---- |
| `sha8` が一致 | 無変化（警告なし。以降の判定はスキップ） |
| 見出しリストが変化 | **警告**（即時） |
| トークン数が ±20% を超えて変化 | **警告** |
| SimHash の Hamming 距離が 6/64 を超える | **警告** |
| 上記以外（軽微な変化） | 警告なし |

しきい値（トークン ±20%、SimHash 距離 > 6）は `src/md_merge/_fingerprint.py` の定数。チェックデータに記録があるが実ファイルが存在しない場合も警告する。チェックデータに無い insertmd（スタンプ後に追加されたもの）は照合をスキップする。`checkgen` は `procedure` の `when:` を無視して全項目のチェックデータを作り、`merge` はその回に適用される項目だけを照合する（`checkverify` 単独実行は全項目、パイプラインのドリフトゲートは適用される項目のみ）。`merge --strict` 指定時は、差異が1件でもあれば終了コード 1 で中断する。

---

## checkverify

### 概要

`merge` を実行せず、insertmd の現在の内容を `output.checkfilename` のチェックデータと**照合するだけ**のサブコマンド。判定ルール・しきい値は [checkgen の「merge 実行時の照合」](#merge-実行時の照合insertmd-整合性チェック) と同一（見出し変化は即時、トークン ±20% 超、SimHash 距離 > 6/64、`sha8` 一致は無変化）。CI や手動確認で、結合前にコンテンツのドリフトを検出する用途に使う。

### 使用例

```bash
pptmdmerge checkverify recipe.yaml
pptmdmerge checkverify recipe.yaml --json
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |

### 動作・終了コード

| 状況 | 出力 | 終了コード |
| ---- | ---- | ---------- |
| すべて許容範囲内 | 「差異なし (N 件)」 | 0 |
| 大きな変化を検出 | 各 mdfilename の差異理由を warning、件数を error | 1 |
| `output.checkfilename` / `targetbasefilename` 未指定 | エラー | 2 |
| チェックデータが存在しない | 「checkgen で生成してください」 | 3 |

チェックデータに無い insertmd（スタンプ後に追加されたもの）は照合対象外として info で件数を報告する（終了コードには影響しない）。`--json` 指定時は `{"status": "ok"|"drift", "checked": N, "unstamped": [...], "problems": [{"mdfilename": ..., "reasons": [...]}]}` を出力する。

---

## validate

### 概要

レシピ YAML を読み込み、(1) **未知のキー**の検査、(2) **`input.cropsrc` と `procedure` の対応**の検査、(3) **`vars` 値の生 LaTeX** の検査、(4) **変数・条件・番号マーカー**の検査を行う。ファイルの生成・変更は行わない。

### 使用例

```bash
pptmdmerge validate recipe.yaml
pptmdmerge validate recipe.yaml --strict   # 警告があれば終了コード 1
pptmdmerge validate recipe.yaml --json
pptmdmerge validate recipe.yaml --list-params   # params: の一覧（切り替えに使える --var）
pptmdmerge validate recipe.yaml --var TARGET=RECIPRO   # --var の値も宣言と照合する
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--strict` | 警告（未知キー・vars 生 LaTeX 等）が1件でもあれば終了コード 1 を返す | 任意 |
| `--list-params` | `params:` で宣言された変数（名前・取りうる値・既定値・説明）を表示して終了する | 任意 |

### 1) 未知キー検査

トップレベル・各セクション（`input` / `output` / `merge` / `pandoc` / `indexer` / `log` / `pptmerge` / `separator` / `puremd`）・`procedure` の各アイテム（操作ごとの許可キー）について、スキーマに無いキーを **warning** で報告する。`procedure` の `when:`（条件付き適用）はどの操作でも許可し、未知のキー・値の型（文字列または文字列のリスト）・実在しないサブコマンド名・同じ名前が `command` と `not_command` の両方にある場合を warning にする。廃止した `tag` / `not_tag` と、`var` の不正な条件式は **error** にする。`- group:`（項目の束）の `when:` も同じ基準で検査し、位置を `procedure[3].group[1]` のように示す。group 要素の書式誤り（値が空・リストでない、許可外のキー）は記法エラーとして **error**。`version` が未指定または `1`（operation 記法は非推奨）の場合も警告する。version 3 以前で `pandoc.typst-cover-md` が無く `cover-md` / `conditional-process-input` がある場合も警告する（version 2 以前は「暗黙の標準表紙を使っている」、version 3 は「LaTeX 用の表紙は使われず表紙が付かない」）。version 3 以前で LaTeX 専用の pandoc キー（`template` / `include-in-header` / `include-before-body` / `conditional-process-*` / `format`）があると「使わない」と警告する。version 3 以前で `pandoc.metadata-file` があると非推奨と警告する。version 4 で廃止した pandoc キー（`typst-cover-md` / `typstdefaults` / `engine` / `metadata-file` と上の LaTeX 専用キー）と、`pandoc.engine` に typst 以外を書いたものは **error**（移行先を案内する）。`version` と `procedure` 記法の不整合（version 2 以降に operation 記法、version 1 に操作キー記法、未対応の `version` 値など）は **error** として全件を報告し、終了コード 1 で終了する（[仕様書トップ](../md_merge_spec.md) 5.3）。`description` はどの階層でも人間用メモとして許可される。`--strict` 指定時、警告が1件以上あれば終了コード 1。

### 2) cropsrc 使用状況チェック（info）

`input.cropsrc` と `procedure` の対応を **info** で表示する（終了コードには影響しない。`cropsrc` 未指定時はスキップ）。

| 種別 | 内容 |
| ---- | ---- |
| 未使用の可能性 | cropsrc の pptx が procedure で参照されていない。判定は insertpptx＝**stem 完全一致**、insertmd＝**`^<stem>_slide<数字>_md.md$` 一致**（MD 命名規則 `<__BASEFILENAME__>_slide<__SLIDENUM__>_md.md` を前提）。規則外の名前で export している場合は誤って未使用と表示されうる点に注意 |
| cropsrc 未登録（逆方向） | procedure の insertpptx（stem）、またはスライド命名規則に一致する insertmd（由来 pptx の stem）が cropsrc に無い。規則に一致しない手書き MD は対象外 |

`pptxfilename` / `pptx` は stem（拡張子なしファイル名）で比較する。`insertmd` の `[from-to]` レンジは展開して判定する。

### 3) vars 生 LaTeX 検査（warning）

`vars` の各値に**生 LaTeX が含まれていないか**を検査し、あれば **warning** で報告する。`{{v:}}` は実データ置換専用で、生 latex はセマンティックマーカー（`{{vspace}}` / `{{pagebreak}}` / `{{vfill}}` 等）や fenced div へ移行する方針のため。検出対象は **制御綴り `\cmd`（バックスラッシュ＋英字）** と **`{=fmt}` raw attribute**（例 `{=latex}`）。`__DATE__` のような定数プレースホルダや通常テキストは対象外。`--strict` 指定時、警告が1件以上あれば終了コード 1。

（`!include ../../common_assets/TEX_VARS.yaml` 等で取り込んだ legacy な `TEX_*` 変数は生 latex 値なので、この検査で移行対象として可視化される。）

### 4) 変数・条件・番号マーカー検査

レシピに加え、procedure の **insertmd が参照する MD**、**insertvar が挿入する変数の値** と **`input.cropsrc` の pptx ノート**を読んで検査する（見つからないファイルは飛ばし、件数を info で表示する。生成前の MD は検査されないので、ノート側の `{{#if}}` は cropsrc で検査される）。` ``` ` / `~~~` のフェンス内は対象外。

| 種別 | 内容 | 重さ |
| ---- | ---- | ---- |
| `params:` の誤り | 書式、`vars:` との重複、`--var` の未宣言名・範囲外の値、`when.var` の未宣言名・範囲外の比較値（[md_pipeline](md_pipeline.md#切り替え用の変数の宣言params) と同じ検査） | error |
| 未宣言の変数（`params:` あり） | MD / ノートの `{{#if}}` が `params:` にも `vars:` にも無い名前、または取りうる値でない比較値を使っている（実行時もエラーになる） | error |
| 未定義の変数（`params:` なし） | `when.var` / `{{#if}}` が `vars:` に無い名前を使っている（未定義は偽になり、打ち間違いでも黙って除外される）。名前ごとにまとめて場所を表示 | warning |
| 未定義の `{{v:}}` | `vars:`・`params:`・insertpptx の `vars:` のどれにも無い名前（置換されずに残る） | warning |
| 未定義の insertvar | procedure の `insertvar` の変数名が `vars:` にも `params:` にも無い（`--var` で渡さなければ何も挿入されない） | warning |
| 未使用の param | `params:` で宣言したが when.var / insertvar / MD / ノートのどこからも参照されていない（表紙テンプレートだけで使う場合は無視してよい） | warning |
| 結果が変わらない when | 値を列挙できる param（`values` / `bool`）だけを使う `when.var` で、どの値の組み合わせでも常に適用、または常に除外になる（group から引き継いだ条件も含めて判定。`command` 条件は見ない） | warning |
| 深すぎる入れ子 | `{{#if}}` が 3 段以上、`group` が 2 段以上 | warning |
| 番号マーカーの誤り | `{{nolabel}}` / `{{noref}}` / `{{nonum}}` が `{{#id:}}` の無い行にある（効かない）。`{{nolabel}}` と `{{nonum}}` の併用（`nonum` は採番しないので `nolabel` は不要） | warning |
| 同じ when の連続 | トップレベルで同じ `when:` が 3 回以上続く（insertvfill 等の区切りは連続を切らない）。`- group:` にまとめる提案 | info |

error が 1 件でもあれば終了コード 1。warning は `--strict` のときだけ終了コード 1。info は終了コードに影響しない。

### 終了コード

| 状況 | 終了コード |
| ---- | ---------- |
| 警告なし（cropsrc 使用状況の info の有無は不問） | 0 |
| 警告あり・`--strict` 未指定 | 0 |
| 警告あり・`--strict` 指定 | 1 |
| エラーあり（記法・`params:`・未宣言の変数） | 1 |
| 入力ファイル未指定 | 2 |
| 入力ファイルが存在しない | 3 |
| YAML 読み込みエラー | 1 |

`--json` 指定時は `{"status": "ok"|"warn", "input": ..., "warnings": [...], "cropsrc_usage": [...], "suggestions": [...]}` を出力する（エラー時は `{"status": "error", "errors": [...], "warnings": [...]}`）。

---

## explain

### 概要

条件（procedure の `when:` / `group` と、MD の `{{#if}}`）を展開した結果を表示する。ファイルの生成・変更は行わない。与えた `--var` のもとで procedure のどの項目が採用／除外されるかを、判定に使った条件つきで一覧にする（レシピの「デバッガ」）。

### 使用例

```bash
pptmdmerge explain recipe.yaml                          # 既定値（params: の default）で
pptmdmerge explain recipe.yaml --var TARGET=RECIPRO     # 値を与えて
pptmdmerge explain recipe.yaml --command ppt_to_pdf     # when.command も判定する
pptmdmerge explain recipe.yaml --matrix TARGET          # 値ごとに結果が変わる項目だけ
pptmdmerge explain recipe.yaml --matrix TARGET --matrix STEP   # 全組み合わせ
pptmdmerge explain recipe.yaml --matrix EDITION=print,web      # params: に無い変数は値を並べる
pptmdmerge explain recipe.yaml --blocks                 # 採用された insertmd の {{#if}} の判定も
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input の相対パスをこのディレクトリ基準で解釈する（`--blocks` 用） | 任意 |
| `--command` NAME | `when.command` / `not_command` をこのサブコマンド名で判定する。省略時は command 条件を満たすものとして扱い、行末に `(command 条件は未評価)` と出す | 任意 |
| `--matrix` NAME[=a,b] | 変数の値ごとに結果を比べ、値によって採用／除外が変わる項目だけを表示する。値は `params:` の `values` / `type: bool` から取る（`NAME=a,b` で明示も可）。繰り返すと全組み合わせ（上限 64） | 任意 |
| `--blocks` | 採用された insertmd ファイル中の `{{#if}}` / `{{#else}}` ごとに「残す／削る」を表示する（見つからないファイルは飛ばす） | 任意 |

### 出力

```
# explain: book.yaml
# vars: TARGET=RECIPRO
 0 ✓ insertpptx src/cover.pptx (slides: all)
 1 ✓ insertmd q1_md.md
 2 ✓ insertmd q1_answer_md.md   [var TARGET=RECIPRO ○]
 3 ✗ insertmd q1_note_md.md   [procedure[4] var TARGET=PDF ×]
# 採用 3 / 全 4 項目
```

- 番号は group 展開後の procedure の位置。条件の前の `procedure[4]` は、その条件を引き継いだ group の位置。
- `--matrix` は列ごとの採用（`✓`）／除外（`·`）を並べる。どの組み合わせでも同じなら「差はありません」と出す。
- 出力は安定したテキストなので、ファイルに保存して git diff すれば、レシピを編集したときに意図しない項目が入った／消えたことを検出できる。
- `--json` では `{"status": "ok", "items": [{"index", "item", "active", "conditions", "command_unevaluated"}], "blocks": {...}}`（`--matrix` 時は `{"matrix": [...], "items": [{"index", "item", "active": [...]}], "total": N}`）。
- `params:` の誤り・記法の誤りは他のサブコマンドと同じくエラー（終了コード 1）。

