# テンプレート変数置換・条件ブロック処理仕様

## 1. 目的

表紙 Markdown などのテンプレートファイル内に記述されたユーザー定義変数参照、および条件ブロックを、構成指示 YAML の `vars` セクションに定義された値に基づいて展開する。

主な用途は、`pandoc.cover-md`（PDF の表紙）に書いた表紙 Markdown を、レシピの値で埋めてから typst 断片に変換することである（[output_formats.md「表紙」](spec/output_formats.md#表紙cover-md--htmlcover)）。

> LaTeX 用の `condblockprocess` サブコマンド（`.tex` の表紙テンプレートを展開して `include-before-body` に渡す）は LaTeX と一緒に撤去した（2026-11-15）。記法と処理（`md_merge/_condblock.py`）はそのまま残り、下記の各段で使われる。

条件ブロック（`{{#if:...}}`）は表紙テンプレだけでなく、原稿 MD・PPTX ノートの MD / YAML ブロックにも書ける（[9. 適用箇所](#9-適用箇所)）。変数は起動時の `--var NAME=VALUE` で上書きできるので、同じ原稿から版違い（学生用／講師用、ドラフト／最終版など）を行単位で切り替えて出力できる。

---

## 2. 入力

### 2.1 テンプレートファイル

UTF-8 テキストファイル。

例：

```markdown
{{#if:COVERIMAGE}}
![]({{v:COVERIMAGE}}){width=40%}

{{vspace:2}}
{{#endif:COVERIMAGE}}

**{{v:TITLE}}**

著者：{{v:AUTHOR}}
```

### 2.2 変数定義

構成指示 YAML の `vars` セクションを使用する。

例：

```yaml
vars:
  TITLE: PPT & MD merger
  AUTHOR: 山田太郎
  CONTACT: https://example.com
  COVERIMAGE: figures/cover.png
```

---

## 3. 対応する記法

### 3.1 変数参照

```text
{{v:VARIABLE}}
```

`VARIABLE` は英数字とアンダースコアのみ使用可能とする。

正規表現：

```regex
\{\{v:([A-Za-z0-9_]+)\}\}
```

処理内容：

```text
vars.VARIABLE の値に置換する
```

例：

```text
{{v:AUTHOR}}
```

↓

```text
山田太郎
```

---

### 3.2 条件ブロック

```text
{{#if:VARIABLE}}
...
{{#else:VARIABLE}}      ← 任意
...
{{#endif:VARIABLE}}
```

タグは**必ず単独の行**に書く（前後の空白は可）。タグ行自体は出力しない。終了タグ・else タグには開始タグと同じ変数名を書く。

開始タグの書き方：

| 記法 | ブロックを残す条件 |
|---|---|
| `{{#if:NAME}}` | NAME が真（[6. 真偽の判定](#6-真偽の判定)） |
| `{{#if:!NAME}}` | NAME が偽 |
| `{{#if:NAME=VALUE}}` | NAME の値（文字列として比較）が VALUE と一致 |
| `{{#if:NAME!=VALUE}}` | NAME の値が VALUE と一致しない（未定義も「一致しない」） |

- `NAME` は英数字とアンダースコア、`VALUE` は英数字と `_` `.` `-`（空白不可、空も可）。
- `{{#else:NAME}}` 以降は開始タグの条件の逆で残す。1 ブロックに 1 回まで。
- タグは `#if` / `#else` / `#endif` の 3 種類だけ。`{{#elseif:…}}` / `{{#elif:…}}` のような多分岐のタグはない（書くとエラー。[10. エラー条件](#10-エラー条件)）。3 通り以上に分けたいときは、変数ごとにブロックを分けるか、`{{#else:NAME}}` の中に別の変数の `{{#if}}` を入れ子にする。

```markdown
{{#if:EDITION=student}}
学生用
{{#else:EDITION}}
{{#if:LEVEL=advanced}}
講師用（上級）
{{#else:LEVEL}}
講師用
{{#endif:LEVEL}}
{{#endif:EDITION}}
```
- YAML の `true` / `false` は文字列 `true` / `false` として比較する（`{{#if:DRAFT=true}}`）。

例：

```markdown
{{#if:COVERIMAGE}}
![]({{v:COVERIMAGE}})
{{#endif:COVERIMAGE}}
```

`COVERIMAGE` が定義されている場合：

```markdown
![](figures/cover.png)
```

`COVERIMAGE` が未定義または空の場合：

```markdown
```

版の切り替え例（原稿 MD）：

```markdown
{{#if:EDITION=student}}
> 演習問題の解答は巻末にあります。
{{#else:EDITION}}
> 解答例は講師用資料を参照。
{{#endif:EDITION}}
```

---

## 4. 処理順序

必ず以下の順で処理する。

```text
1. 条件ブロックを処理する
2. 変数参照を置換する
3. 結果を出力ファイルへ保存する
```

理由：

条件ブロック内に変数参照が含まれるため、先に変数置換すると、不要なブロック内の変数まで処理対象になってしまう。

merge では各ファイルの条件ブロックを `!include` の展開・画像コピーより先に処理する。偽のブロック内の `!include` や画像参照は読み込まれない。

---

## 5. 未定義変数の扱い

条件ブロックの判定に使われる変数は、未定義でもエラーにしない（偽として扱う）。

通常の変数参照 `{{v:VARIABLE}}` で `VARIABLE` が未定義の場合の扱いは段ごとに決まる。表紙 Markdown（`cover-md` / `htmlcover`）では空文字に置換する（表紙は欠落しても致命ではないため寛容に扱う）。render・pptmerge の扱いはそれぞれの仕様による。

理由：

* 条件ブロックでは「存在しなければ出さない」という使い方が自然

---

## 6. 真偽の判定

次の値は「偽」とみなす。

```text
未定義
null（None）
空文字 ""
YAML の false
文字列 false / 0 / no / off / none / null（大文字小文字・前後の空白は無視）
```

それ以外（空でない文字列、0 以外の数値、true）は「真」とみなす。

文字列の `false` / `0` / `no` / `off` を偽にするのは、`--var DRAFT=off` のようにコマンドラインから切り替えるため。

---

## 7. ネスト

条件ブロックはネストできる。

```text
{{#if:A}}
  {{#if:B}}
  ...
  {{#endif:B}}
{{#endif:A}}
```

外側が偽なら内側は条件にかかわらず出力しない。終了タグは変数名で対応をとるため、**同じ変数名のブロックの入れ子**（`{{#if:A=x}}` の中の `{{#if:A}}` など）はエラーとする。

---

## 8. 出力

処理後のテキストは各段がそのまま次の処理に渡す（表紙なら typst 断片への変換、merge なら結合）。独立した出力ファイルは作らない。

---

## 9. 適用箇所

条件ブロックの処理は `md_merge/_condblock.py` に集約し、次の段で行う。変数はレシピ `vars:`（＋ `--var`）を使う。

| 段 | 対象 | 備考 |
|---|---|---|
| pandoc 表紙 | 表紙 Markdown（`cover-md`。version 3 以前は `typst-cover-md`。HTML は `htmlcover`） | 未定義の `{{v:}}` は空文字 |
| merge | procedure の insertmd ファイル（`!include` 先も各ファイルごとに） | Markdown モード |
| pptmdexport | ノートの `{{BLOCK:MD}}` 本文（`export-note:` 行を含む全体） | Markdown モード。`export-note:` 行ごと囲めばそのブロックを出力しない |
| pptyamlexport | ノートの `{{BLOCK:YAML}}` 本文（YAML 解析の前） | `_include` で読み込むファイルの中は対象外 |

**Markdown モード**では、フェンスコード（` ``` ` / `~~~`）の中のタグは解釈せずそのまま残す（記法の説明をコードブロックで書けるように）。フェンス全体を条件ブロックで囲むことはできる。

レシピ YAML 自体には適用しない。procedure の項目を条件で切り替えるには `when:`（[md_pipeline.md](spec/md_pipeline.md#procedure-の条件付き適用when)）を使う。

### 9.1 コマンドラインでの切り替え（`--var`）

全サブコマンド共通のオプション `--var NAME=VALUE`（繰り返し可）でレシピ `vars:` を上書きする。`ppt_to_pdf` などのパイプラインでは全段に効く。

```text
pptmdmerge ppt_to_pdf recipe.yaml --var EDITION=student --var SHOW_ANSWER=off
pptmdmerge merge recipe.yaml --var DRAFT          # 値を省略すると true
pptmdmerge merge recipe.yaml --var COVERIMAGE=    # 空文字（偽）
```

上書きは条件ブロックだけでなく `{{v:NAME}}` の置換（render / pptmerge / 表紙）にも効く（CLI がレシピより優先）。

### 9.2 procedure 項目単位の切り替え（`when.var`）

同じ条件式は、レシピ `procedure` の項目に `when: {var: …}` として書くと、項目（pptx・MD ファイル・章など）単位の取捨にも使える（`docs/spec/md_pipeline.md` の「procedure の条件付き適用」）。

```yaml
procedure:
  - insertmd: answers.md
    when:
      var: SHOW_ANSWER          # --var SHOW_ANSWER で含める
  - insertpptx: print_only.pptx
    when:
      var: EDITION=print
```

---

## 10. エラー条件

以下の場合は例外を発生させる。

* 通常変数参照 `{{v:VARIABLE}}` の `VARIABLE` が `vars` に存在しない
* `{{#if:VARIABLE}}` に対応する `{{#endif:VARIABLE}}` が存在しない
* `{{#endif:VARIABLE}}` に対応する開始タグが存在しない
* 開始タグと終了タグの変数名が一致しない
* 同じ変数名の条件ブロックを入れ子にした
* `{{#else:VARIABLE}}` が開始タグと対応しない、または重複している
* 行頭が `{{#if` / `{{#el` / `{{#end` だがタグの文法に合わない（例: タグの後ろに文字がある、`{{#if:!A=1}}`、未定義のタグ `{{#elseif:A}}` / `{{#elif:A}}` / `{{#end:A}}`）。`{{#elseif}}` には `{{#else:NAME}}` か入れ子を使うよう案内を出す。`{{#id:…}}` など他の記法の行は対象外
* 変数名が仕様外文字を含む

エラーメッセージにはファイル名（ノートなら pptx 名とスライド番号）とブロック内の行番号を含める。

---

## 11. 実装上の注意

置換する値のエスケープ（Markdown・Typst の特殊文字）は行わない。

理由：

```text
画像パス、URL などをそのまま渡したいケースがあるため
```

必要なら将来、以下のようにエスケープ付き記法を追加する。

```text
{{vraw:COVERIMAGE}}
```

初期版では `{{v:...}}` は raw 置換とする。

---

## 12. 使用例

### 入力テンプレート

```markdown
{{#if:COVERIMAGE}}
![]({{v:COVERIMAGE}}){width=40%}
{{#endif:COVERIMAGE}}

**{{v:TITLE}}**

著者：{{v:AUTHOR}}
```

### vars

```yaml
vars:
  TITLE: サンプル文書
  AUTHOR: 山田太郎
  COVERIMAGE: figures/cover.png
```

### 出力

```markdown
![](figures/cover.png){width=40%}

**サンプル文書**

著者：山田太郎
```

```
```
