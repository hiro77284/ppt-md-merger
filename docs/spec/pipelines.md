# パイプライン仕様（crop_to_pdf / ppt_to_pdf / ppt_to_transfer / ppt_to_puremd / ppt_to_notecom）

> [仕様書トップ](../md_merge_spec.md) — 共通オプション・入力/出力指定・ログ・JSON・dry-run の各仕様はトップを参照。

---

## crop_to_pdf

### 概要

`crop` → `merge` → `idcollect` → `idresolve` → `render` → `pandoc` の 6 ステップを  
1 コマンドで順に実行するパイプラインサブコマンド。  
いずれかのステップが非ゼロ終了コードを返した時点で停止する。

### 使用例

```
pptmdmerge crop_to_pdf recipe.yaml
pptmdmerge crop_to_pdf recipe.yaml --force --workdir /path/to/workdir
pptmdmerge crop_to_pdf recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--no-check` | merge 直前の insertmd ドリフトゲート（後述）をスキップする | 任意 |
| `--engine latex\|typst` | pandoc 段の PDF 組版エンジン（[pandoc の Typst エンジン](output_formats.md#typst-エンジンengine-typst)）。レシピの `pandoc.engine` より優先 | 任意 |

その他は共通オプション（`--log-level`, `--dry-run`, `--json`, `--workdir`, `--force`）のみ。各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。

### insertmd ドリフトゲート

`output.checkfilename`（[checkgen](validation.md#checkgen) で生成）が存在する場合、**merge ステップの直前**に insertmd の現在の内容をチェックデータと照合する（`checkverify` と同じ判定）。**大きな変化**、または**チェックデータに無い insertmd**（`checkgen` 以降に追加されたもの）を検出すると、検出内容を表示して `処理を続行しますか? [y/N]` と**確認を求め、`y` 以外なら中断**する。`--json` や入力が読めない（EOF＝CI・cron 等）場合は確認できないため中断する（`--no-check` でスキップ可）。Windows の Git Bash/mintty は `isatty()` が偽を返すが、プロンプトは試行されるため通常どおり `[y/N]` で応答できる（POSIX では非 TTY を非対話として中断）。チェックデータ（`output.checkfilename`）自体が無い場合はゲートをスキップする。パイプライン内では merge 自身のチェックは無効化され、このゲートが一括して担う。

### 実行ステップ

| 順序 | ステップ | 担当サブコマンド |
|---:|------|---------|
| 1 | 画像クロップ | `crop` |
| 2 | MD 結合 | `merge` |
| 3 | ID 収集 | `idcollect` |
| 4 | ID 解決 | `idresolve` |
| 5 | 参照レンダー | `render` |
| 6 | PDF 変換 | `pandoc` |

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- エラーログに失敗したステップ名と終了コードを出力する。
- `crop` ステップは `input.imagesdir` が未定義または対象画像なしの場合も  
  非ゼロを返さないため（`crop` 単体の仕様に従う）、パイプラインは継続する。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

---

## ppt_to_pdf

### 概要

`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `condblockprocess` → `pandoc` の 9 ステップを 1 コマンドで順に実行するパイプラインサブコマンド。いずれかのステップが非ゼロ終了コードを返した時点で停止する。

### 使用例

```bash
pptmdmerge ppt_to_pdf recipe.yaml
pptmdmerge ppt_to_pdf recipe.yaml --force --workdir /path/to/workdir
pptmdmerge ppt_to_pdf recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | 各ステップの相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 全ステップで既存ファイルを上書きする | 任意 |
| `--rebuild` | `pptpdfexport` ステップで、出力 PDF がソース PPTX より新しくても再生成する（タイムスタンプによるスキップを無効化） | 任意 |
| `--preprocess` | 各 `input.cropsrc.pptx` を前処理し、以降の pptx 利用ステップで前処理済み pptx を使用する（後述） | 任意 |
| `--deletecsl` `[on\|off]` | **無視される。** パイプラインでは CSL マーカーを一切処理しないため効果がない（指定すると警告を出す）。後述「CSL マーカーの扱い」参照 | 任意 |
| `--deletecsp` `[on\|off]` | 前処理時に `#CSP#` を含むシェイプを削除する。引数省略（ベアフラグ）で `on`、`off` で明示無効、オプション自体を省略するとレシピ `indexer.deletecsp` に従う。`--preprocess` 指定時のみ有効 | 任意 |
| `--closepptx` | `pptpdfexport` / `pptimgexport` / `pptmdexport` で処理完了後にファイルを close する（**省略時も close する**。COM ファイルロックを解放するため `ppt_to_pdf` ではデフォルト有効） | 任意 |
| `--ppquit` | `pptpdfexport` で PowerPoint アプリケーションを終了する | 任意 |
| `--no-check` | merge 直前の insertmd ドリフトゲート（[crop_to_pdf の insertmd ドリフトゲート](#insertmd-ドリフトゲート)と同仕様）をスキップする | 任意 |
| `--engine latex\|typst` | pandoc 段の PDF 組版エンジン（[pandoc の Typst エンジン](output_formats.md#typst-エンジンengine-typst)）。レシピの `pandoc.engine` より優先 | 任意 |

各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。`output.checkfilename` がある場合、merge ステップの直前に insertmd ドリフトゲートが動作し、大きな変化を検出すると確認を求める（`pptmdexport` で生成された MD を照合）。

### 前処理（`--preprocess`）

`--preprocess` を指定すると、パイプライン本体の実行前に、各 `input.cropsrc.pptx` に対して**単一ファイルの pptmerge** を行い、前処理済み pptx を生成する。以降の pptx を利用するステップ（`pptpdfexport` / `pptimgexport` / `pptmdexport`）は、元の pptx の代わりに前処理済み pptx の**内容を読み込む**。増分ビルドチェック対象も前処理済み pptx に差し替わるため、結果として増分ビルドは行われず、常に再生成される（--rebuildが指定されたと同じ動き）。

| 項目 | 内容 |
| ---- | ---- |
| 前処理の内容 | 単一ファイルに対する pptmerge。レシピの `procedure` は無視し、対象 pptx を `insertpptx`（`slides: all`）1 件として処理する。**一般マーカー処理のみ**（`--deletecsp`、`#TEMP#`/`#MEMO#`、`#CHAPT#`/`#SECTION#`/`#STAY#` 等）と、レシピ `vars` による `{{v:..}}` 置換を適用する。`pptmerge.stylebase` は適用しない |
| CSL マーカーの扱い | **一切処理しない**（後述） |
| 出力ファイル名 | 元の pptx 名に `_preprocessed` を付加（例 `deck.pptx` → `deck_preprocessed.pptx`） |
| 出力先 | `output.outputdir` |
| 利用範囲 | 各ステップは前処理済み pptx を**読み込み**にのみ使用する。PDF 名や `export-note` / `export-image` の出力先は元の pptx の位置基準のまま |
| 削除 | `--keep-work` 未指定時は、全ステップ完了後（`pandoc` 完了後）に前処理済み pptx を削除する |

Windows 専用（pptmerge が PowerPoint COM を使用する）。`--dry-run` 時は前処理を実行しない。

### 実行ステップ

| 順序 | ステップ | 担当サブコマンド |
|---:|------|---------|
| 1 | PPTX → PDF 変換 | `pptpdfexport` |
| 2 | PDF 画像切り出し | `pptimgexport` |
| 3 | MD テキスト抽出 | `pptmdexport` |
| 4 | MD 結合 | `merge` |
| 5 | ID 収集 | `idcollect` |
| 6 | ID 解決 | `idresolve` |
| 7 | 参照レンダー | `render` |
| 8 | 条件ブロック・変数展開 | `condblockprocess` |
| 9 | PDF 変換 | `pandoc` |

### 進捗・完了メッセージ

各ステップの開始前と完了後に標準出力へ進捗行を出力する。

```
[ppt_to_pdf] pptpdfexport ...
OK: slides/deck.pptx
-> slides/deck.pdf
[ppt_to_pdf] pptpdfexport OK
[ppt_to_pdf] pptimgexport ...
...
[ppt_to_pdf] pandoc OK

========================================
  ppt_to_pdf 完了
========================================
```

`--json` モード時は進捗行も JSON 形式で出力する（`{"command": "ppt_to_pdf", "step": "...", "status": "..."}`）。完了ブロックは `--json` 時は出力しない。

出力がリアルタイムに表示されるよう、`run()` 開始時に `sys.stdout.reconfigure(line_buffering=True)` でラインバッファリングに切り替える。

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- 失敗したステップ名と終了コードを標準出力に出力する（`[ppt_to_pdf] <step> FAILED (exit <code>)`）。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

---

## ppt_to_transfer

### 概要

`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd` → `transfer` の 9 ステップを 1 コマンドで順に実行するパイプラインサブコマンド。PPTX 群から静的サイト生成システム（Astro 等）の投入用ディレクトリへ MD と画像を転送するところまでを一気通貫で行う。`ppt_to_pdf` が `pandoc` で PDF を生成するのに対し、こちらは最終段が `transfer` である点が異なる。`render` の後に `puremd`（LaTeX rawblock 等の除去）を挟み、`transfer` はレンダー済み MD ではなく puremd 処理済み MD（`output.puremdfilename`）を転送対象とする。いずれかのステップが非ゼロ終了コードを返した時点で停止する。

### 使用例

```bash
pptmdmerge ppt_to_transfer recipe.yaml
pptmdmerge ppt_to_transfer recipe.yaml --rebuild
pptmdmerge ppt_to_transfer recipe.yaml --keep-work --workdir /path/to/workdir
pptmdmerge ppt_to_transfer recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | 各ステップの相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 全ステップで既存ファイルを上書きする | 任意 |
| `--rebuild` | `pptpdfexport` ステップで、出力 PDF がソース PPTX より新しくても再生成する（タイムスタンプによるスキップを無効化） | 任意 |
| `--preprocess` | 各 `input.cropsrc.pptx` を前処理し、以降の pptx 利用ステップで前処理済み pptx を使用する（[ppt_to_pdf の「前処理」](#前処理--preprocess)と同仕様。削除は `transfer` 完了後） | 任意 |
| `--deletecsl` `[on\|off]` | **無視される。** パイプラインでは CSL マーカーを一切処理しない（指定すると警告を出す） | 任意 |
| `--deletecsp` `[on\|off]` | 前処理時に `#CSP#` を含むシェイプを削除する。ベアフラグで `on`、`off` で明示無効、省略でレシピ追従（`--preprocess` 指定時のみ有効） | 任意 |
| `--keep-work` | 完了後に中間生成ファイル（後述）を削除せず残す。前処理済み pptx も保持する | 任意 |
| `--no-check` | merge 直前の insertmd ドリフトゲート（[crop_to_pdf の insertmd ドリフトゲート](#insertmd-ドリフトゲート)と同仕様）をスキップする | 任意 |
| `--source` `{puremd\|rendered\|merged}` | `transfer` ステップの転送対象 MD を選択する。`puremd`→`output.puremdfilename`、`rendered`→`output.renderedfilename`、`merged`→`output.mdfilename`。省略時は既定の `puremd`。指定時は `transfer.inputmd` より優先される | 任意 |

各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。`pptpdfexport` / `pptimgexport` / `pptmdexport` での PPTX クローズは常に有効（COM ファイルロック解放のため）。

### 実行ステップ

| 順序 | ステップ | 担当サブコマンド |
|---:|------|---------|
| 1 | PPTX → PDF 変換 | `pptpdfexport` |
| 2 | PDF 画像切り出し | `pptimgexport` |
| 3 | MD テキスト抽出 | `pptmdexport` |
| 4 | MD 結合 | `merge` |
| 5 | ID 収集 | `idcollect` |
| 6 | ID 解決 | `idresolve` |
| 7 | 参照レンダー | `render` |
| 8 | rawblock 除去 | `puremd` |
| 9 | dataentry へ転送 | `transfer` |

`puremd` ステップはレンダー済み MD（`output.renderedfilename`）から LaTeX rawblock 等を除去し `output.puremdfilename` を生成する（生 raw ブロックの除去は組み込み、追加パターンは `puremd.strip_config`。[puremd](output_formats.md#puremd別名-githubmd) を参照）。

最終段の `transfer` は `transfer.dataentry_input`・`transfer.slug` 等のレシピキーを必要とする（[transfer](output_formats.md#transfer) を参照）。転送対象 MD の優先順位は `--source` > `transfer.inputmd` > パイプライン既定（`output.puremdfilename`）。すなわち `--source` も `transfer.inputmd` も未指定の場合、このパイプラインでは `output.puremdfilename`（puremd 処理済み MD）を転送対象とする（単体 `transfer` の既定である `output.renderedfilename` とは異なる）。`--source` を指定すると `transfer.inputmd` を上書きして対象を選択できる。

### 中間生成ファイルの削除

完了後、以下の中間生成ファイルを削除する（`--keep-work` 指定時は残す）。

* `output.mdfilename`（結合 MD）
* `output.idcollectfilename`（inventory YAML）
* `output.idresolvedfilename`（resolved YAML）
* `output.renderedfilename`（レンダー済み MD）
* `output.puremdfilename`（puremd 処理済み MD）
* `output.resourcepathfilename`（graphicspath TeX）
* `--preprocess` で生成した前処理済み pptx（`<stem>_preprocessed.pptx`）

削除を1件以上行った場合は「`--keep-work` で残せる」旨を案内する。

### 進捗・完了メッセージ

各ステップの開始前と完了後に標準出力へ進捗行（`[ppt_to_transfer] <step> ...` / `OK`）を出力する。`--json` 時は進捗行も JSON 形式で出力する（`{"command": "ppt_to_transfer", "step": "...", "status": "..."}`）。

実行中に発生した WARNING 以上のログを収集し、完了時にまとめて再表示する。

```
======== 警告まとめ ========
WARNING: ...
============================
```

警告が1件もない場合はまとめブロックを出力しない。`--json` 時は `{"command": "ppt_to_transfer", "status": "warnings", "warnings": [...]}` として出力する。

出力がリアルタイムに表示されるよう、`run()` 開始時に `sys.stdout.reconfigure(line_buffering=True)` でラインバッファリングに切り替える。

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- 失敗したステップ名と終了コードを標準出力に出力する（`[ppt_to_transfer] <step> FAILED (exit <code>)`）。

---

## ppt_to_puremd

`ppt_to_puremd` は `ppt_to_transfer` から末尾の `transfer` ステップを除いた 8 ステップのパイプライン（`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd`）。静的サイトへの転送までは行わず、**puremd 処理済み MD（`output.puremdfilename`）を最終成果物として生成する**用途に使う。共通ランナー（`md_merge/_pipeline.py`）を `ppt_to_transfer` と共有し、進捗・警告まとめ・エラー処理の挙動は同一（プレフィックスは `[ppt_to_puremd]`）。

`ppt_to_transfer` との差分は次の 2 点のみ。

* **`transfer` ステップを実行しない。** したがって `transfer.dataentry_input` / `transfer.slug` 等の `transfer:` セクションや `--source` オプションは不要（持たない）。
* **中間生成ファイルの削除対象から `output.puremdfilename` を除外する。** puremd 処理済み MD はこのパイプラインの成果物なので、`--keep-work` を付けなくても削除されない。それ以外（`mdfilename` / `idcollectfilename` / `idresolvedfilename` / `renderedfilename` / `resourcepathfilename`、および `--preprocess` 生成物）は `ppt_to_transfer` と同様に完了後に削除する。

固有オプションは `--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（無視）/ `--deletecsp` / `--no-check` / `--keep-work`（`--source` を除き `ppt_to_transfer` と同じ）。

```bash
pptmdmerge ppt_to_puremd recipe.yaml
pptmdmerge ppt_to_puremd recipe.yaml --keep-work --workdir /path/to/workdir
```


---

## ppt_to_notecom

`ppt_to_notecom` は `ppt_to_transfer` の末尾 `transfer` を `notecomexport` に差し替えた 9 ステップのパイプライン（`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd` → `notecomexport`）。**note.com 投稿用 YAML（`output.notecomyamlfilename`）を最終成果物として生成する**。共通ランナーを他の `ppt_to_*` と共有し、進捗・警告まとめ・エラー処理の挙動は同一（プレフィックスは `[ppt_to_notecom]`）。

`ppt_to_transfer` との差分は次の 3 点。

* **`transfer` の代わりに `notecomexport` を実行する。** `transfer:` セクションは不要。`notecomexport:` セクションは任意（[notecomexport](output_formats.md#notecomexport) を参照）。
* **`--source` は `notecomexport` の変換対象 MD を選ぶ**（`puremd` 既定 / `rendered` / `merged`）。指定時は `notecomexport.inputmd` より優先される。
* **中間生成ファイルの削除対象から `output.puremdfilename` を除外する**（`ppt_to_puremd` と同じ）。note.com と Astro の両方へ出したい場合、`ppt_to_notecom` の完了後に単体 `transfer --source puremd` を続けて実行できるようにするため。

固有オプションは `--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（無視）/ `--deletecsp` / `--no-check` / `--keep-work` / `--source`。

```bash
pptmdmerge ppt_to_notecom recipe.yaml
pptmdmerge ppt_to_notecom recipe.yaml --force --rebuild
# 1 pptx から note.com と Astro の両方へ
pptmdmerge ppt_to_notecom recipe.yaml && pptmdmerge transfer recipe.yaml --source puremd
python tools/notecom_autopilot.py build/<base>_notecom.yaml --auth-state auth.json
```

---

## パイプラインにおける CSL マーカーの扱い

全体方針として **CSL スライド削除処理は `pptmerge` の最後（結合済み pptx）でのみ行う**。`ppt_to_pdf` / `ppt_to_transfer` / `ppt_to_puremd` / `ppt_to_notecom` / `crop_to_pdf` のパイプライン系コマンドは `pptmerge` を通らないため、**CSL マーカーを一切処理しない**。

| 項目 | 挙動 |
| ---- | ---- |
| `--preprocess` での個別 pptx 処理 | 一般マーカー（`#CSP#` / `#TEMP#` / `#MEMO#` / `#CHAPT#` / `#SECTION#` / `#STAY#` 等）のみ処理する |
| `#CSL#` | スライド削除・マーカー消去のいずれも行わない。マーカー文字列はそのまま残る |
| `indexer.deletecsl` | 参照しない（設定されていれば info ログを出す） |
| `--deletecsl` | 無視する（指定されていれば警告を出す） |

**注意:** CSL マーカーが未処理のまま残るため、`#CSL#` を含むスライドは PDF・切り出し画像・エクスポート MD にそのまま出力され、`#CSL#` の文字列も見えたままになる。パイプラインのソース pptx には `#CSL#` を使わない運用を前提とする。

`#CSL#` を含む pptx をパイプラインに通す必要がある場合は、パイプライン実行前に [pptdeletecsl](pptx.md#pptdeletecsl) でソース pptx を処理しておく。

```bash
pptmdmerge pptdeletecsl source.pptx -o source_nocsl.pptx   # または --mode strip
```

マーカーの分類と各処理の定義は [pptmerge のマーカーの分類と処理タイミング](pptx.md#マーカーの分類と処理タイミング) を参照。
