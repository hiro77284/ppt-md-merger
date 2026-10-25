# 記法一覧（出力形式別の変換）

同じ原稿を PDF（Typst / LaTeX）・HTML・GFM（puremd）に出したときの変換先の一覧です。正典は `src/md_merge/semantics.yaml`、設計の背景は `docs/design_semantic_lowering.md` にあります。

## ブロック

| 記法 | 意味 | Typst | LaTeX | HTML | GFM |
|---|---|---|---|---|---|
| `::: {.note}` | 補足 | `#sem-box("note")` | `notebox` | div＋CSS | `> [!NOTE]` |
| `::: {.warning}` | 注意 | `#sem-box("warning")` | `warningbox` | div＋CSS | `> [!WARNING]` |
| `::: {.leadline}` | 擬似見出し | `#sem-box("leadline")` | `leadlinebox` | div＋CSS | `> [!IMPORTANT]` |
| `::: {.widequote}` | 幅広引用 | `#sem-box("widequote")` | `widequotebox` | div＋CSS | 素の引用 |
| `::: {.largefontblock}` | 大きい文字 | `#semlargefontblock` | 専用環境 | div＋CSS | ラベル付き引用 |
| `::: {.blockindent}` | 字下げ | `#semblockindent` | 専用環境 | margin-left | ラベル付き引用 |
| `::: {.keep-together}` | 分割しない | `#semkeeptogether` | minipage | break-inside | 囲みを外す |
| `::: {.center}` | 中央寄せ | `#semcenter` | center 環境 | text-align | 囲みを外す |

## インライン

| 記法 | 意味 | Typst | LaTeX | HTML | GFM |
|---|---|---|---|---|---|
| `[x]{.term}` | 用語 | `#semterm` | `\semterm` | span＋CSS | `**x**` |
| `[x]{.keyword}` | キーワード | `#semkeyword` | `\semkeyword` | span＋CSS | `**x**` |
| `[x]{.path}` | パス | `#sempath` | `\sempath` | `<code>` | `` `x` `` |
| `[x]{.kbd}` | キー入力 | `#semkbd` | `\semkbd` | `<kbd>` | `<kbd>` |
| `[x]{.emph}` | 強調 | `#emph` | `\emph` | span | `*x*` |
| `[x]{.rightlabel}` | 右寄せ | `#semrightlabel` | `\semrightlabel` | float:right | 素通し |

## リーフ

| 記法 | 意味 | Typst | LaTeX | HTML | GFM |
|---|---|---|---|---|---|
| `{{vspace:N}}` | 行空け | `#v(N * 1.65em)` | `\vspace{N\baselineskip}` | div.vspace | 破棄 |
| `{{pagebreak}}` | 改ページ | `#pagebreak(weak: true)` | `\newpage` | div.pagebreak | `---` |
| `{{vfill}}` | 残りを埋める | `#v(1fr)` | `\vspace*{\fill}` | div.vfill | 破棄 |
| `{{br}}` | 見出し内改行 | `#linebreak()` | `\hdbreak` | `<br>` | 破棄 |

## 見た目を変えたいとき

PDF（Typst）での見た目は `src/md_merge/templates/semantic_macros.typ` の関数が決めています（色・余白・文字の大きさ）。原稿を書き換えずに見た目だけを変えたいときは、このファイルを複製して手を入れ、レシピの `pandoc.typstdefaults` で `include-in-header` を差し替えます。
