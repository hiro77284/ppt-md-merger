# MD_MERGEツールスイート仕様書

> 本書はリファレンスです。**はじめて使う場合は [getting_started.md](getting_started.md)**（1 つの pptx から PDF と Markdown を出すまでの一本道）から読んでください。

## 1. 概要

### ツール名

`pptmdmerge`

### 目的

このCLIツールは、複数のmarkdownファイルを結合する処理を、統一された操作体系で実行するためのツールである。

### 基本形式

```bash
pptmdmerge <subcommand> [options] [arguments]
```

例：

```bash
pptmdmerge merge input.yaml
```

---

## 2. 対象範囲

### 含める機能

* `merge`: mdファイルを結合する。当ツールスイートの主目的
* `idcollect`: 結合済み MD から `{{#id:...}}` マーカーを抽出し、IDインベントリ YAML を生成する
* `idresolve`: IDインベントリ YAML を読み込み、number と label を付与した ID解決済み YAML を生成する
* `render`: 結合済み MD に対してタイトル置換・参照置換を行い、レンダー済み MD を生成する
* `pandoc`: レンダー済み MD を pandoc に渡して PDF・LaTeX 等を生成する

### 含めない機能

* <今回の対象外>
* <将来対応予定だが初期版では除外するもの>

---

## 3. サブコマンド一覧

| サブコマンド             | 概要                                                                                                                                  | 入力       | 出力            |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------- |
| `merge`            | mdファイルを結合する                                                                                                                         | yamlファイル | mdファイル        |
| `checkgen`         | procedure の insertmd / insertpptx のフィンガープリント（ドリフト検査用データ）を別 YAML に生成する                                                               | yamlファイル | チェック YAML     |
| `checkverify`      | insertmd の内容をチェック YAML と照合する（merge を行わない）。大きな変化があれば終了コード 1                                                                          | yamlファイル | （なし。検査結果のみ）   |
| `idcollect`        | 結合済み MD から ID マーカーを抽出してインベントリ YAML を生成する                                                                                            | yamlファイル | インベントリ YAML   |
| `idresolve`        | IDインベントリ YAML から number / label を付与した ID解決済み YAML を生成する                                                                             | yamlファイル | ID解決済み YAML   |
| `render`           | 結合済み MD のタイトル・参照を ID解決済みマップで置換してレンダー済み MD を生成する                                                                                     | yamlファイル | レンダー済み MD     |
| `pandoc`           | レンダー済み MD を pandoc に渡して PDF・LaTeX 等を生成する                                                                                            | yamlファイル | PDF / LaTeX 等 |
| `pptmerge`         | 複数の PowerPoint ファイルをレシピに従って結合する                                                                                                     | yamlファイル | pptxファイル      |
| `pptimgexport`     | PPTX スライドのノートに記述された指示に従い PDF から画像を切り出して保存する                                                                                         | yamlファイル | PNG ファイル群     |
| `pptmdexport`      | PPTX スライドのノートのブロック構造から MD テキストを抽出してファイルに出力する                                                                                        | yamlファイル | MD ファイル群      |
| `pptyamlexport`    | PPTX スライドのノートの YAML ブロックから図版定義 YAML を出力する（slot / region 座標の `auto` を名前付きシェイプから算出）                                                   | yamlファイル | YAML ファイル群    |
| `pptpdfexport`     | PowerPoint COM 自動化を使って PPTX を PDF に変換する（Windows 専用）                                                                                 | yamlファイル | PDF ファイル      |
| `pptdeletecsl`     | 既存 pptx（マージ後ファイル）に対して `#CSL#` の処理だけを単独で行う。入力のみ **pptx を CLI で直接指定** する                                                              | pptxファイル | pptxファイル      |
| `ppt_to_pdf`       | pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → condblockprocess → pandoc を順に連続実行する            | yamlファイル | PDF 等         |
| `puremd`           | レンダー済み MD から LaTeX 等の raw ブロックを除去して純粋な MD を生成する                                                                                     | yamlファイル | MD ファイル       |
| `condblockprocess` | テンプレートファイル内の条件ブロックと変数参照を展開して出力ファイルを生成する                                                                                             | yamlファイル | テキストファイル      |
| `transfer`         | render 済み MD と画像を静的サイト生成用の dataentry 入力ディレクトリにコピーする                                                                                 | yamlファイル | MD・画像ファイル     |
| `notecomexport`    | puremd 処理済み MD（frontmatter ＋ GFM）を note.com 投稿用 YAML（ブロック列）に変換する。投入は `tools/notecom_autopilot.py`                                   | yamlファイル | YAML ファイル     |
| `crop_to_pdf`      | crop → merge → idcollect → idresolve → render → pandoc を順に連続実行する                                                                    | yamlファイル | PDF 等         |
| `ppt_to_transfer`  | pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → puremd → transfer を順に連続実行する                    | yamlファイル | MD・画像ファイル     |
| `ppt_to_puremd`    | `ppt_to_transfer` から末尾の transfer を除いた版。pptpdfexport → … → render → puremd まで実行し、puremd 処理済み MD を成果物として残す                            | yamlファイル | MD・画像ファイル     |
| `ppt_to_notecom`   | `ppt_to_transfer` の末尾 transfer を notecomexport に差し替えた版。pptpdfexport → … → puremd → notecomexport を連続実行し、note.com 投稿用 YAML を成果物として残す | yamlファイル | YAML・画像ファイル   |
| `validate`         | レシピ YAML の整合性（未知キー・vars 値の生 LaTeX）を検査し、cropsrc と procedure の対応（未使用 pptx / cropsrc 未登録）を info 表示する                                   | yamlファイル | （検査結果のみ）      |

---

## 4. 共通オプション

| オプション       | 省略形  | 説明               | 既定値         |
| ----------- | ---- | ---------------- | ----------- |
| `--log-level` | `-l` | ログレベル（`debug`\|`info`\|`warn`\|`error`） | `info` |
| `--dry-run` | なし   | 実際には処理せず実行内容だけ表示 | false       |
| `--json`    | なし   | 結果を JSON 形式で標準出力へ出力する | false |
| `--tag NAME` | なし | `procedure` 項目の条件付き適用（`when.tag` / `when.not_tag`）に使うタグ。繰り返し指定可。詳細は `docs/spec/md_pipeline.md` の「procedure の条件付き適用」 | なし |

---

## 5. 入力指定仕様

### 基本形

```bash
pptmdmerge <subcommand> INPUT
```

### ルール

* `INPUT` は位置引数で指定する。相対パスまたは絶対パスを使用できる。

---

## 5.1 レシピ YAML の _include

マッピングの中に `_include: <path>` と書くと、指定した YAML ファイルを読み込んでそのマッピングに合成する。ふつうの YAML キーなので、エディタの YAML linter でエラーにならない。

```yaml
# main.yaml
output:
  _include: shared/output.yaml           # セクションごと読み込む
pandoc:
  _include: ../pandocsettings.yaml       # 共通設定を読み込み、
  typst-cover-md: ../assets/cover.md     # 兄弟キーで追加・上書きする
vars:
  _include:                              # 複数ファイルはリストで（後のものが勝つ）
    - shared/vars.yaml
    - local_vars.yaml
```

### 仕様

| 項目 | 内容 |
| ---- | ---- |
| 記述位置 | 任意の階層のマッピング（トップレベルも可） |
| 値 | パス文字列、またはそのリスト |
| 合成 | 読み込み先がマッピングなら浅くマージする。リストの後のファイルが前を上書きし、同じ階層の兄弟キーは常に読み込み先より優先される（`_include` を書く位置は問わない） |
| マッピング以外 | `key: {_include: list.yaml}` のように兄弟キーが無ければ、読み込み先の値（リスト・スカラー）でそのまま置き換える。リストを複数指定すると連結する |
| パス解決 | `_include` を書いたファイルのディレクトリ基準（絶対パスも可） |
| 再帰 | 読み込み先でもさらに `_include` / `_constants` が使える。循環はエラー |
| 読み込み先 | それ自体が妥当な YAML であること |

### 旧書式（非推奨）

`!include <path>`（行頭・値の位置）と `!constants <path>` は、YAML パース前の行単位のテキスト展開として当面そのまま動く。読み込むと、ファイルごとに 1 回非推奨の警告を出す。兄弟キーと並べた書き方（`pandoc:` の下に `!include` と他のキー）は YAML の文法上不正なので、エディタではエラーになる。

旧書式と新書式の違い:

* 旧書式は後に書いたものが勝つ（`!include` より前の兄弟キーは読み込み先で上書きされる）。新書式では兄弟キーが常に勝つ
* 旧書式の `!constants` で読んだ定数は、`!include` 先を含むテキスト全体に効く。`_constants` で読んだ定数は、そのファイルと、そこから `_include` で読むファイルにだけ効く

既存レシピの変換には `tools/convert_include_keys.py` を使う（行単位の置換でコメントを保持する。`.yaml` と `.md` の ```yaml フェンスに対応）。上の違いで意味が変わりうる箇所は警告を出すので、手で確かめること。

---

## 5.2 レシピ YAML の特殊定数

YAML パース前に（旧書式の `!include` は展開後に）、以下の `__NAME__` 形式の特殊定数をその時点の値に置換する。

| 定数 | 置換される値 | 例 |
| ---- | ------------ | -- |
| `__DATE__` | 実行日（`YYYY-MM-DD`） | `2026-06-06` |
| `__TIME__` | 実行時刻（`HH:MM:SS`） | `14:32:05` |
| `__DATETIME__` | 実行日時（`YYYY-MM-DDThh:mm:ss`） | `2026-06-06T14:32:05` |

```yaml
log:
  filename: pptmerge___DATE__.log       # → pptmerge_2026-06-06.log
output:
  pdffilename: doc___DATETIME__.pdf     # → doc_2026-06-06T14:32:05.pdf
  outputdir: out___DATE__               # → out_2026-06-06
```

### 仕様

- 同一プロセス実行内では全サブコマンドで同一のタイムスタンプを使用する（セッションキャッシュ）
- YAML 値・キー・コメントを問わずテキスト全体に適用される
- `_include` で読み込まれたファイル内の定数も同様に置換される（読み込み元の `_constants` も効く）
- 値に改行を含む定数は、その定数だけが書かれた行全体を複数行に置換する

### ユーザー定義定数ファイル（TOML）

組み込み定数に加え、TOML ファイルでユーザー独自の定数を定義できる。

#### 指定方法

| 方法 | 記述 | 説明 |
|------|------|------|
| レシピ内キー | `_constants: path/to/file.toml` | トップレベルに書く。リスト可。`_include` 先にも書ける（旧書式 `!constants path` も非推奨で可） |
| CLI 引数 | `--constants path/to/file.toml` | 繰り返し指定で複数ファイル |

#### 優先順位（低 → 高）

組み込み（`__DATE__` 等） → `--constants` CLI → 読み込み元の `_constants` → そのファイルの `_constants`

同名定数は高優先度で上書きされる。

#### TOML 書式

```toml
# インライン定数（改行なし）
__AUTHOR__  = '山田太郎'
__VERSION__ = '1.0.0'

# 複数行定数（シングルクォートでバックスラッシュをそのまま保持）
__LATEX_PACKAGES__ = '''
\usepackage{luatexja}
\usepackage{graphicx}
\setmainfont{Noto Serif CJK JP}
'''
```

複数行定数の使用例：

```yaml
_constants: project/constants.toml

output:
  pdffilename: doc___DATE__.pdf

pandoc:
  include-in-header:
    __LATEX_PACKAGES__   # この行全体が複数行に展開される
```

## 5.3 レシピ YAML の version と procedure 記法

レシピのトップレベル `version` は、後方互換のない仕様変更を区別するための番号である。どのセクションでも、後方互換のない変更を行うときは `version` を上げる。現在の最新は `2`。

| version | procedure の記法 | 状態 |
| ------- | ---------------- | ---- |
| `1`（省略時も 1） | operation 記法（`- operation: insertpptx` ＋ `pptxfilename: ...`） | 非推奨。読み込み時にファイルごとに 1 回 warning |
| `2` | 操作キー記法（`- insertpptx: somefile.pptx`） | 推奨 |

### version 2 の操作キー記法

各要素は「操作名をキー、主引数を値」とする。その他の引数（`slides` / `title` / `when` / `description` など）は同じ要素の兄弟キーに書く。引数のない操作は `- beginstay` のように文字列 1 つで書ける（兄弟キーがある場合は `- beginstay:`）。

```yaml
version: 2
procedure:
  - chapter: "+"
    title: 背景
  - insertpptx: deck.pptx
    slides: 2-5
  - insertmd: deck_slide[2-5]_md.md
  - insertvspace: 0.5
  - beginstay
  - endstay
```

| 操作 | 値（主引数） | version 1 での書き方 |
| ---- | ------------ | -------------------- |
| `insertpptx` | 入力 pptx ファイル名 | `pptxfilename` |
| `insertmd` | 入力 MD ファイル名（`[from-to]` レンジ可） | `mdfilename` |
| `chapter` / `section` / `subsection` | カウンタ値（`"+"` / `n` / `+n` / `-n`）。省略可 | 同名キー |
| `insertvspace` | 行数または単位付き長さ | `lines` |
| `beginstay` / `endstay` / `insertpagebreak` / `insertvfill` | なし | — |

version 2 では次をエラーにする（読み込んだ時点で全サブコマンドが停止する）:

* `operation` キーを書いた要素（version 1 の記法の混入）
* 操作キーが 1 つもない要素（version 1 で許していた「`operation` 省略時は insertpptx」は廃止）
* 1 要素に操作キーが 2 つ以上ある要素。version 1 で chapter 操作に書けた `section` キー（およびその逆）は書けない
* 主引数キーの併記（例: `- insertpptx: a.pptx` と `pptxfilename: b.pptx`）
* 引数のない操作に値を書いた要素（例: `- beginstay: true`）
* `insertpptx` / `insertmd` の値が文字列でない要素（YAML の `no` → `false` など。引用符で囲む）

逆に version 1 のレシピに操作キー記法（`operation` のない要素に操作名のキーがある、または `- beginstay` のような文字列要素）が混入した場合もエラーにする。

### 注意

* `_include` や `_constants` の複数行定数で取り込んだ procedure 要素は、取り込んだ側のレシピの `version` で解釈される。同じ定数ファイルを version の異なるレシピで共有することはできない
* 既存レシピの変換には `tools/convert_procedure_v2.py` を使う（行単位の置換でコメントを保持する。`.yaml` / `.toml` / `.md` の ```yaml フェンスに対応）
* `pptmdexport` が書き出す procedure 貼り付け用サンプルは、入力レシピの `version` の記法で出力する

---

## 6. 出力指定仕様

出力先はすべてレシピ YAML の `output` セクションで指定する。

### workdir / output.outputdir（全サブコマンド共通）

| キー | 省略時の既定値 |
| ---- | -------------- |
| `workdir` | 省略時は YAML ファイルの親ディレクトリ基準 |
| `output.outputdir` | 省略時は `workdir`（または YAML ファイルと同じディレクトリ） |

`--workdir` CLI 引数が指定された場合はレシピの `workdir` キーより優先される。

### output.force（全サブコマンド共通）

レシピ YAML の `output.force` を `true` にすると、CLI で `--force` を指定したのと同等の動作をすべてのサブコマンドに対して適用する。CLI で `--force` を明示指定した場合はその値を優先する。

```yaml
output:
  force: true   # --force 相当（全サブコマンドに適用）
```

### 出力ファイル名の自動生成規則

#### targetbasefilename による一括自動生成

`output.targetbasefilename` を指定すると、他の出力ファイルキーを省略した際にファイル名を自動生成する。`targetbasefilename` には拡張子を含めないベース名を指定する（拡張子を含む場合は警告を出力して除去する）。

| 出力ファイルキー | 自動生成されるファイル名 | 例（`targetbasefilename: target`）|
| -------------- | -------------------- | ---- |
| `output.mdfilename` | `work_<base>_merged.md` | `work_target_merged.md` |
| `output.idcollectfilename` | `work_<base>_idcollect.yaml` | `work_target_idcollect.yaml` |
| `output.idresolvedfilename` | `work_<base>_idresolve.yaml` | `work_target_idresolve.yaml` |
| `output.renderedfilename` | `<base>_rendered.md` | `target_rendered.md` |
| `output.resourcepathfilename` | `work_<base>_resourcepath.tex` | `work_target_resourcepath.tex` |
| `output.pdffilename` | `<base>.pdf` | `target.pdf` |
| `output.texfilename` | `<base>.tex` | `target.tex` |
| `output.htmlfilename` | `<base>.html` | `target.html` |
| `output.revealfilename` | `<base>_reveal.html` | `target_reveal.html` |
| `output.puremdfilename` | `<base>_puremd.md` | `target_puremd.md` |
| `output.notecomyamlfilename` | `<base>_notecom.yaml` | `target_notecom.yaml` |
| `output.pptxfilename` | `<base>.pptx` | `target.pptx` |

各キーを明示的に指定した場合は、`targetbasefilename` より指定値が優先される。`targetbasefilename` を指定しない場合は従来どおりで、各ファイルキーを個別に指定する必要がある。

#### merge の後方互換フォールバック

`output.targetbasefilename` も `output.mdfilename` も未指定の場合、`merge` コマンドのみ入力 YAML のステム名をもとに自動生成する。

```text
<input_stem>_merge.md
```

例：

```text
sample.yaml → sample_merge.md
```

---

## 7. サブコマンド詳細仕様

サブコマンドごとの詳細仕様は、パイプライン上の役割ごとに以下へ分冊した。

| 分冊 | 収録サブコマンド |
|---|---|
| [spec/md_pipeline.md](spec/md_pipeline.md) | [merge](spec/md_pipeline.md#merge) / [idcollect](spec/md_pipeline.md#idcollect) / [idresolve](spec/md_pipeline.md#idresolve) / [render](spec/md_pipeline.md#render) |
| [spec/output_formats.md](spec/output_formats.md) | [pandoc](spec/output_formats.md#pandoc) / [puremd](spec/output_formats.md#puremd別名-githubmd) / [condblockprocess](spec/output_formats.md#condblockprocess) / [transfer](spec/output_formats.md#transfer) / [notecomexport](spec/output_formats.md#notecomexport) |
| [spec/pptx.md](spec/pptx.md) | [pptmerge](spec/pptx.md#pptmerge) / [pptimgexport](spec/pptx.md#pptimgexport) / [pptmdexport](spec/pptx.md#pptmdexport) / [pptyamlexport](spec/pptx.md#pptyamlexport) / [pptpdfexport](spec/pptx.md#pptpdfexport) / [pptdeletecsl](spec/pptx.md#pptdeletecsl) |
| [spec/pipelines.md](spec/pipelines.md) | [crop_to_pdf](spec/pipelines.md#crop_to_pdf) / [ppt_to_pdf](spec/pipelines.md#ppt_to_pdf) / [ppt_to_transfer](spec/pipelines.md#ppt_to_transfer) / [ppt_to_puremd](spec/pipelines.md#ppt_to_puremd) / [ppt_to_notecom](spec/pipelines.md#ppt_to_notecom) |
| [spec/validation.md](spec/validation.md) | [checkgen](spec/validation.md#checkgen) / [checkverify](spec/validation.md#checkverify) / [validate](spec/validation.md#validate) |

レシピ YAML の全キー一覧は [recipe_key_reference.md](recipe_key_reference.md) を正典とする。分冊側は各キーの**挙動**を記述し、キーの網羅列挙は行わない。

原稿 MD・PPTX ノート・テンプレートに書ける**記法**の一覧は [notation_reference.md](notation_reference.md) を索引とする。こちらも同様に、分冊側が挙動の正典で、索引側は網羅と相互リンクに徹する。

---

## 8. ログ仕様

### 通常出力

処理結果の要約を表示する。

```text
OK: input.yaml -> input_merge.md
```

### verbose時

```text
input: input.yaml
output: input_merge.md
mode: merge
files: a.md,b.md,c.md
```

### quiet時

* 成功時は出力しない
* エラー時のみ表示する

---

## 9. JSON出力仕様

`--json` 指定時は標準出力にJSONを出す。

```json
{
  "status": "ok",
  "command": "crop",
  "input": "sample.png",
  "output": "sample_crop.png"
}
```

エラー時：

```json
{
  "status": "error",
  "command": "crop",
  "message": "input file not found",
  "input": "sample.png"
}
```

---

## 10. dry-run仕様

`--dry-run` 指定時は、ファイルの作成・更新・削除を行わない。

表示例：

```text
DRY-RUN: input.yaml -> input_merge.md
```

---

## 11. エラー処理仕様

| 条件      | 動作         | 終了コード |
| ------- | ---------- | ----- |
| 正常終了    | 処理成功       | 0     |
| 入力不備    | エラーメッセージ表示 | 2     |
| ファイル未検出 | エラーメッセージ表示 | 3     |
| 処理失敗    | エラーメッセージ表示 | 1     |

---

## 12. ディレクトリ構成

## 12.1 ツールのソース構成

```text
md_merge/
├── pyproject.toml
├── docs/
│   ├── md_merge_spec.md            # ツール仕様書（共通仕様 ＋ 分冊への索引）
│   ├── spec/                       # サブコマンド詳細仕様（§7 の分冊）
│   │   ├── md_pipeline.md          #   merge / idcollect / idresolve / render
│   │   ├── output_formats.md       #   pandoc / puremd / condblockprocess / transfer / notecomexport
│   │   ├── pptx.md                 #   pptmerge / pptimgexport / pptmdexport / pptyamlexport / pptpdfexport
│   │   ├── pipelines.md            #   crop_to_pdf / ppt_to_pdf / ppt_to_transfer / ppt_to_puremd / ppt_to_notecom
│   │   └── validation.md           #   checkgen / checkverify / validate
│   ├── md_pptx_merge_spec.yaml     # レシピ YAML スキーマ仕様
│   ├── md_inventory_spec.yaml      # インベントリ YAML スキーマ仕様
│   └── md_resolved_spec.yaml       # ID解決済み YAML スキーマ仕様
├── src/
│   └── md_merge/
│       ├── __init__.py
│       ├── __main__.py
│       ├── _filters.py             # 共有フィルター（escape_backslash_smart・replace_slide_placeholders）（pptmdexport / pptimgexport / pptyamlexport / condblockprocess 共有）
│       ├── _cropsrc.py             # input.cropsrc の正規化・パス解決（ppt*export / --preprocess 共有）
│       ├── _note_parser.py         # NOTE_CONTENT_FORMAT パーサー（pptmdexport / pptimgexport / pptyamlexport 共有）
│       ├── _inventory.py           # ID インベントリ抽出・出力（merge / idinventory 共有）
│       ├── _output.py              # 終了コード・ログ設定・emit（全サブコマンド共有）
│       ├── _render.py              # タイトル置換・参照置換ロジック（render 用）
│       ├── _resolve.py             # ID 解決ロジック（idresolve 用）
│       ├── filters/                # ビルトイン Lua filter（パッケージデータ）
│       │   └── *.lua
│       ├── templates/              # TeX テンプレートサンプル（パッケージデータ）
│       │   └── *.tex
│       ├── idcollect/
│       │   └── __init__.py         # idcollect サブコマンド
│       ├── idresolve/
│       │   └── __init__.py         # idresolve サブコマンド
│       ├── merge/
│       │   ├── __init__.py         # merge サブコマンド
│       │   ├── _images.py          # 画像コピー・パス書き換え
│       │   ├── _inventory.py       # md_merge._inventory の再エクスポート
│       │   └── _recipe.py          # YAML 解析・ファイル収集・パス解決・MD 展開
│       ├── pandoc/
│       │   └── __init__.py         # pandoc サブコマンド
│       ├── pptmerge/
│       │   ├── __init__.py         # pptmerge サブコマンド
│       │   ├── _config.py          # YAML 読み込み・バリデーション・パス解決
│       │   ├── _merger.py          # COM を使った PPTX 結合・スライド挿入
│       │   ├── _slide_operation.py # SlideOperation データクラス・操作リスト構築
│       │   └── _slide_titles.py    # タイトル連番付与・マーカー除去（後処理）
│       ├── pptimgexport/
│       │   └── __init__.py         # pptimgexport サブコマンド（python-pptx + pymupdf）
│       ├── pptmdexport/
│       │   └── __init__.py         # pptmdexport サブコマンド（python-pptx）
│       ├── pptyamlexport/
│       │   └── __init__.py         # pptyamlexport サブコマンド（python-pptx）
│       ├── pptpdfexport/
│       │   └── __init__.py         # pptpdfexport サブコマンド（win32com PDF エクスポート）
│       ├── ppt_to_pdf/
│       │   └── __init__.py         # ppt_to_pdf パイプライン（pptimgexport→pptmdexport→…→pandoc）
│       ├── condblockprocess/
│       │   └── __init__.py         # condblockprocess サブコマンド（条件ブロック・変数置換）
│       ├── puremd/
│       │   └── __init__.py         # puremd サブコマンド（LaTeX raw ブロック除去）
│       ├── render/
│       │   └── __init__.py         # render サブコマンド
│       ├── transfer/
│       │   └── __init__.py         # transfer サブコマンド（静的サイト生成用 dataentry 転送）
│       ├── notecomexport/
│       │   ├── __init__.py         # notecomexport サブコマンド（puremd MD → note.com 投稿用 YAML）
│       │   └── _convert.py         # GFM ブロックパーサと note ブロックへの変換
│       └── ppt_to_notecom/
│           └── __init__.py         # ppt_to_notecom パイプライン（… → puremd → notecomexport）
├── tools/
│   └── notecom_autopilot.py       # note.com 半自動投稿（Playwright。pip install "pptmdmerge[notecom]"）
└── tests/
```

## 12.2 文書プロジェクトの構成例（複数文書）

複数の文書を管理するプロジェクトでの典型的なディレクトリ構成を示す。

```text
my_project/
├── pandoc/                          # プロジェクト共通 pandoc 設定
│   ├── defaults_pdf.yaml            # PDF 出力用 defaults
│   ├── defaults_latex.yaml          # LaTeX 出力用 defaults
│   └── metadata_common.yaml        # 共通メタデータ（組織名・フォント等）
│
├── doc_a/                           # 文書 A
│   ├── recipe.yaml                  # pptmdmerge レシピ
│   ├── md/                          # 入力 MD ソース
│   │   ├── chapter1.md
│   │   └── chapter2.md
│   ├── pandoc/                      # doc_a 固有の pandoc 設定（任意）
│   │   └── metadata.yaml           # タイトル・著者・日付
│   └── out/                         # 生成物（recipe.yaml の output.outputdir）
│       ├── merged.md
│       ├── inventory.yaml
│       ├── resolved.yaml
│       ├── rendered.md
│       └── doc_a.pdf
│
├── doc_b/                           # 文書 B
│   ├── recipe.yaml
│   ├── md/
│   └── out/
│
└── out/                             # プロジェクト全体の最終成果物置き場（任意）
```

### 設定スコープの整理

| スコープ | 場所 | 例 |
| -------- | ---- | -- |
| 環境（機種固有） | `%APPDATA%\pandoc\`（Windows）など | フォント・システムテンプレート |
| プロジェクト共通 | `<project_root>/pandoc/` | 共通 defaults・スタイル |
| 文書固有 | `<doc>/pandoc/` | 文書のメタデータ・固有テンプレート |
| ツール同梱（filter） | `src/md_merge/filters/` | ビルトイン Lua filter（実行時使用） |
| ツール同梱（template） | `src/md_merge/templates/` | TeX テンプレートサンプル（コピーして使用） |

### レシピ YAML の記述例（doc_a）

```yaml
# doc_a/recipe.yaml
version: 2
input:
  mddir: md
output:
  outputdir: out
  mdfilename: merged.md
  idcollectfilename: inventory.yaml
  idresolvedfilename: resolved.yaml
  renderedfilename: rendered.md
  pdffilename: doc_a.pdf
pandoc:
  defaults: pandoc/defaults_pdf.yaml   # --workdir でプロジェクトルート基準に解決
  filters:
    - cross_ref.lua                    # ビルトイン filter
```

### 実行例

```bash
# プロジェクトルートから --workdir を使って実行
pptmdmerge merge      doc_a/recipe.yaml --workdir .
pptmdmerge idcollect  doc_a/recipe.yaml --workdir .
pptmdmerge idresolve  doc_a/recipe.yaml --workdir .
pptmdmerge render      doc_a/recipe.yaml --workdir .
pptmdmerge pandoc      doc_a/recipe.yaml --workdir .
```

---

## 13. インストール方法

### 開発用

```bash
pip install -e .
```

### 通常インストール

```bash
pip install .
```

---

## 14. テスト方針

* 入出力パス解決のテスト
* オプション組み合わせのテスト
* 各サブコマンドの正常系テスト
* 不正入力時の異常系テスト
* dry-run時にファイルが作成されないことのテスト

---

## 15. 将来拡張

* 未定
