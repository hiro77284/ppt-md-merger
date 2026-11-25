# samples 小テーマ別ケース案

作成: 2026-11-24 / 元資料: pptmdmerge-dev `docs/notation_reference.md`（main, 75e72bb）

- 番号は大分類ごとに 100 刻み。**100 番台 = 「とりあえずこれを見ておけば間に合う超基本」**、200 番台以降 = テーマ別の詳しい話。
- slug は仮。「既存」= samples に既にあるケース。「移植元」= 本体 examples に近い内容があるもの。

## 100 番台: 超基本

| slug | 内容（1行） | 扱う記法・機能 | 状況 |
|---|---|---|---|
| 100-slide-md | スライドの図＋ノートの MD を切り出して 1 本の MD にする | `NOTE_CONTENT_FORMAT`, `===BLOCK===`, `{{BLOCK:IMAGE}}`, `{{BLOCK:MD}}`, `export-note`, `export-image-mode: named_shape`, `export-image-target`, `export-image` | **既存** |
| 101-special-variable | スライド番号でファイル名を自動化し export 指示をコピペで済ませる | `<__BASEFILENAME__>`, `<__SLIDENUM__>`, `<__FILENAME__>` | **既存** |
| 102-pdf | 切り出した MD を PDF にする | `ppt_to_pdf` / `ppt_build --pdf`, レシピ `pandoc` | 新規（移植元: pdf1_minimum） |
| 103-pdf-cover-toc | PDF に表紙と目次を付ける | `cover-md`, `COVER_*` 変数（`COVER_TITLE` / `COVER_IMAGE` 等）, `defaults`（目次の深さ） | 新規（移植元: pdf1_minimum） |
| 104-chapter-section-number | 章・節に番号を振り、本文から番号付きで参照する | `{{#id:chapter/section:PART:LOCAL}}`, `{{num:}}`, `{{label:}}`, スライドの `#CHAPT#` / `#SECTION#` | 新規（移植元: pm2_simple_numbering, pm3_chapter_marker_numbering） |
| 105-merge-pptx | 複数の pptx を 1 本に結合する | `procedure` の `insertpptx`, `ppt_to_pptx` 相当 | 新規（移植元: pm1_simple_ppt_merge） |
| 106-pdf-pptx-sync | 同じソースから結合 pptx と PDF を一度に作る（番号もそろう） | `ppt_build --pdf ...`（1 回の render から複数出力） | 新規 |

## 200 番台: ノート → 画像・MD 切り出しの詳細

| slug | 内容 | 扱う記法 | 状況 |
|---|---|---|---|
| 201-multistep-animation | アニメーションの途中ステップを画像化 | `export-image-step`, `<__STEP__>`, `<!-- #steps -->`…`<!-- /steps -->` | **既存（ルート直下 pptx-multistep-animation・未移行）** |
| 202-image-mode | 切り出しモード 3 種の違いと余白調整 | `export-image-mode: slide / slide_with_rectpct`, `export-image-inset` | 新規 |
| 203-crop-filename | ファイル名だけで画像の切り出し範囲を指定 | `fig__L_T_R_B.png` | 新規 |
| 204-title-placeholder | スライドタイトルを MD 見出しに流用し、置換を止めたい所だけ止める | `<__TITLE__>`, `#NOREPLACE#`, `{{noref:begin}}`…`{{noref:end}}` | 新規（移植元: pm11_title_filename） |
| 205-yaml-block | ノートに図版定義 YAML を書いて書き出す | `{{BLOCK:YAML}}`, ノート内 `_include` / `_constants` | 新規 |

## 300 番台: 採番・相互参照の詳細

| slug | 内容 | 扱う記法 | 状況 |
|---|---|---|---|
| 301-ref-kinds | 参照の種類の違い（番号・タイトル・ラベル・原文タイトル） | `{{num:}}`, `{{title:}}`, `{{label:}}`, `{{rawtitle:}}` | 新規 |
| 302-number-control | 番号を飛ばす・振り直す・振らない | `<!-- md_merge {{chapter:VALUE}} -->`, `{{nolabel}}`, `{{nonum}}`, `{{noref}}`, `{.unnumbered}` | 新規 |
| 303-figure-number | 図番号を振って本文で「図 3」と参照 | `{{#id:image:...}}`, `{{num:}}` | 新規 |
| 304-sectionlist | 章とびらに節一覧を自動展開 | `{{sectionlist}}`, `{{sectionlist:chapter:PART:LOCAL}}` | 新規 |
| 305-slide-title-number | スライドタイトルに番号・ラベルを付ける（ID を定義しない） | `{{enclosenum:}}`, `{{titlelabel:}}` | 新規 |
| 306-pptx-numbering-detail | pptx 側の章・節番号の細かい制御 | `#SUBSECTION#`, `#STAY#`, `#NONUMBERING#`, `indexer.chapter_marker` 等での名前変更 | 新規（移植元: pm3_chapter_marker_numbering） |

## 400 番台: 変数・条件分岐・定数

| slug | 内容 | 扱う記法 | 状況 |
|---|---|---|---|
| 401-vars | 製品名などを変数化し、MD・ノート・スライド・表紙で一括置換 | `{{v:NAME}}`, `--var` | 新規（移植元: pm4_variable_replacement） |
| 402-two-editions | 1 つの原稿から社内版／社外版を出し分け | `{{#if:NAME}}`, `{{#if:NAME=VALUE}}`, `{{#if:!NAME}}`, `{{#else:}}`, `{{#endif:}}`, ネスト, `--var` | 新規 |
| 403-constants | 日付や共通値を TOML 定数・YAML 部品で共有 | `_constants`, `__DATE__` / `__TIME__` / `__DATETIME__`, `__NAME__`, `_include` | 新規 |
| 404-cover-template | 表紙 MD に変数と条件を入れ、版ごとに表紙を変える | テンプレ内 `{{v:}}`, `{{#if:}}`（未定義は偽扱い） | 新規 |

## 500 番台: MD の結合・ページ構成

| slug | 内容 | 扱う記法 | 状況 |
|---|---|---|---|
| 501-include-range | 多数の MD を連番で取り込み、1 ページずつ組む | `!include`, `name[1-7].md`（insertmd / insertmdpages） | 新規 |
| 502-page-layout | 改ページ・行空け・下寄せ・見出し内改行 | `{{pagebreak}}`, `{{vspace:N}}`, `{{vspace:5mm}}`, `{{vfill}}`, `{{br}}` | 新規 |

## 600 番台: セマンティック記法（PDF / HTML / GitHub MD の見え方比較）

| slug | 内容 | 扱う記法 | 状況 |
|---|---|---|---|
| 601-boxes | 補足・注意・リード行・幅広引用ボックス | `.note`, `.warning`, `.leadline`, `.widequote`, box 属性（`frame` / `colback` 等） | 新規（移植元: semantic_notation_guide） |
| 602-indent-largefont | 字下げ量の指定と大きい文字ブロックの入れ子 | `.blockindent`（`indent=`）, `.largefontblock` | 新規（同上） |
| 603-keep-center | 改ページさせない塊、中央寄せ | `.keep-together`, `.center` | 新規（同上） |
| 604-inline | 用語・キーワード・パス・キー入力・右寄せラベル | `.term`, `.keyword`, `.path`, `.kbd`, `.emph`, `.rightlabel` | 新規（同上） |
| 605-raw-passthrough | Typst / HTML の生コードを直接書く | ` ```{=typst} `, ` ```{=html} ` | 新規 |
| 606-code-image-pitfalls | コードブロック・画像幅と、ハマりどころ | ` ```bash `, `{ width= }`, 非対応の画像記法, コードフェンス内でもマーカーが展開される件 | 新規（注意喚起型） |

## 700 番台: pptx 結合の詳細

| slug | 内容 | 扱う記法・機能 | 状況 |
|---|---|---|---|
| 701-delete-markers | 作業メモや不要スライドを結合時に消す | `#CSL#`, `#CSP#`, `#TEMP#`, `#MEMO#` | 新規（移植元: pm8_delete_csp, pm9_delete_csl, pm10_memo_temp） |
| 702-chapter-cover | 章の区切りに章とびらスライドを差し込む | レシピ機能（chapter cover 挿入） | 新規（移植元: pm5_chapter_cover_insertion） |
| 703-stylebase | 体裁の違う pptx を共通のスタイルにそろえて結合 | レシピ機能（stylebase） | 新規（移植元: pm6_stylebase） |
| 704-splitted-insertion | pptx の一部のスライドだけを差し込む | レシピ機能（分割挿入） | 新規（移植元: pm7_splitted_insertion） |

## 対象外にしたもの

- `<!-- md_merge_rawtitle: -->` / `<!-- source: -->`：自動生成なので単独ケースにしない（104 / 501 の解説で触れる）
- `{{BLOCK:MD:SHORT}}` / `{{BLOCK:HTML}}` / `{{BLOCK:EXPORT}}` / `{{BLOCK:PLAIN}}`：現状ほぼ未使用
- ` ```{.include} `：予約済みのみ
- `hero:` / `notecom_cover:` frontmatter 画像キー：用途が限定的（必要なら 200 番台に追加）
