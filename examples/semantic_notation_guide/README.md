# セマンティック記法 用例集（PDF 編）

原稿 MD に書けるセマンティック記法（ブロック・囲みの属性・インライン・リーフ・procedure 挿入・escape hatch）を一つずつ取り上げ、「書き方」と「PDF（Typst）での表示結果」を並べた用例集。pptx は使わず、MD 原稿だけを結合して PDF にする例も兼ねる。

## ビルド

```bash
cd examples/semantic_notation_guide
pptmdmerge crop_to_pdf semantic_notation_recipe.yaml --force
```

出力: `build/semantic_notation_guide.pdf`（と同名の `.typ`）。typst 0.15.1・pandoc 3.9 が PATH 上に必要。

## 構成

| ファイル | 内容 |
|---|---|
| `semantic_notation_recipe.yaml` | レシピ（version 2、`engine: typst`、同梱の標準表紙） |
| `COVER_VARS.yaml` | 表紙用変数 |
| `src/sn01_intro.md` | はじめに（記法の 4 カテゴリ・読み方・ビルド方法） |
| `src/sn02_blocks.md` | ブロック記法（note / warning / leadline / widequote / largefontblock / blockindent / center / keep-together / 入れ子） |
| `src/sn03_box_attrs.md` | 囲みの属性（frame / colback / colframe / boxrule / width / center / 余白 / 前後の空き / fontsize / stretch） |
| `src/sn04_inlines.md` | インライン記法（term / keyword / path / kbd / emph / rightlabel / 組み合わせ） |
| `src/sn05_leaves.md` | リーフ記法（vspace / pagebreak / vfill / br） |
| `src/sn06_procedure*.md` | レシピの insertvspace / insertpagebreak / insertvfill（レシピ側で実演） |
| `src/sn07_raw.md` | escape hatch（`{=typst}` / `{=latex}` / 行内の生コード） |
| `src/sn08_reference.md` | 出力形式別（Typst / LaTeX / HTML / GFM）の変換一覧 |

記法の正典は [`src/md_merge/semantics.yaml`](../../src/md_merge/semantics.yaml)、索引は [`docs/notation_reference.md`](../../docs/notation_reference.md)。
