# 記法リファレンス（索引）

原稿・PPTX ノート・テンプレートに書ける**記法**の一覧。レシピ YAML のキーは [recipe_key_reference.md](recipe_key_reference.md) を正典とする（本書はキーを扱わない）。

本書は**網羅と索引に徹する**。各記法の詳細な挙動は分冊側が正典で、「詳細」欄からたどる。挙動の説明を本書に書き足さないこと（二重管理になるため）。

凡例:

| 欄 | 意味 |
| -- | ---- |
| 書く場所 | **原稿MD** = 結合対象の MD / **ノート** = PPTX スライドのノート / **スライド** = PPTX のシェイプ本文 / **テンプレ** = LaTeX/HTML テンプレート / **レシピ** = レシピ YAML |
| 処理する段 | その記法を解釈・除去するサブコマンドやフィルタ |

---

## 1. ID・参照マーカー

| 記法 | 書く場所 | 処理する段 | 意味 | 詳細 |
|---|---|---|---|---|
| `{{#id:TYPE:PART:LOCAL}}` | 原稿MD / ノート | idcollect → idresolve → render | ID 定義。直後の見出しを採番対象にする。`TYPE` = `chapter`/`section`/`subsection`/`image`/`var` | [md_pipeline](spec/md_pipeline.md#マーカーフォーマット) |
| `{{num:FULL_ID}}` | 原稿MD | render | 番号参照 | [md_pipeline](spec/md_pipeline.md#2-参照変換) |
| `{{title:FULL_ID}}` | 原稿MD | render | タイトル参照 | 同上 |
| `{{label:FULL_ID}}` | 原稿MD | render | ラベル（番号＋タイトル）参照 | 同上 |
| `{{rawtitle:FULL_ID}}` | 原稿MD | render | pptx のタイトル枠の原文を参照（加工されない） | 同上 |
| `{{v:NAME}}` | 原稿MD / ノート / スライド / テンプレ | render（MD）・pptmerge（pptx）・condblockprocess（テンプレ） | レシピ `vars:` の値に置換 | [md_pipeline](spec/md_pipeline.md#3-変数置換) |
| `{{sectionlist}}` / `{{sectionlist:chapter:PART:LOCAL}}` | 原稿MD | render | 章に属するセクション一覧を箇条書きに展開（章とびら用） | [md_pipeline](spec/md_pipeline.md#4-セクション一覧展開sectionlist) |
| `{{nolabel}}` | 原稿MD（`{{#id:}}` と同じ行） | render | その見出しの label 置換をスキップ（**採番はされる**） | [md_pipeline](spec/md_pipeline.md#インライン制御マーカー) |
| `{{noref}}` | 原稿MD（`{{#id:}}` と同じ行） | render | その行と直後の見出しの参照変換・変数置換をスキップ | 同上 |
| `{{enclosenum:FULL_ID}}` | ノート | pptmerge（idresolve モード） | スライドタイトルの先頭に `(番号) ` を前置。ID を定義しないので複数スライドで使える | [pptx](spec/pptx.md#idresolve-モードの動作詳細) |
| `{{titlelabel:FULL_ID}}` | ノート | pptmerge（idresolve モード） | スライドタイトルを label で置換。ID を定義しない | 同上 |

> `{{enclosenum:}}` / `{{titlelabel:}}` は pptmdexport が MD 出力時に除去するため、`{{BLOCK:MD}}` 内に書いてもエクスポート MD には残らない。

## 2. 結合・採番の制御コメント

| 記法 | 書く場所 | 処理する段 | 意味 | 詳細 |
|---|---|---|---|---|
| `!include path/to/file.md` | 原稿MD | merge | MD を再帰的に取り込む（行頭）。**コードフェンス内でも展開される** | [md_pipeline](spec/md_pipeline.md#インクルード展開) |
| `<!-- md_merge {{chapter\|section\|subsection:VALUE}} {{title:TITLE}} -->` | 原稿MD | idcollect → idresolve | 直後のマーカーの採番を制御。`+`/省略 = +1、整数 = その値へリセット | [md_pipeline](spec/md_pipeline.md#value-による番号の加算リセット) |
| `<!-- md_merge_rawtitle: ... -->` | 自動生成 | pptmdexport が挿入、idcollect が読む | pptx のタイトル原文を inventory の `rawtitle` へ運ぶ | — |
| `<!-- source: ... -->` | 自動生成 | merge が挿入、idcollect / transfer が読む | 結合済み MD 内でのソースファイル境界 | — |
| `{{#id:...}}` 等を**コードフェンス内**に書いた場合 | — | — | merge / render はフェンス非対応のため**展開・置換される** | [pandoc_filters](pandoc_filters.md#コードブロック内でもマーカーは置換される) |

## 3. セマンティック構造（原稿 MD）

定義の正典は [semantics.yaml](../src/md_merge/semantics.yaml)。設計方針は [design_semantic_lowering.md](design_semantic_lowering.md)。

### 3.1 ブロック（fenced div）

| 記法 | 意味 | LaTeX | HTML | GFM（puremd） |
|---|---|---|---|---|
| `::: {.note}` | 補足情報ボックス | `notebox` | `<div class>`＋CSS | `> [!NOTE]` |
| `::: {.warning}` | 注意喚起ボックス | `warningbox` | 同上 | `> [!WARNING]` |
| `::: {.leadline}` | 擬似見出し・リード行 | `leadlinebox` | 同上 | `> [!IMPORTANT]` |
| `::: {.widequote}` | 幅広引用 | `widequotebox` | 同上 | 素の blockquote |
| `::: {.largefontblock}` | 大きい文字ブロック | 専用環境 | 同上 | ラベル付き blockquote |
| `::: {.blockindent}` | 字下げブロック（`indent=3em`） | 専用環境 | 同上 | ラベル付き blockquote |
| `::: {.keep-together}` | 改ページ抑制 | minipage / `\Needspace` | `break-inside:avoid` | unwrap |
| `::: {.center}` | 中央寄せ | `center` 環境 | `text-align:center` | unwrap |

属性（`frame` / `colback` / `fontsize` / `left` / `width` / `center` ほか）は box 系で LaTeX のみ有効。一覧は [pandoc_filters](pandoc_filters.md#divboxeslua-の属性)。

### 3.2 インライン（bracketed span）

| 記法 | 意味 | LaTeX | HTML | GFM |
|---|---|---|---|---|
| `[語句]{.term}` | 用語 | `\semterm` | span＋CSS | `**語句**` |
| `[語句]{.keyword}` | キーワード | `\semkeyword` | 同上 | `**語句**` |
| `[path]{.path}` | パス・コマンド名 | `\sempath` | `<code>` | `` `path` `` |
| `[Ctrl+C]{.kbd}` | キー入力 | `\semkbd` | `<kbd>` | `<kbd>` |
| `[語句]{.emph}` | 強調 | `\emph` | span | `*語句*` |
| `[語句]{.rightlabel}` | 行末右寄せラベル | `\semrightlabel` | float:right | 素通し |

### 3.3 リーフ記法

| 記法 | 意味 | LaTeX | HTML | GFM |
|---|---|---|---|---|
| `{{vspace:N}}` / `{{vspace:5mm}}` | 垂直スペース（数値=行数、単位付き=その長さ） | `\vspace` | `div.vspace` | 破棄 |
| `{{pagebreak}}` | 改ページ | `\newpage` | `div.pagebreak` | `---` |
| `{{vfill}}` | 残り高を埋める | `\vspace*{\fill}` | `div.vfill` | 破棄 |
| `{{br}}` | 見出し内の強制改行 | `\hdbreak` | `<br>` | 破棄 |

> リーフ記法はレシピの `procedure` に `insertvspace` / `insertpagebreak` / `insertvfill` 操作を書いても挿入できる（[md_pipeline](spec/md_pipeline.md#行空け改ページの挿入insertvspace--insertpagebreak--insertvfill)）。

### 3.4 escape hatch

| 記法 | 意味 |
|---|---|
| ` ```{=latex} ` / ` ```{=html} ` | 生コードの passthrough。非対象形式では警告して破棄、puremd は `=latex` を破棄 |

## 4. コードブロック・画像（原稿 MD）

| 記法 | 意味 | 詳細 |
|---|---|---|
| ` ```bash ` 等 | 通常のフェンスドコードブロック。独自記法はない。言語名は pandoc（skylighting）準拠 | [pandoc_filters](pandoc_filters.md#コードブロックの書き方) |
| ` ```{.include} ` | **予約済み**。別 MD の取り込み（include-files.lua） | [pandoc_filters](pandoc_filters.md#include-コードブロックinclude-fileslua--include-files-resource-pathlua) |
| `![alt](ref){ width=100% }` | 画像参照＋pandoc 属性。ローカル相対パスは merge / transfer がコピーし書き換える | [md_pipeline](spec/md_pipeline.md#画像ファイルの処理) |
| `hero:` / `notecom_cover:`（frontmatter） | 画像パスとして扱われる frontmatter キー。正典は `_imagerefs.FRONTMATTER_IMAGE_KEYS` | [design_image_refs](design_image_refs.md) |
| `![alt](a.png "title")` / スペース入りパス / `<...>` 囲み / 参照リンク形式 / `<img>` | **非対応**。書き換えもコピーもされず素通しする（警告なし） | [md_pipeline](spec/md_pipeline.md#非対応の記法) |
| `## 見出し {.unnumbered}` | 番号を振らない見出し（pandoc 標準）。dump-sections が除外する | [pandoc_filters](pandoc_filters.md#unnumbered-見出し--dump-sectionslua) |

## 5. PPTX ノート（NOTE_CONTENT_FORMAT）

構造の正典は [note_content_format.md](note_content_format.md)。

| 記法 | 意味 |
|---|---|
| `NOTE_CONTENT_FORMAT: 1.0` | ノート 1 行目。これが無いとノートは解析対象外。行末にコメント可 |
| `===BLOCK===` | ブロック区切り行。行末に `#` コメント可 |
| `{{BLOCK:MD}}` / `{{BLOCK:MD:LONG}}` | MD 本文ブロック（両者は同義）。行末に `#` コメント可 |
| `{{BLOCK:MD:SHORT}}` | MD 短縮版ブロック（文法上は有効。現状どの段も優先利用しない） |
| `{{BLOCK:PLAIN}}` | プレーンテキスト。MD ブロックが無いときの代替 |
| `{{BLOCK:IMAGE}}` | 画像切り出し指示ブロック（pptimgexport） |
| `{{BLOCK:YAML}}` | 図版定義 YAML ブロック（pptyamlexport） |
| `{{BLOCK:EXPORT}}` | ディレクティブ専用ブロック（`key: value` 列） |
| `{{BLOCK:HTML}}` | 文法上は有効（現状未使用） |

### 5.1 ブロック本文に書くディレクティブ

| 記法 | ブロック | 意味 | 詳細 |
|---|---|---|---|
| `export-note: path.md` | MD ブロックの 1 行目 | その MD を切り出すファイル名。相対パスは **pptx のディレクトリ**基準 | [pptx](spec/pptx.md#pptmdexport) |
| `export-image-mode:` | IMAGE | `slide` / `named_shape` / `slide_with_rectpct` | [pptx](spec/pptx.md#export-image-mode-の値) |
| `export-image-target:` | IMAGE | 参照するシェイプ名 | 同上 |
| `export-image:` | IMAGE | 出力パス。相対パスは **pptx のディレクトリ**基準 | 同上 |
| `export-image-inset:` | IMAGE | 切り出し枠の拡大（正）/ 縮小（負）ピクセル | 同上 |
| `export-image-step:` | IMAGE | アニメーションの途中ステップを切り出す（`2` / `0-3, 5` / `all` / `last`）。省略時は PDF から最終状態。Windows 専用 | [pptx](spec/pptx.md#アニメーションのステップ切り出しexport-image-step) |
| `<__STEP__>` | IMAGE の `export-image:` 内 | ステップ番号に展開。複数ステップ指定時は必須 | 同上 |

> **基準ディレクトリの注意**: `export-image:` は pptx 基準、MD ブロック内の `![](...)` は切り出された MD 基準。両方を `../images/…` と書けるのは `src/` と `mds/` を同階層に置く規約の帰結。詳細は [design_image_refs](design_image_refs.md)。

### 5.2 プレースホルダー（ノート・スライド本文の両方で使える）

| 記法 | 置換内容 |
|---|---|
| `<__BASEFILENAME__>` | ソース pptx のファイル名（拡張子なし） |
| `<__FILENAME__>` | ソース pptx のファイル名（拡張子あり） |
| `<__SLIDENUM__>` | ソース pptx でのスライド番号（1 始まり） |
| `<__TITLE__>` | そのスライドのタイトル文字列 |

`#NOREPLACE#` を含むスライドでは置換をスキップする。

### 5.3 テキストマーカー（スライド内のシェイプ本文に書く）

| マーカー | 分類 | 意味 | 詳細 |
|---|---|---|---|
| `#CSL#` | CSL マーカー | そのスライドを削除（`indexer.deletecsl: true`）またはマーカーのみ消去。**結合済み pptx でのみ処理** | [pptx](spec/pptx.md#マーカーの分類と処理タイミング) |
| `#CSP#` | 一般 | `deletecsp: true` のときそのシェイプを削除 | 同上 |
| `#TEMP#` / `#MEMO#` | 一般 | そのシェイプを**常に削除** | 同上 |
| `#CHAPT#` | 一般 | チャプタースライド（`pptxnumbering: chapt_section`） | [pptx](spec/pptx.md#タイトル後処理アルゴリズム) |
| `#SECTION#` | 一般 | セクションスライド（同上） | 同上 |
| `#STAY#` | 一般 | 章・節カウンタのインクリメントを抑制（同上） | [pptx](spec/pptx.md#stay-マーカーの動作chapt_section-モード) |
| `#NONUMBERING#` | 一般 | `chapt_section` の番号付きタイトル書き換えをスキップ（**カウンタは進む**） | [pptx](spec/pptx.md#nonumbering-マーカーの動作) |
| `#NOREPLACE#` | 一般 | そのスライドのタイトル置換・プレースホルダー置換をスキップ | [pptx](spec/pptx.md#noreplace-マーカーの動作) |

マーカー名は `indexer.chapter_marker` 等で変更できる（[recipe_key_reference](recipe_key_reference.md)）。

## 6. テンプレート（condblockprocess）

| 記法 | 意味 | 詳細 |
|---|---|---|
| `{{v:NAME}}` | レシピ `vars:` の値に置換 | [conditional_block_process](conditional_block_process.md) |
| `{{#if:NAME}}` … `{{#endif:NAME}}` | 変数が定義されていればブロックを残す。未定義でもエラーにしない | 同上 |

## 7. レシピ YAML / ファイル名の記法

レシピの**キー**は [recipe_key_reference.md](recipe_key_reference.md) が正典。ここではキー以外の記法のみ挙げる。

| 記法 | 書く場所 | 意味 | 詳細 |
|---|---|---|---|
| `_include: path.yaml` | レシピ / ノート YAML ブロック | YAML を読み込み、そのマッピングに合成する（兄弟キー優先・リスト可）。旧書式 `!include` は非推奨 | [md_merge_spec](md_merge_spec.md#51-レシピ-yaml-の-_include) |
| `_constants: path.toml` | 同上（トップレベル） | TOML の定数ファイルを読み込む（リスト可）。旧書式 `!constants` は非推奨 | [pptx](spec/pptx.md#ノート-yaml-での-_include) |
| `__NAME__` | 同上 | 定数置換。組み込みは `__DATE__` / `__TIME__` / `__DATETIME__` | 同上 |
| `name[1-7].md` | `procedure` の `insertmd` | レンジ展開（`name1.md` … `name7.md`） | [md_pipeline](spec/md_pipeline.md#insertmd-ファイル名のレンジ展開from-to) |
| `fig__10_20_90_80.png` | crop 対象の画像ファイル名 | 末尾の `__{L}_{T}_{R}_{B}`（各 0〜100）で切り出し範囲を指定 | [pipelines](spec/pipelines.md) |

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [recipe_key_reference.md](recipe_key_reference.md) | レシピ YAML の全キー一覧（キーの正典） |
| [spec/md_pipeline.md](spec/md_pipeline.md) | merge / idcollect / idresolve / render の挙動 |
| [spec/pptx.md](spec/pptx.md) | pptmerge / pptimgexport / pptmdexport / pptyamlexport の挙動 |
| [spec/output_formats.md](spec/output_formats.md) | pandoc / puremd / condblockprocess / transfer の挙動 |
| [note_content_format.md](note_content_format.md) | PPTX ノートのブロック構造の文法 |
| [pandoc_filters.md](pandoc_filters.md) | ビルトイン Lua filter と fenced div クラス・属性 |
| [design_semantic_lowering.md](design_semantic_lowering.md) | セマンティック記法と lowering の設計 |
| [design_image_refs.md](design_image_refs.md) | 画像参照とディレクトリ規約の設計 |
| [semantics.yaml](../src/md_merge/semantics.yaml) | クラス × 出力形式の lowering 規則（セマンティック記法の正典） |
