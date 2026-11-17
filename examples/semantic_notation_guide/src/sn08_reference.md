# 記法一覧（出力形式別の変換）

同じ原稿を PDF（Typst）・HTML・GFM（puremd）に出したときの変換先の一覧です。正典は `src/md_merge/semantics.yaml`、設計の背景は `docs/design_semantic_lowering.md` にあります。

## ブロック

| 記法 | 意味 | Typst | HTML | GFM |
|---|---|---|---|---|
| `::: {.note}` | 補足 | `#sem-box("note")` | div＋CSS | `> [!NOTE]` |
| `::: {.warning}` | 注意 | `#sem-box("warning")` | div＋CSS | `> [!WARNING]` |
| `::: {.leadline}` | 擬似見出し | `#sem-box("leadline")` | div＋CSS | `> [!IMPORTANT]` |
| `::: {.widequote}` | 幅広引用 | `#sem-box("widequote")` | div＋CSS | 素の引用 |
| `::: {.largefontblock}` | 大きい文字 | `#semlargefontblock` | div＋CSS | ラベル付き引用 |
| `::: {.blockindent}` | 字下げ | `#semblockindent` | margin-left | ラベル付き引用 |
| `::: {.keep-together}` | 分割しない | `#semkeeptogether` | break-inside | 囲みを外す |
| `::: {.center}` | 中央寄せ | `#semcenter` | text-align | 囲みを外す |

## インライン

| 記法 | 意味 | Typst | HTML | GFM |
|---|---|---|---|---|
| `[x]{.term}` | 用語 | `#semterm` | span＋CSS | `**x**` |
| `[x]{.keyword}` | キーワード | `#semkeyword` | span＋CSS | `**x**` |
| `[x]{.path}` | パス | `#sempath` | `<code>` | `` `x` `` |
| `[x]{.kbd}` | キー入力 | `#semkbd` | `<kbd>` | `<kbd>` |
| `[x]{.emph}` | 強調 | `#emph` | span | `*x*` |
| `[x]{.rightlabel}` | 右寄せ | `#semrightlabel` | float:right | 素通し |

## リーフ

| 記法 | 意味 | Typst | HTML | GFM |
|---|---|---|---|---|
| `{{vspace:N}}` | 行空け | `#v(N * 1.65em)` | div.vspace | 破棄 |
| `{{pagebreak}}` | 改ページ | `#pagebreak(weak: true)` | div.pagebreak | 破棄 |
| `{{vfill}}` | 残りを埋める | `#v(1fr)` | div.vfill | 破棄 |
| `{{br}}` | 見出し内改行 | `#linebreak()` | `<br>` | 破棄 |

## 見た目を変えたいとき

PDF（Typst）での見た目は `src/md_merge/templates/semantic_macros.typ` の関数が決めています（色・余白・文字の大きさ）。原稿を書き換えずに見た目だけを変えたいときは、このファイルを複製して手を入れ、レシピの `pandoc.defaults`（version 3 以前は `typstdefaults`）に渡す defaults ファイルで `include-in-header` を差し替えます。
