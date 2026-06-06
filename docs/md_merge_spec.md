# MD_MERGEツールスイート仕様書

## 1. 概要

### ツール名

`md-merge`

### 目的

このCLIツールは、複数のmarkdownファイルを結合する処理を、統一された操作体系で実行するためのツールである。

### 基本形式

```bash
md-merge <subcommand> [options] [arguments]
```

例：

```bash
md-merge merge input.yaml
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

| サブコマンド | 概要           | 入力     | 出力          |
| ------ | ------------ | ------ | ----------- |
| `merge` | mdファイルを結合する | yamlファイル | mdファイル      |
| `idcollect` | 結合済み MD から ID マーカーを抽出してインベントリ YAML を生成する | yamlファイル | インベントリ YAML |
| `idresolve` | IDインベントリ YAML から number / label を付与した ID解決済み YAML を生成する | yamlファイル | ID解決済み YAML |
| `render` | 結合済み MD のタイトル・参照を ID解決済みマップで置換してレンダー済み MD を生成する | yamlファイル | レンダー済み MD |
| `pandoc` | レンダー済み MD を pandoc に渡して PDF・LaTeX 等を生成する | yamlファイル | PDF / LaTeX 等 |
| `pptmerge` | 複数の PowerPoint ファイルをレシピに従って結合する | yamlファイル | pptxファイル |
| `pptimgexport` | PPTX スライドのノートに記述された指示に従い PDF から画像を切り出して保存する | yamlファイル | PNG ファイル群 |
| `pptmdexport` | PPTX スライドのノートのブロック構造から MD テキストを抽出してファイルに出力する | yamlファイル | MD ファイル群 |
| `pptpdfexport` | PowerPoint COM 自動化を使って PPTX を PDF に変換する（Windows 専用） | yamlファイル | PDF ファイル |
| `ppt_to_pdf` | pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → condblockprocess → pandoc を順に連続実行する | yamlファイル | PDF 等 |
| `puremd` | レンダー済み MD から LaTeX 等の raw ブロックを除去して純粋な MD を生成する | yamlファイル | MD ファイル |
| `condblockprocess` | テンプレートファイル内の条件ブロックと変数参照を展開して出力ファイルを生成する | yamlファイル | テキストファイル |
| `crop_to_pdf` | crop → merge → idcollect → idresolve → render → pandoc を順に連続実行する | yamlファイル | PDF 等 |

---

## 4. 共通オプション

| オプション       | 省略形  | 説明               | 既定値         |
| ----------- | ---- | ---------------- | ----------- |
| `--log-level` | `-l` | ログレベル（`debug`\|`info`\|`warn`\|`error`） | `info` |
| `--dry-run` | なし   | 実際には処理せず実行内容だけ表示 | false       |
| `--json`    | なし   | 結果を JSON 形式で標準出力へ出力する | false |

---

## 5. 入力指定仕様

### 基本形

```bash
md-merge <subcommand> INPUT
```

### ルール

* `INPUT` は位置引数で指定する。相対パスまたは絶対パスを使用できる。

---

## 5.1 レシピ YAML の !include

レシピ YAML 内の任意の位置に `!include <path>` と記述すると、指定したファイルの内容をその位置にインクルードする。

```yaml
# main.yaml
output: !include shared/output.yaml          # セクションごとインクルード
pandoc:
  defaults: defaults.yaml
  metadata-file: !include shared/meta.yaml   # 行途中でも可
vars: !include shared/vars.yaml
```

### 仕様

| 項目 | 内容 |
| ---- | ---- |
| 記述位置 | 行頭・行途中を問わず YAML 値が書ける位置であればどこでも使用可 |
| パス解決 | インクルード元ファイルのディレクトリ基準で解決する（絶対パスも可） |
| 再帰インクルード | インクルードされたファイル内でもさらに `!include` が使える |
| コメント | `!include path.yaml  # コメント` のようにコメントを付けてよい |

---

## 5.2 レシピ YAML の特殊定数

`!include` 展開後・YAML パース前に、以下の `__NAME__` 形式の特殊定数をその時点の値に置換する。

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
- `!include` で読み込まれたファイル内の定数も同様に置換される

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

## 7.1 merge

### 概要

yamlファイルからマージ対象のmdファイルリストとマージ設定情報を取得し、マージ処理を行う

### 使用例

```bash
md-merge merge sample.yaml
```

### 固有オプション

| オプション      | 説明   | 必須   |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--strict` | 警告をエラーとして扱う | 任意 |
| `--no-copy-images` | 画像ファイルのコピーおよびパス書き換えを行わない | 任意 |
| `--image-dir` NAME | 画像コピー先サブディレクトリ名（既定: 空 = 出力 MD と同じディレクトリ） | 任意 |
| `--flatten-images` | すべての画像を `<outdir>/<image-dir>/` にフラット集約する。同名ファイルはサフィックスで衝突回避する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |

### 入力

* input.yaml 結合条件および結合対象mdファイルを指示する 

### 出力

* 結合後のmdファイル

### エラー条件

* 入力ファイルが存在しない
* 出力先に既存ファイルがあり、上書き不可

### 処理ステップ

| ステップ | 内容 |
| ------ | ---- |
| 入力解決 | 位置引数 `INPUT` で指定された YAML ファイルを読み込む |
| `input.mddir` 解決 | `input` セクションまたは `input.mddir` 省略時は YAML ファイルと同じディレクトリを使用する。相対パスは `workdir`（省略時は YAML ファイルの親ディレクトリ）基準で解決する |
| ファイル収集 | `procedure` を走査し、`operation: insertmd` はファイルパスを収集、`operation: chapter`/`section`/`subsection` はマーカーコメント行を生成する |
| 出力先解決 | `output.mdfilename` > `output.targetbasefilename`（`<base>_merged.md`）> 自動生成（`<yaml_stem>_merge.md`）の優先順で決定する。`output.outputdir` が指定されている場合はその下に配置する |
| 上書きガード | `--force` なしで出力先に既存ファイルがある場合はエラー（終了コード 1）とする |
| `--dry-run` | 上書きガードをスキップし、ファイルへの書き込みを行わず実行内容のみ表示する |
| `--strict` | MD ファイルが見つからない場合を warning ではなく error として扱い、処理を中断する（終了コード 3）|
| `--json` | 成功・エラーともに JSON 形式で標準出力へ出力する |

### レシピ YAML による merge オプションの指定

CLI オプションと同等の設定をレシピ YAML の `merge:` セクションに記述できる。CLI フラグが明示的に指定された場合はその値を優先し、省略された場合のみレシピの値を参照する。

```yaml
merge:
  no-copy-images: false     # --no-copy-images 相当
  image-dir: ""             # --image-dir 相当（既定: 空 = 出力 MD と同じディレクトリ）
  flatten-images: false     # --flatten-images 相当
  strict: false             # --strict 相当

output:
  force: false              # --force 相当（全サブコマンドに共通。merge セクションから移動）
```

---

### インクルード展開

MDファイル内に以下の構文が含まれる場合、対象ファイルを再帰的に展開して結合する。

```text
!include path/to/file.md
```

パスはインクルード元ファイルのディレクトリを基準とした相対パスまたは絶対パスで指定する。

#### 循環検出

| 状態 | 動作 |
| ---- | ---- |
| 現在の呼び出しスタック上に同じファイルが存在する | 循環インクルードエラー（終了コード 1） |
| 別ブランチ（並列位置）で同じファイルを参照する | 許可 |

呼び出しスタックを `frozenset` で管理し、インクルード時に対象パスがスタック内に存在する場合のみ循環と判定する。これにより、同一ファイルを複数箇所から参照する並列インクルードは問題なく動作する。

#### インクルード先ファイルが存在しない場合

| モード | 動作 |
| ------ | ---- |
| 通常 | 警告を出力し、そのインクルード行をスキップして処理を継続する |
| `--strict` | エラーとして処理を中断する（終了コード 3） |

### 画像ファイルの処理

MDファイル内のローカル画像参照（`![alt](ref)` 形式）を検出し、画像を出力ディレクトリへコピーしたうえでパスを書き換える。URL・絶対パス・`#` アンカーで始まる参照は処理しない。

#### コピー先の決定

| オプション | 動作 |
| ---------- | ---- |
| なし（既定） | `<outdir>/` 直下に `input.mddir` からの相対構造を保持してコピーする |
| `--image-dir NAME` | コピー先として `<outdir>/NAME/` サブディレクトリを使用する |
| `--flatten-images` | すべての画像を `<outdir>/<image-dir>/` にフラット集約する。同名ファイルは `_1`, `_2` … のサフィックスを付けて上書きを回避する |
| `--no-copy-images` | 画像のコピーおよびパス書き換えを行わない |

#### パス書き換え

コピー後、MD内の参照パスを出力 MD ファイルからの相対パス（`/` 区切り）に書き換える。

#### 重複コピーの防止

同一ソースファイルが複数箇所から参照された場合、コピーは1回のみ行い、すべての参照を同じコピー先パスに書き換える。

### 章見出しマーカーの挿入

`procedure` に `operation: chapter` / `section` / `subsection` を記述すると、結合済み MD にマーカーコメント行を挿入する。

#### レシピ YAML の記述形式

```yaml
procedure:
  - operation: chapter
    chapter: "1"        # マーカーに埋め込む値（引用符は除去される）
    title: 序論         # title 項目（省略可）
  - operation: insertmd
    mdfilename: intro.md
  - operation: section
    section: "1.1"
    title: 背景
  - operation: subsection
    subsection: "1.1.1"
    # title 省略 → 空値
```

#### 挿入される行のフォーマット

```text
<!-- md_merge {{chapter:VALUE}} {{title:TITLE}} -->
{{#id:chapter:AUTOCHAPTER:AUTOID_N}}
# TITLE
```

3行セットで挿入される。`chapter` の部分と見出し `#` の数は operation の種別に対応する。

| operation | `#id:` の種別 | 見出しレベル |
| --------- | ------------- | ----------- |
| `chapter` | `chapter` | `#` |
| `section` | `section` | `##` |
| `subsection` | `subsection` | `###` |

| フィールド | 内容 |
| ---------- | ---- |
| `VALUE` | レシピの同名フィールドの値。引用符（`"` / `'`）は除去する |
| `TITLE` | `title` フィールドの値。未定義の場合は空値 |
| `AUTOCHAPTER` | リテラル文字列 `AUTOCHAPTER`（固定） |
| `AUTOID_N` | `N` は `chapter`/`section`/`subsection` 共通の登場順連番（1 始まり） |

上記レシピの出力例：

```text
<!-- md_merge {{chapter:1}} {{title:序論}} -->
{{#id:chapter:AUTOCHAPTER:AUTOID_1}}
# 序論

<!-- source: intro.md -->
…intro.md の内容…

<!-- md_merge {{section:1.1}} {{title:背景}} -->
{{#id:section:AUTOCHAPTER:AUTOID_2}}
## 背景

<!-- md_merge {{subsection:1.1.1}} {{title:}} -->
{{#id:subsection:AUTOCHAPTER:AUTOID_3}}
###
```

---

## 7.2 idcollect

### 概要

`merge` で生成した結合済み MD ファイルを読み込み、`{{#id:...}}` マーカーを抽出して ID インベントリ YAML を生成する。入出力パスは入力 YAML の `output` セクションから取得する。

### 使用例

```bash
md-merge idcollect recipe.yaml
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存のインベントリファイルを上書きする | 任意 |

### 入力

| 項目 | 説明 |
| ---- | ---- |
| 入力 YAML | `output.mdfilename` で結合済み MD のファイル名を、`output.idcollectfilename` でインベントリ出力先ファイル名を指定する。どちらも省略した場合は `output.targetbasefilename` から自動生成する |
| 結合済み MD | `output.outputdir / output.mdfilename` で解決されるファイル。事前に `merge` で生成しておく必要がある |

### 出力

* `output.outputdir / output.idcollectfilename` にスキーマ `md_inventory_spec.yaml` 準拠の YAML ファイルを出力する

### エラー条件

* 入力 YAML に `output.mdfilename` も `output.targetbasefilename` も未定義
* 入力 YAML に `output.idcollectfilename` も `output.targetbasefilename` も未定義
* 結合済み MD ファイルが存在しない
* 出力先に既存ファイルがあり、`--force` 未指定

### マーカーフォーマット

```text
{{#id:<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>}}
```

| フィールド | 説明 |
| ---------- | ---- |
| `IDENTIFIER_TYPE` | `chapter` / `section` / `subsection` / `image` / `var`。未知の値は警告を出したうえで受け入れ、処理を続行する |
| `PART_ID` | パート識別子 |
| `LOCAL_ID` | ローカル識別子 |

### 抽出ロジック

結合済み MD を行スキャンし、`<!-- source: ... -->` コメントを追跡することで各エントリの `source.md`（検出元ソースファイル）を特定する。1行に複数のマーカーがある場合はすべて記録する。

| エントリフィールド | 内容 |
| ------------------ | ---- |
| `full_id` | `<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>` |
| `location.file` | 結合済み MD の YAML 基準相対パス |
| `location.line` | 結合済み MD 上の行番号 |
| `source.md` | 検出元ソース MD の YAML 基準相対パス |
| `source.pptx`, `document.*` | 後日実装。現時点では `<DUMMY>` を出力する |

#### title 検出

ID マーカー行の**直後の行**を検査し、`#` / `##` / `###` で始まる見出し行からタイトルを取得する。

| 条件 | 動作 |
| ---- | ---- |
| 直後の行が `#`/`##`/`###` で始まる | `#` プレフィックスと空白を除いた文字列を `title` に設定する |
| `identifier_type` が `chapter`/`section`/`subsection` で見出しレベルが期待値と異なる | 警告を出力するが `title` は受け入れる（`chapter`→`#`, `section`→`##`, `subsection`→`###`） |
| 直後の行が見出しで始まらない | 警告を出力し、`title` を `TITLE NOT FOUND` とする |

---

## 7.3 idresolve

### 概要

`idcollect` で生成した ID インベントリ YAML を読み込み、各エントリに `number` と `label` を付与した ID解決済み YAML（IDresolved）を生成する。入出力パスは入力 YAML の `output` セクションから取得する。

### 使用例

```bash
md-merge idresolve recipe.yaml
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の ID解決済みファイルを上書きする | 任意 |

### 入力

| 項目 | 説明 |
| ---- | ---- |
| 入力 YAML | `output.idcollectfilename` でインベントリ YAML のファイル名を、`output.idresolvedfilename` で出力先ファイル名を指定する。どちらも省略した場合は `output.targetbasefilename` から自動生成する |
| インベントリ YAML | `output.outputdir / output.idcollectfilename` で解決されるファイル。事前に `idcollect` で生成しておく必要がある |

### 出力

* `output.outputdir / output.idresolvedfilename` にスキーマ `md_resolved_spec.yaml` 準拠の YAML ファイルを出力する

### エラー条件

* 入力 YAML に `output.idcollectfilename` も `output.targetbasefilename` も未定義
* 入力 YAML に `output.idresolvedfilename` も `output.targetbasefilename` も未定義
* インベントリ YAML ファイルが存在しない
* 出力先に既存ファイルがあり、`--force` 未指定

### numbering・label 付与ロジック

カウンタ変数 `cnum`, `snum`, `ssnum`, `fnum` を持つ（初期値はすべて 0）。エントリを出現順に走査し、`identifier_type` に応じて以下の処理を行う。

| identifier_type | カウンタ操作 | number の値 |
| --------------- | ------------ | ----------- |
| `chapter`    | `cnum += 1`、`snum = 0`、`ssnum = 0` | `{cnum}` |
| `section`    | `snum += 1`、`ssnum = 0` | `{cnum}{delimiter}{snum}` |
| `subsection` | `ssnum += 1` | `{cnum}{delimiter}{snum}{delimiter}{ssnum}` |
| `figure`     | `fnum += 1` | `{fnum}` |
| その他 | なし | `""` |

`label` は `{number}{separator}{title}` で生成する（`number` が空の場合は `label` も `""`）。

`delimiter` と `separator` はレシピ YAML の `indexer` セクションから取得する。

| キー | 既定値 |
| ---- | ------ |
| `indexer.delimiter` | `"."` |
| `indexer.separator` | `") "` |

---

## 7.4 pandoc

### 概要

`render` で生成したレンダー済み MD を pandoc に渡し、PDF・LaTeX 等を生成する。pandoc の設定はレシピ YAML の `pandoc` セクションと文書プロジェクト内の defaults ファイルで管理する。

### 使用例

```bash
md-merge pandoc recipe.yaml
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--tex` | LaTeX 出力モード。`output.texfilename` を使い `-t latex` で pandoc を起動する | 任意 |
| `--html` | HTML 出力モード。`output.htmlfilename` を使い `-t html` で pandoc を起動する | 任意 |
| `--reveal` | reveal.js 出力モード。`output.revealfilename` を使い `-t revealjs` で pandoc を起動する | 任意 |

### 出力ファイルとフォーマットの決定

| オプション | 出力ファイルキー | pandoc `-t` | defaults キー | template / include-in-header / resource-path |
| ---------- | --------------- | ----------- | ------------- | -------------------------------------------- |
| なし       | `output.pdffilename` | `pdf`（`pandoc.format` で上書き可） | `pandoc.defaults` | 使用する |
| `--tex`    | `output.texfilename` | `latex`（固定） | `pandoc.defaults` | 使用する |
| `--html`   | `output.htmlfilename` | `html`（固定） | `pandoc.htmldefaults` | 使用しない |
| `--reveal` | `output.revealfilename` | `revealjs`（固定） | `pandoc.revealdefaults` | 使用しない |

### レシピ YAML スキーマ

```yaml
output:
  renderedfilename: rendered.md   # 入力（render の出力）
  pdffilename: doc.pdf            # PDF 出力ファイル名（オプションなし時）
  texfilename: doc.tex            # LaTeX 出力ファイル名（--tex 指定時）
  htmlfilename: doc.html          # HTML 出力ファイル名（--html 指定時）
  revealfilename: doc_reveal.html # reveal.js 出力ファイル名（--reveal 指定時）
  outputdir: out                  # 上記ファイルの基準ディレクトリ

pandoc:
  defaults: pandoc/defaults.yaml        # pandoc defaults ファイルへのパス（省略可。--html 時は無視）
  htmldefaults: pandoc/html_defaults.yaml    # --html 時に使用する defaults ファイル（省略可）
  revealdefaults: pandoc/reveal_defaults.yaml  # --reveal 時に使用する defaults ファイル（省略可）
  format: pdf                           # 出力フォーマット（--tex 未指定時のみ有効。省略時は pdf）
  filters:                              # Lua filter リスト（省略可）
    - cross_ref.lua                     # ビルトイン filter（md-merge 同梱）
    - pandoc/my_filter.lua              # カスタム filter（yaml 基準の相対パス）
  metadata-file: pandoc/metadata.yaml   # --metadata-file に渡すパス（省略可）
  template: pandoc/template.tex         # --template に渡すパス（省略可。data-dir 基準で解決）
  include-in-header: pandoc/header.tex  # --include-in-header に渡すパス（省略可。data-dir 基準で解決）
  include-before-body: pandoc/before.tex  # --include-before-body に渡すパス（省略可。リスト可）
  syntax-highlighting: tango          # --syntax-highlighting に渡すスタイル名またはテーマファイルパス（省略可）
  data-dir: pandoc/                   # --data-dir に渡すパス（省略可）
  resource-path: figures/             # 画像等のリソース検索パス（省略可。リスト・;区切り可）
```

### パスの解決基準

| キー | 解決基準 |
| ---- | -------- |
| `defaults` / `htmldefaults` / `revealdefaults` | `data-dir` → workdir の順にフォールバック |
| `template` / `include-in-header` | `data-dir` → workdir の順にフォールバック |
| `conditional-process-input` | `data-dir` → workdir の順にフォールバック |
| `metadata-file` / `include-before-body` / `filters` | workdir（省略時は YAML の親ディレクトリ） |
| `resource-path` | レシピ YAML のあるディレクトリ（workdir の影響を受けない） |
| `data-dir` 自体 | workdir 基準で解決後、`..`・`.` を除去した正規パスで pandoc に渡す |

`data-dir` を指定すると、テンプレート・defaults 等の検索が `data-dir` 内から先に行われる。相対パスで指定したファイルが `data-dir` に存在しない場合は workdir にフォールバックする。

### Lua filter の解決順

各 filter エントリに対して以下の順で解決する。

| 順序 | 条件 | 動作 |
| ---- | ---- | ---- |
| 1 | 絶対パス | そのまま使用 |
| 2 | 相対パス → yaml 基準で存在する | カスタム filter として使用 |
| 3 | ファイル名 → `md_merge/filters/` に存在する | ビルトイン filter として使用 |
| — | いずれにも該当しない | エラー（終了コード 3） |

ビルトイン filter は `md-merge` パッケージに同梱され、`src/md_merge/filters/` に配置する。

### pandoc の呼び出し形式

```
pandoc <rendered.md> -o <pdffilename|texfilename> -t <pdf|tex>
      [-d <defaults>] [-L <filter>...>]
      [--metadata-file <path>] [--template <path>] [--include-in-header <path>]
      [--syntax-highlighting=<style>]
      [--include-before-body <path>...]
```

`--html` / `--reveal` モード時は `--template`・`--include-in-header`・`--include-before-body` を省略する。

### 完了メッセージ

単体実行（`ppt_to_pdf` 経由ではない）で成功すると、標準出力に完了ブロックを出力する。`--json` / `--dry-run` 時は出力しない。

```
========================================
  pandoc 完了
========================================
```

### エラー条件

* 入力 YAML に `output.renderedfilename` / `output.pdffilename`（または対応する出力キー）も `output.targetbasefilename` も未定義
* レンダー済み MD が存在しない
* `pandoc.defaults` / `pandoc.metadata-file` / `pandoc.template` / `pandoc.include-in-header` / `pandoc.include-before-body` に指定したファイルが存在しない
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
│   ├── defaults.yaml     # --pdf-engine, --toc, --metadata-file 等
│   ├── metadata.yaml     # タイトル・著者・日付
│   └── template.tex      # 文書専用テンプレート（任意）
└── out/
```

---

## 7.5 render

### 概要

`merge` で生成した結合済み MD と `idresolve` で生成した ID解決済み YAML を読み込み、タイトル置換・参照置換を行ってレンダー済み MD を出力する。

### 使用例

```bash
md-merge render recipe.yaml
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存のレンダー済みファイルを上書きする | 任意 |

### 入力

| 項目 | 説明 |
| ---- | ---- |
| 入力 YAML | `output.mdfilename`・`output.idresolvedfilename`・`output.renderedfilename` を参照する。いずれも省略した場合は `output.targetbasefilename` から自動生成する |
| 結合済み MD | `output.outputdir / output.mdfilename` で解決。事前に `merge` で生成しておく必要がある |
| ID解決済み YAML | `output.outputdir / output.idresolvedfilename` で解決。事前に `idresolve` で生成しておく必要がある |

### 出力

* `output.outputdir / output.renderedfilename` にレンダー済み MD を出力する

### エラー条件

* 入力 YAML に `output.mdfilename` / `output.idresolvedfilename` / `output.renderedfilename` のいずれかも `output.targetbasefilename` も未定義
* 結合済み MD または ID解決済み YAML が存在しない
* 出力先に既存ファイルがあり、`--force` 未指定

### 1) タイトル変換

結合済み MD から `{{#id:TYPE:PART:LOCAL}}` を検出し、直後の見出し行（`#`/`##`/`###`）のタイトル部分を、`full_id` が一致する `label` の値で置き換える。ID マーカー行自体は `<!-- #id:TYPE:PART:LOCAL -->` に変換する。label 置換後の見出し行には、さらに参照変換・変数置換（後述の「2) 参照変換」「3) 変数置換」）を適用する。

#### `indexer.pptxnumbering` による制御

レシピ YAML の `indexer.pptxnumbering` の値によって見出しへの `label` 置換を制御する。

| `indexer.pptxnumbering` | 見出しへの label 置換 |
| ------------------------ | --------------------- |
| `no`（省略時の既定）     | スキップ（見出しタイトルを変更しない） |
| `chapt_section`          | 実行する |
| `idresolve`              | 実行する |

ID マーカー行のコメント変換・参照変換・変数置換は `pptxnumbering` の値に関わらず常に行う。

#### インライン制御マーカー

`{{#id:...}}` と同じ行に以下のマーカーを記述することで、行単位で置換動作を制御できる。マーカー自体は出力から除去される。複数のマーカーを同時に指定できる。

| マーカー | 効果 |
| -------- | ---- |
| `{{nolabel}}` | label による見出しタイトル置換をスキップする。参照変換・変数置換は通常通り適用される |
| `{{noref}}` | `{{#id:...}}` 行と直後の見出し行の参照変換・変数置換をスキップする |

```markdown
{{#id:chapter:foo:bar}} {{nolabel}}
# タイトル（label 置換なし、参照変換あり）

{{#id:section:foo:baz}} {{noref}}
## タイトル（参照変換なし、label 置換あり）

{{#id:subsection:foo:qux}} {{nolabel}} {{noref}}
### タイトル（label 置換なし、参照変換なし）
```

#### 見出し行の検索ルール

| 条件 | 動作 |
| ---- | ---- |
| ID行の直後に見出し行がある（間に 0〜2 行の空白行） | 見出し行を処理する |
| 空白行が 3 行以上続く | 見出し行を処理しない |
| 非空白・非見出し行が 1 行以上続く | 見出し行を処理しない |
| 見出し行が連続する場合 | 1 行目のみ処理する |

見出しレベルと `identifier_type` が対応しない場合（`chapter`→`#`, `section`→`##`, `subsection`→`###`）は警告を出力するが置換は行う。

`full_id` が ID解決済みマップに存在しない場合は警告を出力し、見出しを変更しない。

### 2) 参照変換

結合済み MD から `{{TYPE:FULL_ID}}` 形式の参照を検出し、ID解決済みマップの対応エントリの値に置き換える。

| 参照フォーマット | 置換内容 |
| ---------------- | -------- |
| `{{num:FULL_ID}}` | `number` フィールドの値 |
| `{{title:FULL_ID}}` | `title` フィールドの値 |
| `{{label:FULL_ID}}` | `label` フィールドの値 |

`FULL_ID` とは `<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>` の形式。`full_id` がマップに存在しない場合は警告を出力し、元のテキストのままにする。

### 3) 変数置換

レシピ YAML の `vars:` セクションで定義した変数を、本文中の `{{v:VARIABLE}}` プレースホルダーに展開する。

#### レシピ YAML の記述形式

```yaml
vars:
  CUSTOMER_NAME: A社
  TARGET_SYSTEM: 画像検査システム
  DEPARTMENT: 品質保証部
  PRODUCT_NAME: AI検査支援ツール
```

#### プレースホルダー書式

```
{{v:VARIABLE_NAME}}
```

`VARIABLE_NAME` は英数字とアンダースコア（`[A-Za-z0-9_]+`）で構成する。

#### 置換ルール

| 条件 | 動作 |
| ---- | ---- |
| `vars:` に対応する変数が定義されている | 変数の値に置き換える |
| 対応する変数が未定義 | 警告を出力し、`{{v:VARIABLE_NAME}}` のまま残す |
| `vars:` セクション自体が未定義 | 変数置換をスキップする（エラーにしない） |

変数値はすべて文字列として展開される。置換は参照変換（`{{num:...}}` 等）の後に適用される。

---

## 7.6 pptmerge

### 概要

レシピ YAML に従って複数の PowerPoint ファイルを結合し、1 つの PPTX ファイルを生成する。スライド挿入後にタイトル連番付与・マーカー除去・テキスト置換などの後処理を行う。Windows 専用（win32com を使用）。

### 使用例

```bash
md-merge pptmerge recipe.yaml
md-merge pptmerge recipe.yaml --force --deletecsl --deletecsp
md-merge pptmerge recipe.yaml --pptxnumbering idresolve
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--deletecsl` | `#CSL#` マーカーを含むスライドを削除する（レシピ `indexer.deletecsl` を上書き） | 任意 |
| `--deletecsp` | `#CSP#` マーカーを含むシェイプを削除する（レシピ `indexer.deletecsp` を上書き） | 任意 |
| `--pptxnumbering` `no`\|`chapt_section`\|`idresolve` | タイトル連番アルゴリズムを指定する（レシピ `indexer.pptxnumbering` を上書き） | 任意 |

### レシピ YAML スキーマ

```yaml
workdir: .                    # 入出力パスの基準ディレクトリ（省略時: YAML と同じディレクトリ）
                              # --workdir CLI 引数で上書き可能

input:                        # セクション全体省略可。省略時は各キーの既定値を使用する
  pptxdir: src                # 入力 PPTX が格納されたディレクトリ（省略時: workdir と同じディレクトリ）

output:
  outputdir: out              # 出力先ディレクトリ（省略時: workdir と同じディレクトリ）
  targetbasefilename: target  # 出力ファイル名のベース部分（省略可）。指定すると他の出力キーを自動生成
  pptxfilename: merged.pptx  # 出力ファイル名（targetbasefilename 未指定時は必須）
  idresolvedfilename: resolved.yaml  # idresolve モード使用時に参照。省略時は targetbasefilename から自動生成

pptmerge:                     # スタイルベース PPTX の指定（省略可）
  stylebase: style.pptx       # マージ先の雛形となる PPTX ファイル。一時ファイルにコピーしてから開く
                              # 省略時は procedure 内の最初の insertpptx ファイルを代わりに使用する

indexer:
  pptxnumbering: no           # タイトル連番アルゴリズム（no / chapt_section / idresolve。省略時は no）
  chapter_marker: "#CHAPT#"   # チャプタースライドを示すテキストマーカー（chapt_section モードのみ）
  section_marker: "#SECTION#" # セクションスライドを示すテキストマーカー（chapt_section モードのみ）
  stay_marker: "#STAY#"       # 章・節カウンタのインクリメントを抑制するテキストマーカー（chapt_section モードのみ）
  delimiter: "."              # 節番号の区切り文字（例: 1.2）
  separator: ") "             # 番号とタイトルの区切り文字（例: 1) タイトル）
  deletecsl: false            # #CSL# 含むスライドを削除する
  deletecsp: false            # #CSP# 含むシェイプを削除する

procedure:
  - operation: chapter
    chapter: 1          # チャプターカウンタを設定する値
  - operation: section
    section: 1          # セクションカウンタを設定する値
  - operation: subsection
    subsection: 1
  - operation: beginstay        # この行以降、連番カウンタを凍結する
  - operation: endstay          # 連番カウンタ凍結を解除する
  - operation: insertpptx
    pptxfilename: doc_a.pptx   # input.pptxdir 基準のファイル名
    slides: all                 # 挿入するスライド（省略または all で全スライド）
                                # カンマ区切り文字列: "1, 3-5, 7"
                                # 配列: [1, "3-5", 7]
    separator_before: false     # 直前に空白スライドを挿入するか（省略時は separator.enabled に従う）

separator:
  enabled: false        # insertpptx 間に自動で空白スライドを挿入する

log:
  filename: merge.log   # ログファイル名（省略時は <pptxfilename_stem>_merge.log）
  dir: logs             # ログ出力先ディレクトリ（省略時は output.outputdir）。workdir 基準
  level: info
  duplicate: stdout     # ログをファイルと同時に stdout / stderr にも出力する（省略で無効）
```

### 入力

* `input.pptxdir` 配下の PPTX ファイル群（`procedure` の `insertpptx` で指定）。`input` セクションまたは `input.pptxdir` 省略時は YAML と同じディレクトリを使用する

### 出力

* `output.outputdir / output.pptxfilename` に結合済み PPTX を出力する

### エラー条件

* 入力 YAML に `output.pptxfilename` も `output.targetbasefilename` も未定義
* `insertpptx` エントリに `pptxfilename` が未定義
* 入力 PPTX ファイルが存在しない
* `pptmerge.stylebase` に指定したファイルが存在しない
* 出力先に既存ファイルがあり `--force` 未指定
* `pptxnumbering: idresolve` 時に `output.idresolvedfilename` が未定義
* `pptxnumbering: idresolve` 時に resolved ファイルが存在しない
* win32com / PowerPoint が利用不可（Windows 以外の環境など）

### 処理ステップ

| ステップ | 内容 |
| -------- | ---- |
| 設定読み込み | レシピ YAML を読み込み、CLI フラグ（`--deletecsl` / `--deletecsp` / `--pptxnumbering`）で `indexer` セクションを上書きする |
| 出力先解決 | `output.outputdir`（省略時: YAML と同じディレクトリ）/ `output.pptxfilename` を解決し、上書きガードを行う |
| 作業ファイル準備 | `pptmerge.stylebase` が指定されている場合はそのファイルを一時ファイル（`._tmp_<pptxfilename>`）にコピーして開く。省略時は `procedure` 内の最初の `insertpptx` ファイルを代わりに使用する。どちらも未設定の場合は空のプレゼンテーションを新規作成する。いずれの場合も `clear_slides()` で全スライドを削除してからマージを開始する |
| 結合処理 | `procedure` を順に処理し、`insertpptx` ごとに COM 経由でスライドを挿入する |
| `<__BASEFILENAME__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__BASEFILENAME__>` をソース PPTX のファイル名（拡張子なし）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__FILENAME__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__FILENAME__>` をソース PPTX のファイル名（拡張子あり）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__SLIDENUM__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__SLIDENUM__>` を挿入元 PPTX でのスライド番号（ソース PPTX 全体での 1 始まり番号）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__TITLE__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__TITLE__>` を該当スライドのタイトル文字列で置換する。`#NOREPLACE#` があるスライドはスキップ |
| `{{v:VARIABLE}}` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `{{v:VARIABLE}}` をレシピ `vars:` セクションの対応する値に置換する。`#NOREPLACE#` があるスライドはスキップ |
| タイトル後処理 | `indexer.pptxnumbering` の値に応じて下表のアルゴリズムでスライドタイトルを書き換える（`#NOREPLACE#` の有無に関わらず実行） |
| CSL / CSP 処理 | `deletecsl` が true のとき `#CSL#` 含むスライドを削除する。`deletecsp` が true のとき `#CSP#` 含むシェイプを削除する。`#TEMP#` / `#MEMO#` 含むシェイプは常に削除する（`#NOREPLACE#` の有無に関わらず実行） |
| 保存・リネーム | 一時ファイルに保存・クローズ後、`output.pptxfilename` の最終パスへリネームする |

### タイトル後処理アルゴリズム

| `indexer.pptxnumbering` | 動作 |
| ----------------------- | ---- |
| `no`（省略時の既定） | スライドタイトルを変更しない |
| `chapt_section` | `chapter` / `section` カウンタに従い、`#CHAPT#` / `#SECTION#` / `#STAY#` マーカーでスライドタイトルを連番付与形式に書き換える。`#NOREPLACE#` があるスライドも連番タイトル書き換えは実行される |
| `idresolve` | `output.idresolvedfilename` を読み込み、各スライドのノートから `{{#id:<TYPE>:<PART>:<LOCAL>}}` を検出して、一致する `full_id` の `label` でスライドタイトルを置き換える |

#### idresolve モードの動作詳細

1. 結合済み PPTX の全スライドのノートを走査し、`{{#id:<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>}}` マーカーを抽出する
2. `<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>` を `FULL_ID` とし、`output.idresolvedfilename` の `entries` から `full_id` が一致するエントリを探す
3. 一致が 1 件 → そのエントリの `label` でスライドタイトルを置き換える
4. 一致が 2 件以上 → 警告を出力してスライドタイトルは変更しない
5. 一致が 0 件 → 警告を出力してスライドタイトルは変更しない

### `<__BASEFILENAME__>` / `<__FILENAME__>` / `<__SLIDENUM__>` 置換の詳細

`procedure` の `insertpptx` でスライドを挿入するたびに、挿入されたスライド範囲（スライドテキストおよびノート）の各プレースホルダーをそのソースファイル名に置換する。

| プレースホルダー | 置換内容 |
| ---------------- | -------- |
| `<__BASEFILENAME__>` | ソース PPTX のファイル名（拡張子なし） |
| `<__FILENAME__>` | ソース PPTX のファイル名（拡張子あり） |
| `<__SLIDENUM__>` | 挿入元 PPTX でのスライド番号（ソース PPTX 全体での 1 始まり番号） |

| 置換対象 | 説明 |
| -------- | ---- |
| スライド上のすべてのシェイプのテキストフレーム | テキストボックス・タイトル・コンテンツプレースホルダ等 |
| テーブルシェイプの全セル | テーブル内の文字列も置換対象 |
| グループシェイプの子要素（再帰） | 何段ネストされたグループでも末端まで処理 |
| ノートページのテキストフレーム | スピーカーノート等 |

例：`doc_a.pptx` を挿入した場合、`<__BASEFILENAME__>` → `doc_a`、`<__FILENAME__>` → `doc_a.pptx` に置換される。

#### 置換の実装方式（2 フェーズ）

スライド本体のシェイプ（テキストフレーム・テーブル・グループ）は COM 経由で置換する。ノートページは COM `TextRange.Replace` が同一テキスト内の複数一致のうち最初の 1 件しか置換しない制約があるため、COM SaveAs 後に python-pptx で文字列全置換（`str.replace`）してから XML を再構築する方式を採用している。

### `{{v:VARIABLE}}` 変数置換の詳細

レシピ YAML の `vars:` セクションで変数を定義すると、`insertpptx` でスライドを挿入するたびに挿入済みスライドのテキスト・ノートに含まれる `{{v:VARIABLE}}` を対応する値に置換する。

#### レシピ YAML の記述形式

グローバル変数はレシピ最上位の `vars:` に定義する。`insertpptx` 単位で `vars:` を追加すると、その操作のスライドにのみ追加・上書き適用する（グローバルより優先される）。

```yaml
vars:                          # グローバル変数（全 insertpptx に適用）
  CUSTOMER_NAME: A社
  TARGET_SYSTEM: 画像検査システム

procedure:
  - operation: insertpptx
    pptxfilename: doc_a.pptx
    vars:                      # この insertpptx にのみ追加・上書き適用
      DEPARTMENT: 品質保証部
```

#### 置換ルール

| 条件 | 動作 |
| ---- | ---- |
| `vars:` に対応する変数が定義されている | 変数の値に置き換える |
| `vars:` セクション自体が未定義、または空 | 変数置換をスキップする（エラーにしない） |
| 対応する変数が未定義 | 警告を出力する |

- `<__BASEFILENAME__>` → `<__FILENAME__>` → `<__SLIDENUM__>` → `<__TITLE__>` → `{{v:VARIABLE}}` の順に適用される
- 置換対象はスライド上のすべてのシェイプのテキストフレーム、テーブルシェイプの全セル、グループシェイプの子要素（再帰）、およびノートページのテキストフレーム
- `chapt_section` モードでタイトル連番を付与する際も、有効変数（グローバル＋per-insertpptx）がスライドタイトルに事前適用されるため、`{{v:VARIABLE}}` を含むタイトルも正しく連番形式に組み込まれる

#### タイトル書式の保持

`chapt_section` / `idresolve` モードでスライドタイトルを書き換える際、XML を直接操作することで段落の配置（センタリング等）とランのフォント書式（フォント名・サイズ・太字・色）を保持する。

### insertpptx の slides 指定書式

| 書式 | 例 | 説明 |
| ---- | -- | ---- |
| `all`（省略時） | `slides: all` | 全スライドを挿入する |
| カンマ区切り文字列 | `slides: 1, 3-5, 7` | 整数とN-M範囲を混在できる |
| 配列 | `slides: [1, "3-5", 7]` | 整数とN-M範囲を混在できる |
| 単一整数（引用符なし） | `slides: 5` | YAML の整数値として解釈され、スライド5だけ挿入する |
| 単一整数文字列 | `slides: "5"` | スライド5だけ挿入する |
| 単一範囲文字列 | `slides: 3-7` | スライド3〜7を挿入する |

範囲記法 `N-M` は `N ≤ M`、`N ≥ 1` でなければエラーとなる。

### `#STAY#` マーカーの動作（chapt_section モード）

スライドに `#STAY#` マーカーが含まれる場合、カウンタのインクリメントを抑制する。

| 状況 | `#STAY#` なし | `#STAY#` あり |
| ---- | ------------ | ------------ |
| `#CHAPT#` あり | chapter +1、section → 0 | chapter・section 変化なし |
| `#SECTION#` あり | section → 1（セクション先頭リセット） | section 変化なし |
| マーカーなし（通常スライド） | section +1 | section 変化なし |

`beginstay` / `endstay` 操作によるカウンタ凍結（`chapsectfreeze_flag`）も同様にインクリメントを抑制するが、`#STAY#` はスライド単位・テキストマーカー方式で機能する。

### `#NOREPLACE#` マーカーの動作

スライドのシェイプテキストに `#NOREPLACE#` が含まれる場合、そのスライドに対する文字列置換・テキストクリーンアップをスキップする。

| 処理 | `#NOREPLACE#` なし | `#NOREPLACE#` あり |
| ---- | ----------------- | ----------------- |
| `<__BASEFILENAME__>` 置換 | 実行 | スキップ |
| `<__FILENAME__>` 置換 | 実行 | スキップ |
| `<__SLIDENUM__>` 置換 | 実行 | スキップ |
| `<__TITLE__>` 置換 | 実行 | スキップ |
| `{{v:VARIABLE}}` 置換 | 実行 | スキップ |
| `#CHAPT#`/`#SECTION#`/`#STAY#` テキスト除去 | 実行 | スキップ |
| `#CSL#` テキスト除去（`deletecsl: false` 時） | 実行 | スキップ |
| `#CSP#` テキスト除去（`deletecsp: false` 時） | 実行 | スキップ |
| 章・節番号付きタイトル書き換え（chapt_section） | 実行 | **実行**（スキップしない） |
| `{{#id:...}}` タイトル書き換え（idresolve） | 実行 | スキップ |

### `#NONUMBERING#` マーカーの動作

スライドのシェイプテキストに `#NONUMBERING#` が含まれる場合、`chapt_section` モードの章・節番号付きタイトル書き換えをスキップする。カウンタのインクリメント自体は通常通り行われる。

| 処理 | `#NONUMBERING#` なし | `#NONUMBERING#` あり |
| ---- | ------------------- | ------------------- |
| 章・節カウンタのインクリメント | 実行 | **実行**（スキップしない） |
| 章・節番号付きタイトル書き換え | 実行 | スキップ（元のタイトルを保持） |

`#NOREPLACE#` と `#NONUMBERING#` は独立して機能する。両方あれば両方の抑制が適用される。
| `deletecsl` スライド除外フィルタ | 実行 | **実行**（スキップしない） |
| `deletecsp` / `#TEMP#` / `#MEMO#` シェイプ削除 | 実行 | **実行**（スキップしない） |

### CSL / CSP マーカーの動作

| マーカー | `deletecsl`/`deletecsp` が false | true |
| -------- | -------------------------------- | ---- |
| `#CSL#` | `#CSL#` 以降のテキストを除去（スライドは残す） | スライドごと削除 |
| `#CSP#` | `#CSP#` テキストを除去（シェイプは残す） | シェイプごと削除 |
| `#TEMP#` / `#MEMO#` | — | 常にシェイプごと削除 |

検出対象はテキストフレーム・テーブルセル・グループ子要素（再帰）に及ぶ。テーブルセルにマーカーが含まれる場合はテーブルシェイプごと削除される。

#### グループシェイプの特別処理

グループシェイプの**グループ名**（PowerPoint のシェイプ名）に `#CSP#` が含まれ、`deletecsp: true` の場合は、グループ内の子要素を検査せずにグループごと削除する。グループ名に `#CSP#` がない場合は子要素を再帰的に検査する。

---

## 7.7 crop_to_pdf

### 概要

`crop` → `merge` → `idcollect` → `idresolve` → `render` → `pandoc` の 6 ステップを  
1 コマンドで順に実行するパイプラインサブコマンド。  
いずれかのステップが非ゼロ終了コードを返した時点で停止する。

### 使用例

```
md-merge crop_to_pdf recipe.yaml
md-merge crop_to_pdf recipe.yaml --force --workdir /path/to/workdir
md-merge crop_to_pdf recipe.yaml --dry-run
```

### 固有オプション

なし。共通オプション（`--log-level`, `--dry-run`, `--json`, `--workdir`, `--force`）のみ受け付ける。  
各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。

### 実行ステップ

| 順序 | ステップ | 担当サブコマンド |
|---:|------|---------|
| 1 | 画像クロップ | `crop` |
| 2 | MD 結合 | `merge` |
| 3 | ID 収集 | `idcollect` |
| 4 | ID 解決 | `idresolve` |
| 5 | 参照レンダー | `render` |
| 6 | PDF 変換 | `pandoc` |

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- エラーログに失敗したステップ名と終了コードを出力する。
- `crop` ステップは `input.imagesdir` が未定義または対象画像なしの場合も  
  非ゼロを返さないため（`crop` 単体の仕様に従う）、パイプラインは継続する。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

---

## 7.8 pptimgexport

### 概要

PPTX ファイルの各スライドのノートに記述されたメタデータを読み取り、対応する PDF ページから指定範囲の画像を切り出して PNG ファイルとして保存する。python-pptx と pymupdf（fitz）を使用し、win32com は不要（Windows 以外でも動作する）。

### 使用例

```bash
# PDF から画像を切り出して保存
md-merge pptimgexport recipe.yaml

# 既存ファイルを上書き
md-merge pptimgexport recipe.yaml --force

# ドライラン（ファイルを書き込まない）
md-merge pptimgexport recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--closepptx` | 処理完了後に PDF ドキュメントを close する（省略時は close しない） | 任意 |

### レシピ YAML スキーマ

```yaml
input:
  cropsrc:                    # 単一エントリ（辞書形式）または複数エントリ（リスト形式）
    pptx: slides/deck.pptx   # 読み込む PPTX ファイル（必須）。workdir 基準
    pdf: slides/deck.pdf      # 切り出し元 PDF（必須）。workdir 基準
    dpi: 150                  # PDF レンダリング解像度（省略時: 150）

# 複数ペア指定の場合はリスト形式
# input:
#   cropsrc:
#     - pptx: slides/deck1.pptx
#       pdf: slides/deck1.pdf
#       dpi: 150
#     - pptx: slides/deck2.pptx
#       pdf: slides/deck2.pdf

output:
  force: false                # --force 相当（全サブコマンド共通）
```

`cropsrc` は辞書形式（単一ペア）またはリスト形式（複数ペア）のどちらでも指定できる。各エントリの `pptx` および `pdf` はいずれも必須。

### スライドノートのメタデータ形式

各スライドのノートは [NOTE_CONTENT_FORMAT](note_content_format.md) に従って記述する。`IMAGE_BLOCK`（`{{BLOCK:IMAGE}}`）に画像エクスポート指示を記述する。1 スライドに複数の `IMAGE_BLOCK` を記述した場合はすべて処理される。

各 `IMAGE_BLOCK` の `CONTENT_BODY` には以下のキー: 値 ペアを記述する。行ごとに 1 ペア。

```text
export-image-mode: slide_with_rectpct
export-image-target: CropRect
export-image: images/fig01.png
```

| キー | 説明 |
| ---- | ---- |
| `export-image-mode` | 切り出しモード（下表参照）。未知の値は処理対象外としてスキップする |
| `export-image-target` | 参照するシェイプの名前。`slide` モードでは不要 |
| `export-image` | 出力ファイルパス。相対パスは PPTX ファイルの親ディレクトリを基準に解決する |

メタデータ解析前に、ノートテキスト全体へ下記プレースホルダー置換を適用する。キー値（`export-image:` 等）にもプレースホルダーを使用できる。

| プレースホルダー | 置換内容 |
| ---------------- | -------- |
| `<__TITLE__>` | そのスライドのタイトル文字列（タイトルシェイプが存在しない場合は空文字） |
| `<__FILENAME__>` | PPTX ファイル名（拡張子あり） |
| `<__BASEFILENAME__>` | PPTX ファイル名（拡張子なし） |
| `<__SLIDENUM__>` | スライド番号（1 始まりの整数） |

#### `export-image-mode` の値

| 値 | `export-image-target` | 動作 |
| -- | --------------------- | ---- |
| `slide` | 不要 | スライド全体を切り出す（L=0, T=0, R=100, B=100） |
| `named_shape` | シェイプ名 | 指定したシェイプの正確な境界ボックスを切り出す（浮動小数点精度） |
| `slide_with_rectpct` | シェイプ名 | 指定したシェイプの座標を整数パーセントに丸めてスライド画像の一部を切り出す |

#### `slide_with_rectpct` モードの座標計算（L/T/R/B）

シェイプの境界ボックスをスライド全体に対するパーセント（0〜100 の整数）に変換する。

```
L = round( shape.left                    / slide_width  × 100 )
T = round( shape.top                     / slide_height × 100 )
R = round( (shape.left + shape.width)    / slide_width  × 100 )
B = round( (shape.top  + shape.height)   / slide_height × 100 )
```

丸め方式は四捨五入（`math.floor(x + 0.5)`）。`crop` サブコマンドの `__{L}_{T}_{R}_{B}` 形式と互換。

`named_shape` モードでは整数丸めを行わず浮動小数点のまま使用する。

### 入力

| 項目 | 説明 |
| ---- | ---- |
| 入力 YAML | `input.cropsrc.pptx` で PPTX ファイルを、`input.cropsrc.pdf` で PDF ファイルを指定する |
| PPTX ファイル | 各スライドのノートにエクスポート指示メタデータを記述しておく |
| PDF ファイル | PPTX と同じスライド順でレンダリングされた PDF（必須） |

### 出力

* `export-image:` で指定したパスに PNG ファイルを保存する
* 相対パスは PPTX ファイルの親ディレクトリを基準に解決する
* 出力先ディレクトリが存在しない場合は自動作成する

### エラー条件

* `input.cropsrc.pptx` が未定義
* `input.cropsrc.pdf` が未定義
* PPTX ファイルが存在しない
* PDF ファイルが存在しない
* PDF のページ数が対象スライド番号より少ない
* 出力先に既存ファイルがあり `--force` 未指定
* `export-image-target` が未指定（`named_shape` / `slide_with_rectpct` モード）
* `export-image-target` に指定したシェイプ名がスライド上に存在しない

### 処理ステップ

| ステップ | 内容 |
| -------- | ---- |
| パス解決 | `input.cropsrc.pptx` と `input.cropsrc.pdf` を解決し、両ファイルの存在を確認する |
| PPTX 読み込み | python-pptx で PPTX を開き、スライドサイズ（幅・高さ）を取得する |
| プレースホルダー置換 | 各スライドのノートテキストに `<__TITLE__>` / `<__FILENAME__>` / `<__BASEFILENAME__>` / `<__SLIDENUM__>` を置換する（ノート解析前） |
| ノート解析 | 置換済みノートテキストを NOTE_CONTENT_FORMAT として解析し、すべての `IMAGE_BLOCK` の `CONTENT_BODY` をキー: 値として読み取る。`export-image-mode` が既知の値のブロックを処理対象とする |
| 座標計算 | モードに従い L/T/R/B を決定する。`slide` は固定値、`named_shape` は浮動小数点、`slide_with_rectpct` は四捨五入整数 |
| タスク一覧表示 | スライド番号・モード・シェイプ名・L/T/R/B・出力先の一覧を標準出力に表示する |
| PDF クロップ | pymupdf で PDF を開き、`dpi` 解像度でページをラスタライズし、PIL で座標範囲をクロップして PNG として保存する |
| `--dry-run` | ファイルへの書き込みを行わず実行内容のみ表示する |
| `--json` | 処理結果（タスク一覧・クロップ結果）を JSON 形式で標準出力へ出力する |

---

## 7.9 pptmdexport

### 概要

PPTX ファイルの各スライドのノートに記述されたブロック構造を解析し、`export-note:` 指示がある場合はその次のブロックの MD テキストを指定ファイルに出力する。python-pptx を使用し、win32com は不要。

### 使用例

```bash
md-merge pptmdexport recipe.yaml
md-merge pptmdexport recipe.yaml --force
md-merge pptmdexport recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--closepptx` | 処理完了後に PPTX ファイルを close する（省略時は close しない） | 任意 |

### レシピ YAML スキーマ

```yaml
input:
  cropsrc:                    # 単一エントリ（辞書形式）または複数エントリ（リスト形式）
    pptx: slides/deck.pptx   # 読み込む PPTX ファイル（必須）。workdir 基準

# 複数ペア指定の場合はリスト形式
# input:
#   cropsrc:
#     - pptx: slides/deck1.pptx
#     - pptx: slides/deck2.pptx

output:
  force: false                # --force 相当（全サブコマンド共通）
```

`cropsrc` は辞書形式（単一）またはリスト形式（複数）のどちらでも指定できる。

### スライドノートのブロック構造

各スライドのノートは [NOTE_CONTENT_FORMAT](note_content_format.md) に従って記述する。`MD_BLOCK`（`{{BLOCK:MD}}`）に MD テキストを記述する。1 スライドに複数の `MD_BLOCK` を記述した場合はすべて処理される。

各 `MD_BLOCK` の `CONTENT_BODY` は以下の形式で記述する。

```text
export-note: ../extracted/overview_slide1_md.md
# 見出し

本文テキスト（複数行可）
```

| 行 | 内容 |
| -- | ---- |
| 1 行目 | `export-note: <出力ファイルパス>` 形式のエクスポート指示。1 行目がこの形式でない場合は警告を出力してそのブロックをスキップする |
| 2 行目以降 | MD テキスト。ファイルに書き出す内容 |

`export-note:` の値の拡張子が `.md` でない場合は警告を出力してスキップする。

### 出力パスの解決

`export-note:` の値が相対パスの場合、PPTX ファイルの親ディレクトリを基準に解決する。絶対パスはそのまま使用する。

### 入力

| 項目 | 説明 |
| ---- | ---- |
| 入力 YAML | `input.cropsrc.pptx` で PPTX ファイルを指定する |
| PPTX ファイル | 各スライドのノートにブロック構造で MD テキストを記述しておく |

### プレースホルダー置換

ノートテキスト全体（ノート解析前）に以下のプレースホルダーを置換する。`export-note:` のファイルパスおよび MD テキストの両方に使用できる。

| プレースホルダー | 置換内容 |
| ---------------- | -------- |
| `<__TITLE__>` | そのスライドのタイトル文字列（タイトルシェイプが存在しない場合は空文字） |
| `<__FILENAME__>` | PPTX ファイル名（拡張子あり） |
| `<__BASEFILENAME__>` | PPTX ファイル名（拡張子なし） |
| `<__SLIDENUM__>` | スライド番号（1 始まりの整数） |

### 出力

* `export-note:` で指定したパスに MD テキストをプレーンテキスト（UTF-8 / Unix 改行）として保存する
* 出力先ディレクトリが存在しない場合は自動作成する

### エラー条件

* `input.cropsrc.pptx` が未定義
* PPTX ファイルが存在しない
* 出力先に既存ファイルがあり `--force` 未指定

### 処理ステップ

| ステップ | 内容 |
| -------- | ---- |
| PPTX 読み込み | python-pptx で PPTX を開く |
| プレースホルダー置換 | 各スライドのノートテキスト全体に `<__TITLE__>` / `<__FILENAME__>` / `<__BASEFILENAME__>` / `<__SLIDENUM__>` を置換する（ノート解析前） |
| ノート解析 | 置換済みノートテキストを NOTE_CONTENT_FORMAT として解析し、すべての `MD_BLOCK` を取得する |
| タスク収集 | 各 `MD_BLOCK` の 1 行目が `export-note:` 形式で、かつ拡張子が `.md` のブロックをタスクとして収集する。1 行目が `export-note:` でない場合は警告を出してそのブロックをスキップする |
| タスク一覧表示 | スライド番号・出力先・MD テキストの 1 行目の一覧を標準出力に表示する |
| ファイル書き出し | `MD_BLOCK` の 2 行目以降を MD テキストとして出力ファイルに書き込む |
| `--dry-run` | ファイルへの書き込みを行わず実行内容のみ表示する |
| `--json` | 処理結果（タスク一覧・書き出し結果）を JSON 形式で標準出力へ出力する |

---

## 7.10 pptpdfexport

### 概要

PowerPoint COM 自動化（win32com）を使い、PPTX ファイルを PDF に変換するサブコマンド。Windows 専用（pywin32 が必要）。

生成した PDF は `pptimgexport` の入力（`input.cropsrc.pdf`）として使用できる。

### 使用例

```bash
md-merge pptpdfexport recipe.yaml

# 既存 PDF を上書き
md-merge pptpdfexport recipe.yaml --force

# ドライラン
md-merge pptpdfexport recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力 PDF を上書きする | 任意 |
| `--closepptx` | エクスポート後にプレゼンテーションを close する（省略時は close しない）。コマンド実行前から開いていたプレゼンテーションは close しない | 任意 |
| `--ppquit` | 処理完了後に PowerPoint アプリケーションを終了する（省略時は終了しない） | 任意 |

### レシピ YAML キー

```yaml
input:
  cropsrc:                    # 単一エントリ（辞書形式）または複数エントリ（リスト形式）
    pptx: slides/deck.pptx   # 変換元 PPTX（必須）。workdir 基準
    pdf: slides/deck.pdf      # 出力先 PDF（必須）。workdir 基準

# 複数ペア指定の場合はリスト形式
# input:
#   cropsrc:
#     - pptx: slides/deck1.pptx
#       pdf: slides/deck1.pdf
#     - pptx: slides/deck2.pptx
#       pdf: slides/deck2.pdf
```

`cropsrc` は辞書形式（単一ペア）またはリスト形式（複数ペア）のどちらでも指定できる。各エントリの `pptx` および `pdf` はいずれも必須。パスは `workdir`（省略時は YAML と同じディレクトリ）を基準に解決する。PowerPoint アプリケーションは全エントリを通じて 1 回だけ起動する。

### エラー条件

* `input.cropsrc.pptx` が未定義
* `input.cropsrc.pdf` が未定義
* PPTX ファイルが存在しない
* 出力 PDF が既に存在し `--force` 未指定
* win32com（pywin32）がインポートできない（Windows 以外または未インストール）

### 処理手順

| ステップ | 内容 |
| -------- | ---- |
| パス解決 | `input.cropsrc.pptx` と `input.cropsrc.pdf` を解決する |
| PPTX 存在確認 | PPTX ファイルが存在しない場合エラー終了 |
| 上書き確認 | 出力 PDF が存在し `--force` 未指定の場合エラー終了 |
| COM 起動 | `PowerPoint.Application` を起動し PPTX を開く |
| PDF 変換 | `Presentation.SaveAs(pdf_path, 32)` で PDF として保存（32 = ppSaveAsPDF） |
| COM 終了 | `--closepptx` 指定時かつコマンドが開いたプレゼンテーションのみ `Close()` する（実行前から開いていたものは閉じない）。`--ppquit` 指定時は PowerPoint を終了する |

---

## 7.11 ppt_to_pdf

### 概要

`pptpdfexport` → `pptimgexport` → `pptmdexport` → `merge` → `idcollect` → `idresolve` → `render` → `condblockprocess` → `pandoc` の 9 ステップを 1 コマンドで順に実行するパイプラインサブコマンド。いずれかのステップが非ゼロ終了コードを返した時点で停止する。

### 使用例

```bash
md-merge ppt_to_pdf recipe.yaml
md-merge ppt_to_pdf recipe.yaml --force --workdir /path/to/workdir
md-merge ppt_to_pdf recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | 各ステップの相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 全ステップで既存ファイルを上書きする | 任意 |
| `--closepptx` | `pptpdfexport` / `pptimgexport` / `pptmdexport` で処理完了後にファイルを close する（**省略時も close する**。COM ファイルロックを解放するため `ppt_to_pdf` ではデフォルト有効） | 任意 |
| `--ppquit` | `pptpdfexport` で PowerPoint アプリケーションを終了する | 任意 |

各ステップ固有のオプション（`--strict`, `--no-copy-images` 等）はレシピ YAML の該当セクションで指定する。

### 実行ステップ

| 順序 | ステップ | 担当サブコマンド |
|---:|------|---------|
| 1 | PPTX → PDF 変換 | `pptpdfexport` |
| 2 | PDF 画像切り出し | `pptimgexport` |
| 3 | MD テキスト抽出 | `pptmdexport` |
| 4 | MD 結合 | `merge` |
| 5 | ID 収集 | `idcollect` |
| 6 | ID 解決 | `idresolve` |
| 7 | 参照レンダー | `render` |
| 8 | 条件ブロック・変数展開 | `condblockprocess` |
| 9 | PDF 変換 | `pandoc` |

### 進捗・完了メッセージ

各ステップの開始前と完了後に標準出力へ進捗行を出力する。

```
[ppt_to_pdf] pptpdfexport ...
OK: slides/deck.pptx
-> slides/deck.pdf
[ppt_to_pdf] pptpdfexport OK
[ppt_to_pdf] pptimgexport ...
...
[ppt_to_pdf] pandoc OK

========================================
  ppt_to_pdf 完了
========================================
```

`--json` モード時は進捗行も JSON 形式で出力する（`{"command": "ppt_to_pdf", "step": "...", "status": "..."}`）。完了ブロックは `--json` 時は出力しない。

出力がリアルタイムに表示されるよう、`run()` 開始時に `sys.stdout.reconfigure(line_buffering=True)` でラインバッファリングに切り替える。

### エラー処理

- いずれかのステップが非ゼロを返すと、以降のステップを実行せずに終了する。
- 失敗したステップ名と終了コードを標準出力に出力する（`[ppt_to_pdf] <step> FAILED (exit <code>)`）。

### `--force` の扱い

`--force` は全ステップに共通で渡される。各ステップは既存ファイルを上書きする。

---

## 7.12 puremd

### 概要

レンダー済み MD ファイル（`output.renderedfilename`）から LaTeX の raw ブロック等を削除し、純粋な MD ファイル（`output.puremdfilename`）を生成する。

削除対象パターンはビルトインのデフォルトを使用するか、`puremd.strip_config` でカスタム設定ファイルを指定できる。

### 使用例

```bash
md-merge puremd recipe.yaml
md-merge puremd recipe.yaml --force --workdir /path/to/workdir
md-merge puremd recipe.yaml --dry-run
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
| `puremd.strip_config` | string | strip パターン設定ファイルのパス（省略時はビルトインデフォルト） |

#### 例

```yaml
output:
  outputdir: out
  renderedfilename: rendered.md
  puremdfilename: puremd.md
puremd:
  strip_config: puremd_strip.yaml   # 省略時はビルトインデフォルト
```

### strip 設定ファイル

`puremd.strip_config` で指定する YAML ファイル。`strip:` キーにパターンのリストを記述する。設定ファイルを指定した場合はビルトインデフォルトを**置き換える**（マージではない）。

#### ファイル書式

```yaml
# puremd_strip.yaml
strip:
  - name: latex_raw_block                        # 識別名（任意）
    description: "Pandoc raw LaTeX fenced blocks" # 説明（任意）
    type: fenced_block                            # パターン種別
    lang: "{=latex}"                              # フェンスの言語識別子（type: fenced_block 必須）

  # - name: html_raw_block
  #   type: fenced_block
  #   lang: "{=html}"

  # - name: my_inline_command
  #   type: regex
  #   pattern: '\\someCommand\{[^}]*\}'
  #   dotall: false      # 省略時 false（true で . が改行にもマッチ）
  #   ignorecase: false  # 省略時 false
```

#### パターン種別

| `type` | 説明 | 必須キー |
|---|---|---|
| `fenced_block` | ` ```{lang}...``` ` 形式のフェンスブロック全体を削除 | `lang` |
| `regex` | 任意の正規表現にマッチする部分を削除 | `pattern` |

`fenced_block` の削除範囲: 開始フェンス行（` ```{lang} `）から終了フェンス行（` ``` `）まで（両端の行の改行を含む）。

`regex` はデフォルトで `re.MULTILINE` フラグ付きで適用される。`dotall: true` を加えると `re.DOTALL` も付与される。

#### ビルトインデフォルト

`puremd.strip_config` を省略した場合は以下の 1 パターンが適用される。

| name | type | 削除対象 |
|---|---|---|
| `latex_raw_block` | `fenced_block` (`lang: "{=latex}"`) | Pandoc raw LaTeX ブロック |

### 処理手順

1. `output.renderedfilename` のファイルを読み込む
2. 設定ファイルまたはビルトインデフォルトから strip パターンをコンパイルする
3. パターンをリスト順に適用し、マッチした部分を削除する
4. 結果を `output.puremdfilename` に書き込む（上書き不可の場合はエラー）

### エラー処理

| 条件 | 動作 | 終了コード |
|---|---|---|
| `output.renderedfilename` が未設定 | エラー終了 | 2 |
| `output.puremdfilename` が未設定 | エラー終了 | 2 |
| `puremd.strip_config` ファイルが見つからない | エラー終了 | 3 |
| 設定ファイルの書式エラー | エラー終了 | 2 |
| 正規表現が無効 | エラー終了 | 2 |
| 出力ファイルが既存で `--force` なし | エラー終了 | 1 |
| レンダー済み MD が見つからない | エラー終了 | 3 |

---

## 7.13 condblockprocess

### 概要

テンプレートファイル（LaTeX・テキスト等）内に記述された条件ブロック（`{{#if:VAR}}`〜`{{#endif:VAR}}`）と変数参照（`{{v:VAR}}`）を、レシピ YAML の `vars:` セクションに定義された値に基づいて展開し、出力ファイルを生成する。

詳細仕様: [conditional_block_process.md](conditional_block_process.md)

### 使用例

```bash
md-merge condblockprocess recipe.yaml
md-merge condblockprocess recipe.yaml --force
md-merge condblockprocess recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |

### レシピ YAML キー

```yaml
vars:
  TITLE: サンプル文書
  AUTHOR: 山田太郎
  COVERIMAGE: figures/cover.png   # 未定義または空文字で条件ブロックが削除される

pandoc:
  conditional-process-input: templates/cover.tex       # テンプレートファイル（必須。data-dir 基準で解決）
  conditional-process-output: out/cover_generated.tex  # 出力ファイル（省略時は output.outputdir に自動生成）
```

`conditional-process-input` は `pandoc.data-dir` → workdir の順に解決する。`conditional-process-output` を省略すると `output.outputdir / work_<input_basename>` を自動生成し、pandoc の `include-before-body` 先頭にも自動追加する。

### 変数値のエスケープ処理

`{{v:VAR}}` を置換する直前に、変数の値に対して `escape_backslash_smart` 処理を適用してから埋め込む。`vars` 辞書の値自体は変更しない。

`escape_backslash_smart` はコードブロック（` ``` ` で囲まれた範囲）とインラインコード（`` ` `` で囲まれた範囲）の外側にある `\` を `\\` に、`&` を `\&` にエスケープする。

### エラー条件

* `pandoc.conditional-process-input` が未定義
* 入力ファイルが存在しない
* 出力先に既存ファイルがあり `--force` 未指定
* `{{v:VAR}}` の `VAR` が `vars:` に未定義
* 条件ブロックの開始・終了タグ不一致、ネスト、変数名不正（詳細は [conditional_block_process.md](conditional_block_process.md) 参照）

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
│   ├── md_merge_spec.md            # ツール仕様書
│   ├── md_pptx_merge_spec.yaml     # レシピ YAML スキーマ仕様
│   ├── md_inventory_spec.yaml      # インベントリ YAML スキーマ仕様
│   └── md_resolved_spec.yaml       # ID解決済み YAML スキーマ仕様
├── src/
│   └── md_merge/
│       ├── __init__.py
│       ├── __main__.py
│       ├── _filters.py             # 共有フィルター（escape_backslash_smart・replace_slide_placeholders）（pptmdexport / pptimgexport / condblockprocess 共有）
│       ├── _note_parser.py         # NOTE_CONTENT_FORMAT パーサー（pptmdexport / pptimgexport 共有）
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
│       ├── pptpdfexport/
│       │   └── __init__.py         # pptpdfexport サブコマンド（win32com PDF エクスポート）
│       ├── ppt_to_pdf/
│       │   └── __init__.py         # ppt_to_pdf パイプライン（pptimgexport→pptmdexport→…→pandoc）
│       ├── condblockprocess/
│       │   └── __init__.py         # condblockprocess サブコマンド（条件ブロック・変数置換）
│       ├── puremd/
│       │   └── __init__.py         # puremd サブコマンド（LaTeX raw ブロック除去）
│       └── render/
│           └── __init__.py         # render サブコマンド
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
│   ├── recipe.yaml                  # md-merge レシピ
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
version: 1
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
md-merge merge      doc_a/recipe.yaml --workdir .
md-merge idcollect  doc_a/recipe.yaml --workdir .
md-merge idresolve  doc_a/recipe.yaml --workdir .
md-merge render      doc_a/recipe.yaml --workdir .
md-merge pandoc      doc_a/recipe.yaml --workdir .
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
