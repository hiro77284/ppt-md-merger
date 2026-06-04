# レシピ YAML キー参照マトリクス

各サブコマンドがレシピ YAML のどのキーを参照するかを示す。

## 凡例

| 記号 | 意味 |
| ---- | ---- |
| R | 読む（入力として参照する） |
| W | 書く（このコマンドが出力先として使う） |
| （空欄） | 使用しない |

## コマンド略称

| 略称 | サブコマンド |
| ---- | ------------ |
| mg | `merge` |
| ic | `idcollect` |
| ir | `idresolve` |
| rd | `render` |
| pd | `pandoc` |
| ur | `puremd` |
| cb | `condblockprocess` |
| pm | `pptmerge` |
| ie | `pptimgexport` |
| me | `pptmdexport` |
| pe | `pptpdfexport` |
| cr | `crop` |

パイプライン系（`ppt_to_pdf`・`crop_to_pdf`）は構成するサブコマンドのキーをすべて継承するため、個別には記載しない。

---

## トップレベルキー

| キー | 全コマンド | 備考 |
| ---- |:----------:| ---- |
| `workdir` | R | 入出力パスの基準ディレクトリ。省略時は YAML と同じディレクトリ。`--workdir` CLI 引数で上書き可能 |

---

## output セクション

| キー | mg | ic | ir | rd | pd | ur | cb | pm | ie | me | pe | cr | 備考 |
| ---- |:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:| ---- |
| `output.outputdir` | W | R | R | R | R | R |  | W | | | | | 省略時は `workdir` と同じディレクトリ |
| `output.force` | R | R | R | R | R | R | R | R | R | R | R | R | `true` で全コマンドに `--force` 相当 |
| `output.mdfilename` | W | R |  | R |  |  |  |  |  |  |  |  | |
| `output.idcollectfilename` |  | W | R |  |  |  |  |  |  |  |  |  | |
| `output.idresolvedfilename` |  |  | W | R |  |  |  | R |  |  |  |  | pm は `{{num/title/label:}}` 参照置換にも使用 |
| `output.renderedfilename` |  |  |  | W | R | R |  |  |  |  |  |  | |
| `output.pdffilename` |  |  |  |  | W |  |  |  |  |  |  |  | `--tex`/`--html`/`--reveal` 未指定時 |
| `output.texfilename` |  |  |  |  | W |  |  |  |  |  |  |  | `--tex` 指定時 |
| `output.htmlfilename` |  |  |  |  | W |  |  |  |  |  |  |  | `--html` 指定時 |
| `output.revealfilename` |  |  |  |  | W |  |  |  |  |  |  |  | `--reveal` 指定時 |
| `output.resourcepathfilename` |  |  |  |  | W |  |  |  |  |  |  |  | `pandoc.resource-path` 指定時に生成 |
| `output.puremdfilename` |  |  |  |  |  | W |  |  |  |  |  |  | |
| `output.pptxfilename` |  |  |  |  |  |  |  | W |  |  |  |  | |

---

## input セクション

| キー | mg | ic | ir | rd | pd | ur | cb | pm | ie | me | pe | cr | 備考 |
| ---- |:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:| ---- |
| `input.mddir` | R |  |  |  |  |  |  |  |  |  |  |  | 省略時は `workdir` と同じディレクトリ。リスト可 |
| `input.pptxdir` |  |  |  |  |  |  |  | R |  |  |  |  | 省略時は `workdir` と同じディレクトリ。リスト可 |
| `input.cropsrc.pptx` |  |  |  |  |  |  |  |  | R | R | R |  | 辞書またはリスト形式 |
| `input.cropsrc.pdf` |  |  |  |  |  |  |  |  | R |  | W |  | pe が生成、ie が読む |
| `input.cropsrc.dpi` |  |  |  |  |  |  |  |  | R |  |  |  | 省略時 150 |
| `input.imagesdir` |  |  |  |  |  |  |  |  |  |  |  | R | crop 専用 |

---

## merge セクション

| キー | mg | 備考 |
| ---- |:--:| ---- |
| `merge.no-copy-images` | R | `--no-copy-images` 相当 |
| `merge.image-dir` | R | `--image-dir` 相当 |
| `merge.flatten-images` | R | `--flatten-images` 相当 |
| `merge.strict` | R | `--strict` 相当 |

---

## pandoc セクション

| キー | pd | cb | 備考 |
| ---- |:--:|:--:| ---- |
| `pandoc.format` | R |  | 省略時 `pdf`。`--tex`/`--html`/`--reveal` 指定時は無視 |
| `pandoc.defaults` | R |  | PDF / LaTeX モード用 pandoc defaults ファイル |
| `pandoc.htmldefaults` | R |  | `--html` モード用 |
| `pandoc.revealdefaults` | R |  | `--reveal` モード用 |
| `pandoc.filters` | R |  | Lua フィルターリスト |
| `pandoc.metadata-file` | R |  | |
| `pandoc.template` | R |  | PDF / LaTeX モードのみ |
| `pandoc.include-in-header` | R |  | PDF / LaTeX モードのみ |
| `pandoc.include-before-body` | R |  | PDF / LaTeX モードのみ。リスト可 |
| `pandoc.syntax-highlighting` | R |  | |
| `pandoc.data-dir` | R |  | |
| `pandoc.resource-path` | R |  | `;` 区切り文字列またはリスト |
| `pandoc.conditional-process-input` |  | R | テンプレートファイルパス |
| `pandoc.conditional-process-output` |  | W | 展開後の出力ファイルパス |

---

## pptmerge セクション

| キー | pm | 備考 |
| ---- |:--:| ---- |
| `pptmerge.stylebase` | R | 省略時は最初の `insertpptx` ファイルをスタイルベースとして使用 |

---

## indexer セクション

| キー | ir | rd | pm | 備考 |
| ---- |:--:|:--:|:--:| ---- |
| `indexer.pptxnumbering` |  | R | R | `no`（既定）/ `chapt_section` / `idresolve` |
| `indexer.delimiter` | R |  | R | 節番号の区切り文字。既定 `"."` |
| `indexer.separator` | R |  | R | 番号とタイトルの区切り文字。既定 `") "` |
| `indexer.chapter_marker` |  |  | R | 既定 `"#CHAPT#"`。`chapt_section` モードのみ |
| `indexer.section_marker` |  |  | R | 既定 `"#SECTION#"`。`chapt_section` モードのみ |
| `indexer.stay_marker` |  |  | R | 既定 `"#STAY#"`。`chapt_section` モードのみ |
| `indexer.deletecsl` |  |  | R | `#CSL#` スライドを削除するか |
| `indexer.deletecsp` |  |  | R | `#CSP#` シェイプを削除するか |

---

## その他のトップレベルセクション

| キー | mg | rd | pm | cb | 備考 |
| ---- |:--:|:--:|:--:|:--:| ---- |
| `vars.*` | R | R | R | R | 変数置換に使用。`mg` は chapter/section タイトル、`rd` は `{{v:VAR}}`、`pm` はスライドテキスト、`cb` は条件ブロック展開 |
| `procedure` | R |  | R |  | `mg` は `insertmd`/`chapter`/`section`/`subsection`、`pm` は `insertpptx`/`chapter`/`section`/`subsection`/`beginstay`/`endstay` |
| `separator.enabled` |  |  | R |  | `insertpptx` 間に空白スライドを挿入するか |
| `log.filename` |  |  | R |  | 省略時は `<pptxfilename_stem>_merge.log` |
| `log.dir` |  |  | R |  | 省略時は `output.outputdir`。`workdir` 基準 |
| `log.level` |  |  | R |  | 既定 `info` |
| `log.duplicate` |  |  | R |  | `stdout` / `stderr` / 省略 |
| `puremd.strip_config` |  |  |  |  | `puremd` のみ参照。省略時はビルトインデフォルト |

※ `puremd.strip_config` は `ur`（puremd）が参照するが、他のコマンドとの比較列が不要なため単独記載。

---

## パイプラインコマンドの構成

| コマンド | 構成ステップ |
| -------- | ------------ |
| `crop_to_pdf` | `crop` → `merge` → `idcollect` → `idresolve` → `render` → `pandoc` |
| `ppt_to_pdf` | `pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `condblockprocess` → `pandoc` |
