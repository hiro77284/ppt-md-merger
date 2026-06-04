# テンプレート変数置換・条件ブロック処理仕様

## 1. 目的

LaTeX などのテンプレートファイル内に記述されたユーザー定義変数参照、および条件ブロックを、構成指示 YAML の `vars` セクションに定義された値に基づいて展開する。

主な用途は、`cover_template.tex` などのテンプレートから `cover_generated.tex` を生成し、Pandoc の `include-before-body` で読み込める実体ファイルを作ることである。

---

## 2. 入力

### 2.1 テンプレートファイル

UTF-8 テキストファイル。

例：

```tex
{{#if:COVERIMAGE}}
\vspace{10mm}
\begin{flushleft}
  \includegraphics[width=0.40\linewidth]{{v:COVERIMAGE}}
\end{flushleft}
\vspace{20mm}
{{#endif:COVERIMAGE}}

{\Huge {{v:TITLE}}}

著者：{{v:AUTHOR}}
````

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
{{#endif:VARIABLE}}
```

`VARIABLE` は英数字とアンダースコアのみ使用可能とする。

処理内容：

* `vars.VARIABLE` が存在し、かつ空文字でない場合、ブロック内部を残す
* `vars.VARIABLE` が存在しない、または空文字の場合、ブロック全体を削除する
* 開始タグ・終了タグ自体は出力しない

例：

```tex
{{#if:COVERIMAGE}}
\includegraphics{{v:COVERIMAGE}}
{{#endif:COVERIMAGE}}
```

`COVERIMAGE` が定義されている場合：

```tex
\includegraphics{figures/cover.png}
```

`COVERIMAGE` が未定義または空の場合：

```tex
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

---

## 5. 未定義変数の扱い

条件ブロックの判定に使われる変数は、未定義でもエラーにしない。

```text
{{#if:VARIABLE}}
```

で `VARIABLE` が未定義の場合、そのブロックは削除する。

一方、通常の変数参照：

```text
{{v:VARIABLE}}
```

で `VARIABLE` が未定義の場合はエラーとする。

理由：

* 条件ブロックでは「存在しなければ出さない」という使い方が自然
* 通常変数参照では、未置換のまま出力されると LaTeX/Pandoc 側で分かりにくいエラーになるため

---

## 6. 空文字の扱い

次の値は「偽」とみなす。

```text
未定義
None
空文字 ""
```

次の値は「真」とみなす。

```text
空でない文字列
数値
true
false という文字列
```

注意：

YAML の boolean `false` を偽にするかどうかは実装方針次第だが、最初は単純化のため「None または空文字のみ偽」とする。

---

## 7. ネスト

条件ブロックのネストは、初期版では非対応とする。

非対応例：

```text
{{#if:A}}
  {{#if:B}}
  ...
  {{#endif:B}}
{{#endif:A}}
```

ネストが検出された場合はエラーにしてよい。

---

## 8. 出力

テンプレート処理後のテキストを、指定された出力ファイルへ UTF-8 で保存する。
pandoc.conditional-process-input を入力とし、pandoc.conditional-process-outputを出力とする

例：

```text
pandoc:
  conditional-process-input: ../pandocdatadir/cover.tex
  conditional-process-output: build/cover-processed.tex
```

---

## 10. エラー条件

以下の場合は例外を発生させる。

* 通常変数参照 `{{v:VARIABLE}}` の `VARIABLE` が `vars` に存在しない
* `{{#if:VARIABLE}}` に対応する `{{#endif:VARIABLE}}` が存在しない
* `{{#endif:VARIABLE}}` に対応する開始タグが存在しない
* 開始タグと終了タグの変数名が一致しない
* 条件ブロックのネストを検出した
* 変数名が仕様外文字を含む

---

## 11. 実装上の注意

LaTeX 内で使用する値を置換する場合でも、この処理では LaTeX エスケープは行わない。

理由：

```text
画像パス、URL、LaTeXコマンドなどをそのまま渡したいケースがあるため
```

必要なら将来、以下のようにエスケープ付き記法を追加する。

```text
{{vtex:TITLE}}
{{vraw:COVERIMAGE}}
```

初期版では `{{v:...}}` は raw 置換とする。

---

## 12. 使用例

### 入力テンプレート

```tex
{{#if:COVERIMAGE}}
\includegraphics[width=0.40\linewidth]{{v:COVERIMAGE}}
{{#endif:COVERIMAGE}}

{\Huge {{v:TITLE}}}

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

```tex
\includegraphics[width=0.40\linewidth]{figures/cover.png}

{\Huge サンプル文書}

著者：山田太郎
```

```
```
