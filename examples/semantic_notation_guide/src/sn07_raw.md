# escape hatch（生コード）

セマンティック記法で表せない見た目がどうしても必要なときだけ、出力形式を指定した生コード（raw attribute）を書けます。**原稿での使用は非推奨**で、同じ原稿を別の形式に出すとその部分は失われます。

| 書き方 | 意味 |
|---|---|
| ```` ```{=typst} ```` … ```` ``` ```` | Typst のときだけ出力する生ブロック |
| ```` ```{=latex} ```` … ```` ``` ```` | LaTeX のときだけ出力する生ブロック |
| ```` ```{=html} ```` … ```` ``` ```` | HTML のときだけ出力する生ブロック |
| `` `…`{=typst} `` | 行内の生コード（Typst） |

出力形式が合わない生コードは破棄されます。puremd（GFM）では `latex` と `typst` の生ブロックを破棄し、`html` は残します。

## Typst の生ブロック

**書き方**

`````markdown
```{=typst}
#align(center, rect(stroke: 1pt + red, inset: 6pt)[
  #text(fill: red, weight: "bold")[Typst の生コードで描いた枠]
])
```
`````

**表示結果**

```{=typst}
#align(center, rect(stroke: 1pt + red, inset: 6pt)[
  #text(fill: red, weight: "bold")[Typst の生コードで描いた枠]
])
```

## 行内の生コード

**書き方**

````markdown
ここだけ `#text(size: 1.5em, fill: blue)[大きな青]`{=typst} の文字にします。
````

**表示結果**

ここだけ `#text(size: 1.5em, fill: blue)[大きな青]`{=typst} の文字にします。

## 出力形式が合わない生コード

Typst エンジンで PDF にするとき、LaTeX の生ブロックは破棄されます。

**書き方**

`````markdown
この下に LaTeX の生ブロックがあります。

```{=latex}
\begin{center}LaTeX エンジンのときだけ表示される\end{center}
```

この上の LaTeX の生ブロックは、Typst では何も出力しません。
`````

**表示結果**

この下に LaTeX の生ブロックがあります。

```{=latex}
\begin{center}LaTeX エンジンのときだけ表示される\end{center}
```

この上の LaTeX の生ブロックは、Typst では何も出力しません。

::: {.warning}
このように、LaTeX エンジン時代の原稿に残っている生 LaTeX は Typst では黙って消えます。`pptmdexport` の `latex_check`（既定 `warn`）で生コードの混入を検出できるので、見つかったものはセマンティック記法に書き換えてください（例：`\begin{center}` → `::: {.center}`、`\newpage` → `{{pagebreak}}`、`\par\vspace{1\baselineskip}` → `{{vspace:1}}`、`\hfill` → `[…]{.rightlabel}`）。
:::
