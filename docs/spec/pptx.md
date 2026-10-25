# PPTX 系サブコマンド仕様（pptmerge / pptimgexport / pptmdexport / pptyamlexport / pptpdfexport）

> [仕様書トップ](../md_merge_spec.md) — 共通オプション・入力/出力指定・ログ・JSON・dry-run の各仕様はトップを参照。

---

## pptmerge

### 概要

レシピ YAML に従って複数の PowerPoint ファイルを結合し、1 つの PPTX ファイルを生成する。スライド挿入後にタイトル連番付与・マーカー除去・テキスト置換などの後処理を行う。Windows 専用（win32com を使用）。

### 使用例

```bash
pptmdmerge pptmerge recipe.yaml
pptmdmerge pptmerge recipe.yaml --force --deletecsl on --deletecsp on
pptmdmerge pptmerge recipe.yaml --deletecsl off --deletecsp off
pptmdmerge pptmerge recipe.yaml --pptxnumbering idresolve
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--rebuild` | 出力 pptx が全入力より新しくても再マージする（増分ビルドのタイムスタンプスキップを無効化。後述） | 任意 |
| `--deletecsl` `on`\|`off` | **結合済み pptx** に対する CSL マーカー処理を指定する。`on`＝CSL スライド削除処理、`off`＝CSL マーカー消去処理（レシピ `indexer.deletecsl` を上書き）。個別 pptx の前処理には影響しない | 任意 |
| `--deletecsp` `on`\|`off` | `#CSP#` マーカーを含むシェイプを削除するか指定する（レシピ `indexer.deletecsp` を上書き） | 任意 |
| `--pptxnumbering` `no`\|`chapt_section`\|`idresolve` | タイトル連番アルゴリズムを指定する（レシピ `indexer.pptxnumbering` を上書き） | 任意 |
| `--no-check` | チェックデータ（`output.checkfilename` の `pptx_entries`）が存在しても insertpptx 整合性チェックをスキップする | 任意 |
| `--preprocess` | マージ前に各 `procedure` の `insertpptx` ソース pptx を前処理し、前処理済み pptx をマージ入力として読み込む（後述） | 任意 |

### 増分ビルド（`--rebuild`）

出力 pptx が既に存在し、**全入力より新しい**場合はマージをスキップする（増分ビルド）。`--rebuild` を指定するとスキップを無効化し、常に再マージする。

| 項目 | 内容 |
| ---- | ---- |
| 入力（新しさの比較対象） | レシピ YAML、`procedure` の各 `insertpptx` ソース pptx、`pptmerge.stylebase`（あれば）、`{{num/title/label}}` 置換に使う resolved YAML（存在すれば） |
| スキップ条件 | 出力が存在し、上記すべての mtime 以上（`出力mtime >= 各入力mtime`）。入力のいずれかが欠けている場合はスキップしない（マージ側でエラーにする） |
| スキップ時 | マージを行わず終了コード 0。`最新のためスキップ (--rebuild で再生成)` をログ出力（`--json` 時は `status: "skip"`） |
| `--rebuild` | 上記スキップを無効化し、常に再マージする |
| `--tag` / `when:` との関係 | 比較対象は `when:` 適用後の `insertpptx` ソースだが、`--tag` や起動コマンドの違い自体は判定に入らない。条件を変えて同じ出力先に作り直すときは `--rebuild` を付ける |
| `--preprocess` との関係 | `--preprocess` 指定時は前処理済みソースを毎回生成するため、増分スキップは行わず常に再マージする（`ppt_to_*` パイプラインと同仕様） |
| `--force` との関係 | 増分スキップは `--force` の有無に関わらず判定する。スキップされず実際に上書きが必要な場合は従来どおり `--force` が必要（未指定かつ出力が存在すればエラー） |

`--force` は「既存出力の上書き許可」、`--rebuild` は「増分スキップの無効化」で役割が異なる（`pptpdfexport` と同じ関係）。stale な出力を再マージするには `--force`（上書き許可）が必要。

### 前処理（`--preprocess`）

`--preprocess` を指定すると、マージ本体の実行前に、`procedure` の各 `insertpptx` が指すソース pptx に対して**単一ファイルの pptmerge** を行い、前処理済み pptx を生成する。マージ本体は、元の pptx の代わりに前処理済み pptx の**内容を読み込む**。

| 項目 | 内容 |
| ---- | ---- |
| 前処理対象 | `procedure` 内の各 `insertpptx` に指定した pptx（`input` のディレクトリ基準で解決。同一 pptx は 1 回だけ前処理） |
| 前処理の内容 | 単一ファイルに対する pptmerge。対象 pptx を `insertpptx`（`slides: all`）1 件として処理する。**一般マーカー処理のみ**（`--deletecsp`、`#TEMP#`/`#MEMO#`、`#CHAPT#`/`#SECTION#`/`#STAY#` 等）と、レシピ `vars` による `{{v:..}}` 置換を適用する。`pptmerge.stylebase` は適用しない |
| CSL マーカーの扱い | **一切処理しない**（`#CSL#` はそのまま残す）。`indexer.deletecsl` / `--deletecsl` を指定しても前処理の挙動は変わらない。CSL 処理は結合後にのみ行う |
| 出力ファイル名 | 元の pptx 名に `_preprocessed` を付加（例 `deck.pptx` → `deck_preprocessed.pptx`） |
| 出力先 | `output.outputdir` |
| 利用範囲 | マージ本体は前処理済み pptx を**内容の読み込み**にのみ使用する。`<__BASEFILENAME__>` / `<__FILENAME__>` 等のプレースホルダやログ表示は元の pptx 名のまま |
| 削除 | `--keep-work` 未指定時は、マージ完了後に前処理済み pptx を削除する |

Windows 専用（前処理が PowerPoint COM を使用する）。`--dry-run` 時は前処理を実行しない。パイプライン（`ppt_to_pdf` 等）の `--preprocess` が `input.cropsrc.pptx` を対象とするのに対し、`pptmerge` の `--preprocess` は `procedure` の `insertpptx` ソースを対象とする（どちらも「そのコマンドがマージ／エクスポートで消費する pptx」を前処理する点で一貫している）。

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
  - chapter: 1          # チャプターカウンタを設定する値
  - section: 1          # セクションカウンタを設定する値
  - subsection: 1
  - beginstay  # この行以降、連番カウンタを凍結する
  - endstay  # 連番カウンタ凍結を解除する
  - insertpptx: doc_a.pptx   # input.pptxdir 基準のファイル名
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
* `insertpptx` エントリにファイル名が未定義
* 入力 PPTX ファイルが存在しない
* `pptmerge.stylebase` に指定したファイルが存在しない
* 出力先に既存ファイルがあり `--force` 未指定
* `pptxnumbering: idresolve` 時に `output.idresolvedfilename` が未定義
* `pptxnumbering: idresolve` 時に resolved ファイルが存在しない
* win32com / PowerPoint が利用不可（Windows 以外の環境など）

### 処理ステップ

| ステップ | 内容 |
| -------- | ---- |
| 設定読み込み | レシピ YAML を読み込み、CLI オプション（`--deletecsl on`\|`off` / `--deletecsp on`\|`off` / `--pptxnumbering`）で `indexer` セクションを上書きする |
| 出力先解決 | `output.outputdir`（省略時: YAML と同じディレクトリ）/ `output.pptxfilename` を解決し、上書きガードを行う |
| 作業ファイル準備 | `pptmerge.stylebase` が指定されている場合はそのファイルを一時ファイル（`._tmp_<pptxfilename>`）にコピーして開く。省略時は `procedure` 内の最初の `insertpptx` ファイルを代わりに使用する。どちらも未設定の場合は空のプレゼンテーションを新規作成する。いずれの場合も `clear_slides()` で全スライドを削除してからマージを開始する |
| 結合処理 | `procedure` を順に処理し、`insertpptx` ごとに COM 経由でスライドを挿入する |
| `<__BASEFILENAME__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__BASEFILENAME__>` をソース PPTX のファイル名（拡張子なし）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__FILENAME__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__FILENAME__>` をソース PPTX のファイル名（拡張子あり）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__SLIDENUM__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__SLIDENUM__>` を挿入元 PPTX でのスライド番号（ソース PPTX 全体での 1 始まり番号）に置換する。`#NOREPLACE#` があるスライドはスキップ |
| `<__TITLE__>` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `<__TITLE__>` を該当スライドのタイトル文字列で置換する。`#NOREPLACE#` があるスライドはスキップ |
| `{{v:VARIABLE}}` 置換 | `insertpptx` でスライド挿入直後、挿入済みスライドのテキスト・ノートに含まれる `{{v:VARIABLE}}` をレシピ `vars:` セクションの対応する値に置換する。`#NOREPLACE#` があるスライドはスキップ |
| タイトル後処理 | `indexer.pptxnumbering` の値に応じて下表のアルゴリズムでスライドタイトルを書き換える（`#NOREPLACE#` の有無に関わらず実行） |
| 一般マーカー処理 | `deletecsp` が true のとき `#CSP#` 含むシェイプを削除する。`#TEMP#` / `#MEMO#` 含むシェイプは常に削除する（`#NOREPLACE#` の有無に関わらず実行） |
| CSL マーカー処理 | **結合済み pptx に対してここでのみ実行する。** `deletecsl` が true なら CSL スライド削除処理、false なら CSL マーカー消去処理。**タイトル後処理（付番）より後**に行うため、削除されたスライドの分だけ章・節番号は飛ぶ |
| 保存・リネーム | 一時ファイルに保存・クローズ後、`output.pptxfilename` の最終パスへリネームする |

### タイトル後処理アルゴリズム

| `indexer.pptxnumbering` | 動作 |
| ----------------------- | ---- |
| `no`（省略時の既定） | スライドタイトルを変更しない |
| `chapt_section` | `chapter` / `section` カウンタに従い、`#CHAPT#` / `#SECTION#` / `#STAY#` マーカーでスライドタイトルを連番付与形式に書き換える。`#NOREPLACE#` があるスライドも連番タイトル書き換えは実行される |
| `idresolve` | `output.idresolvedfilename` を読み込み、各スライドのノートから `{{#id:<TYPE>:<PART>:<LOCAL>}}` を検出して、一致する `full_id` の `label` でスライドタイトルを置き換える |

#### idresolve モードの動作詳細

idresolve モードのタイトル後処理は、**定義マーカー**と**参照マーカー**の 2 系統をノートから読み取る。

| マーカー | 種別 | FULL_ID 重複 | idcollect | タイトルへの作用 |
|---|---|---|---|---|
| `{{#id:FULL_ID}}` | 定義 | 不可（一意前提） | 収集する | その ID を定義したスライドのタイトルを `label` で置換 |
| `{{enclosenum:FULL_ID}}` | 参照 | 可（複数スライド可） | 収集しない | `number` を `"(number) スライドタイトル"` の形式で前置（元タイトルは保持） |
| `{{titlelabel:FULL_ID}}` | 参照 | 可（複数スライド可） | 収集しない | タイトルを `label` で置換 |

- `FULL_ID` = `<IDENTIFIER_TYPE>:<PART_ID>:<LOCAL_ID>`。`number` / `label` は `output.idresolvedfilename` の `entries` から `full_id` 一致で引く。
- 参照マーカー（`{{enclosenum:}}` / `{{titlelabel:}}`）は ID を**定義しない**ため idcollect の inventory に拾われず、同一 FULL_ID を複数スライドで使える。これらは pptmdexport が MD 出力時に除去する（[pptmdexport のノート専用参照マーカー除去](#ノート専用参照マーカーの除去)参照）ため、`{{BLOCK:MD}}` の `export-note:` 直後など MD ブロック内に記述してもエクスポート MD には残らない。pptmerge idresolve は結合済み pptx のノート原文を走査するため、MD から除去されても番号付けは正しく機能する。
- 参照先の FULL_ID は、別の md（`{{#id:}}`）等で定義され resolved に存在している必要がある。

各マーカーごとの処理:

1. ノートから上記マーカーを抽出する
2. `FULL_ID` で resolved の `entries` を検索する
3. 一致が 1 件 → 上表の作用を適用する
4. 一致が 2 件以上 → 警告を出力してスライドタイトルは変更しない
5. 一致が 0 件 → 警告を出力してスライドタイトルは変更しない

同一スライドに label 置換系（`{{#id:}}` / `{{titlelabel:}}`）と番号前置（`{{enclosenum:}}`）が混在する場合、**ノート上の記述順に関わらず** label 置換を先に適用し、番号前置を最後に適用する。したがって両方ある場合の結果は常に `"(number) label"`（label 置換がなければ `"(number) 元タイトル"`）となる。

補足:

- `{{#id:}}` 行に `{{nolabel}}` がある場合は、その定義による label 置換をスキップする（参照マーカーには適用しない）
- `#NOREPLACE#` を含むスライドは全マーカーのタイトル置換をスキップする
- タイトルの書き換えは XML 直接操作で行い、段落配置・ランのフォント書式を保持する（[タイトル書式の保持](#タイトル書式の保持) 参照）

> 用途例: ある章タイトルを定義した md に付与された `number`（例: `3`）を、関連する複数の PPTX スライドのタイトル先頭に `(3) ` として表示したい場合、それらのスライドのノートに `{{enclosenum:chapter:proj:intro}}` を記述する。

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
  - insertpptx: doc_a.pptx
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
| `#CSL#` テキスト除去（CSL マーカー消去処理） | 実行 | スキップ |
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

### マーカーの分類と処理タイミング

マーカーを 2 つに分けて扱う。

| 分類 | 対象 | 処理する場所 |
| ---- | ---- | ------------ |
| **一般マーカー** | `#CSL#` 以外のすべて（`#CSP#` / `#TEMP#` / `#MEMO#` / `#CHAPT#` / `#SECTION#` / `#STAY#` など） | 個別 pptx でも結合済み pptx でも処理してよい |
| **CSL マーカー** | `#CSL#` のみ | **結合済み pptx に対して pptmerge の最後でのみ**処理する |

CSL マーカーへの処理は 2 種類ある。

| 処理 | 内容 | 適用条件 |
| ---- | ---- | -------- |
| **CSL スライド削除処理** | `#CSL#` を含むスライドを削除する | `indexer.deletecsl: true` / `--deletecsl on` |
| **CSL マーカー消去処理** | スライドは残し `#CSL#` 以降のテキストを除去する | `indexer.deletecsl: false`（既定）/ `--deletecsl off` |

全体方針として **CSL スライド削除は pptmerge の最後にのみ行う**。したがって:

- `--preprocess` で個別 pptx を前処理する際は CSL マーカーを**残す**
- `ppt_to_pdf` / `ppt_to_transfer` / `ppt_to_puremd` パイプラインでは CSL マーカーを**一切処理しない**（[パイプライン仕様](pipelines.md)参照）

### 一般マーカーの動作

| マーカー | `deletecsp` が false | true |
| -------- | -------------------- | ---- |
| `#CSP#` | `#CSP#` テキストを除去（シェイプは残す） | シェイプごと削除 |
| `#TEMP#` / `#MEMO#` | — | 常にシェイプごと削除 |

検出対象はテキストフレーム・テーブルセル・グループ子要素（再帰）に及ぶ。テーブルセルにマーカーが含まれる場合はテーブルシェイプごと削除される。

`#NOREPLACE#` があるスライドでも `deletecsp` / `#TEMP#` / `#MEMO#` のシェイプ削除はスキップされない。

### CSL マーカーの動作

| 項目 | 内容 |
| ---- | ---- |
| 判定 | スライドの全シェイプテキスト（グループ・表セルを含む）を連結して `#CSL#` の有無を見る |
| スライド削除 | `sldIdLst` から該当エントリを除去し、パート関連（rel）も破棄する |
| マーカー消去 | ラン単位で `#CSL#` 以降を行末まで除去する。**ランをまたいだ文字は残る** |
| 付番との順序 | 付番（章・節番号付きタイトル書き換え）→ CSL スライド削除の順。削除されたスライドが消費した番号は飛ぶ |
| 全スライドが対象の場合 | 空の pptx になるのを避けるため、警告を出して削除をスキップする |
| `#NOREPLACE#` | マーカー消去はスキップする。スライド削除はスキップしない |

同じ処理は [pptdeletecsl](#pptdeletecsl) サブコマンドで任意の既存 pptx にも単独で適用できる（実装は共有）。

#### グループシェイプの特別処理

グループシェイプの**グループ名**（PowerPoint のシェイプ名）に `#CSP#` が含まれ、`deletecsp: true` の場合は、グループ内の子要素を検査せずにグループごと削除する。グループ名に `#CSP#` がない場合は子要素を再帰的に検査する。

---

## pptimgexport

### 概要

PPTX ファイルの各スライドのノートに記述されたメタデータを読み取り、対応する PDF ページから指定範囲の画像を切り出して PNG ファイルとして保存する。python-pptx と pymupdf（fitz）を使用し、win32com は不要（Windows 以外でも動作する）。

> **制約: アニメーションには対応しない。** PDF 書き出しは 1 スライド = 1 ページで全オブジェクトが配置された状態を 1 枚描くため、クリック送りで段階的に出現する図は「全段階が重なった最終状態」としてしか得られない。段階ごとの画像が必要な場合は、原稿側で段階ごとのスライドに分ける。検討した自動化案と技術メモは [design_pptx_animation_capture.md](../design_pptx_animation_capture.md) を参照。

### 使用例

```bash
# PDF から画像を切り出して保存
pptmdmerge pptimgexport recipe.yaml

# 既存ファイルを上書き
pptmdmerge pptimgexport recipe.yaml --force

# ドライラン（ファイルを書き込まない）
pptmdmerge pptimgexport recipe.yaml --dry-run
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

各スライドのノートは [NOTE_CONTENT_FORMAT](../note_content_format.md) に従って記述する。`IMAGE_BLOCK`（`{{BLOCK:IMAGE}}`）に画像エクスポート指示を記述する。1 スライドに複数の `IMAGE_BLOCK` を記述した場合はすべて処理される。

各 `IMAGE_BLOCK` の `CONTENT_BODY` には以下のキー: 値 ペアを記述する。行ごとに 1 ペア。

```text
export-image-mode: slide_with_rectpct
export-image-target: CropRect
export-image: images/fig01.png
```

| キー | 説明 |
| ---- | ---- |
| `export-image-mode` | 切り出しモード（下表参照）。未指定・未知の値は**警告して**処理対象外とする |
| `export-image-target` | 参照するシェイプの名前。`slide` モードでは不要。**スライド直下のシェイプのみ**が対象で、グループ化された子シェイプは使えない（座標が親の子座標系で表されるため）。グループ内に同名シェイプがある場合は「グループを解除してください」と警告する |
| `export-image` | 出力ファイルパス。相対パスは PPTX ファイルの親ディレクトリを基準に解決する |
| `export-image-inset` | 出力ピクセル単位のインセット（整数、省略時 0）。**正でクロップ枠を外側へ拡大**（枠線を確実に含めたいとき）、負で内側へ縮小。画像範囲にクランプする。全モードで有効 |
| `export-image-step` | アニメーションの途中ステップを切り出す（省略時は PDF から最終状態）。[下記](#アニメーションのステップ切り出しexport-image-step)参照 |

> **基準ディレクトリの規約:** `export-image` の相対パスは **PPTX のディレクトリ**基準、同じノートの `{{BLOCK:MD}}` 内に書く `![](...)` は切り出された **MD のディレクトリ**基準で解決される。両方を `../images/名前.png` と同じ綴りで書けるのは、`src/`（pptx）と `mds/`（切り出した MD）を**同じ階層に置く**という構成を前提にしているため。この 2 つを別階層に移すと一方が壊れる。構成の規約と判断の経緯は [design_image_refs.md](../design_image_refs.md) を参照。

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
| `slide_with_rectpct` | シェイプ名 | 指定したシェイプ（領域マーカー）の境界でスライド画像の一部を切り出す（浮動小数点精度） |

#### `slide_with_rectpct` モードの座標計算（L/T/R/B）

シェイプの境界ボックスをスライド全体に対するパーセントに変換する（**丸めなし＝浮動小数点**。`named_shape` と同じ計算）。

```
L = shape.left                    / slide_width  × 100
T = shape.top                     / slide_height × 100
R = (shape.left + shape.width)    / slide_width  × 100
B = (shape.top  + shape.height)   / slide_height × 100
```

> **補足（枠線について）**: かつては整数パーセントに四捨五入していたが、各辺で最大 ±0.5%（描画解像度で数〜十数 px）ずれ、シェイプの枠線（境界をまたいで描画される）が「入ったり消えたり」した。同じ大きさのシェイプを移動しただけで挙動が変わるのはこのため。現在は浮動小数点で実エッジに追従し、この不安定さを解消している。枠線を**確実にすべて含めたい**場合は `export-image-inset` に正の値（数 px）を指定してクロップ枠を外側へ広げる。

`named_shape` モードでは整数丸めを行わず浮動小数点のまま使用する。

#### アニメーションのステップ切り出し（`export-image-step`）

PDF は全オブジェクトが出揃った最終状態しか持たない。クリックで段階的に出る図の途中状態は、`export-image-step` を書いた IMAGE ブロックだけ**スライドショーを COM で再生してウィンドウをキャプチャ**して切り出す（**Windows 専用**、デスクトップ版 PowerPoint が必要）。設計と経緯は [design_pptx_animation_capture.md](../design_pptx_animation_capture.md)。

```text
export-image-mode: slide_with_rectpct
export-image-target: exportrange
export-image-step: 0-3, 5
export-image: ../images/<__BASEFILENAME__>_slide<__SLIDENUM__>_step<__STEP__>.png
```

| 値 | 意味 |
| -- | ---- |
| 省略（空） | 従来どおり PDF から切り出す（最終状態） |
| `0` | クリック前の状態 |
| `N` | N 回クリックした後の状態 |
| `0-3, 5` | 範囲とカンマ区切り。重複は 1 つにまとめ昇順に処理 |
| `all` | `0` 〜 最終ステップの全部 |
| `last` | 最終ステップ（最終状態をキャプチャで撮る） |

* `export-image:` 内の `<__STEP__>` はステップ番号（素の整数）に展開する。**複数ステップ（範囲・カンマ・`all`）では必須**
* モード・`export-image-target`・`export-image-inset` は PDF 経路と同じ意味で使える
* **解像度**: キャプチャしたスライド領域を、`cropsrc` の `dpi` で PDF をラスタライズしたときと**同じピクセル寸法**へリサンプルしてから切り出す。出力寸法は PDF 経路と一致し、モニタに依存しない。スライドショーウィンドウは目標寸法以上になるよう自動で広げる。それでも足りず 1.05 倍を超えて拡大する場合は警告する
* pptx 1 つにつきスライドショーを 1 回起動する。実行中はスライドショーのウィンドウが画面に出る（前面である必要はない）。**最小化・画面ロック中は撮れない**
* 非表示スライドもキャプチャできる
* `--dry-run` では PowerPoint を起動しない（`all` / `last` は展開せずに表示）

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
* `export-image-step` の書式が不正（該当ブロックのみ失敗、他は継続）
* 複数ステップ指定なのに `export-image` に `<__STEP__>` が無い（同上）
* 指定ステップがスライドのステップ数を超える（超えた分のみ失敗）
* Windows 以外で `export-image-step` を指定、またはスライドショーを起動・キャプチャできない

### 警告条件（該当 IMAGE ブロックをスキップし、コマンド自体は継続）

* `export-image-mode` が不正な値（typo 等）
* `export-image-mode` が未指定だが他の `export-image-*` に値がある（書きかけの不備。全項目が空の IMAGE ブロックはプレースホルダとして無警告でスキップ）
* `export-image` が未指定（mode は有効だが出力先が空）
* `export-image-target` が未指定（`named_shape` / `slide_with_rectpct` モード）
* `export-image-target` に指定したシェイプ名がスライド上に存在しない
* `export-image-inset` が整数でない（`0` を使用して継続）

### 処理ステップ

| ステップ | 内容 |
| -------- | ---- |
| パス解決 | `input.cropsrc.pptx` と `input.cropsrc.pdf` を解決し、両ファイルの存在を確認する |
| PPTX 読み込み | python-pptx で PPTX を開き、スライドサイズ（幅・高さ）を取得する |
| プレースホルダー置換 | 各スライドのノートテキストに `<__TITLE__>` / `<__FILENAME__>` / `<__BASEFILENAME__>` / `<__SLIDENUM__>` を置換する（ノート解析前） |
| ノート解析 | 置換済みノートテキストを NOTE_CONTENT_FORMAT として解析し、すべての `IMAGE_BLOCK` の `CONTENT_BODY` をキー: 値として読み取る。`export-image-mode` が既知の値のブロックを処理対象とする |
| 座標計算 | モードに従い L/T/R/B を決定する。`slide` は固定値、`named_shape` / `slide_with_rectpct` は浮動小数点。`export-image-inset` 指定時は出力 px 単位でクロップ枠を拡大／縮小する |
| タスク一覧表示 | スライド番号・モード・シェイプ名・L/T/R/B・出力先の一覧を標準出力に表示する |
| ステップキャプチャ | `export-image-step` 付きのタスクのみ。スライドショーを起動して各ステップを撮り、`dpi` 相当の寸法へリサンプルしてから同じ座標でクロップする |
| PDF クロップ | pymupdf で PDF を開き、`dpi` 解像度でページをラスタライズし、PIL で座標範囲をクロップして PNG として保存する |
| `--dry-run` | ファイルへの書き込みを行わず実行内容のみ表示する |
| `--json` | 処理結果（タスク一覧・クロップ結果）を JSON 形式で標準出力へ出力する |

---

## pptmdexport

### 概要

PPTX ファイルの各スライドのノートに記述されたブロック構造を解析し、`export-note:` 指示がある場合はその次のブロックの MD テキストを指定ファイルに出力する。python-pptx を使用し、win32com は不要。

### 使用例

```bash
pptmdmerge pptmdexport recipe.yaml
pptmdmerge pptmdexport recipe.yaml --force
pptmdmerge pptmdexport recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--force` | 既存の出力ファイルを上書きする | 任意 |
| `--closepptx` | 処理完了後に PPTX ファイルを close する（省略時は close しない） | 任意 |
| `--latex-check` `{off\|warn\|error}` | 抽出した MD ブロック内の pandoc raw passthrough（`{=latex}` / `{=html}` 等）を検出する。`warn`=警告のみ・`error`=当該ファイルを書き出さず非ゼロ終了・`off`=無効。省略時はレシピ `pptmdexport.latex_check`、それも無ければ `warn`。CLI がレシピより優先 | 任意 |

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

pptmdexport:
  latex_check: warn           # off | warn | error（省略時 warn）。--latex-check で上書き可
```

`cropsrc` は辞書形式（単一）またはリスト形式（複数）のどちらでも指定できる。

### 生 raw コードの検出（latex_check）

原稿 pptx の MD ブロックには、最終出力形式（PDF / MD / HTML）に依存しない**セマンティックな記述**のみを書くことを推奨する。pandoc の raw attribute（` ```{=latex} ` フェンスや行内 `` `…`{=latex} ``）のような**特定形式専用の生コード**は、他形式への lowering で失われるため原稿には書くべきでない。

`latex_check` は、抽出した各 MD ブロックを次の 2 点について走査する。

1. `{=FORMAT}`（`{=latex}` / `{=html}` 等、任意の raw attribute）
2. **フェンスなしの LaTeX コマンド**（本文に直接書いた `\hspace*{4em}` / `{\bfseries …}` / `\vspace{5mm}` など）。pptmdexport は本文のバックスラッシュをエスケープするので、これらはどの出力形式でも効かず文字どおり表示される。コードブロック・インラインコード・fenced div / span の属性値（`{.widequote width="0.6\linewidth"}` 等。フィルタが読み替える）・Markdown のエスケープ（`\*` `\_` `\\`）は対象外

| モード | 動作 |
|---|---|
| `off` | 検出を行わない |
| `warn`（既定） | 検出したスライド番号・出力ファイル名・検出個数・最初の行番号を警告ログに出力し、処理は継続する |
| `error` | 同内容をエラーログに出力し、**当該 MD ファイルは書き出さず**、コマンド全体を非ゼロ終了（`EXIT_FAILURE`）させる |

- 言語タグ付きコードフェンス（` ```latex ` のような `=` の無い形式）は通常のコードリスト表示なので検出しない。
- `ppt_to_pdf` / `ppt_to_transfer` / `ppt_to_puremd` パイプライン内の `pptmdexport` ステップにも適用される（パイプラインには専用 CLI フラグが無いため、レシピ `pptmdexport.latex_check` で指定する）。
- 既存の生 latex を一括変換するまでの移行期間は `warn` で検出・可視化し、移行完了後に `error` で再混入を防ぐ運用を想定する。

### スライドノートのブロック構造

各スライドのノートは [NOTE_CONTENT_FORMAT](../note_content_format.md) に従って記述する。`MD_BLOCK`（`{{BLOCK:MD}}`）に MD テキストを記述する。1 スライドに複数の `MD_BLOCK` を記述した場合はすべて処理される。

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
* MD 本文の `\` と `&` を LaTeX 向けに `\\` / `\&` へエスケープする。コードブロック・インラインコードの中と、**先頭の YAML frontmatter（`---` … `---`。直前の空行・`<!-- -->` 行は許容）は対象外**。frontmatter は pandoc がメタデータとして読むだけで LaTeX に直接出ず、`transfer`（Astro）と `notecomexport`（note.com）が `title` / `excerpt` 等をそのまま使うため、エスケープすると Web 側にバックスラッシュが漏れる
* スライドのタイトル枠にテキストがある場合、MD の先頭に `<!-- md_merge_rawtitle: <スライドタイトル> -->` ディレクティブ行を付加する。これは MD 本文のエスケープ対象外（生テキスト。改行は空白に畳み、`-->` は無害化）。`merge` 後の結合 MD にそのまま残り、`idcollect` がこれを読み取って inventory の `rawtitle` フィールドに格納する。`idresolve`・`render` では `{{rawtitle:FULL_ID}}` で参照できる

#### サンプルファイル（procedure 貼り付け用）

`procedure` に貼り付けるためのサンプルを 1 つのファイル `output.insertsamplefilename`（省略時は `output.targetbasefilename` から `{base}_insertsample.yaml` を自動生成。`output.outputdir` 配下）に書き出す。各行頭は空白2個でインデント。エントリは入力レシピの `version` の procedure 記法で書く（version 2 は `- insertpptx: ...`、version 1 は `- operation: insertpptx`）。`--dry-run` 時は書き出さない。出力先が未設定（`targetbasefilename` も `insertsamplefilename` も無い）の場合は生成しない。

ファイルは **3 ブロック**で構成する。各ブロック内は cropsrc の登場順 → スライド順に列挙する（cropsrc が複数あれば各ブロックで全 pptx をまたいで列挙）。

| ブロック | 内容 |
| -------- | ---- |
| ブロック1 | 各 pptx の**全スライド**を `insertpptx`（1 スライド 1 エントリ）として列挙 |
| ブロック2 | 出力した各 MD を `insertmd` として列挙 |
| ブロック3 | 両者のミックス。**スライド単位**で、その slide の `insertpptx` の直後にその slide 由来の `insertmd` を並べたもの。スライドが変わる境界に**スライドセパレータ行**（コメント）を挿入する |

**NEW PPTX セパレータ**: 全ブロック共通で、pptx が変わる境界（各 pptx の先頭エントリの直前）に、その pptx の区切りを示すコメント行を挿入する（ファイル名は basename）。ブロック2 では md エントリを持つ pptx の先頭のみに挿入する。書式は次のとおり。

```
  # __________ NEW PPTX: deck.pptx __________
```

**スライドセパレータ（ブロック3 のみ）**: スライドの先頭（その slide の `insertpptx` の直前、NEW PPTX セパレータがある場合はその後）に置くコメント行で、**スライド番号を先・pptx ファイル名を後**に記す（ファイル名は basename）。書式は次のとおり。

```
  # ----------- slide 1 deck.pptx -----------
```

```yaml
  # ===== ブロック1: insertpptx サンプル =====
  # __________ NEW PPTX: deck.pptx __________
  - insertpptx: src/deck.pptx
    slides: 1
    description: PPT & MD merger とは？

  # ===== ブロック2: insertmd サンプル =====
  # __________ NEW PPTX: deck.pptx __________
  - insertmd: deck_slide1_md.md
    description: PPT & MD merger とは？

  # ===== ブロック3: insertpptx + insertmd ミックス（スライド単位） =====
  # __________ NEW PPTX: deck.pptx __________
  # ----------- slide 1 deck.pptx -----------
  - insertpptx: src/deck.pptx
    slides: 1
    description: PPT & MD merger とは？
  - insertmd: deck_slide1_md.md
    description: PPT & MD merger とは？
  # ----------- slide 2 deck.pptx -----------
  - insertpptx: src/deck.pptx
    slides: 2
    description: 次のスライドのタイトル
```

`description` は、insertmd では各 MD の**最初の Markdown 見出し**、insertpptx ではその**スライドのタイトル枠テキスト**。いずれも `<__TITLE__>` / `<__BASEFILENAME__>` 等のスライドプレースホルダー（置換済み）に加えて、レシピ `vars:` による `{{v:VARIABLE}}` 置換を適用する（未定義の変数はそのまま残す）。`{{num/title/label:FULL_ID}}` 等の `#id` 参照変換は行わない。insertpptx の値（ファイル名）は `input.cropsrc[].pptx` の指定値、`slides` は 1 始まりのスライド番号。`description` は merge / pptmerge では無視される補助情報。

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
| ファイル書き出し | `MD_BLOCK` の 2 行目以降を MD テキストとして出力ファイルに書き込む（ノート専用参照マーカーは除去する。後述） |
| `--dry-run` | ファイルへの書き込みを行わず実行内容のみ表示する |
| `--json` | 処理結果（タスク一覧・書き出し結果）を JSON 形式で標準出力へ出力する |

#### ノート専用参照マーカーの除去

`MD_BLOCK` の本文に含まれる pptmerge idresolve 専用の参照マーカー（`{{enclosenum:FULL_ID}}` / `{{titlelabel:FULL_ID}}`）は、MD には不要なためエクスポート時に除去する。

- マーカーだけの行は行ごと削除する。行内に他の内容があればマーカー部分のみ除去する。
- 定義マーカー `{{#id:...}}` や `{{nolabel}}`、参照 `{{num:...}}` / `{{label:...}}` / `{{title:...}}` / `{{rawtitle:...}}` は MD 側で idcollect / render が使うため除去しない。
- これにより参照マーカーを `export-note:` 直後など MD ブロック内に記述してもエクスポート MD に残らない。pptmerge idresolve は結合済み pptx のノート原文を参照するため、番号付け・タイトル置換は正しく機能する（[pptmerge の idresolve モードの動作詳細](#idresolve-モードの動作詳細)参照）。

---

## pptyamlexport

### 概要

PPTX スライドのノートの `YAML_BLOCK`（`{{BLOCK:YAML}}`）から、別システム投入用の図版定義 YAML を書き出すサブコマンド。python-pptx のみを使用しクロスプラットフォームで動作する。

`pptmdexport` とは扱うデータが根本的に異なる（PDF 文書用の散文 MD ではなく、座標を持つ構造化データ）ため、別サブコマンドとして独立している。共通するのは `input.cropsrc` の解決とスライド走査だけで、MD 側の後処理（バックスラッシュエスケープ・`rawtitle` コメント付与・`latex_check`・insertsample 生成）は一切行わない。

ノート本文は**投入先 YAML そのものをテンプレートとして**記述し、slot の座標には `auto` を書く。`auto` はスライド上の名前付きシェイプの実位置から、`baseframe` シェイプの矩形内の相対値（0〜1）として算出して埋める。トップレベルの `regions`（領域の定義）も slot とまったく同じ規則で解決する。

### 使用例

```bash
# ノートの YAML ブロックから図版定義 YAML を書き出す
pptmdmerge pptyamlexport recipe.yaml

# 既存ファイルを上書き
pptmdmerge pptyamlexport --force recipe.yaml

# ドライラン（ファイルを書き込まない）
pptmdmerge pptyamlexport --dry-run recipe.yaml
```

### 固有オプション

| オプション | 説明 |
|---|---|
| `--workdir DIR` / `-w DIR` | 相対パスの基準ディレクトリ |
| `--force` | 既存の出力ファイルを上書きする |
| `--closepptx` | 処理後に PPTX を閉じる |

### レシピ YAML スキーマ

`pptmdexport` / `pptimgexport` と同じ `input.cropsrc` を使う。固有の設定キーは持たない。

```yaml
input:
  cropsrc:
    pptx: slides/deck.pptx
```

### ノートの記述

```
NOTE_CONTENT_FORMAT: 1.0

===BLOCK===
{{BLOCK:IMAGE}}
export-image-mode: named_shape
export-image-target: exportrange
export-image: sample.png

===BLOCK===
{{BLOCK:YAML}}
id: sample
title: "サンプル図: 原因・結果・対策"
image: sample.png
baseframe: exportrange

slots:
  - id: slot1
    x: auto
    y: auto
    width: auto
    height: auto
    font_size: 0.022
    font_family: sans-serif
    text_align: center
    vertical_align: middle

regions:
  - id: regionA
    label: 上
    x: auto
    y: auto
    width: auto
    height: auto
    snap: true

samples:
  - key: model
    name: 模範解答
    standard: true
    values:
      slot1: 睡眠時間の不足
```

| キー | 説明 |
|---|---|
| `id` | 図版 ID（必須）。`export-note` 未指定時は出力ファイル名 `{id}.yaml` の基になる |
| `export-note` | 出力ファイル名（省略時は `{id}.yaml`）。**出力 YAML には残らない** |
| `baseframe` | 座標の基準となるシェイプ名。**出力 YAML には残らない**。slot / region に `auto` があるとき必須（予約値 `slide` と省略時の推論は後述） |
| `image` | 図版の PNG。省略時は `baseframe` を切り出す IMAGE ブロックの `export-image` から補完される |
| `type` | 定義の種類。`module` を書くと **`slots` が任意**になる（`regions` だけの部品定義用）。値は解釈せずそのまま出力へ通す |
| `kind` | 定義の種別。`reading` を書くと **`slots` が任意**になる（slot を持たない読み物定義用）。値は解釈せずそのまま出力へ通す |
| `slots[].id` | slot ID。`auto` 解決時は**同名のシェイプ名としても使われる** |
| `slots[].x` / `y` / `width` / `height` | `auto` ならシェイプ位置から算出、数値ならその値をそのまま使う（**キー単位で混在可**）。**キーごと省略した場合は `auto` とみなす** |
| `regions[]` | 領域の定義（任意）。`id` / 座標の扱いは `slots[]` とまったく同じ |

`slots` は必須（キーが無いとエラー）。ただし `type: module` と `kind: reading` を書いた定義では任意で、前者は `regions` だけの部品定義、後者は slot を持たない読み物定義を書ける。**省略を許すだけ**で、`slots` が書かれていれば扱いは同じ（`auto` も通常どおり解決し、形式も検証する）。

#### 座標の基準（`baseframe`）

slot / region に `auto`（キーの省略を含む）があるとき、座標の基準となる矩形を次の順で決める。

| `baseframe` | 基準になる矩形 |
| ----------- | -------------- |
| シェイプ名 | そのシェイプの境界ボックス（スライド直下にあること。グループ内はエラー） |
| `slide`（予約値） | **スライド全体**。`export-image-mode: slide` で切り出した PNG の範囲と一致する |
| 省略 | 同じスライドの IMAGE ブロックが `export-image-mode: slide` なら**スライド全体**を基準にする（PNG の範囲がスライドそのものに決まるため）。それ以外（`named_shape` / `slide_with_rectpct` のクロップ画像）は基準が定まらないのでエラー |

`slide` は予約値なので、`slide` という名前のシェイプを基準にはできない（別名を付けること）。

`auto` 以外のキー（`font_size` / `font_family` / `text_align` / `vertical_align` / `label` / `snap` など）は解釈せずそのまま出力へ通す。

1 スライドに複数の `YAML_BLOCK` を記述した場合はすべて処理される。空の `YAML_BLOCK` はプレースホルダとみなし黙ってスキップする。

### ノート YAML での `_include`

`YAML_BLOCK` の本文は、**レシピ YAML とまったく同じ規則**で読み込む。`_include` / `_constants` / `__CONSTANT__` がそのまま使える（規則は [md_merge_spec 5.1](../md_merge_spec.md#51-レシピ-yaml-の-_include)）。

```
===BLOCK===
{{BLOCK:YAML}}
_include: figdefs/common_head.yaml
id: sample
title: "サンプル図"
baseframe: exportrange

slots:
  _include: figdefs/threebox_slots.yaml
```

| 形式 | 動作 |
|---|---|
| マッピング内の `_include: PATH`（リスト可） | 読み込み先のマッピングを合成する。同じ階層の兄弟キーが優先される |
| `slots:` の下に `_include: PATH` だけ | 兄弟キーが無いので、読み込み先の値（list など）でそのまま置き換える |
| トップレベルの `_constants: PATH.toml` | TOML の定数ファイルを読み込む（キー自体は出力されない） |
| `__NAME__` | 定数を置換。組み込みは `__DATE__` / `__TIME__` / `__DATETIME__`、ほかに `--constants` と `_constants` で与えたもの |

旧書式の `!include` / `!constants`（パース前の行単位のテキスト展開）も非推奨の警告付きで動く。

**パスの基準**

| 位置 | 基準ディレクトリ |
|---|---|
| ノート内の `_include` | **元 PPTX と同じディレクトリ**（`export-note` / `export-image` と同じ基準） |
| 取り込み先ファイル内の `_include`（入れ子） | **その取り込み先ファイル自身のディレクトリ** |

入れ子は再帰的に展開し、循環参照はエラーにする。

**注意**

* 展開は**エクスポート時**に行われ、出力 YAML には**展開後の内容**が書き出される。投入先システムは `_include` を解釈しなくてよい。
* 取り込み先ファイルはそれ自体が妥当な YAML であること（list・スカラー 1 個も可）。断片を行単位で差し込む必要があるときだけ旧書式を使う。
* プレースホルダー置換（`<__TITLE__>` / `<__SLIDENUM__>` など）はノート本文にのみ適用される。**取り込み先ファイルの中身には適用されない**（ノート側の `_include` のパス指定には使える）。
* `--dry-run` でも展開は行われるため、取り込み先ファイルが無ければ dry-run でもエラーになる。

### 座標の算出

`baseframe` シェイプの矩形を単位正方形とみなし、slot シェイプの境界ボックスを相対値に変換する。

```
x      = (slot.left - base.left) / base.width
y      = (slot.top  - base.top)  / base.height
width  =  slot.width  / base.width
height =  slot.height / base.height
```

小数第 4 位に丸める（EMU 由来の除算で生じる浮動小数点ノイズの除去。PNG 数千 px でもサブピクセル精度）。

**座標キーの省略は `auto` の省略記法**。`x` / `y` / `width` / `height` を書かなければ `auto` を書いたのと同じ扱いになり、算出した値が出力 YAML に補われる。したがって 4 つとも自動算出でよければ slot は `id` だけでよい。

```yaml
slots:
  - id: slot1          # x/y/width/height を省略 ＝ 4 つとも auto
    font_size: 0.022
  - id: slot2
    x: 0.9             # 明示した値はそのまま、省略した y/width/height だけ算出
    font_family: serif
```

補った座標は**元のキー順を保ったまま `id` の直後に `x` → `y` → `width` → `height` の順で差し込む**（末尾に追記するとキー順が崩れて読みにくいため）。一部だけ明示している場合も、明示したキーは書いた位置のまま、補ったキーがその並びに収まる。

省略したキーがあると `auto` と同じく **slot と同名のシェイプが必須**になる点に注意（シェイプが無ければエラー）。全 4 キーを数値で明示した slot は従来どおりシェイプを探さない。

**シェイプの回転は反映しない**（境界ボックスから算出するため）。回転したシェイプを slot に使うと警告する。

**グループ内のシェイプは使えない**。python-pptx はグループの子シェイプの `left` / `top` を親グループの子座標系で返すため、スライド基準の相対値を算出できない。グループ内に同名シェイプがあればその旨をエラーで示すので、グループを解除して配置する。

### `regions` の座標

トップレベルの `regions` は領域の定義で、**`slots` とまったく同じ規則**で解決する（任意のセクション。書かなければ何もしない）。`id` が同名のシェイプ名として使われ、`x` / `y` / `width` / `height` が `auto` またはキーごと省略されていれば、そのシェイプから `baseframe` 内の相対値を算出して埋める。

```yaml
# ノートに書く
regions:
  - id: regionA
    label: 上
    x: auto
    y: auto
    width: auto
    height: auto
    snap: true
  - id: regionB      # 4 キーとも省略 ＝ 4 つとも auto
    label: 下
    snap: false
```

```yaml
# 出力（regionA / regionB シェイプの矩形を baseframe 内の相対値に変換）
regions:
  - id: regionA
    label: 上
    x: 0.05
    y: 0.05
    width: 0.9
    height: 0.3
    snap: true
  - id: regionB
    x: 0.05
    y: 0.5
    width: 0.9
    height: 0.3
    label: 下
    snap: false
```

* `label` / `snap` など座標以外のキーは解釈せず**そのまま出力へ通す**。
* 算出式・丸め・キー順の差し込み規則・`id` 重複やシェイプ未発見のエラーは `slots` と共通。
* 領域を示すシェイプ（`regionA` など）も **baseframe に切り出す PNG の中に写り込む**点に注意。枠線・塗りを無しにするか、PNG に写ってよい印にしておく。

### `samples[].layout`（廃止）

サンプル解答ごとの配置を書く `samples[].layout` は**廃止した**。代わりにトップレベルの `regions` を使う。ノートに残っていれば**警告**し、座標は算出せずそのまま出力へ通す。

### 出力

`export-note`（省略時 `{id}.yaml`）が絶対パスならそのまま、相対パスなら**元 PPTX と同じディレクトリ**を基準に解決する（`pptmdexport` / `pptimgexport` と同じ）。

出力 YAML は入力のキー順を保ち、`export-note` と `baseframe`（ノート側の指示専用キー）を取り除いたもの。シーケンスは親キーの下に 2 スペース字下げして出力する。

### 検査と警告

| 条件 | 扱い |
|---|---|
| YAML として解析できない / トップレベルがマッピングでない | エラー |
| `_include` の取り込み先ファイルが見つからない / 循環参照 | エラー（スライド番号を添えて報告） |
| `id` が未指定 | エラー |
| `baseframe` のシェイプが見つからない | エラー |
| slot / region に `auto`（または省略された）座標があるが `baseframe` 未指定 | エラー |
| slot / region と同名のシェイプが見つからない（`auto` または座標キー省略のとき） | エラー |
| `slots` がリストでない（キーが無い場合を含む）。ただし `type: module` なら任意 | エラー |
| `regions` がリストでない / 要素がマッピングでない / `id` が無い | エラー |
| `baseframe` / slot / region のシェイプがグループ内にある | エラー（グループ解除を促す） |
| slot / region の `id` が重複 | エラー |
| 廃止した `samples[].layout` が書かれている | 警告（座標は算出せずそのまま出力） |
| `baseframe` を切り出す IMAGE ブロックに `export-image-inset` が指定されている | 警告（PNG の範囲が `baseframe` とズレて座標が合わない） |
| `image:` が IMAGE ブロックの `export-image` と一致しない | 警告 |
| `baseframe` を切り出す IMAGE ブロックが同じスライドに無い | 警告（整合を検証できない） |
| 座標が 0〜1 の範囲外 / `x+width` や `y+height` が 1 を超える | 警告（値は補正しない） |
| `text_align` / `vertical_align` の値が語彙外 | 警告 |
| slot のシェイプが回転している | 警告 |
| `export-note` の拡張子が `.yaml` / `.yml` でない | 警告 |

エラーが 1 件でもあれば終了コード 1。失敗したタスクは `pptimgexport` と同様、終了直前にまとめて再掲する。

---

## pptpdfexport

### 概要

PowerPoint COM 自動化（win32com）を使い、PPTX ファイルを PDF に変換するサブコマンド。Windows 専用（pywin32 が必要）。

生成した PDF は `pptimgexport` の入力（`input.cropsrc.pdf`）として使用できる。

**増分ビルド（既定動作）**: 出力 PDF が既に存在し、その更新時刻がソース PPTX 以上に新しい場合は、そのエントリの変換をスキップする（PDF が無い、または PPTX のほうが新しい場合のみ変換する）。全エントリがスキップ対象の場合は PowerPoint を起動せずに正常終了する。タイムスタンプを無視して常に作り直すには `--rebuild` を指定する。`--force` / `output.force` は再生成のトリガーにはならない（増分判定はそのまま有効）。

**--preprocess処理時は増分ビルドなし**: --preprocess オプションが指定されたときは、比較対象の PPTX が前処理後の PPTX に差し替わるため、増分ビルドは行われず常に再生成される。

### 使用例

```bash
# 増分ビルド（PDF が最新ならスキップ）
pptmdmerge pptpdfexport recipe.yaml

# タイムスタンプを無視して常に再生成
pptmdmerge pptpdfexport recipe.yaml --rebuild

# ドライラン（変換対象だけを表示）
pptmdmerge pptpdfexport recipe.yaml --dry-run
```

### 固有オプション

| オプション | 説明 | 必須 |
| ---------- | ---- | ---- |
| `--workdir` / `-w` DIR | input / output の相対パスをこのディレクトリ基準で解釈する | 任意 |
| `--rebuild` | 出力 PDF がソース PPTX より新しくても再生成する（タイムスタンプによるスキップを無効化） | 任意 |
| `--force` | 既存ファイル上書き用の共通フラグ。pptpdfexport では増分判定・再生成には影響しない（再生成は `--rebuild`） | 任意 |
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

## pptdeletecsl

### 概要

既存の pptx ファイルに対して CSL マーカー（`#CSL#`）の処理**だけ**を単独で行う。`pptmerge` の CSL 処理はマージ処理と一体になっているため、**すでに手元にある pptx** から後追いで `#CSL#` を落としたい場合にこのサブコマンドを使う。CSL マーカーを未処理のまま出力する `ppt_to_*` パイプラインの成果物に対する後処理としても使える。

他のサブコマンドと異なり、**入力はレシピ YAML ではなく pptx ファイルを CLI で直接指定する**。python-pptx のみで動作し、PowerPoint COM は使わない。

### コマンド形式

```bash
# #CSL# を含むスライドを削除して入力ファイルを直接書き換える（既定）
pptmdmerge pptdeletecsl merged.pptx

# 別ファイルへ出力する
pptmdmerge pptdeletecsl merged.pptx -o cleaned.pptx

# スライドは残し、#CSL# マーカー文字列だけを除去する
pptmdmerge pptdeletecsl merged.pptx --mode strip

# 削除対象スライドを確認するだけ（書き込まない）
pptmdmerge pptdeletecsl merged.pptx --dry-run
```

### オプション

| オプション | 説明 | 必須 |
|---|---|---|
| `PPTX`（位置引数） | 処理対象の pptx ファイル | 必須 |
| `--output` `-o` `PPTX` | 出力先 pptx。**省略時は入力ファイルを直接書き換える（in-place）** | 任意 |
| `--mode` `delete\|strip` | `delete`（既定）＝`#CSL#` を含むスライドを丸ごと削除／`strip`＝スライドは残しマーカー文字列のみ除去 | 任意 |
| `--force` | `--output` の既存ファイルを上書きする（in-place 時は不要） | 任意 |

共通オプション（`--log-level` / `--dry-run` / `--json`）も使用できる。

### モードの違い

`pptmerge` は結合済み pptx に対し `indexer.deletecsl` の値で CSL スライド削除処理／CSL マーカー消去処理を切り替える。本サブコマンドはその 2 つを `--mode` で明示的に選ぶ。処理の実体（`md_merge.pptmerge._csl`）は pptmerge と共有しているため結果は同一。

| モード | 処理 | 対応する pptmerge の挙動 |
|---|---|---|
| `delete`（既定） | スライドの全シェイプテキスト（グループ・表を含む）を連結し、`#CSL#` を含むスライドを削除する | `deletecsl: true`（CSL スライド削除処理） |
| `strip` | スライドは残し、ラン内の `#CSL#` 以降を行末まで除去する | `deletecsl: false`（CSL マーカー消去処理） |

### 動作仕様

| 項目 | 内容 |
|---|---|
| 判定対象テキスト | スライド内の全シェイプテキスト。グループ・表セルも再帰的に走査する |
| スライド削除 | `sldIdLst` から該当エントリを除去し、対応するパート関連（rel）を破棄する |
| マーカー除去（strip） | ラン単位で `#CSL#` 以降を行末まで削除する。**ランをまたいだ文字は残る**（`pptmerge` と共通の制約） |
| `#NOREPLACE#` | `strip` モードでは `#NOREPLACE#` を含むスライドを対象外とする。`delete` モードでは考慮せず削除する（いずれも `pptmerge` の結合済み pptx に対する挙動と同じ） |
| 全スライドが対象の場合 | 空の pptx が生成されるのを防ぐため、`delete` モードではエラー終了する（終了コード 1）。`pptmerge` の postprocess では同じ状況を警告＋スキップとして扱う（マージ自体は成功させるため） |
| 対象なしの場合 | 正常終了し、そのまま保存する（`--output` 指定時は入力のコピーが得られる） |

### 終了コード

| 状態 | コード |
|---|---|
| 正常終了 | 0 |
| pptx を開けない・保存できない／出力が既存で `--force` 未指定／全スライドが `#CSL#` 対象 | 1 |
| pptx が未指定／拡張子が `.pptx` でない | 2 |
| 入力ファイルが存在しない | 3 |
