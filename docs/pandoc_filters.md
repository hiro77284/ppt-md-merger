# pandoc filters（ビルトイン Lua filter）仕様

`pptmdmerge` に同梱されるビルトイン Lua filter（`src/md_merge/filters/`）の一覧と、それぞれが処理する入力マークアップ（fenced div クラス・属性など）をまとめる。

filter は `pandoc` サブコマンドのレシピキー `pandoc.filters` で指定する（解決順や指定方法は [spec/output_formats.md](spec/output_formats.md) の pandoc セクションを参照）。

```yaml
pandoc:
  filters:
    - divboxes.lua        # ビルトイン filter（ファイル名のみで指定可）
    - keep-together.lua
    - pandoc/my_filter.lua  # カスタム filter（YAML 基準の相対パス）
```

---

## fenced div クラス一覧

`::: {.CLASS ...}` 形式の fenced div を処理する filter とクラスの対応。特記なき場合、ラップ処理は出力形式が **LaTeX のときのみ** 適用され、それ以外の形式では素通しする。

| クラス | filter | 処理内容 |
|---|---|---|
| `leadline` | `divboxes.lua` | `leadlinebox` 環境でラップ（擬似見出し用、既定は枠なし） |
| `note` | `divboxes.lua` | `notebox` 環境でラップ（補足情報、薄い囲み） |
| `warning` | `divboxes.lua` | `warningbox` 環境でラップ（注意喚起、強い囲み） |
| `widequote` | `divboxes.lua` | `widequotebox` 環境でラップ |
| `largefontblock` | `largefontblock.lua` | `largefontblock` 環境でラップ |
| `blockindent` | `blockindent.lua` | `blockindent` 環境でラップ |
| `keep-together` | `keep-together.lua` | 直前に `\Needspace{...}` を挿入し、クラスを除去（改ページ抑制） |

> これらの fenced div は LaTeX/PDF 出力では上表の Lua filter が処理する。一方 `puremd` サブコマンドは、pandoc を通さずにこれらの fenced div を素の Markdown（GitHub 風アラート `> [!NOTE]` / ラベル付き引用 `> **CLASS**`）へ変換する。詳細は [spec/output_formats.md の「fenced div の変換」](spec/output_formats.md#fenced-div-の変換) を参照。

### 使用例

```markdown
::: {.leadline left=6mm}
ここは独立行で強く伝えたいポイントです。
:::

::: {.note}
ここは補足説明です。
:::

::: {.warning}
ここは注意書きです。読み飛ばされると困る内容を置く。
:::

::: {.keep-together lines=14}
このブロックは 14 行分のスペースが確保できないとき改ページする。
:::

細い枠
::: {.widequote frame=true}
テキスト
:::

背景色＋細い枠
::: {.widequote frame=true colback=yellow!15}
テキスト
:::

背景色のみ・枠を見せない
枠色を背景色と同じにして罫線を0にします：
::: {.widequote frame=true colback=yellow!15 colframe=yellow!15 boxrule=0pt}
テキスト
:::

背景色つきの中央寄せ：widequoteとcenterを併用する
::: {.widequote frame=true colback=blue!8}
::: {.center}
中央寄せしたいテキスト
:::
:::

幅を狭めたボックス　linewidthは文字領域の幅
:::{.widequote width="0.82\linewidth" frame=true center=true}
幅を狭めたボックス
:::

fontsizeを指定する方法は？

fontsize 属性で指定します（値は LaTeX のフォントサイズ命令）。box 系（note / warning / leadline / widequote）で使えます。内部的には kind/font={値} → fontupper=値 として box の本文に適用されます。

相対サイズ（簡単・推奨）
::: {.widequote fontsize="\large"}
テキスト
:::

使える命令（小→大）：
\tiny \scriptsize \footnotesize \small \normalsize \large \Large \LARGE \huge \Huge

絶対サイズ（pt 指定）
::: {.widequote fontsize="\fontsize{14pt}{17pt}\selectfont"}
テキスト
:::
- 第1引数＝文字サイズ、第2引数＝行送り（目安は文字サイズの約1.2倍。14pt なら 17pt 前後）。

注意点

- 値はクォートで囲む：\ を含むので fontsize="\large" のように必ず "..." で。素で書くとパンドックの属性解析で崩れます。
- 対象は box 系のみ：note / warning / leadline / widequote。largefontblock（＝\Large 固定）・blockindent・center は tcolorbox ではないので fontsize は効きません。
- leadline は太字ゴシックが前置されます（leadline/font が \gtfamily\sffamily\bfseries を付ける）。なので ::: {.leadline fontsize="\LARGE"} はゴシック太字＋特大になります。

背景色や余白と併用する例：
::: {.widequote frame=true colback=blue!8 fontsize="\large" left=6mm}
やや大きめ・淡い青背景・左6mm余白の引用ボックス
:::

```

---

## divboxes.lua の属性

`leadline` / `note` / `warning` / `widequote` の各クラスでは、div 属性を tcolorbox オプションに変換して付与できる。指定できる属性は以下に限定される（`allowed` リスト）。属性は固定順で処理される。

| 属性 | 変換先 / 意味 |
|---|---|
| `frame` | `true`/`yes`/`1` で `<kind>/frame` スタイル、`false`/`no`/`0` で `<kind>/noframe`（既定） |
| `fontsize` | `<kind>/font={...}`（`leadline/font` など） |
| `stretch` | `<kind>/stretch={...}` |
| `before_skip` | `before skip={...}` |
| `after_skip` | `after skip={...}` |
| `left` / `right` / `top` / `bottom` | 同名の tcolorbox オプション `key={value}` |
| `colback` / `colframe` | 背景色 / 枠色 `key={value}` |
| `boxrule` | 枠線太さ `boxrule={value}` |
| `width` | 幅 `width={value}` |
| `center` | `true`/`yes`/`1` のとき `center` オプションを付与 |

- `<kind>` はクラス名（`leadline` / `note` / `warning` / `widequote`）。
- 真偽値は `true`/`yes`/`1` と `false`/`no`/`0` を受け付ける。
- `allowed` にない属性（`style` など）は無視される。

---

## fenced div 以外の処理

### include コードブロック（`include-files.lua` / `include-files-resource-path.lua`）

fenced div ではなく、**フェンスドコードブロック** `` ```{.include} `` を処理して別 MD ファイルを取り込む（transclude）。

````markdown
```{.include}
path/to/file.md
```
````

- `include-files-resource-path.lua` は `resource-path` 対応版。
- metadata で挙動を制御する（`include-base` / `include-resource-paths` / `include-auto` / `include-debug`）。
- 由来: Albert Krewinkel 氏の `include-files.lua`（MIT）。

> 注: `md_merge` 本体の MD 結合は `!include path/to/file.md` 記法（merge サブコマンド）で行う。こちらは pandoc 変換時の取り込みで別系統。

### unnumbered 見出し / dump-sections.lua

`dump-sections.lua` は **見出し（Header）** を走査して章・節・項の番号付き一覧を stderr に JSON / TSV で出力する（本文は変更しない）。

- 分類: level1 + id `chap:*` → chapter、level2 + id `sec:*` → section / `ans:*` → answer、level3 + id `subsec:*` → subsection。
- 除外: `.unnumbered` クラスの見出し、id `#toc` / `#table-of-contents`、タイトルが「目次」/「Table of Contents」。

### back-to-top.lua

出力が **HTML のときのみ**、ページ先頭アンカー `<span id="top">` を挿入し、level2 見出し（`##`）の直後に「↑ top」リンク（`<p class="back-to-top">`）を付与する。

---

## コードブロックの書き方

原稿中のコード（シェルコマンド・設定ファイル等）は、pandoc / GFM 標準のフェンスドコードブロックをそのまま使う。`note` などの fenced div と違い、コードブロック用のセマンティッククラスは `semantics.yaml` に定義していないため、独自記法は不要（全出力形式で pandoc ネイティブのまま通る）。

`````markdown
```bash
pptmdmerge merge recipe.yaml
```
`````

### 言語名とシンタックスハイライト

- 言語名は pandoc（skylighting）の名前をそのまま指定する（`bash` / `sh` / `console` / `powershell` / `yaml` / `python` など）。
- ハイライトのスタイルはレシピキー `pandoc.syntax-highlighting`（例 `tango`）で指定し、`--syntax-highlighting` に渡る。詳細は [spec/output_formats.md](spec/output_formats.md) の pandoc セクションを参照。
- LaTeX 出力では、ハイライト用マクロ（`Shaded` / `Highlighting` / `\KeywordTok` 等）の定義はテンプレート側が担う。同梱テンプレートは `report_template.tex` が pandoc 3.x のパーシャル `$common.latex()$` 経由、`book_template.tex` が `$highlighting-macros$` の直接展開で対応済み。自作テンプレートを使う場合はどちらかを備えること（無いと未定義マクロで LaTeX が失敗する）。
- HTML / GFM（`puremd`・`transfer`）出力ではコードブロックのまま素通しする。

### 予約済みの info string

| info string | 意味 |
|---|---|
| ` ```{.include} ` | 別 MD の取り込み（前述の include コードブロック）。コード例として書くと展開されてしまう |
| ` ```{=latex} ` / ` ```{=html} ` | raw passthrough（`semantics.yaml` の `raw:`）。非対象形式では警告して破棄し、`puremd` では `=latex` を破棄する |

これら以外の info string（`bash` 等）は filter の対象外で、そのまま出力形式へ渡る。

### コードブロック内でもマーカーは置換される

`merge` / `render` はコードフェンスを認識しない（行単位・正規表現での処理）。そのためコードブロックの内側に書いても、次の記法は通常どおり処理される。

- `{{v:NAME}}` / `{{num:...}}` / `{{label:...}}` / `{{#id:...}}` などのマーカー → `render` が置換する
- 行頭の `!include path/to/file.md` → `merge` が展開する

コマンド例としてこれらの記法をリテラルに見せたい場合は、記述を避けるか別の表記に置き換える。

### 長いコードブロックの改ページ抑制

コードブロックがページ境界で分断されるのを避けたい場合は、`keep-together` の fenced div で囲む（挙動は前述の「fenced div クラス一覧」を参照）。

`````markdown
::: {.keep-together}
```bash
pptmdmerge ppt_to_pdf recipe.yaml
```
:::
`````

### インラインのコード・パス

インラインは素の `` `foo` `` でもよいが、セマンティック記述に寄せる場合はインラインクラス `path` を使う（`[recipe.yaml]{.path}` → LaTeX `\sempath` / HTML `<code>` / GFM バッククォート）。キー入力は `kbd`（`[Ctrl+C]{.kbd}`）。

---

## filter 一覧（早見表）

| filter | 主な対象 | 役割 | 主な出力形式 |
|---|---|---|---|
| `divboxes.lua` | fenced div（`leadline`/`note`/`warning`/`widequote`） | tcolorbox 環境でラップ | LaTeX |
| `largefontblock.lua` | fenced div（`largefontblock`） | `largefontblock` 環境でラップ | LaTeX |
| `blockindent.lua` | fenced div（`blockindent`） | `blockindent` 環境でラップ | LaTeX |
| `keep-together.lua` | fenced div（`keep-together`） | `\Needspace{...}` 挿入で改ページ抑制 | LaTeX |
| `include-files.lua` | code block（`include`） | 別 MD を取り込み | 全形式 |
| `include-files-resource-path.lua` | code block（`include`） | 別 MD を取り込み（resource-path 対応） | 全形式 |
| `dump-sections.lua` | Header | 章節項一覧を stderr へ出力 | 全形式（本文不変） |
| `back-to-top.lua` | Header（level2） | 先頭アンカー + 戻るリンク挿入 | HTML |
