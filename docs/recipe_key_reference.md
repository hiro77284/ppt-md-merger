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
| ur | `puremd`（別名 `githubmd`） |
| cb | `condblockprocess` |
| pm | `pptmerge` |
| ie | `pptimgexport` |
| me | `pptmdexport` |
| pe | `pptpdfexport` |
| cr | `crop` |
| tr | `transfer` |
| nc | `notecomexport` |

パイプライン系（`ppt_to_pdf`・`crop_to_pdf`）は構成するサブコマンドのキーをすべて継承するため、個別には記載しない。

---

## トップレベルキー

| キー | 全コマンド | 備考 |
| ---- |:----------:| ---- |
| `version` | R | レシピ仕様の版。`1`（省略時）は procedure の operation 記法（非推奨）、`2` は操作キー記法（`- insertpptx: a.pptx`）。記法の混在はエラー。詳細は `docs/md_merge_spec.md` の 5.3 |
| `_constants` | R | TOML の定数ファイル（パスまたはリスト）。`__NAME__` 置換に使う。読み込み後キーは消える。旧書式 `!constants` は非推奨。詳細は `docs/md_merge_spec.md` の 5.2 |
| `_include` | R | 任意の階層のマッピングに書ける。YAML ファイル（パスまたはリスト）を読み込んでそのマッピングに合成し、兄弟キーが優先される。旧書式 `!include` は非推奨。詳細は `docs/md_merge_spec.md` の 5.1 |
| `workdir` | R | 入出力パスの基準ディレクトリ。省略時は YAML と同じディレクトリ。`--workdir` CLI 引数で上書き可能 |

---

## output セクション

| キー                            | mg  | ic  | ir  | rd  | pd  | ur  | cb  | pm  | ie  | me  | pe  | cr  | tr  | 備考                                                                    |
| ----------------------------- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --------------------------------------------------------------------- |
| `output.outputdir`            |  W  |  R  |  R  |  R  |  R  |  R  |     |  W  |     |     |     |     |  R  | 省略時は `workdir` と同じディレクトリ                                              |
| `output.force`                |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  |  R  | `true` で全コマンドに `--force` 相当                                           |
| `output.targetbasefilename`   |  R  |  R  |  R  |  R  |  R  |  R  |     |  R  |     |     |     |     |     | 出力ファイル名のベース部分。指定すると他の出力キーを省略時に自動生成。拡張子を含む場合は警告して除去                    |
| `output.mdfilename`           |  W  |  R  |     |  R  |     |     |     |     |     |     |     |     |     | 省略時は `targetbasefilename` から自動生成                                      |
| `output.checkfilename`        |  R  |     |     |     |     |     |     |  R  |     |     |     |     |     | `checkgen` が生成（W）、`mg` が読んで insertmd を、`pm` が読んで insertpptx を整合性チェック。省略時は `targetbasefilename` から `{base}_check.yaml` を自動生成 |
| `output.insertsamplefilename` |     |     |     |     |     |     |     |     |     |  W  |     |     |     | `me`（pptmdexport）が procedure 貼り付け用サンプル（insertpptx／insertmd／ミックスの3ブロック）を生成。省略時は `targetbasefilename` から `{base}_insertsample.yaml` を自動生成 |
| `output.idcollectfilename`    |     |  W  |  R  |     |     |     |     |     |     |     |     |     |     | 省略時は `targetbasefilename` から自動生成                                      |
| `output.idresolvedfilename`   |     |     |  W  |  R  |     |     |     |  R  |     |     |     |     |     | pm は `{{num/title/label:}}` 参照置換にも使用。省略時は `targetbasefilename` から自動生成 |
| `output.renderedfilename`     |     |     |     |  W  |  R  |  R  |     |     |     |     |     |     |  R  | 省略時は `targetbasefilename` から自動生成。tr は `transfer.inputmd` 省略時のフォールバック  |
| `output.pdffilename`          |     |     |     |     |  W  |     |     |     |     |     |     |     |     | `--tex`/`--html`/`--reveal` 未指定時。省略時は `targetbasefilename` から自動生成     |
| `output.texfilename`          |     |     |     |     |  W  |     |     |     |     |     |     |     |     | `--tex` 指定時。省略時は `targetbasefilename` から自動生成                          |
| `output.htmlfilename`         |     |     |     |     |  W  |     |     |     |     |     |     |     |     | `--html` 指定時。省略時は `targetbasefilename` から自動生成                         |
| `output.revealfilename`       |     |     |     |     |  W  |     |     |     |     |     |     |     |     | `--reveal` 指定時。省略時は `targetbasefilename` から自動生成                       |
| `output.resourcepathfilename` |     |     |     |     |  W  |     |     |     |     |     |     |     |     | `pandoc.resource-path` 指定時に生成。省略時は `targetbasefilename` から自動生成        |
| `output.puremdfilename`       |     |     |     |     |     |  W  |     |     |     |     |     |     |     | 省略時は `targetbasefilename` から自動生成。nc は既定の入力（`--source` / `notecomexport.inputmd` 未指定時） |
| `output.notecomyamlfilename`     |     |     |     |     |     |     |     |     |     |     |     |     |     | nc が W。省略時は `targetbasefilename` から `<base>_notecom.yaml` を自動生成          |
| `output.pptxfilename`         |     |     |     |     |     |     |     |  W  |     |     |     |     |     | `targetbasefilename` 未指定時は必須。省略時は `targetbasefilename` から自動生成         |

---

## transfer セクション

| キー | tr | 備考 |
| ---- |:--:| ---- |
| `transfer.inputmd` | R | 入力 MD ファイル名。省略時は `output.renderedfilename` を使用。`output.outputdir` 基準で解決 |
| `transfer.outputmd` | R | 転送先の出力 MD ファイル名。省略時は `{slug}.md`。主に `README.md` へのリネーム用。絶対パス・`..` は不可 |
| `transfer.dataentry_input` | R | 出力先ディレクトリ（必須）。存在しない場合は自動作成。絶対パスまたは `workdir` 基準の相対パス |
| `transfer.slug` | R | 画像コピー先サブディレクトリ名 & 出力 MD の既定ベース名（必須）。パターン `^[a-z0-9][a-z0-9-]*[a-z0-9]$` |
| `transfer.image_naming` | R | コピー画像の命名。`preserve`（既定・元名のまま）/ `sanitize`（ASCII スラグ化）。Web URL エンコードや NFC/NFD 差異の回避に |
| `transfer.image_collision` | R | **同一実行内で別のソース画像が同じコピー先になったとき**の扱い。`rename`（既定・`_1`/`_2`）/ `overwrite`（警告して上書き）。`merge.image-collision` と同じ意味 |

---

## notecomexport セクション

| キー | nc | 備考 |
| ---- |:--:| ---- |
| `notecomexport.inputmd` | R | 入力 MD ファイル名。省略時は `output.puremdfilename`。`output.outputdir` 基準で解決。`--source` 指定時は無視 |
| `notecomexport.hashtags` | R | note のハッシュタグのリスト。省略時は frontmatter の `tags` から生成（`#` を前置） |
| `notecomexport.cover` | R | カバー画像パス（入力 MD 基準）。省略時は frontmatter の `notecom_cover`、それも無ければ `hero` |
| `notecomexport.inline` | R | インライン記法の扱い。`plain`（既定・強調・コード・リンク記法等を素のテキストに落とす）/ `markdown`（そのまま） |
| `notecomexport.quote_labels` | R | 引用ブロック先頭のラベル行（`[!NOTE]` / `**QUOTE**` 等）の扱い。`drop`（既定）/ `keep` |
| `notecomexport.link_base` | R | サイト内相対リンク（`/blog/...` 等）を絶対 URL にする基準 URL（`http(s)://` 必須）。省略時は相対リンクをテキストに落とす |

---

## input セクション

| キー | mg | ic | ir | rd | pd | ur | cb | pm | ie | me | pe | cr | 備考 |
| ---- |:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:| ---- |
| `input.dirs` | R |  |  |  |  |  |  | R |  |  |  |  | 入力ファイル（MD/PPTX・`!include` 参照先）の検索パス一覧。リスト可で先頭から順に探索。各エントリは**レシピ YAML のあるディレクトリ基準**で解決（`workdir`・`data-dir` の影響を受けない）。慣例として先頭に `.`（YAML のあるディレクトリ）を置く（無い場合は警告）。省略時は警告のうえ `workdir`（または YAML の親）にフォールバック。非推奨の `mddir`/`pptxdir` は末尾に追加される |
| `input.mddir` | R |  |  |  |  |  |  |  |  |  |  |  | **非推奨**（`input.dirs` 推奨）。省略時は `workdir` と同じディレクトリ。リスト可 |
| `input.pptxdir` |  |  |  |  |  |  |  | R |  |  |  |  | **非推奨**（`input.dirs` 推奨）。省略時は `workdir` と同じディレクトリ。リスト可 |
| `input.cropsrc.pptx` |  |  |  |  |  |  |  |  | R | R | R |  | 辞書またはリスト形式 |
| `input.cropsrc.pdf` |  |  |  |  |  |  |  |  | R |  | W |  | pe が生成、ie が読む |
| `input.cropsrc.dpi` |  |  |  |  |  |  |  |  | R |  |  |  | 省略時 150 |
| `input.imagesdir` |  |  |  |  |  |  |  |  |  |  |  | R | crop 専用 |

---

## merge セクション

| キー | mg | 備考 |
| ---- |:--:| ---- |
| `merge.no-copy-images` | R | `--no-copy-images` 相当 |
| `merge.image-dir` | R | `--image-dir` 相当。**省略時の既定は `images`**（結合済み MD と画像を 1 段構成に保つ規約）。空文字を明示すると `outputdir` 直下に置く |
| `merge.flatten-images` | R | `--flatten-images` 相当 |
| `merge.image-naming` | R | コピー画像の命名。`preserve`（既定・元名のまま）/ `sanitize`（ASCII スラグ化）。`transfer.image_naming` と同じ意味 |
| `merge.image-collision` | R | **同一実行内で別のソース画像が同じコピー先になったとき**の扱い。`rename`（既定・`_1`/`_2` を付けて回避）/ `overwrite`（警告して上書き）。前回実行の同名ファイルの上書きは衝突とみなさない（再実行は冪等） |
| `merge.overwrite-images` | R | **非推奨**: `image-collision: overwrite` のエイリアス |
| `merge.clear-dir-before-merge` | R | **既定 `true`**。`image-dir` が空でないとき merge 前に image-dir 内を全削除（削除前にフルパスを提示して確認。単体 merge は `--force` で確認省略、パイプラインは `--force` に関係なく必ず確認、`false` で無効化）。merge 入力が参照する画像が image-dir 内にあるときは削除をスキップして警告 |
| `merge.strict` | R | `--strict` 相当 |

---

## pandoc セクション

| キー | pd | cb | 備考 |
| ---- |:--:|:--:| ---- |
| `pandoc.format` | R |  | 省略時 `pdf`。`--tex`/`--html`/`--reveal` 指定時は無視 |
| `pandoc.defaults` | R |  | PDF / LaTeX モード用 pandoc defaults ファイル。**単一ファイルまたはリスト**。リスト指定時は各ファイルを順に `-d` として pandoc に渡し、後勝ちでマージする（共有ベース＋文書ごとの上書きに分割する用途。例: `[engine.yaml, this_doc.yaml]`） |
| `pandoc.engine` | R |  | PDF の組版エンジン `typst`（既定。`output.pdffilename` と同名の `.typ` も残す）/ `latex`（lualatex。廃止予定で、指定すると警告）。`--engine` で上書き可（`docs/spec/output_formats.md` の「Typst エンジン」） |
| `pandoc.typstdefaults` | R |  | `engine: typst` 用の pandoc defaults。`defaults` 同様に単一/リスト可。省略時は同梱 `typst_semantic_engine.yaml` |
| `pandoc.typst-cover-md` | R |  | `engine: typst` の表紙（Markdown。レシピ dir 基準 → workdir → 同梱 templates に basename でフォールバック。`typst-cover-md: cover_standard_typst.md` で同梱の標準表紙を明示できる）。`{{#if:NAME}}` と `{{v:NAME}}` を展開して typst 断片に変換。省略時、`cover-md` か `conditional-process-input` があれば同梱の `cover_standard_typst.md`（`COVER_*` を使う標準の表紙）を使う |
| `pandoc.typst-root` | R |  | `engine: typst` の `typst compile --root`。省略時は `.typ`・render 済み MD・`resource-path` を含む共通の上位ディレクトリ |
| `pandoc.htmldefaults` | R |  | `--html` モード用。`defaults` 同様に単一/リスト可 |
| `pandoc.htmlcover` | R |  | `--html` 用の HTML 表紙テンプレ。`{{v:COVER_*}}` をレシピ `vars` で置換して本文前に挿入（`data-dir`→workdir→同梱 `templates/` の basename フォールバック）。同梱の既定は `standard_cover.html`（シンプルなタイトルブロック） |
| `pandoc.revealdefaults` | R |  | `--reveal` モード用。`defaults` 同様に単一/リスト可 |
| `pandoc.filters` | R |  | Lua フィルターリスト |
| `pandoc.metadata-file` | R |  | |
| `pandoc.template` | R |  | PDF / LaTeX モードのみ |
| `pandoc.include-in-header` | R |  | PDF / LaTeX モードのみ |
| `pandoc.include-before-body` | R |  | PDF / LaTeX モードのみ。リスト可 |
| `pandoc.syntax-highlighting` | R |  | |
| `pandoc.data-dir` | R |  |  pandoc 本体への --data-dir 受け渡し。 レシピ内の相対パス解決の基点（対象：defaults,htmldefaults,revealdefalts,template,include-in-header,conditional-process-input |
| `pandoc.resource-path` | R |  | `;` 区切り文字列またはリスト。レシピyamlのあるディレクトリ基準 (pandoc.data-dir,workdirではない) |
| `pandoc.cover-md` | R |  | Markdown で書いた表紙のパス（レシピ dir 基準 → workdir → 同梱 templates に basename でフォールバック）。`{{v:NAME}}` をレシピ `vars` で置換（未定義は空）→ セマンティック lua フィルタ付きで pandoc により tex/html 断片へ変換 → `include-before-body` 先頭に前置する。タイトルの下を Markdown で自由に書ける（`conditional-process-input` の手書き tex 表紙に対する markdown 版）。PDF/LaTeX は tex 断片、`--html`/`--reveal` は該当形式の断片を生成 |
| `pandoc.conditional-process-input` |  | R | テンプレートファイルパス。 (pandoc.data-dir基準 → workdir フォールバック) |
| `pandoc.conditional-process-output` |  | W | 展開後の出力ファイルパス。(workdir基準、 省略時は outputdir 配下に work_<input名> を自動生成）) |

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
| `indexer.deletecsl` |  |  | R | **結合済み pptx** に対する CSL 処理。true=CSL スライド削除処理 / false=CSL マーカー消去処理。個別 pptx の前処理と ppt_to_* パイプラインでは参照されない |
| `indexer.deletecsp` |  |  | R | `#CSP#` シェイプを削除するか |

---

## その他のトップレベルセクション

| キー | mg | rd | pm | cb | 備考 |
| ---- |:--:|:--:|:--:|:--:| ---- |
| `vars.*` | R | R | R | R | 変数置換に使用。`mg` は chapter/section タイトル、`rd` は `{{v:VAR}}`、`pm` はスライドテキスト、`cb` は条件ブロック展開 |
| `procedure` | R |  | R |  | `mg` は `insertmd`/`chapter`/`section`/`subsection`/`insertvspace`/`insertpagebreak`/`insertvfill`、`pm` は `insertpptx`/`chapter`/`section`/`subsection`/`beginstay`/`endstay`。`pm` は MD 専用の操作（`insertmd`/`insertvspace`/`insertpagebreak`/`insertvfill`）も**許可はするが無視**する（同一 procedure を mg と pm で共用できるようにするため） |
| `procedure[].when` | R |  | R |  | 項目の条件付き適用。`command` / `not_command`（起動サブコマンド名）、`tag` / `not_tag`（`--tag` の値）。値は文字列またはリスト。`ck`/`cv`/`va` は条件を無視して全項目を対象にする。詳細は `docs/spec/md_pipeline.md` |
| `separator.enabled` |  |  | R |  | `insertpptx` 間に空白スライドを挿入するか |
| `log.filename` |  |  | R |  | 省略時は `<pptxfilename_stem>_merge.log` |
| `log.dir` |  |  | R |  | 省略時は `output.outputdir`。`workdir` 基準 |
| `log.level` |  |  | R |  | 既定 `info` |
| `log.duplicate` |  |  | R |  | `stdout` / `stderr` / 省略 |
| `puremd.strip_config` |  |  |  |  | `puremd` のみ参照。プロジェクト独自の追加 strip パターン（任意）。生 raw ブロック除去は組み込み |
| `puremd.fenced_div.enabled` |  |  |  |  | `puremd` のみ参照。fenced div 変換の有効/無効（省略時 `true`） |
| `puremd.fenced_div.alerts` |  |  |  |  | `puremd` のみ参照。クラス名→GitHub アラート種別の対応（ビルトインに追加・上書き） |
| `puremd.fenced_div.plain_blockquote` |  |  |  |  | `puremd` のみ参照。ラベルなし blockquote にするクラス名のリスト（ビルトインに追加） |
| `pptmdexport.latex_check` |  |  |  |  | `me`（pptmdexport）のみ参照。抽出 MD 内の生 raw コード（`{=latex}` 等）とフェンスなしの LaTeX コマンドの検出モード `off`/`warn`/`error`（省略時 `warn`）。`--latex-check` で上書き可 |

※ `puremd.*` は `ur`（puremd）が参照するが、他のコマンドとの比較列が不要なため単独記載。`pptmdexport.*` も同様に単独記載。

---

## パイプラインコマンドの構成

| コマンド | 構成ステップ |
| -------- | ------------ |
| `crop_to_pdf` | `crop` → `merge` → `idcollect` → `idresolve` → `render` → `pandoc` |
| `ppt_to_pdf` | `pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `condblockprocess` → `pandoc` |
