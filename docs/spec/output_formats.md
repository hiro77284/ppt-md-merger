# 出力変換仕様（pandoc / puremd / githubmd / 表紙 / transfer）

> [仕様書トップ](../md_merge_spec.md) — 共通オプション・入力/出力指定・ログ・JSON・dry-run の各仕様はトップを参照。

---

## pandoc

### 概要

`render` で生成したレンダー済み MD を pandoc に渡し、PDF（typst）・HTML・reveal.js を生成する。pandoc の設定はレシピ YAML の `pandoc` セクションと文書プロジェクト内の defaults ファイルで管理する。LaTeX（lualatex）の経路は 2026-11-15 に撤去した（[design_typst_migration.md](../design_typst_migration.md) Phase 7）。

### 使用例

```bash
pptmdmerge pandoc recipe.yaml
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--html` | HTML 出力モード。`output.htmlfilename` を使い `-t html` で pandoc を起動する | 任意 |
| `--reveal` | reveal.js 出力モード。`output.revealfilename` を使い `-t revealjs` で pandoc を起動する | 任意 |

### 出力ファイルとフォーマットの決定

| オプション | 出力ファイルキー | pandoc `-t` | defaults キー | 表紙 |
| ---------- | --------------- | ----------- | ------------- | ---- |
| なし（PDF） | `output.pdffilename`（同じ名前の `.typ` も残す） | `typst`（.typ を書き出し `typst compile`） | `pandoc.defaults`（version 3 以前は `typstdefaults`。省略時は同梱 `report_base_defaults.yaml`） | `pandoc.cover-md`（version 3 以前は `typst-cover-md`） |
| `--html`   | `output.htmlfilename` | `html`（固定） | `pandoc.htmldefaults` | `pandoc.htmlcover` |
| `--reveal` | `output.revealfilename` | `revealjs`（固定） | `pandoc.revealdefaults` | `pandoc.htmlcover` |

pandoc のキーはレシピの `version` で読み方が変わる。version 4 は PDF 用のキーを接頭辞なし、HTML 用を `html` 付きにそろえた（`docs/md_merge_spec.md` の 5.3）。

| 用途 | version 4 | version 3 以前 |
| ---- | --------- | -------------- |
| PDF の表紙 | `cover-md` | `typst-cover-md` |
| PDF の pandoc defaults | `defaults` | `typstdefaults` |
| HTML / reveal の表紙 | `htmlcover` | `htmlcover`（と `cover-md` の HTML 変換） |
| LaTeX 専用だったキー（`template` / `include-in-header` / `include-before-body` / `conditional-process-input` / `conditional-process-output` / `format` / `engine`） | エラー | 警告して使わない（`engine` に typst 以外を書くとエラー） |

version 3 以前の `cover-md` / `defaults` は LaTeX 用の意味なので PDF では読まない。version 4 への書き換えは `tools/convert_recipe_v4.py` でできる。

### レシピ YAML スキーマ（version 4）

```yaml
output:
  renderedfilename: rendered.md   # 入力（render の出力）
  pdffilename: doc.pdf            # PDF 出力ファイル名（オプションなし時）
  htmlfilename: doc.html          # HTML 出力ファイル名（--html 指定時）
  revealfilename: doc_reveal.html # reveal.js 出力ファイル名（--reveal 指定時）
  outputdir: out                  # 上記ファイルの基準ディレクトリ

pandoc:
  defaults: pandoc/defaults.yaml        # PDF 用 pandoc defaults（省略時は同梱 report_base_defaults.yaml。リスト可）
  cover-md: cover_standard.md           # PDF の表紙 Markdown（省略時は表紙なし）
  htmldefaults: pandoc/html_defaults.yaml    # --html 時に使用する defaults ファイル（省略可）
  htmlcover: standard_cover.html        # --html / --reveal 用 HTML 表紙テンプレ（省略可）。{{v:COVER_*}} を vars で置換し本文前に挿入
  revealdefaults: pandoc/reveal_defaults.yaml  # --reveal 時に使用する defaults ファイル（省略可）
  filters:                              # Lua filter リスト（省略可）
    - center.lua                        # ビルトイン filter（pptmdmerge 同梱）
    - pandoc/my_filter.lua              # カスタム filter（yaml 基準の相対パス）
  syntax-highlighting: tango          # --syntax-highlighting に渡すスタイル名またはテーマファイルパス（省略可）
  data-dir: pandoc/                   # --data-dir に渡すパス（省略可）
  resource-path: figures/             # 画像等のリソース検索パス（PDF。省略可。リスト・;区切り可）
  typst-root: ..                      # typst compile の --root（省略可）
```

PDF の pandoc テンプレートや、プリアンブルに読み込む `.typ`（`include-in-header`）は defaults ファイルの `template:` / `include-in-header:` に書く（レシピの `pandoc.template` / `pandoc.include-in-header` は LaTeX 用だったので廃止した）。

### パスの解決基準

| キー | 解決基準 |
| ---- | -------- |
| `defaults` / `htmldefaults` / `revealdefaults` | `data-dir` → workdir → **パッケージ同梱 `src/md_merge/templates/`（basename）** の順にフォールバック |
| `cover-md` | レシピ dir → workdir → 同梱 templates（basename）。旧名 `cover_standard_typst.md` はエラー（どの version でも。`cover_standard.md` を案内する） |
| `htmlcover` | `data-dir` → workdir → 同梱 templates（basename）。`{{v:COVER_*}}` を `vars` で置換した `cover-processed.html` を生成して本文前に挿入する |
| `filters`（version 3 以前は `metadata-file` も） | workdir（省略時は YAML の親ディレクトリ） |
| `resource-path` | レシピ YAML のあるディレクトリ（workdir の影響を受けない） |
| `data-dir` 自体 | workdir 基準で解決後、`..`・`.` を除去した正規パスで pandoc に渡す |

`data-dir` を指定すると、defaults 等の検索が `data-dir` 内から先に行われる。相対パスで指定したファイルが `data-dir` に存在しない場合は workdir にフォールバックする。

#### defaults の多層指定（リスト）

`defaults` / `htmldefaults` / `revealdefaults` は **単一ファイルまたはファイルのリスト**を指定できる。リスト指定時は各ファイルを記載順に `-d` として pandoc へ渡し、pandoc が後勝ちでマージする（スカラー・マップは後のファイルが優先、`filters` 等のリストは後のファイルが置換）。

用途は「変わらない共有基盤」と「文書ごとに変わる部分」の分離。`filters` / `include-in-header` / `toc` 等の基本挙動を共有ベースに集約し、`toc-depth`・`metadata` などを文書ごとの上書きファイルに切り出せる。

```yaml
pandoc:
  defaults:
    - report_base_defaults.yaml    # 同梱: filters / テンプレート / include-in-header / 目次
    - this_document.yaml            # 文書ごと: toc-depth など
```

`defaults` を書くと同梱の `report_base_defaults.yaml` は使われない（置き換わる）ので、同梱を土台に一部だけ変えるときは上のように先頭に書く。各ファイルの解決基準・basename フォールバックはリストの各要素にも同様に適用される。

同梱の土台は 2026-11-16 に `typst_semantic_engine.yaml` から `report_base_defaults.yaml` に改名した。旧名は受け付けない（どの version のレシピでも、`pandoc.defaults`／`typstdefaults` に旧名があると `pandoc`・`validate` がエラーにして新しい名前を案内する）。version 3 以前のレシピは `tools/convert_recipe_v4.py` が version 4 への変換と一緒に書き換える。

### Lua filter の解決順

各 filter エントリに対して以下の順で解決する。

| 順序 | 条件 | 動作 |
| ---- | ---- | ---- |
| 1 | 絶対パス | そのまま使用 |
| 2 | 相対パス → yaml 基準で存在する | カスタム filter として使用 |
| 3 | ファイル名 → `md_merge/filters/` に存在する | ビルトイン filter として使用 |
| — | いずれにも該当しない | エラー（終了コード 3） |

ビルトイン filter は `pptmdmerge` パッケージに同梱され、`src/md_merge/filters/` に配置する。各ビルトイン filter が処理する fenced div クラス・属性などの詳細は [pandoc_filters.md](../pandoc_filters.md) を参照。

#### pandoc defaults ファイル内の `filters` / `include-in-header` / `template` も同様に解決する

pandoc 自身は defaults ファイル内のこれらをパッケージ同梱ディレクトリにフォールバックできない（`filters` はスラッシュ付き＝CWD 相対・bare 名は `data-dir/filters/` のみ、`include-in-header`/`template` の bare 名も同梱を探さない）。そのため `pandoc` サブコマンドは **defaults ファイルの `filters` / `include-in-header` / `template` も上表の順序で解決**し（`include-in-header` / `template` は `data-dir` → workdir → 同梱 templates）、名前を解決済み絶対パスに置換した一時 defaults ファイルを生成して pandoc に渡す（実行後に削除）。

これにより defaults ファイルにも **bare 名（例 `center.lua` / `semantic_macros.typ`）で同梱の filter・header・template を書ける**。**文書シリーズごとにテンプレートを差し替えたい場合は、同名ファイルを `data-dir` または workdir 側に置けばそちらが優先される**（同梱正本を上書きする cascade）。解決できないエントリ（外部フィルタ、実在しないパス）と並び順はそのまま保持される。

### pandoc の呼び出し形式

PDF は後述「PDF（Typst）」の 2 段構成。HTML / reveal.js は次の形で呼ぶ。

```
pandoc <rendered.md> -o <htmlfilename|revealfilename> -t <html|revealjs>
      [-d <htmldefaults|revealdefaults>...] [-L <filter>...]
      [--syntax-highlighting=<style>]
      [--include-before-body <htmlcover を置換した cover-processed.html>]
```

#### YAML frontmatter の除去

render 済み MD に YAML frontmatter（`---` … `---`。`transfer` / `notecomexport` 用の `title` / `hero` 等）があれば、pandoc に渡す前に取り除く（PDF / `--html` / `--reveal` すべて）。merge 後の MD では frontmatter の直前に `<!-- source: -->` や `<!-- md_merge_rawtitle: -->` が来るため pandoc がメタデータとして読まず本文に出してしまい、2 ファイル目以降の frontmatter は文書の途中に来るためである。

* 対象は「文書の先頭」と「`<!-- source: ... -->` 行の直後」の `---` … `---` ブロック。開始 `---` の前の空行・1 行の HTML コメントは許容する
* 中身が YAML のマッピングとして読めるものだけを frontmatter とみなす（本文の水平線 `---` は消さない）
* ブロックは空行 1 行に置き換え、コメント行はそのまま残す
* 取り除いたときは info ログに件数を出し、本文は標準入力で pandoc に渡す（`pandoc -o ...` の形になる）。render 済み MD ファイル自体は書き換えない
* frontmatter の `title` 等は pandoc のメタデータにも入らない。PDF の文書タイトル等はレシピ `vars` の `COVER_*` か defaults の `metadata:` で与える（後述「PDF の文書プロパティ」）

#### 画像参照と属性の間の空白詰め

pandoc は画像の属性を `![](a.png){width=80%}` のように画像の直後（空白なし）にしか認めず、`![](a.png) {width=80%}` と空白があると `{width=80%}` が本文の文字列として出力される。このため pandoc に渡す前に、画像参照（`![alt](ref)`）と直後の `{...}` の間の空白・タブを取り除く（PDF / `--html` / `--reveal` すべて）。

* 改行を挟むものは結合しない
* コードフェンス（```` ``` ```` / `~~~`）内とインラインコード内は変えない
* 詰めたときは info ログに件数を出し、本文は標準入力で pandoc に渡す。render 済み MD ファイル自体は書き換えない

### PDF（Typst）

PDF は Typst で組む（2026-10-23 に既定にし、2026-11-15 に lualatex を撤去した。経緯は [design_typst_migration.md](../design_typst_migration.md)）。

**2 段構成:** pandoc で `.typ` を書き出し、続けて `typst compile` で PDF にする。`.typ` は消さずに残すので、typst のエラーはこのファイルの行番号で確認できる。

```
pandoc <rendered.md> -o <pdfstem>.typ -t typst
      [-d <defaults>...] [-L <filter>...] -L typst-images.lua
      [--syntax-highlighting=<style>]
      [--include-before-body <cover-md の .typ 断片>]
      --resource-path <.;resource-path...>
typst compile --root <root> <pdfstem>.typ <pdfstem>.pdf
```

| 項目 | 内容 |
| ---- | ---- |
| 出力 | `output.pdffilename` と、同じ名前の `.typ` |
| defaults | `pandoc.defaults`（version 3 以前は `typstdefaults`。単一またはリスト、後勝ち）。省略時は同梱の `report_base_defaults.yaml`（セマンティックフィルタ一式・テンプレート `report_template.typst`・`semantic_macros.typ`／`report_style.typ`・目次・`lang: ja`）。version 3 以前で `typstdefaults` が無く LaTeX 用の `defaults` だけあると、読まないことを警告する |
| ページ設計 | 同梱の `report_style.typ`: A4・余白 20mm/15mm、和文 BIZ UDGothic 10.5pt／欧文 Times New Roman・Arial、章は改ページして中央 28pt＋下線、節 14pt、項 12pt、右柱に節タイトル（章の開始ページ・目次 1 ページ目は柱なし）、中央下にノンブル（表紙の次から 1）、目次は「目次」20pt＋線。差し替えるときは defaults で `include-in-header` を自分のファイルにする |
| 表 | 同梱の `report_template.typst`: 罫線 0.5pt、セルは左揃え（表そのものは中央に配置）、見出し行（1 行目）は太字＋薄い灰色の背景。Markdown で列揃えを書いた列（`:---:` 中央 / `---:` 右）はその指定に従う。変えるときは `include-in-header` の自分のファイルで `#set table(stroke: ..., fill: ...)` / `#show table.cell: set align(...)` / `#show table.cell.where(y: 0): set text(...)` を上書きする |
| 表紙 | `pandoc.cover-md`（version 3 は `typst-cover-md`）を typst 断片（`<stem>_cover.typ`）に変換し、柱・ノンブルなしの 1 ページ目にする。**省略時は表紙なし**。同梱の標準表紙は `cover-md: cover_standard.md` と明示する（`COVER_IMAGE` / `COVER_TITLE` / `COVER_SUBTITLE` / `COVER_DATE` / `COVER_AUTHOR` / `COVER_AFFILIATION` / `COVER_CONTACT` / `COVER_NOTE` / `COVER_FOOTERIMAGE` を使い、空の項目は省く）。詳しくは後述「表紙（`cover-md` / `htmlcover`）」。version 2 以前のレシピでは、`typst-cover-md` が無く LaTeX 用の表紙（`cover-md` / `conditional-process-input`）だけあると同梱の標準表紙を暗黙に使い、明示するよう警告する（`docs/md_merge_spec.md` 5.3） |
| 文書プロパティ | PDF のタイトル・作成者・サブジェクトはレシピ `vars` の `COVER_TITLE` / `COVER_AUTHOR` / `COVER_SUBTITLE` を流用し、defaults の `metadata:` の `title` / `author` / `subject` で上書きできる。キーワード（`keywords`）と言語（`lang`）は `metadata:` だけ。作成日はビルドした日時。詳しくは後述「PDF の文書プロパティ」 |
| 画像 | 同梱フィルタ `typst-images.lua` が、画像を `resource-path` から探して `.typ` からの相対パスに書き換える（Typst には `\graphicspath` のような複数ディレクトリ探索がないため） |
| `--root` | `pandoc.typst-root`。省略時は `.typ` の場所・render 済み MD の場所・`resource-path` をすべて含む共通の上位ディレクトリ。ドライブが異なると決められないので、その場合は明示する |
| 必要なもの | `typst` が PATH 上にあること（0.15.1 で確認） |

セマンティック記法の Typst への変換は `semantics.yaml` の `typst:` 列で定義し、見た目は `semantic_macros.typ` の関数が決める。ブロックの属性は旧 LaTeX（tcolorbox）版と同じ名前・書き方を受け付け、Typst の値に読み替える（`width="0.6\linewidth"` → 60%、`colback=blue!8` → 青 8%＋白、`fontsize="\large"` → 1.2em など）。読み替えられない値は警告して無視する。`typst:` が無いクラスは中身だけが残る。

### 完了メッセージ

単体実行（`ppt_to_pdf` 経由ではない）で成功すると、標準出力に完了ブロックを出力する。完了行の直後にコマンド開始からの所要時間を表示する（60 秒未満は `12.3秒`、1 時間未満は `2分05.4秒`、それ以上は `1時間02分03秒`）。`--json` / `--dry-run` 時は出力しない。

```
========================================
  pandoc 完了
  所要時間: 12.3秒
========================================
```

### エラー条件

* 入力 YAML に `output.renderedfilename` / `output.pdffilename`（または対応する出力キー）も `output.targetbasefilename` も未定義
* レンダー済み MD が存在しない
* version 4 のレシピに廃止したキー（`typst-cover-md` / `typstdefaults` / `engine` / `template` / `include-in-header` / `include-before-body` / `conditional-process-*` / `format` / `metadata-file`）がある（終了コード 2）
* version 3 以前のレシピの `pandoc.engine` に typst 以外が書いてある（終了コード 2）
* defaults・表紙に指定したファイルが存在しない
* PDF 出力で `typst` が PATH 上に見つからない
* `pandoc` が PATH 上に見つからない
* pandoc が非ゼロ終了コードで終了した
* 出力先に既存ファイルがあり、`--force` 未指定

### 環境単位の設定

pandoc のテンプレート・フォント等の環境固有設定は pandoc 自身のデータディレクトリに置く。

| OS | デフォルトパス |
| -- | -------------- |
| Windows | `%APPDATA%\pandoc\` |
| Linux / macOS | `~/.local/share/pandoc/` |

### 文書単位の設定

defaults ファイル・メタデータ YAML・文書専用テンプレートはレシピ YAML と同じプロジェクト内に置くことを推奨する。

```text
my_document/
├── recipe.yaml
├── md/
├── pandoc/
│   ├── defaults.yaml     # toc-depth 等の上書き（report_base_defaults.yaml の後に重ねる）
│   ├── metadata.yaml     # メタデータ
│   └── cover.md          # 文書専用の表紙 Markdown（任意）
└── out/
```

---

## puremd

### 概要

レンダー済み MD ファイル（`output.renderedfilename`）から LaTeX の raw ブロック等を削除し、さらに pandoc の fenced div（`::: {.note}` 等）・インライン span・リーフ記法を GitHub Flavored Markdown（GFM）へ降格して、純粋な MD ファイル（`output.puremdfilename`）を生成する。出力は GFM（`::: {.note}`→`> [!NOTE]` 等）だが、`transfer`（Astro 等）・`notecomexport`・他の Markdown ビューアと共有する中間形式なので、画像の pandoc 属性（`![](a.png){ width=40% }`）はそのまま残す（Astro 側は属性記法で幅を効かせる）。GitHub はこの属性を解釈しないため、GitHub 向けの仕上げは [githubmd](#githubmd) で行う。

以前は `githubmd` が本サブコマンドの別名だったが、GitHub 専用の別サブコマンドになった（`when.command: [githubmd]` も puremd ではなく githubmd を指す）。

処理は次の 2 段で行う。

1. **strip**: 削除対象パターンにマッチした範囲を削除する。生 raw ブロック（` ```{=latex} `）の除去は `semantics.yaml` の `raw.gfm.drop` 由来の組み込みパターンとして**常に**適用され、`puremd.strip_config` を指定するとプロジェクト独自の追加パターンがそれに上乗せされる。
2. **fenced div 変換**: pandoc の fenced div を unwrap し、GitHub 風アラート（`> [!NOTE]`）またはラベル付き引用（`> **CLASS**`）に変換する。divbox 系の属性（`left` / `colback` / `frame` 等）は破棄するが、地の本文と区別できる形で残す（[fenced div の変換](#fenced-div-の変換) 参照）。

### 使用例

```bash
pptmdmerge puremd recipe.yaml
pptmdmerge puremd recipe.yaml --force --workdir /path/to/workdir
pptmdmerge puremd recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 |
|---|---|
| `--force` | 出力ファイルが既存でも上書きする |

### レシピ YAML キー

| キー | 型 | 説明 |
|---|---|---|
| `output.renderedfilename` | string | 入力となるレンダー済み MD のファイル名（必須） |
| `output.puremdfilename` | string | 出力 MD のファイル名（必須） |
| `puremd.strip_config` | string | プロジェクト独自の**追加** strip パターン設定ファイルのパス（任意）。生 raw ブロックの除去は組み込みのため不要 |
| `puremd.fenced_div.enabled` | bool | fenced div 変換の有効/無効（省略時 `true`） |
| `puremd.fenced_div.alerts` | map | クラス名 → GitHub アラート種別の対応（ビルトインに**追加・上書き**） |
| `puremd.fenced_div.plain_blockquote` | list | ラベルなしの素の blockquote にするクラス名（ビルトインに**追加**） |

#### 例

```yaml
output:
  outputdir: out
  renderedfilename: rendered.md
  puremdfilename: puremd.md
puremd:
  strip_config: puremd_strip.yaml   # 任意。独自の追加除去パターンを書くときのみ
  fenced_div:
    enabled: true                   # 省略時 true
    alerts:                         # ビルトイン {note: NOTE, warning: WARNING, leadline: IMPORTANT} に追加・上書き
      caution: CAUTION
      tip: TIP
    plain_blockquote:               # ビルトイン [widequote] に追加
      - epigraph
```

### strip 設定ファイル

`puremd.strip_config` で指定する YAML ファイル。`strip:` キーにパターンのリストを記述する。ここに書いたパターンは組み込みの raw ブロック除去（下記「組み込みの raw ブロック除去」）に**上乗せ**される。生 LaTeX raw ブロックの除去は組み込みなのでここに書く必要はなく、`lang: "{=latex}"` の `fenced_code` を書いた場合は冗長として警告のうえ無視される。

#### ファイル書式

```yaml
# puremd_strip.yaml
strip:
  # 生 LaTeX raw ブロックの除去は組み込み（semantics.yaml raw.gfm.drop）。
  # ここにはプロジェクト独自の追加除去パターンだけを書く。
  - name: my_inline_command                       # 識別名（任意）
    type: regex                                   # パターン種別
    pattern: '\\someCommand\{[^}]*\}'
    dotall: false      # 省略時 false（true で . が改行にもマッチ）
    ignorecase: false  # 省略時 false
```

#### パターン種別

| `type` | 説明 | 必須キー |
|---|---|---|
| `fenced_code` | ` ```{lang}...``` ` 形式のフェンス**コード**ブロック（fenced code block）全体を削除 | `lang` |
| `regex` | 任意の正規表現にマッチする部分を削除 | `pattern` |

> **非推奨エイリアス**: 旧称 `fenced_block` も当面受理するが、pandoc の fenced **div** と紛らわしいため `fenced_code` に改名した。`fenced_block` 使用時は警告を出す。

`fenced_code` の削除範囲: 開始フェンス行（` ```{lang} `）から終了フェンス行（` ``` `）まで（両端の行の改行を含む）。

`regex` はデフォルトで `re.MULTILINE` フラグ付きで適用される。`dotall: true` を加えると `re.DOTALL` も付与される。

#### 組み込みの raw ブロック除去

生 raw ブロックの除去は `semantics.yaml` の `raw.gfm.drop` で定義され、`puremd.strip_config` の有無に依らず**常に適用**される（GFM で無意味な形式のみ破棄。`html` 等は GFM がそのまま解釈するので残す）。既定では `latex` のみ破棄する。

| 破棄する形式（`raw.gfm.drop`） | 生成される除去パターン | 削除対象 |
|---|---|---|
| `latex` | `fenced_code` (`lang: "{=latex}"`) | Pandoc raw LaTeX ブロック（` ```{=latex} … ``` `） |

`strip_config` に `lang: "{=latex}"` の `fenced_code` を書いても組み込みと重複するため、警告のうえ無視される。

### fenced div の変換

pandoc の fenced div（`::: {.class ...}` … `:::`、または bare 形式 `::: class`）を素の Markdown に変換する。`puremd.fenced_div.enabled: false` で無効化できる（省略時は有効）。

変換規則（先頭クラスで判定）:

| 先頭クラス | 出力 |
|---|---|
| `alerts` マップに対応するクラス（既定: `note`→`NOTE`、`warning`→`WARNING`、`leadline`→`IMPORTANT`） | GitHub 風アラート `> [!TYPE]` + 内容（各行を `> ` で引用） |
| `plain_blockquote` に含まれるクラス（既定: `widequote`） | ラベルなしの素の blockquote（各行を `> ` で引用） |
| それ以外の名前付きクラス（`largefontblock` / `blockindent` / `keep-together` 等） | ラベル付き引用 `> **CLASS**`（大文字化）+ 空行 + 内容 |
| クラスを持たない div（`::: {#id}` のように属性のみ） | unwrap（フェンスを除去し内容のみ残す） |

判定順は **`alerts` → `plain_blockquote` → ラベル付き引用 → unwrap**。すなわち同じクラスが `alerts` と `plain_blockquote` の両方にある場合は `alerts` を優先する。

- divbox 系の属性（`left` / `right` / `colback` / `colframe` / `frame` / `fontsize` / `center` 等）はすべて破棄する。
- 内容の前後の空行はトリムする。
- ネストした fenced div はネストした引用（`> > ...`）として再帰的に変換する。
- 閉じられていない fenced div を検出した場合は警告を出し、残りを内容として扱う。
- `alerts` マップは `puremd.fenced_div.alerts` でビルトイン（`note` / `warning` / `leadline`）に追加・上書きできる。値は GitHub アラート種別（`NOTE` / `TIP` / `IMPORTANT` / `WARNING` / `CAUTION`）を想定し、大文字化して使用する。
- `plain_blockquote` リストは `puremd.fenced_div.plain_blockquote` でビルトイン（`widequote`）に追加できる。

変換例:

```markdown
::: {.note left=6mm colback=blue}
ここは補足説明です。
:::

::: {.leadline}
強く伝えたいポイント。
:::

::: {.widequote}
これは引用です。
:::

::: {.largefontblock}
大きい文字ブロック。
:::
```

↓

```markdown
> [!NOTE]
> ここは補足説明です。

> [!IMPORTANT]
> 強く伝えたいポイント。

> これは引用です。

> **LARGEFONTBLOCK**
>
> 大きい文字ブロック。
```

> 各 fenced div クラスを処理するビルトイン Lua filter（Typst / HTML 出力時）については [pandoc_filters.md](../pandoc_filters.md) を参照。`puremd` はこれらの fenced div を pandoc を通さずに素の Markdown へ変換する別系統の処理である。

### 処理手順

1. `output.renderedfilename` のファイルを読み込む
2. 設定ファイルまたはビルトインデフォルトから strip パターンをコンパイルする
3. パターンをリスト順に適用し、マッチした部分を削除する
4. `puremd.fenced_div.enabled` が有効なら fenced div を変換する
5. 結果を `output.puremdfilename` に書き込む（上書き不可の場合はエラー）

### エラー処理

| 条件 | 動作 | 終了コード |
|---|---|---|
| `output.renderedfilename` が未設定 | エラー終了 | 2 |
| `output.puremdfilename` が未設定 | エラー終了 | 2 |
| `puremd.strip_config` ファイルが見つからない | エラー終了 | 3 |
| 設定ファイルの書式エラー | エラー終了 | 2 |
| `puremd.fenced_div` / `puremd.fenced_div.alerts` がマッピングでない | エラー終了 | 2 |
| `puremd.fenced_div.plain_blockquote` がリストでない | エラー終了 | 2 |
| 正規表現が無効 | エラー終了 | 2 |
| 出力ファイルが既存で `--force` なし | エラー終了 | 1 |
| レンダー済み MD が見つからない | エラー終了 | 3 |

---

## githubmd

### 概要

puremd 処理済み MD（`output.puremdfilename`）を GitHub で表示するための MD（`output.githubmdfilename`）に変換する。puremd の出力は transfer / notecomexport と共有するため変えず、GitHub 専用の変換だけをこの段で行う。現在の変換は画像の属性のみ。

| 入力 | 出力 |
|---|---|
| `![図](a.png){ width=40% }` | `<img src="a.png" alt="図" width="40%">` |
| `![](a.png){width=300px height=200}` | `<img src="a.png" alt="" width="300" height="200">` |
| `[![](a.png){ width=40% }](https://example.com)` | `[<img src="a.png" alt="" width="40%">](https://example.com)` |
| `![](a.png){ width=8cm #fig:a .wide }` | `![](a.png)`（警告） |
| `![](a.png)` | 変更しない |

* HTML 属性に移すのは `width` / `height` のうち `%` か px（単位なしも px）の値だけ。
* それ以外の属性（`cm` / `in` 等の単位、`#id`、`.class`、その他の `key=value`）は GitHub で表現できない（`style` 属性も GitHub が除去する）ため、警告して捨てる。移せる属性が 1 つも無ければ `![alt](src)` に戻す。
* `alt` と `src` は HTML エスケープする。GitHub は画像のキャプションを表示しないので、キャプション文字列は `alt` になるだけで見た目は変わらない。
* コードフェンス内・インラインコード内・YAML frontmatter 内は変換しない。画像と属性の間の空白・タブは許容する。
* 画像のパスは書き換えず、画像のコピーもしない（puremd と同じ相対パスのまま）。`transfer --source githubmd`（または `ppt_to_githubmd --transfer`）で転送すると、`<img src>` の画像もコピーしてパスを書き換える。

### 使用例

```bash
pptmdmerge githubmd recipe.yaml
pptmdmerge githubmd recipe.yaml --force
pptmdmerge ppt_to_githubmd recipe.yaml   # pptx から一気通貫（パイプライン仕様を参照）
```

### 固有オプション

| オプション | 説明 |
|---|---|
| `--force` | 出力ファイルが既存でも上書きする |

### レシピ YAML キー

| キー | 型 | 説明 |
|---|---|---|
| `output.puremdfilename` | string | 入力となる puremd 処理済み MD のファイル名（必須。`targetbasefilename` から自動生成可） |
| `output.githubmdfilename` | string | 出力 MD のファイル名（必須。省略時は `targetbasefilename` から `{base}_github.md`） |

### エラー処理

| 条件 | 終了コード |
|---|---|
| `output.puremdfilename` / `output.githubmdfilename` が解決できない | 2 |
| puremd 処理済み MD が存在しない | 3 |
| 出力が既存で `--force` なし・書き込み失敗 | 1 |

---

## 表紙（`cover-md` / `htmlcover`）

> `condblockprocess` サブコマンド（条件ブロック付き `.tex` 表紙を展開して `include-before-body` に渡す）は LaTeX と一緒に撤去した（2026-11-15）。条件ブロックの記法そのもの（`{{#if:VAR}}` … `{{#endif:VAR}}`）は表紙 Markdown・ノート・insertmd などで引き続き使える（[conditional_block_process.md](../conditional_block_process.md)）。

### PDF の表紙（`pandoc.cover-md`）

表紙を Markdown で書き、`pandoc` サブコマンドが typst 断片に変換して本文前（目次より前）に置く。version 3 以前のレシピでは同じものを `typst-cover-md` に書く。

```yaml
pandoc:
  cover-md: cover_standard.md   # 表紙 Markdown（レシピ dir 基準 → workdir → 同梱 templates の basename フォールバック）
```

**処理**
1. `cover-md` を読み、`{{#if:NAME}}` … `{{#endif:NAME}}` を展開し（値が空のブロックを省く）、`{{v:NAME}}` をレシピ `vars` で置換する（未定義変数は空文字＝寛容）。
2. 表紙の画像参照（`![](...)`。`COVER_IMAGE` など変数で入れたものを含む）を、insertvar と同じくレシピのディレクトリ基準で解決する（レシピ dir → workdir → 表紙 MD のディレクトリの順に探す）。見つかり、`merge.copy-images` が有効（既定 true）なら `merge.image-dir` にコピーして参照を書き換える（下記「表紙の画像」）。
3. 置換後の中間 MD（`<stem>_cover_processed.md`）を PDF と同じ場所に書き出す。
4. セマンティック lua フィルタと `typst-images.lua` 付きで pandoc により typst 断片（`<stem>_cover.typ`）へ変換する。
5. 生成断片を `--include-before-body` で本文前に入れる。テンプレートが `#sem-cover[...]` で包み、柱・ノンブルなしの 1 ページ目にする。

**留意点**
- 表紙のページ体裁（文字の大きさ・空き）は表紙 Markdown 内に raw typst ブロック（```` ```{=typst} ````）で書く。同梱の `cover_standard.md` が書き方の例になる。
- 変換失敗時は pandoc ステップを失敗（終了コード 1）にする。

**表紙の画像**

表紙 MD は merge を通らないので、本文の画像のようには merge が `image-dir` に集めない。そこで pandoc ステップが表紙の画像も同じ場所に集める。

```yaml
vars:
  COVER_IMAGE: ../images/cover_image.png   # レシピ（src/recipe.yaml）からの相対
merge:
  image-dir: ../build/images               # 表紙の画像もここにコピーされる
```

- コピー先は `merge.image-dir`（結合済み MD の場所基準、既定 `images`）の直下（`flatten-images` に関係なくフラット）。命名は `merge.image-naming`、同名衝突は `merge.image-collision` に従う。衝突とみなすのは本文（render 済み MD）が参照する image-dir 内の別内容のファイルと同名になるときだけで、前回実行で置いた同名ファイルは上書きする。既に image-dir 内にある画像はコピーせずその場で参照する。
- レシピ基準で見つからない参照は書き換えない。従来どおり `pandoc.resource-path` から探す（同梱の `ppt_md_merger.png` を名前だけで書く例など、既存のレシピはそのまま動く）。
- `merge.copy-images: false`（`no-copy-images: true`）のときはコピーせず、従来どおり resource-path から探す。
- URL・絶対パス・data URI は対象外。

### PDF の文書プロパティ

PDF のプロパティ（タイトル・作成者など。PDF ビューアの「文書のプロパティ」に出るもの）は、表紙用のレシピ変数 `COVER_*` を流用して付ける。表紙に何を出すかは PDF を作る人が必ず決めるので、それを主な設定項目にする。表紙と違う値にしたいときは、PDF の defaults（`pandoc.defaults`。version 3 以前は `typstdefaults`）の `metadata:` に書くとそちらが優先する（version 3 以前のレシピの `pandoc.metadata-file` も読むが、defaults の `metadata:` に負ける）。表紙（`cover-md`）を付けないレシピでも、`COVER_*` を書けばプロパティは付く。

| プロパティ | `vars` | `metadata:` のキー |
|---|---|---|
| タイトル | `COVER_TITLE` | `title` |
| 作成者 | `COVER_AUTHOR` | `author`（リスト可） |
| サブジェクト | `COVER_SUBTITLE` | `subject` |
| キーワード | （なし） | `keywords`（リスト可） |
| 言語 | （なし） | `lang`（同梱の defaults は `ja`。`en` / `en-US` など） |
| 作成日 | （なし） | 常にビルドした日時（`COVER_DATE` は使わない） |

```yaml
# 上書き用の defaults（pandoc.defaults: [report_base_defaults.yaml, over.yaml] の over.yaml）
metadata:
  title: PDF のプロパティだけ別のタイトル
  keywords: [pptmdmerge, typst]
  lang: en
```

* 値は 1 行の文字列として使う（改行は空白に、Markdown の記法は解釈しない）。`metadata:` に空の値（`subject: ""`）を書くとそのプロパティは付けない
* `lang` は本文の言語（行分割・ハイフネーション・引用符）にも効く。言語コードでない値は警告して使わない
* 同梱テンプレート `report_template.typst` が `#set document(...)` / `#set text(lang: ...)` として出す（`src/md_merge/_pdf_metadata.py`）。自作のテンプレートでは変数 `sem-document` を出力すると同じ結果になる

### HTML / reveal.js の表紙（`pandoc.htmlcover`）

HTML の断片（例: 同梱の `standard_cover.html`）の `{{v:NAME}}` をレシピ `vars` で置換した `cover-processed.html` を本文前に入れる。version 4 の `cover-md` は PDF 専用で、HTML には変換しない（中身が typst の生コードなので HTML では崩れる）。version 3 以前のレシピでは、`cover-md`（LaTeX 用の Markdown 表紙）を書いてあると HTML 出力でもそれを変換して前置する。

---

## transfer

### 概要

render 済み MD を静的サイト生成システム（Astro 等）の DB 投入用ディレクトリに転送する。画像参照の扱いを段ごとに比較した棚卸しは [design_image_refs.md](../design_image_refs.md) を参照。MD 内のローカル画像参照（本文の `![alt](ref)`、[githubmd](#githubmd) が出力する `<img src="...">`、frontmatter の `hero:`）を書き換えて画像を所定のディレクトリへフラットコピーし、出力 MD のファイル名を `{slug}.md`（または `transfer.outputmd` 指定時はその名前）に変換する。

### 使用例

```bash
pptmdmerge transfer recipe.yaml
pptmdmerge transfer recipe.yaml --force
pptmdmerge transfer recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--source` `{puremd\|githubmd\|rendered\|merged}` | 転送対象の MD を選択する。`puremd`→`output.puremdfilename`、`githubmd`→`output.githubmdfilename`、`rendered`→`output.renderedfilename`、`merged`→`output.mdfilename`。指定時は `transfer.inputmd` より優先される | 任意 |

### レシピ YAML キー

```yaml
transfer:
  inputmd: one_blogpost_rendered.md    # 入力 MD ファイル名。省略時は output.renderedfilename を使用
  outputmd: README.md                  # 転送先の出力 MD 名。省略時は {slug}.md（主に README.md 用）
  dataentry_input: /dbworkdir/dataentry/input  # 出力先ディレクトリ（必須）
  slug: one_blogpost_slug              # 画像コピー先サブディレクトリ名 & 出力 MD の既定ベース名（必須）
  image_naming: preserve               # コピー画像の命名。preserve（既定・元名）/ sanitize（ASCII スラグ化）
```

### 処理ステップ

| ステップ | 内容 |
| ------ | ---- |
| slug 検証 | `^[a-z0-9][a-z0-9-]*[a-z0-9]$` に一致しない場合はエラー（終了コード 2） |
| 入力 MD 解決 | 優先順位は `--source` > `transfer.inputmd` > 既定（`output.renderedfilename`）。`--source` 指定時は対応する出力キー（`puremd`→`puremdfilename` / `rendered`→`renderedfilename` / `merged`→`mdfilename`）を `output.outputdir` 配下で解決する。`--source` 省略かつ `transfer.inputmd` 指定時は `{output.outputdir}/{inputmd}` として解決する。いずれも省略時は `output.renderedfilename` を使用する |
| dataentry_input 解決 | 絶対パスはそのまま使用、相対パスは `workdir` 基準で解決する。存在しない場合は自動作成する |
| MD 読み込み | 入力 MD をテキストとして読み込む |
| 画像参照書き換え | MD 内の `![alt](ref)` 形式のローカル相対パス参照と、YAML frontmatter の画像キー行（`hero:` / `notecom_cover:`）を `{slug}/{filename}` に書き換える。URL・絶対パス・data URI はスキップする |
| 画像コピー | 参照された画像を `{dataentry_input}/{slug}/` にフラットコピーする。コピー名は `transfer.image_naming` で決まる（`preserve`＝元名のまま／`sanitize`＝NFKC 正規化・小文字化して非 ASCII 連続を `-` に畳み、拡張子は小文字保持、空になれば `img`）。同一実行内で別のソース画像が同名になったときの扱いは `transfer.image_naming` とは独立に `transfer.image_collision` で決まる（`rename`＝既定・`_1`, `_2` の連番／`overwrite`＝警告して上書き）。前回実行の同名ファイルは衝突とみなさず上書きするので、再実行しても連番は増えない。定義は [spec/md_pipeline.md の「衝突」の定義](md_pipeline.md#衝突の定義) と共通 |
| MD 書き出し | 書き換え済みの MD を `{dataentry_input}/{outputmd}`（`transfer.outputmd` 省略時は `{slug}.md`）として出力する |

画像参照として認識される記法は `merge` と同じ（`![alt](ref)` ＋直後の pandoc 属性のみ）。title 付き・スペース入りパス・`<...>` 囲み・参照リンク形式・`<img>` タグは非対応で素通しする。詳細は [spec/md_pipeline.md の「非対応の記法」](md_pipeline.md#非対応の記法) を参照。

### エラー条件

| 条件 | 終了コード |
| ---- | ---------- |
| `transfer.slug` が未指定または不正パターン | 2 |
| `transfer.inputmd` が不正なファイル名 | 2 |
| `transfer.outputmd` が絶対パスまたは `..` を含む | 2 |
| `transfer.dataentry_input` が未指定または不正 | 2 |
| `transfer.image_naming` が `preserve` / `sanitize` 以外 | 2 |
| `transfer.inputmd` / `output.renderedfilename` のどちらも未指定 | 2 |
| `--source` 指定時に対応する出力キー（`puremdfilename` / `renderedfilename` / `mdfilename`）が未指定 | 2 |
| 入力 MD ファイルが存在しない | 3 |
| 入力 MD ファイルを読み込めない | 1 |
| 出力 MD が既に存在し `--force` 未指定 | 1 |
| ディレクトリ作成・書き込みに失敗 | 1 |
| 画像コピーに失敗（部分失敗を含む） | 1 |

---

## notecomexport

### 概要

puremd 処理済み MD（YAML frontmatter ＋ 素の GFM）を、note.com 投稿用の YAML（ブロック列）に変換する。note.com は Markdown の取り込みができずエディタをブロック単位で操作する必要があるため、`tools/notecom_autopilot.py`（Playwright）が読める形に落とす。

`transfer` が Astro 等の静的サイト向けに puremd MD を転送するのと対になる出力先で、**同じ puremd MD から note.com 用と Astro 用の両方を生成できる**（1 pptx → 2 投稿先）。

### 使用例

```bash
pptmdmerge notecomexport recipe.yaml
pptmdmerge notecomexport recipe.yaml --force --source puremd
pptmdmerge notecomexport recipe.yaml --dry-run
python tools/notecom_autopilot.py build/article_notecom.yaml --auth-state auth.json
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--source` `{puremd\|rendered\|merged}` | 変換対象の MD を選択する。`puremd`→`output.puremdfilename`（既定）、`rendered`→`output.renderedfilename`、`merged`→`output.mdfilename`。指定時は `notecomexport.inputmd` より優先される | 任意 |

### レシピ YAML キー

```yaml
output:
  notecomyamlfilename: article_notecom.yaml  # 省略時は {targetbasefilename}_notecom.yaml

notecomexport:
  inputmd: article_puremd.md      # 入力 MD。省略時は output.puremdfilename（output.outputdir 基準）
  hashtags: ["#図解", "#読解力"]   # note のハッシュタグ。省略時は frontmatter の tags から生成（# を前置）
  cover: images/cover.png         # カバー画像。省略時は frontmatter の notecom_cover → hero
  inline: plain                   # plain（既定）/ markdown。後述
  quote_labels: drop              # drop（既定）/ keep。後述
  link_base: https://ideacraft.jp # サイト内相対リンク（/blog/... 等）を絶対 URL にする基準。省略時は相対リンクをテキストに落とす
```

### 出力 YAML の形式

```yaml
meta:
  title: 記事タイトル          # frontmatter.title → <!-- md_merge_rawtitle --> → "無題"
  cover: images/cover.png     # notecomexport.cover → frontmatter.notecom_cover → frontmatter.hero（無ければ省略）
  hashtags: ['#a', '#b']      # notecomexport.hashtags → frontmatter.tags（無ければ省略）
  author: 著者                # frontmatter.author（任意）
  date: '2026-06-15'          # frontmatter.published_at / date の日付部分（任意）
  excerpt: 抜粋               # frontmatter.excerpt（任意）
blocks:
  - {type: paragraph, text: "..."}                 # 段落内の改行は \n で保持
  - {type: paragraph, text: "...", runs: [{text: "..."}, {text: "...", url: "https://..."}]}  # リンク入り（後述）
  - {type: heading1 | heading2, text: "..."}       # 大見出し（H1・H2）
  - {type: heading3, text: "..."}                  # 小見出し（H3 以下はすべて heading3）
  - {type: unordered_list | ordered_list, items: [...]}   # 項目は文字列、リンク入りは {text, runs}
  - {type: quote, lines: [...]}                            # 行も同様
  - {type: code, code: "...", lang: python}        # lang は任意
  - {type: image, path: images/x.png, caption: "...", link: "https://..."}  # link は任意（画像にリンク設定）
  - {type: horizontal_rule}
```

`author` / `date` / `excerpt` は autopilot では使わない（記録用）。

**リンク（`runs`）**: 段落・リスト項目・引用行にリンクがあると、`text` に加えて `runs`（テキストと URL の並び）を出す。autopilot は `runs` があればそれを使い、リンク部分のテキストを打った直後に選択して Ctrl+K で URL を設定する（本物のリンクになる）。`text` は `runs` の内容を 1 本にした読みやすさ用の表現で、リンクは `text（url）` の形になる。`runs` が無いブロックは従来どおり `text` をそのまま打つ。

note.com のカバー画像は 1280×670 に切り抜かれるため、自社サイト用の `hero` と同じ画像では構図が合わないことが多い。原稿の frontmatter に `notecom_cover:` を書くと note 専用のカバー画像を指定できる。原稿には `hero` と同じく**原稿 MD からの相対パス**で書き、`merge` が画像をコピーして `{merge.image-dir}/ファイル名` に、`transfer` がさらに `{slug}/ファイル名` に書き換える（frontmatter の画像キーはすべて同じ扱い。[design_image_refs.md](../design_image_refs.md) 参照）。自社サイト側は `notecom_cover` を読まないので、`{slug}/` に note 用の画像が 1 枚余分に入るだけで表示には影響しない。`notecom_cover` が無く `hero` に fallback したときは info ログで知らせる。

```yaml
---
title: 記事タイトル
hero: cs-thinking-trial/site_hero.png        # 自社サイト用
notecom_cover: cs-thinking-trial/note_cover.png  # note.com 用（任意）
---
```

### 変換規則

| 入力（puremd MD） | 出力ブロック | 備考 |
| ---- | ---- | ---- |
| `---` … `---` の YAML frontmatter | `meta` | 開始 `---` の前の空行・`<!-- -->` 行は許容（merge が `<!-- source: -->` を挿入するため） |
| `<!-- ... -->`（複数行可） | 除去 | コードフェンス内は残す |
| `# `〜`###### ` 見出し | `heading1`〜`heading3` | H4 以下は `heading3` に丸める。`<br>` は空白に |
| 段落 | `paragraph` | 空行区切り。連続行は `\n` で連結 |
| `- ` / `* ` / `1. ` リスト | `unordered_list` / `ordered_list` | 先頭空白付き（puremd 出力の ` - item`）も可。**ネストは平坦化**（警告） |
| `> ` 引用 | `quote` | 先頭行が `[!NOTE]` 等の alert ラベルや `**QUOTE**` 等の太字ラベルだけなら `quote_labels: drop`（既定）で落とす |
| コードフェンス（バッククォート 3 個以上 / `~~~`） | `code` | `{=latex}` 等の raw ブロックは削除（警告） |
| `![caption](path){ width=95% }` | `image` | 末尾の pandoc 属性 `{...}` を除去。`path` は出力 YAML のディレクトリからの相対パスに書き換え（同一ディレクトリなら不変）。存在しない場合は警告 |
| `[![caption](path){...}](url)`（画像リンク） | `image`（`link` 付き） | autopilot が画像を選択して Ctrl+K で URL を設定する。設定に失敗したときは画像の直後にリンク段落（テキストは caption、無ければ URL）を置く |
| 空行に挟まれた `---` / `***` / `___` | `horizontal_rule` | |
| `\| a \| b \|` 表 | `code` | note.com に表が無いため等幅で出す（警告） |
| `::: {.class}` fenced div | 囲い行を除去 | 中身は通常どおり処理（警告） |
| `{{name}}` リーフ記法の残骸 | 除去 | 警告 |

### インライン記法（`notecomexport.inline`）

note エディタはキーボード入力で本文を受け取るため、Markdown のインライン記法は文字どおり表示されてしまう。`plain`（既定）では次のように素のテキストへ落とす。`markdown` を指定するとリーフ記法と `<br>` 以外はそのまま残す。

| 入力 | plain の出力 |
| ---- | ---- |
| `**太字**` / `__太字__` | 太字 |
| `*強調*` / `_強調_` | 強調（`2*3` や `snake_case` は変えない） |
| バッククォートで囲んだ `code` | code |
| `[text](url)`（絶対 URL） | `runs` に `{text, url}` として出す（autopilot が本物のリンクにする）。`text` 欄では `text（url）`、text と url が同じなら url のみ |
| `[text](/path)`（サイト内相対リンク） | `link_base` があれば `link_base + /path` の絶対 URL としてリンクにする。無ければ `text（/path）` のテキストに落とす（警告） |
| `[text](#anchor)`（ページ内リンク） | text のみ（警告） |
| `**[text](url)**` のように記法がリンクをまたぐもの | 記法を先に除去してからリンクを切り出すので、リンクは保たれる |
| `<kbd>Ctrl</kbd>` | Ctrl |
| `<br>` | 改行 |
| `\&` `\_` `\#` 等のバックスラッシュエスケープ | `&` `_` `#` |
| `[text]{.class}` の残骸 | text |

### note.com への投入（tools/notecom_autopilot.py）

生成した YAML は `tools/notecom_autopilot.py` が読む。Playwright で note.com の新規記事エディタを開き、カバー画像（1280×670 にリサイズ）・タイトル・本文ブロック・目次を順に入力したのち Inspector で一時停止する。再開すると「公開に進む」を押してハッシュタグ（`meta.hashtags`）を埋め、公開直前の画面で `--close-wait` 秒（既定 60 秒）待って終了する。要素待ちのタイムアウトはスクリプト冒頭の `TIMEOUT_*` 定数にまとめてある。**最終的な公開ボタンは押さない。**

```bash
pip install "pptmdmerge[notecom]"            # playwright, pyperclip
python -m playwright install chromium
python -m playwright codegen --save-storage=auth.json https://note.com/login   # 初回のみ。ログインして閉じる
python tools/notecom_autopilot.py build/article_notecom.yaml --auth-state auth.json [--imagedir DIR] [--hashtags "#a,#b"] [--no-pause] [--close-wait SEC] [--record-video DIR] [--viewport WxH]
```

`--auth-state` 省略時は環境変数 `NOTE_AUTH_STATE` を使う。`--record-video DIR` を付けると自動操作を録画し、`DIR/{YAML名}_{日時}.webm` に保存する。録画範囲はページの描画領域（ビューポート。既定 1280×1400、`--viewport 1024x768` のように変更可）のみで、アドレスバーやタブは含まない。Inspector での一時停止中や公開画面での待機中も録画は続く。途中でエラーになってもそこまでの録画は残る。録画には Playwright 同梱の ffmpeg が要る（`playwright install chromium` で入る。無いと言われたら `python -m playwright install ffmpeg`）。画像は `--imagedir` 配下を優先し、無ければ YAML のディレクトリ基準で解決する。既知の制約: リストは 1 階層のみ、表は等幅ブロック、インライン装飾は `inline: plain` で除去したものがそのまま表示される。

リンク（`runs` の `url` 付き要素）は、リンクテキストを打った直後に Shift+← で選択し、バブルメニューが出るまで約 0.6 秒待ってから note の標準ショートカット Ctrl+K で URL 入力欄（`textarea` placeholder `https://`）を開き、URL を入れて「適用」→ Esc で確定し、End で行末に戻って続きを打つ。選択直後に Ctrl+K を押しても入力欄は開かないので待ちが必要。URL 入力欄が 3 秒以内に現れなければリンクを諦め、`（url）` をテキストとして補う（警告を表示）。

画像リンク（`image` の `link`）は、アップロード完了から約 1.5 秒待って画像をクリックし、Ctrl+K で同じ URL 入力欄を開いて「適用」→ Esc で確定してからキャプションを入力する。Ctrl+K で開かなければ画像ツールバーの `リンク` ボタンを試し、それでも入力欄が見つからなければ画像の直後にリンク段落を置く（警告を表示）。起動直後に出る案内ポップオーバーは操作を妨げるので最初に閉じる。

### エラー条件

| 条件 | 終了コード |
| ---- | ---------- |
| `notecomexport.inline` / `quote_labels` が不正、`hashtags` がリストでない | 2 |
| `--source` 指定時に対応する出力キーが未指定 | 2 |
| `notecomexport.inputmd` / `output.puremdfilename` のどちらも未指定 | 2 |
| `output.notecomyamlfilename` / `output.targetbasefilename` のどちらも未指定 | 2 |
| MD の解析に失敗（frontmatter の YAML 不正、閉じていないコードフェンス） | 2 |
| 入力 MD ファイルが存在しない | 3 |
| 入力 MD ファイルを読み込めない | 1 |
| 出力 YAML が既に存在し `--force` 未指定 | 1 |
| 書き込みに失敗 | 1 |
