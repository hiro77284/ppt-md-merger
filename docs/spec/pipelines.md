# パイプライン仕様（crop_to_pdf / ppt_to_pdf / ppt_to_transfer / ppt_to_puremd / ppt_to_githubmd / ppt_to_notecom / ppt_build）

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

その他は共通オプション（`--log-level`, `--dry-run`, `--json`, `--workdir`, `--force`, `--yes-clear-dir`）のみ。各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。

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
- `crop` ステップは `source.cropimagedirs` が未定義または対象画像なしの場合も  
  非ゼロを返さないため（`crop` 単体の仕様に従う）、パイプラインは継続する。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

`--force` は merge 前の image-dir 全削除（clear-dir-before-merge）の承認にはならない。確認を省くには `--yes-clear-dir` を指定する（[md_pipeline の clear-dir-before-merge](md_pipeline.md#clear-dir-before-merge)）。

---

## ppt_to_pdf

### 概要

`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `pandoc` の 8 ステップを 1 コマンドで順に実行するパイプラインサブコマンド。いずれかのステップが非ゼロ終了コードを返した時点で停止する。共通ランナー（`md_merge/_pipeline.py`）を他の `ppt_to_*` と共有し、完了時の警告まとめも同じ形式で出力する。

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
| `--yes-clear-dir` | merge 前の image-dir 全削除（clear-dir-before-merge）の確認を省略して削除する。`--force` では省略されない | 任意 |
| `--rebuild` | `pptpdfexport` ステップで、出力 PDF がソース PPTX より新しくても再生成する（タイムスタンプによるスキップを無効化） | 任意 |
| `--preprocess` | 各 `source.cropsrc.pptx` を前処理し、以降の pptx 利用ステップで前処理済み pptx を使用する（後述） | 任意 |
| `--deletecsl` `[on\|off]` | **無視される。** パイプラインでは CSL マーカーを一切処理しないため効果がない（指定すると警告を出す）。後述「CSL マーカーの扱い」参照 | 任意 |
| `--deletecsp` `[on\|off]` | 前処理時に `#CSP#` を含むシェイプを削除する。引数省略（ベアフラグ）で `on`、`off` で明示無効、オプション自体を省略するとレシピ `indexer.deletecsp` に従う。`--preprocess` 指定時のみ有効 | 任意 |
| `--closepptx` | `pptpdfexport` / `pptimgexport` / `pptmdexport` で処理完了後にファイルを close する（**省略時も close する**。COM ファイルロックを解放するため `ppt_to_pdf` ではデフォルト有効） | 任意 |
| `--ppquit` | `pptpdfexport` で PowerPoint アプリケーションを終了する | 任意 |
| `--no-check` | merge 直前の insertmd ドリフトゲート（[crop_to_pdf の insertmd ドリフトゲート](#insertmd-ドリフトゲート)と同仕様）をスキップする | 任意 |

各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。`output.checkfilename` がある場合、merge ステップの直前に insertmd ドリフトゲートが動作し、大きな変化を検出すると確認を求める（`pptmdexport` で生成された MD を照合）。

### 前処理（`--preprocess`）

`--preprocess` を指定すると、パイプライン本体の実行前に、各 `source.cropsrc.pptx` に対して**単一ファイルの pptmerge** を行い、前処理済み pptx を生成する。以降の pptx を利用するステップ（`pptpdfexport` / `pptimgexport` / `pptmdexport`）は、元の pptx の代わりに前処理済み pptx の**内容を読み込む**。増分ビルドチェック対象も前処理済み pptx に差し替わるため、結果として増分ビルドは行われず、常に再生成される（--rebuildが指定されたと同じ動き）。

| 項目 | 内容 |
| ---- | ---- |
| 前処理の内容 | 単一ファイルに対する pptmerge。レシピの `procedure` は無視し、対象 pptx を `insertpptx`（`slides: all`）1 件として処理する。**一般マーカー処理のみ**（`--deletecsp`、`#TEMP#`/`#MEMO#`、`#CHAPT#`/`#SECTION#`/`#SUBSECTION#`/`#STAY#` 等）と、レシピ `vars` による `{{v:..}}` 置換を適用する。`pptmerge.stylebase` は適用しない |
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
| 8 | PDF 変換 | `pandoc` |

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
  所要時間: 1分23.4秒
========================================
```

完了行の直後に、コマンド開始（引数解析前）から完了までの所要時間を表示する。他のパイプライン（`ppt_to_puremd` / `ppt_to_transfer` / `ppt_to_notecom` 等）の完了ブロックも同じ形式。

`--json` モード時は進捗行も JSON 形式で出力する（`{"command": "ppt_to_pdf", "step": "...", "status": "..."}`）。完了ブロック（所要時間を含む）は `--json` 時は出力しない。

出力がリアルタイムに表示されるよう、`run()` 開始時に `sys.stdout.reconfigure(line_buffering=True)` でラインバッファリングに切り替える。

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- 失敗したステップ名と終了コードを標準出力に出力する（`[ppt_to_pdf] <step> FAILED (exit <code>)`）。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

`--force` は merge 前の image-dir 全削除（clear-dir-before-merge）の承認にはならない。確認を省くには `--yes-clear-dir` を指定する（[md_pipeline の clear-dir-before-merge](md_pipeline.md#clear-dir-before-merge)）。

---

## ppt_to_transfer

### 概要

`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd` → `transfer` の 9 ステップを 1 コマンドで順に実行するパイプラインサブコマンド。PPTX 群から静的サイト生成システム（Astro 等）の投入用ディレクトリへ MD と画像を転送するところまでを一気通貫で行う。`ppt_to_pdf` が `pandoc` で PDF を生成するのに対し、こちらは最終段が `transfer` である点が異なる。`render` の後に `puremd`（raw ブロック等の除去）を挟み、`transfer` はrender済み MD ではなく puremd 処理済み MD（`output.puremdfilename`）を転送対象とする。いずれかのステップが非ゼロ終了コードを返した時点で停止する。

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
| `--yes-clear-dir` | merge 前の image-dir 全削除（clear-dir-before-merge）の確認を省略して削除する。`--force` では省略されない | 任意 |
| `--rebuild` | `pptpdfexport` ステップで、出力 PDF がソース PPTX より新しくても再生成する（タイムスタンプによるスキップを無効化） | 任意 |
| `--preprocess` | 各 `source.cropsrc.pptx` を前処理し、以降の pptx 利用ステップで前処理済み pptx を使用する（[ppt_to_pdf の「前処理」](#前処理--preprocess)と同仕様。削除は `transfer` 完了後） | 任意 |
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

`puremd` ステップはrender済み MD（`output.renderedfilename`）から raw ブロック等を除去し `output.puremdfilename` を生成する（生 raw ブロックの除去は組み込み、追加パターンは `puremd.strip_config`。[puremd](output_formats.md#puremd) を参照）。

最終段の `transfer` は `transfer.dataentry_input`・`transfer.slug` 等のレシピキーを必要とする（[transfer](output_formats.md#transfer) を参照）。転送対象 MD の優先順位は `--source` > `transfer.inputmd` > パイプライン既定（`output.puremdfilename`）。すなわち `--source` も `transfer.inputmd` も未指定の場合、このパイプラインでは `output.puremdfilename`（puremd 処理済み MD）を転送対象とする（単体 `transfer` の既定である `output.renderedfilename` とは異なる）。`--source` を指定すると `transfer.inputmd` を上書きして対象を選択できる。

### 中間生成ファイルの削除

完了後、以下の中間生成ファイルを削除する（`--keep-work` 指定時は残す）。

* `output.mdfilename`（結合 MD）
* `output.idcollectfilename`（inventory YAML）
* `output.idresolvedfilename`（resolved YAML）
* `output.renderedfilename`（render済み MD）
* `output.puremdfilename`（puremd 処理済み MD）
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
* **中間生成ファイルの削除対象から `output.puremdfilename` を除外する。** puremd 処理済み MD はこのパイプラインの成果物なので、`--keep-work` を付けなくても削除されない。それ以外（`mdfilename` / `idcollectfilename` / `idresolvedfilename` / `renderedfilename`、および `--preprocess` 生成物）は `ppt_to_transfer` と同様に完了後に削除する。

固有オプションは `--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（無視）/ `--deletecsp` / `--no-check` / `--keep-work` / `--yes-clear-dir` / `--transfer`（`--source` を除き `ppt_to_transfer` と同じ）。

`--transfer` を付けると、最後に `transfer` ステップを実行し、puremd 処理済み MD とその画像を `transfer.dataentry_input` へ転送する（`ppt_to_transfer` と同じく `transfer:` セクションが必要）。転送対象 MD の優先順位は `transfer.inputmd` > `output.puremdfilename`。`ppt_to_transfer` と違い、puremd 処理済み MD は成果物として残す。

```bash
pptmdmerge ppt_to_puremd recipe.yaml
pptmdmerge ppt_to_puremd recipe.yaml --keep-work --workdir /path/to/workdir
pptmdmerge ppt_to_puremd recipe.yaml --transfer   # = ppt_to_transfer（ただし puremd MD を残す）
```


---

## ppt_to_githubmd

`ppt_to_githubmd` は `ppt_to_puremd` の末尾に `githubmd` を足した 9 ステップのパイプライン（`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd` → `githubmd`）。**GitHub 表示用 MD（`output.githubmdfilename`）を最終成果物として生成する**（[githubmd](output_formats.md#githubmd) を参照）。共通ランナーを他の `ppt_to_*` と共有し、進捗・警告まとめ・エラー処理の挙動は同一（プレフィックスは `[ppt_to_githubmd]`）。

* **中間生成ファイルの削除対象から `output.puremdfilename` を除外する**（`ppt_to_notecom` と同じ）。同じ実行結果から `transfer --source puremd` や `notecomexport` を続けて実行できるようにするため。`output.githubmdfilename` も成果物なので削除しない。

固有オプションは `ppt_to_puremd` と同じ（`--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（無視）/ `--deletecsp` / `--no-check` / `--keep-work` / `--yes-clear-dir` / `--transfer`）。

`--transfer` を付けると、最後に `transfer` ステップを実行し、GitHub 表示用 MD（`output.githubmdfilename`）とその画像を `transfer.dataentry_input` へ転送する（`transfer:` セクションが必要）。githubmd が出力した `<img src="...">` の画像も、`![](...)` と同じく `{slug}/` へコピーしてパスを書き換える。転送対象 MD の優先順位は `transfer.inputmd` > `output.githubmdfilename`。

```bash
pptmdmerge ppt_to_githubmd recipe.yaml
pptmdmerge ppt_to_githubmd recipe.yaml --transfer
```

---

## ppt_to_notecom

`ppt_to_notecom` は `ppt_to_transfer` の末尾 `transfer` を `notecomexport` に差し替えた 9 ステップのパイプライン（`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `puremd` → `notecomexport`）。**note.com 投稿用 YAML（`output.notecomyamlfilename`）を最終成果物として生成する**。共通ランナーを他の `ppt_to_*` と共有し、進捗・警告まとめ・エラー処理の挙動は同一（プレフィックスは `[ppt_to_notecom]`）。

`ppt_to_transfer` との差分は次の 3 点。

* **`transfer` の代わりに `notecomexport` を実行する。** `transfer:` セクションは不要。`notecomexport:` セクションは任意（[notecomexport](output_formats.md#notecomexport) を参照）。
* **`--source` は `notecomexport` の変換対象 MD を選ぶ**（`puremd` 既定 / `rendered` / `merged`）。指定時は `notecomexport.inputmd` より優先される。
* **中間生成ファイルの削除対象から `output.puremdfilename` を除外する**（`ppt_to_puremd` と同じ）。note.com と Astro の両方へ出したい場合、`ppt_to_notecom` の完了後に単体 `transfer --source puremd` を続けて実行できるようにするため。

固有オプションは `--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（無視）/ `--deletecsp` / `--no-check` / `--keep-work` / `--yes-clear-dir` / `--source`。

```bash
pptmdmerge ppt_to_notecom recipe.yaml
pptmdmerge ppt_to_notecom recipe.yaml --force --rebuild
# 1 pptx から note.com と Astro の両方へ
pptmdmerge ppt_to_notecom recipe.yaml && pptmdmerge transfer recipe.yaml --source puremd
python tools/notecom_autopilot.py build/<base>_notecom.yaml --auth-state auth.json
```

---

## ppt_build

`ppt_build` は、全 `ppt_to_*` に共通する前半（`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render`）を **1 回だけ**実行し、そのあと**オプションで選んだ出力だけ**を作るパイプライン。PDF と GitHub 用 MD の両方が欲しいときに `ppt_to_pdf` と `ppt_to_githubmd` を続けて実行すると前半が 2 回走るが、`ppt_build --pdf --githubmd` なら 1 回で済む。共通ランナーを他の `ppt_to_*` と共有し、進捗・警告まとめ・エラー処理の挙動は同一（プレフィックスは `[ppt_build]`）。

```bash
pptmdmerge ppt_build recipe.yaml --pdf --githubmd
pptmdmerge ppt_build recipe.yaml --pdf --githubmd --transfer   # GitHub 用 MD を転送
pptmdmerge ppt_build recipe.yaml --puremd --notecom --transfer  # puremd MD を転送
pptmdmerge ppt_build recipe.yaml --pdf --pptx                  # PDF と結合済み pptx（pptmerge）を 1 回で
pptmdmerge ppt_build recipe.yaml                                # 出力指定なし: render まで（rendered MD を残す）
```

### 出力オプション

**1 つも指定しなければ `render` まで実行して終わる**（成果物は `output.renderedfilename` の rendered MD。`pandoc` 以降の段は走らない）。`when.command` の照合と中間ファイルの扱いは `ppt_to_pdf` と同じ（rendered MD を残し、それ以外の work ファイルを削除）。PDF のパス衝突検査は行わない。

| オプション | 追加される段 | 成果物 | 同等のコマンド |
| ---------- | ------------ | ------ | -------------- |
| `--pdf` | `pandoc` | `output.pdffilename` | `ppt_to_pdf` |
| `--puremd` | `puremd` | `output.puremdfilename` | `ppt_to_puremd` |
| `--githubmd` | `puremd` → `githubmd` | `output.githubmdfilename`（puremd MD も残す） | `ppt_to_githubmd` |
| `--notecom` | `puremd` → `notecomexport` | `output.notecomyamlfilename`（puremd MD も残す） | `ppt_to_notecom` |
| `--transfer` | `puremd` → `transfer` | `transfer.dataentry_input` への転送 | `ppt_to_transfer`（`--puremd` / `--githubmd` と併用時はそれぞれの `--transfer`） |
| `--pptx` | `pptmerge` | `output.pptxfilename`（結合済み pptx） | `pptmerge`（詳細は [`--pptx`（pptmerge）](#--pptxpptmerge)） |

* `render` の後の段は `puremd` → `githubmd` → `notecomexport` → `transfer` → `pptmerge` → `pandoc` の順に、選んだものだけ実行する。`puremd` は MD 系の出力のどれかを選べば 1 回だけ入る。**`pandoc` は最後**に回す（最も時間がかかり失敗しやすいため。PDF が失敗しても MD 系の成果物は残る）。`pptmerge`（`--pptx`）も PowerPoint を操作して時間がかかるので MD 系の後、`pandoc` の直前に置く。
* 中間生成ファイルの削除は、各出力に対応する `ppt_to_*` が残すファイルの和集合を残し、それ以外を削除する（`--pdf` なら `output.renderedfilename`、`--puremd` / `--githubmd` / `--notecom` なら `output.puremdfilename` を残す）。`--keep-work` で全て残す。
* `--pdf` を含むときは `ppt_to_pdf` と同じく、`source.cropsrc` のスライド PDF と成果物 PDF のパス衝突を開始前に検査する。

### `--transfer` の転送元

`--githubmd` を併用していれば GitHub 用 MD（`output.githubmdfilename`）、そうでなければ puremd 処理済み MD（`output.puremdfilename`）を転送する。優先順位は `--source`（`puremd` / `githubmd` / `rendered` / `merged`）> `transfer.inputmd` > 上記の既定。

### `when.command` の扱い

1 回の merge で全ての出力を作るため、procedure の `when.command` / `not_command` は、選んだ出力に対応するコマンド（上表の「同等のコマンド」。出力指定なしなら `ppt_to_pdf`）の名前で照合する。対応するコマンドごとに残る procedure 項目が**同じなら**そのまま 1 回で実行する。**異なる場合**（例: `not_command: ppt_to_pdf` の項目があるレシピで `--pdf --githubmd`）は、1 回の merge では両方を正しく作れないので**開始前にエラー（終了コード 2）**とし、該当する `ppt_to_*` を別々に実行するよう案内する。`ppt_build` 自体の名前は `when.command` には書けない。

### `--pptx`（pptmerge）

`--pptx` を付けると、同じレシピで `pptmerge` を実行して結合済み pptx（`output.pptxfilename`）も作る。`pptmerge recipe.yaml` を別に実行するのと同じ結果になる。

* **実行位置**: `idresolve` より後（MD 系の出力の後、`pandoc` の直前）。`indexer.pptxnumbering: idresolve` のときは `idresolve` が作った `output.idresolvedfilename` を読んで番号を振る。ID 解決済みマップは work ファイルとして最後に削除されるが、削除は全段の後なので `pptmerge` からは読める。
* **MD 系の出力は増えない**: `--pptx` だけを指定した場合、MD 側は出力指定なしと同じ扱い（`render` まで実行し、rendered MD を残す。`when.command` は `ppt_to_pdf` で照合）。
* **`when.command`**: `pptmerge` 段は MD の merge とは別の結合なので、procedure を **`pptmerge` の名前で**照合する（単独の `pptmerge` と同じ項目が残る）。MD 側の「出力ごとに procedure が同じか」の検査には加わらない。
* **Windows 専用**: `pptmerge` は PowerPoint（Windows + pywin32）を使う。win32com を読み込めない環境で `--pptx` を指定すると、**どの段も実行せずに開始前にエラー（終了コード 2）**にする（`--dry-run` のときは検査しない）。
* **上書き**: 既存の pptx を上書きするには `--force` か `output.force: true` が要る（`pptmerge` と同じ）。`pptmerge` の差分スキップは ID 解決済みマップも入力に含めるため、`ppt_build` では毎回作り直しになることが多い。
* **`pptmerge` 段にだけ効くオプション**: `--deletecsl`（結合済み pptx の CSL 処理）、`--pptxnumbering`（`indexer.pptxnumbering` を上書き）。`--pptx` なしで指定すると無視して警告する。
* **両方に効くオプション**: `--deletecsp`（前処理と結合済み pptx）、`--rebuild`（`pptpdfexport` の PDF と結合済み pptx を作り直す）、`--preprocess`（`source.cropsrc.pptx` に加え、`pptmerge` 段では procedure の insertpptx 元も前処理する。`pptmerge --preprocess` と同じ）、`--no-check`（insertmd のドリフトゲートに加え insertpptx のドリフトチェックも省く）。

固有オプションは出力オプションのほか `--workdir` / `--force` / `--rebuild` / `--preprocess` / `--deletecsl`（`--pptx` 時のみ有効）/ `--deletecsp` / `--pptxnumbering`（`--pptx` 時のみ有効）/ `--no-check` / `--keep-work` / `--yes-clear-dir` / `--source`。

---

## パイプラインにおける CSL マーカーの扱い

全体方針として **CSL スライド削除処理は `pptmerge` の最後（結合済み pptx）でのみ行う**。`ppt_to_pdf` / `ppt_to_transfer` / `ppt_to_puremd` / `ppt_to_githubmd` / `ppt_to_notecom` / `ppt_build` / `crop_to_pdf` のパイプライン系コマンドは `pptmerge` を通らないため、**CSL マーカーを一切処理しない**（例外は `ppt_build --pptx` の `pptmerge` 段で、ここでは単独の `pptmerge` と同じく結合済み pptx に CSL 処理を行う。PDF・MD 側は下表のとおり未処理のまま）。

| 項目 | 挙動 |
| ---- | ---- |
| `--preprocess` での個別 pptx 処理 | 一般マーカー（`#CSP#` / `#TEMP#` / `#MEMO#` / `#CHAPT#` / `#SECTION#` / `#SUBSECTION#` / `#STAY#` 等）のみ処理する |
| `#CSL#` | スライド削除・マーカー消去のいずれも行わない。マーカー文字列はそのまま残る |
| `indexer.deletecsl` | 参照しない（設定されていれば info ログを出す） |
| `--deletecsl` | 無視する（指定されていれば警告を出す） |

**注意:** CSL マーカーが未処理のまま残るため、`#CSL#` を含むスライドは PDF・切り出し画像・エクスポート MD にそのまま出力され、`#CSL#` の文字列も見えたままになる。パイプラインのソース pptx には `#CSL#` を使わない運用を前提とする。

`#CSL#` を含む pptx をパイプラインに通す必要がある場合は、パイプライン実行前に [pptdeletecsl](pptx.md#pptdeletecsl) でソース pptx を処理しておく。

```bash
pptmdmerge pptdeletecsl source.pptx -o source_nocsl.pptx   # または --mode strip
```

マーカーの分類と各処理の定義は [pptmerge のマーカーの分類と処理タイミング](pptx.md#マーカーの分類と処理タイミング) を参照。
