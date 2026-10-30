# MD 結合パイプライン仕様（merge / idcollect / idresolve / render）

> [仕様書トップ](../md_merge_spec.md) — 共通オプション・入力/出力指定・ログ・JSON・dry-run の各仕様はトップを参照。

---

## merge

### 概要

yamlファイルからマージ対象のmdファイルリストとマージ設定情報を取得し、マージ処理を行う

### 使用例

```bash
pptmdmerge merge sample.yaml
```

### 固有オプション

| オプション      | 説明   | 必須   |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--strict` | 警告をエラーとして扱う | 任意 |
| `--no-copy-images` | 画像ファイルのコピーおよびパス書き換えを行わない | 任意 |
| `--image-dir` NAME | 画像コピー先サブディレクトリ名（既定: 空 = 出力 MD と同じディレクトリ） | 任意 |
| `--flatten-images` | すべての画像を `<outdir>/<image-dir>/` にフラット集約する。同名ファイルはサフィックスで衝突回避する | 任意 |
| `--clear-dir-before-merge` | image-dir 指定時、merge 前に image-dir 内を全削除する（**既定 on**。削除前に確認、後述） | 任意 |
| `--no-check` | チェックデータ（`output.checkfilename`）が存在しても insertmd 整合性チェックをスキップする | 任意 |
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
| ファイル収集 | `procedure` を走査し、`insertmd` はファイルパスを収集（ファイル名のレンジ展開を含む。後述）、`chapter`/`section`/`subsection` はマーカーコメント行を、`insertvspace`/`insertpagebreak`/`insertvfill` は semantic リーフ記法（`{{vspace:N}}` 等）を生成する |
| 出力先解決 | `output.mdfilename` > `output.targetbasefilename`（`<base>_merged.md`）> 自動生成（`<yaml_stem>_merge.md`）の優先順で決定する。`output.outputdir` が指定されている場合はその下に配置する |
| 上書きガード | `--force` なしで出力先に既存ファイルがある場合はエラー（終了コード 1）とする |
| `--dry-run` | 上書きガードをスキップし、ファイルへの書き込みを行わず実行内容のみ表示する |
| `--strict` | MD ファイルが見つからない場合を warning ではなく error として扱い、処理を中断する（終了コード 3）|
| `--json` | 成功・エラーともに JSON 形式で標準出力へ出力する |

### insertmd ファイル名のレンジ展開（`[from-to]`）

`procedure` の `insertmd` に指定するファイル名には `[from-to]` 形式のレンジを 1 つ書ける。merge はこれを展開して複数ファイルの挿入に変換する（同じレシピ位置に、レンジ順で連続挿入される）。

```yaml
- insertmd: deck_slide[2-4]_md.md   # → deck_slide2_md.md, deck_slide3_md.md, deck_slide4_md.md
```

| 種別 | 例 | 展開 |
| ---- | -- | ---- |
| 数値 | `[2-4]` | `2`, `3`, `4` |
| 数値（降順） | `[4-2]` | `4`, `3`, `2` |
| 数値（ゼロ埋め） | `[01-03]` | `01`, `02`, `03`（桁幅を維持） |
| 単一英字 | `[a-c]` / `[A-C]` | `a,b,c` / `A,B,C`（降順も可） |

仕様・制約:

* **1 ファイル名につきレンジは 1 つだけ**展開する。2 つ目以降の `[...]` はリテラルとして残る（例: `z[1-3]_[4-6].md` は `[1-3]` のみ展開）。
* 英字レンジは from/to とも**単一文字**で、**大文字小文字が一致**している必要がある（`[a-C]` は不可）。
* 全角文字を含むレンジ、`[1-2-3]` のような不正書式は **ValueError** となり、merge ではその insertmd エントリを警告してスキップする。
* レンジを含まない通常のファイル名はそのまま 1 件として扱う。
* この展開は `checkgen` / `checkverify` / `validate` の insertmd 判定でも同様に行われる。

### レシピ YAML による merge オプションの指定

CLI オプションと同等の設定をレシピ YAML の `merge:` セクションに記述できる。CLI フラグが明示的に指定された場合はその値を優先し、省略された場合のみレシピの値を参照する。

```yaml
merge:
  no-copy-images: false        # --no-copy-images 相当
  image-dir: ""                # --image-dir 相当（既定: 空 = 出力 MD と同じディレクトリ）
  flatten-images: false        # --flatten-images 相当
  clear-dir-before-merge: true # 既定 true。image-dir が空でないとき merge 前に image-dir 内を全削除（削除前に確認）
  strict: false                # --strict 相当

output:
  force: false              # --force 相当（全サブコマンドに共通。merge セクションから移動）
```

#### clear-dir-before-merge

`merge.clear-dir-before-merge`（既定 **`true`**。`--clear-dir-before-merge` でも指定可）が有効、**かつ** `image-dir` が空でない場合、merge 処理（画像コピー）の前に画像ディレクトリ `<output.outputdir>/<image-dir>` の中身をすべて削除する。古い画像が残らないようにするための設定。

- **既定が `true`**。無効化するにはレシピで `clear-dir-before-merge: false` を指定する。
- **削除前の確認**: 削除対象があるとき、解決済みのフルパスと項目数を提示して確認を求める（`[y/N]`）。
  - `y` で削除して続行、それ以外（`n`・EOF 等）は **merge 全体を中止**（終了コード 1）。
  - 単体の `merge` サブコマンドでは、`--force` 指定時は確認を省いて削除する（承認とみなす）。
  - パイプライン（`ppt_to_pdf` / `ppt_to_transfer` / `ppt_to_puremd` / `crop_to_pdf`）では、**全処理を始める前**に一度だけ確認する（承認後は後段の merge ステップで再確認しない）。パイプラインでは `--force` の有無に関係なく**必ず確認する**（承認なしに image-dir を破壊しない）。このため非対話環境では中止となる。
- 削除対象は image-dir の**中身**（ディレクトリ自体は残す）。
- `--dry-run` 時は削除しない。
- 安全のため、image-dir が出力ディレクトリ配下の真のサブディレクトリでない場合（`.` / `..` / 絶対パス等）は削除を中止しエラーを出す（merge は続行）。
- `image-dir` が空、または削除対象が無い場合は何もしない（確認も出さない）。
- merge 入力（include 先を含む）が参照する画像が image-dir 内にある場合は、merge 自身のコピー元を消してしまうため**削除をスキップして警告する**（確認も出さない）。`output.outputdir` を指定せず、ノートの `export-image: ../images/...` で書き出した画像を merge がそのまま参照する構成がこれに当たる。このとき image-dir 内の画像はコピーせずその場で参照する（`images/images/...` の入れ子は作らない）。抽出先と image-dir を分けたい場合は `output.outputdir`（例: `build`）を指定する。

---

### インクルード展開

MDファイル内に以下の構文が含まれる場合、対象ファイルを再帰的に展開して結合する。

```text
!include path/to/file.md
```

パスはインクルード元ファイルのディレクトリを基準とした相対パスまたは絶対パスで指定する。

> 注: インクルード展開は行単位で行い、コードフェンス（```）の内側も対象になる。コード例として `!include ...` を見せたい場合は表記を変える。書き方の詳細は [pandoc_filters.md の「コードブロックの書き方」](../pandoc_filters.md#コードブロックの書き方) を参照。

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

MDファイル内のローカル画像参照を検出し、画像を出力ディレクトリへコピーしたうえでパスを書き換える。URL・絶対パス・`#` アンカーで始まる参照は処理しない。

> 画像参照の書き換えは `merge` / `transfer` / `notecomexport` に別実装があり、対象記法と基準ディレクトリが揃っていない。現状の棚卸しと統一方針は [design_image_refs.md](../design_image_refs.md) を参照。

対象となる記法は次の 2 種。frontmatter の画像キーは [_imagerefs.py](../../src/md_merge/_imagerefs.py) の `FRONTMATTER_IMAGE_KEYS` が単一の真実源で、`transfer` / `notecomexport` も同じ一覧を使う。

| 記法 | 対象範囲 |
| ---- | -------- |
| `![alt](ref)` | 本文（frontmatter 以外） |
| `hero:` / `notecom_cover:`（値は `<path>` または `"<path>"`） | 先頭の `---` … `---` で囲まれた YAML frontmatter 内のみ。開始 `---` の前に空行と HTML コメント（`<!-- md_merge_rawtitle: ... -->` 等）があってもよい。キー名は大文字小文字を区別しない。引用符の有無は保持する |

#### 非対応の記法

次の形式はパス書き換え・コピーのいずれも行わず、原稿の記述がそのまま素通しする（警告も出ない）。画像は `![alt](パス)` 形式で、パスにスペースを含めずに書くこと。

| 非対応 | 例 |
| ---- | -- |
| title 付き | `![alt](a.png "キャプション")` |
| パスにスペースを含む | `![alt](my image.png)` |
| `<...>` 囲みのパス | `![alt](<my image.png>)` |
| 参照リンク形式 | `![alt][ref]` ＋ `[ref]: a.png` |
| HTML の `<img>` タグ | `<img src="a.png">` |

対応するのは `![alt](ref)` と、その直後に続く pandoc 属性（`{ width=100% }` 等）のみ。判断の経緯は [design_image_refs.md](../design_image_refs.md) の §6.5 を参照。

#### 画像ファイル不存在警告

相対パスまたは絶対パスで参照している画像ファイルが、実際には存在していない場合は警告を出す。

#### コピー先の決定

| オプション | 動作 |
| ---------- | ---- |
| なし（既定） | `<outdir>/images/` に `input.dirs` の先頭からの相対構造を保持してコピーする（`image-dir` の既定値は `images`） |
| `--image-dir NAME` | コピー先として `<outdir>/NAME/` サブディレクトリを使用する。レシピで `image-dir: ""` と空文字を明示すると `<outdir>/` 直下に置く |
| `--flatten-images` | すべての画像を `<outdir>/<image-dir>/` にフラット集約する（相対構造を保持しない） |
| `--image-naming MODE` | コピー名の変換。`preserve`（既定・元名のまま）/ `sanitize`（NFKC 正規化・小文字化して非 ASCII 連続を `-` に畳む。空になれば `img`） |
| `--image-collision MODE` | 衝突時の扱い。`rename`（既定・`_1`, `_2` … を付けて回避）/ `overwrite`（警告して上書き）。`--overwrite-images` は後者の非推奨エイリアス |
| `--no-copy-images` | 画像のコピーおよびパス書き換えを行わない |

#### 「衝突」の定義

衝突とは **同一実行内で別のソース画像が同じコピー先になること**（例: 別ディレクトリにある同名ファイルをフラット集約した場合）。前回実行で置かれた同名ファイルの上書きは衝突ではない（同じ原稿から同じ画像を出すのだから上書きして再現するのが正しい）。この区別により、`rename` / `overwrite` のどちらでも**再実行は冪等**になり、連番が実行ごとに増えていくことはない。命名変換（`image-naming`）と衝突回避（`image-collision`）は直交した設定で、`transfer` 側も同じ 2 軸（`transfer.image_naming` / `transfer.image_collision`）を持つ。

#### パス書き換え

コピー後、MD内の参照パスを出力 MD ファイルからの相対パス（`/` 区切り）に書き換える。

#### 重複コピーの防止

同一ソースファイルが複数箇所から参照された場合、コピーは1回のみ行い、すべての参照を同じコピー先パスに書き換える。

### 章見出しマーカーの挿入

`procedure` に `chapter` / `section` / `subsection` を記述すると、結合済み MD にマーカーコメント行を挿入する。

#### レシピ YAML の記述形式

```yaml
procedure:
  - chapter: "1"        # マーカーに埋め込む値（引用符は除去される）
    title: 序論         # title 項目（省略可）
  - insertmd: intro.md
  - section: "1.1"
    title: 背景
  - subsection: "1.1.1"
    # title 省略 → 空値
  - chapter: "+"
    id: "doc:solve"    # 任意 ID（PART:LOCAL）。省略時は自動採番
    title: 解決すべき問題とは？
```

#### 挿入される行のフォーマット

```text
<!-- md_merge {{chapter:VALUE}} {{title:TITLE}} -->
{{#id:chapter:AUTOCHAPTER:AUTOID_N}}
# TITLE
```

3行セットで挿入される。`chapter` の部分と見出し `#` の数は操作の種別に対応する。

#### `id` キー（任意 ID の指定）

`id: PART:LOCAL` を指定すると、`{{#id:TYPE:PART:LOCAL}}` を生成する（自動採番の代わり）。`{{num:TYPE:PART:LOCAL}}` / `{{label:...}}` で安定的に参照でき、章の追加・削除で番号がズレても参照が壊れない。

- 書式は `PART:LOCAL`（各部は空・`:`・`{`・`}`・空白を含まない）。例 `id: "doc:solve"` → `{{#id:chapter:doc:solve}}`。
- 省略時、または書式が不正なときは警告を出して従来どおり `AUTOCHAPTER:AUTOID_N` に自動採番する（後方互換）。
- FULL_ID（`TYPE:PART:LOCAL`）は idcollect の一意制約に従う（重複はエラーで検出）。

| 操作 | `#id:` の種別 | 見出しレベル |
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

### procedure の条件付き適用（`when:`）

`procedure` の各項目（操作の種類を問わない）に `when:` を書くと、条件を満たすときだけその項目を適用する。`when:` が無い項目は従来どおり常に適用する。

```yaml
procedure:
  - insertpptx: blog_only.pptx
    when:
      command: [ppt_to_puremd, ppt_to_transfer]   # このサブコマンドで起動したときだけ
  - insertmd: print_note.md
    when:
      not_command: ppt_to_pdf                     # このサブコマンドで起動したときは除外
  - chapter:
    title: おまけ
    when:
      tag: extra                                  # --tag extra を付けたときだけ
```

| キー | 適用条件 |
| ---- | -------- |
| `command` | 起動したサブコマンドが列挙したいずれかである |
| `not_command` | 起動したサブコマンドが列挙したいずれでもない |
| `tag` | `--tag` で指定したタグに、列挙したいずれかが含まれる |
| `not_tag` | `--tag` で指定したタグに、列挙したいずれも含まれない |

- 値は文字列 1 つ、または文字列のリスト。リスト内は OR、キー同士は AND。
- **サブコマンドはトップレベルで起動したコマンド名で照合する。** パイプラインは各段に同じ引数を渡すため、`ppt_to_pdf` の中の merge 段では command は `ppt_to_pdf` になる。逆に `merge` を単独実行すると command は `merge` なので、`command: [ppt_to_puremd]` の項目は除外される。別名 `githubmd` は `puremd` として扱う。
- `--tag` は全サブコマンド共通のオプション（`--tag blog --tag extra` のように繰り返し指定）。
- 条件判定はレシピ読み込み直後に 1 回だけ行い、除外した項目は procedure から取り除いてから後段に渡す（除外した項目は info ログに `procedure[N] (...) をスキップ` と出る）。章・節を除外すると、以降の番号はそのぶん詰まる。
- 対象: `merge`、`pptmerge`（`--preprocess` の前処理対象も含む）、パイプラインの insertmd ドリフトゲート。`checkgen` / `checkverify` / `validate` は条件を無視して**全項目**を対象にする（チェックデータはどの組み合わせで実行しても照合できるよう全項目分を作る）。
- `pptpdfexport` / `pptimgexport` / `pptmdexport` は procedure を参照しない（`input.cropsrc` が対象）ので、除外した pptx の書き出しはそのまま行われる。
- 実装は `src/md_merge/_conditions.py`。

### 行空け・改ページの挿入（insertvspace / insertpagebreak / insertvfill）

`procedure` に以下の操作を書くと、結合済み MD の**その位置に semantic リーフ記法を独立段落として挿入**する。MD ファイル間の行空け・改ページ調整を、原稿 MD 本文とは別に、正規の YAML として記述できる。挿入されたマーカーは後段で出力形式ごとに lower される（`puremd` で MD、`semantic-leaf.lua` で PDF/HTML。[fenced div／リーフ記法の仕様](../design_semantic_lowering.md)参照）。

| 操作 | 値 | 挿入されるマーカー | 意味 |
|---|---|---|---|
| `insertvspace` | 数値=baselineskip 単位の倍（整数/小数、省略時 1）、または単位付き長さ `5mm` / `1.5cm` 等 | `{{vspace:N}}` | 垂直スペース |
| `insertpagebreak` | なし | `{{pagebreak}}` | 改ページ |
| `insertvfill` | なし | `{{vfill}}` | 残り高を埋める |

```yaml
procedure:
  - insertmd: a.md
  - insertvspace: 0.5              # {{vspace:0.5}} を挿入
  - insertpagebreak
  - insertmd: b.md
  - insertvfill
```

`insertvspace` の値が数値でも単位付き長さでもない・負値の場合は警告して `1` を使用する。各出力形式での挙動: PDF は `\par\vspace{N\baselineskip}`（単位付きは `\par\vspace{5mm}` のようにそのまま）/ `\newpage` / `\vspace*{\fill}`、HTML は対応する `<div class>`（vspace は `height`。数値=`em`、単位付き=その単位）、MD（puremd）は vspace/vfill を破棄・pagebreak を `---` に変換。

#### 見出し内の強制改行（`{{br}}`）

章・節タイトルの途中に `{{br}}` を書くと、その位置で**強制改行**する。長いタイトルが単語の途中で折り返して見栄えが悪くなるのを、著者が改行位置を指定して防ぐためのマーカー。タイトルのテキストにインラインで埋め込む（`chapter` 操作の見出し文字列や、pptx ノートの見出しに直接記述）。

各出力形式での挙動:

| 形式 | 変換 | 備考 |
|---|---|---|
| PDF (LaTeX) | `\hdbreak`（`semantic_macros.tex` 定義のロバストマクロ） | 既定は空白。見出しの**組版時のみ** `report_header.tex` の `\titleformat` が局所的に `\\` へ上書きするため、本文（章・節・項の見出し）だけ改行になる。目次・柱（running head）・PDF しおりでは空白として扱われ、`\\` による moving 引数エラーを避ける |
| HTML | `<br>` | 見出し `<h1>`〜内で改行 |
| MD (puremd/GFM) | （除去） | 改行位置の指定は PDF の固定幅組版向けで、表示幅が可変な Web（transfer / notecomexport の入力）では不要なため破棄する。空白も入れない（`問題解決に役立つ{{br}}情報整理` → `問題解決に役立つ情報整理`） |
| pptx スライドタイトル | （除去） | `pptmerge` がスライドタイトルを置換する際、タイトル文字列中の `{{br}}` は除去する（タイトルは1行に収めるため。`{{ br }}` のような空白入りも許容） |

変換は pandoc の場合 `filters/semantic-break.lua`（インライン。`semantics.yaml` の他リーフと異なり Str を分割）、GFM は `semantics.yaml` の `leaves.br`（`gfm.drop: true`）を puremd が処理する。あわせて章タイトルは `\hyphenpenalty=10000` 等で単語途中のハイフン改行を抑止している。

注: 見出し以外の本文中に `{{br}}` を書いた場合、PDF では `\hdbreak` の既定（空白）になり改行しない（改行は見出しの `\titleformat` 内でのみ有効）。HTML では常に `<br>`、GFM では常に除去。

#### `VALUE` による番号の加算・リセット

`chapter` / `section` / `subsection` の `VALUE` は、`idresolve` での番号付けを制御する（カウンタは 0 始まり）。

| `VALUE` の指定 | 挙動 |
| -------------- | ---- |
| `"+"`（または省略・空） | そのレベルのカウンタを **+1**（既定） |
| 整数（例 `"0"`, `"5"`, `"-1"`） | そのレベルのカウンタを **その値にリセット**。当該見出しの番号もその値になる |
| 上記以外（例 `"1.1"` のような値） | 後方互換のため **+1** として扱う（リセットしない） |

例：`chapter: "0"` を挟むと以降の章番号が 0 に戻り、次の `chapter: "+"` で 1 から再開する。section/subsection のカウンタは上位の章が変わると 0 に戻る点は従来どおり。

リセット値は `idcollect` が生成する inventory YAML のエントリに `numbering_op` フィールドとして記録され（`"+"` の場合は省略）、`idresolve` がこれを参照する。

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

## idcollect

### 概要

`merge` で生成した結合済み MD ファイルを読み込み、`{{#id:...}}` マーカーを抽出して ID インベントリ YAML を生成する。入出力パスは入力 YAML の `output` セクションから取得する。

### 使用例

```bash
pptmdmerge idcollect recipe.yaml
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

## idresolve

### 概要

`idcollect` で生成した ID インベントリ YAML を読み込み、各エントリに `number` と `label` を付与した ID解決済み YAML（IDresolved）を生成する。入出力パスは入力 YAML の `output` セクションから取得する。

### 使用例

```bash
pptmdmerge idresolve recipe.yaml
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

## render

### 概要

`merge` で生成した結合済み MD と `idresolve` で生成した ID解決済み YAML を読み込み、タイトル置換・参照置換を行ってレンダー済み MD を出力する。

### 使用例

```bash
pptmdmerge render recipe.yaml
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

| 参照フォーマット            | 置換内容             |
| ------------------- | ---------------- |
| `{{num:FULL_ID}}`   | `number` フィールドの値 |
| `{{title:FULL_ID}}` | `title` フィールドの値  |
| `{{rawtitle:FULL_ID}}` | `rawtitle` フィールドの値（pptx スライドのタイトル枠から取得した生のタイトル。参照展開・エスケープ・番号付けで加工されない原文。pptx 由来でない場合は見出しテキストにフォールバック） |
| `{{label:FULL_ID}}` | `label` フィールドの値  |

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

> 注: 参照変換・変数置換ともコードフェンス（```）の内側にも及ぶ。コード例中に `{{v:...}}` 等をリテラルで残すことはできない。詳細は [pandoc_filters.md の「コードブロックの書き方」](../pandoc_filters.md#コードブロックの書き方) を参照。

### 4) セクション一覧展開（`{{sectionlist}}`）

chapter とびらページ等で、その章に属するセクションの一覧を差し込むためのマーカー。ID解決済みマップの**文書順エントリ**から、対象 chapter の直後～次の chapter の手前にある `section`（`identifier_type: section`）を抜き出し、Markdown 箇条書きに展開する。`subsection` は含めない。

| 記法 | 対象 chapter |
| ---- | ---- |
| `{{sectionlist}}` | **現在の章**（マーカーより前で直近に出現した `{{#id:chapter:...}}`） |
| `{{sectionlist:chapter:PART:LOCAL}}` | `full_id` で明示指定した章 |

- 各項目は resolved の `label`（例 `2.1) 障害とは何か`）を用いた `- label` 形式。番号が無効な場合は `title` にフォールバックする。
- 章の判定は番号の前置（`2.` 等）ではなく**文書順のグルーピング**で行うため、番号方式に依存しない。
- 生成物は `label` 済みの文字列なので、一覧に対する追加の参照変換・変数置換は行わない。
- `{{sectionlist}}`（引数なし）でマーカーより前に chapter が無い場合は警告を出し、空に置換する。
- pandoc に箇条書きとして認識させるため、マーカーは前後を空行で挟んだ独立行に置くこと。

とびらページは MD ファイルとして用意し（`insertmd` 等で結合）、その MD 内に chapter の `{{#id:chapter:...}}` を書いた後で `{{sectionlist}}` を置くのが基本の使い方。
