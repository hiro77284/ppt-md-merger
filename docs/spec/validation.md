# 検証系サブコマンド仕様（checkgen / checkverify / validate）

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

レシピ YAML を読み込み、(1) **未知のキー**の検査、(2) **`input.cropsrc` と `procedure` の対応**の検査、(3) **`vars` 値の生 LaTeX** の検査を行う。ファイルの生成・変更は行わない。

### 使用例

```bash
pptmdmerge validate recipe.yaml
pptmdmerge validate recipe.yaml --strict   # 警告があれば終了コード 1
pptmdmerge validate recipe.yaml --json
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--strict` | 警告（未知キー・vars 生 LaTeX 等）が1件でもあれば終了コード 1 を返す | 任意 |

### 1) 未知キー検査

トップレベル・各セクション（`input` / `output` / `merge` / `pandoc` / `indexer` / `log` / `pptmerge` / `separator` / `puremd`）・`procedure` の各アイテム（操作ごとの許可キー）について、スキーマに無いキーを **warning** で報告する。`procedure` の `when:`（条件付き適用）はどの操作でも許可し、未知のキー・値の型（文字列または文字列のリスト）・実在しないサブコマンド名・同じ名前が `command` と `not_command`（または `tag` と `not_tag`）の両方にある場合を warning にする。`version` が未指定または `1`（operation 記法は非推奨）の場合も警告する。`version` と `procedure` 記法の不整合（version 2 に operation 記法、version 1 に操作キー記法、未対応の `version` 値など）は **error** として全件を報告し、終了コード 1 で終了する（[仕様書トップ](../md_merge_spec.md) 5.3）。`description` はどの階層でも人間用メモとして許可される。`--strict` 指定時、警告が1件以上あれば終了コード 1。

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

### 終了コード

| 状況 | 終了コード |
| ---- | ---------- |
| 警告なし（cropsrc 使用状況の info の有無は不問） | 0 |
| 警告あり・`--strict` 未指定 | 0 |
| 警告あり・`--strict` 指定 | 1 |
| 入力ファイル未指定 | 2 |
| 入力ファイルが存在しない | 3 |
| YAML 読み込みエラー | 1 |

`--json` 指定時は `{"status": "ok"|"warn", "input": ..., "warnings": [...], "cropsrc_usage": [...]}` を出力する。
