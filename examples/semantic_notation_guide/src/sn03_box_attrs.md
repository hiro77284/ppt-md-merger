# 囲みの属性

note / warning / leadline / widequote の 4 つ（囲み系）は、`{ }` の中に `属性=値` を並べて見た目を調整できます。属性名は LaTeX（tcolorbox）版と同じで、Typst では同じ意味の値に読み替えます。

| 属性 | 意味 | 値の例 |
|---|---|---|
| `frame` | 枠と背景を描く | `true` / `false`（既定 false） |
| `colback` | 背景色 | `yellow!15` / `blue!8` / `#FFF3B0` |
| `colframe` | 枠の色 | `red` / `gray!50` |
| `boxrule` | 枠線の太さ | `0pt` / `1pt` |
| `width` | 囲みの幅 | `0.6\linewidth` / `80%` / `120mm` |
| `center` | 囲みを中央に置く | `true` / `false` |
| `left` / `right` / `top` / `bottom` | 内側の余白 | `6mm` / `2pt` |
| `before_skip` / `after_skip` | 囲みの前後の空き | `4pt` / `5mm` |
| `fontsize` | 文字の大きさ | `"\large"` / `"\small"` / `14pt` |
| `stretch` | 行送りの倍率 | `1.6` |

`frame` を付けない囲みには、枠も背景も描かれません。`colback` などの色の属性は、**`frame=true` と一緒に使ったときだけ**効きます。

## frame … 枠と背景を付ける

**書き方**

````markdown
::: {.note frame=true}
note に枠と背景を付けました。
:::

::: {.widequote frame=true}
widequote に細い枠を付けました。
:::
````

**表示結果**

::: {.note frame=true}
note に枠と背景を付けました。
:::

::: {.widequote frame=true}
widequote に細い枠を付けました。
:::

## colback / colframe / boxrule … 色と枠線

色は xcolor 式の `色名`・`色名!割合`（白と混ぜる）・`色名!割合!色名2`、または `#RRGGBB` で書きます。色名は black / white / red / green / blue / cyan / magenta / yellow / gray / lightgray / darkgray / orange / brown / purple / violet / teal / olive / lime / pink です。

**書き方**

````markdown
::: {.widequote frame=true colback=yellow!15}
背景色＋細い枠
:::

::: {.widequote frame=true colback=yellow!15 colframe=yellow!15 boxrule=0pt}
背景色だけ（枠色を背景色と同じにし、罫線を 0 に）
:::

::: {.note frame=true colback="#E8F4EA" colframe=teal boxrule=1pt}
#RRGGBB の背景色と、太めの teal の枠
:::
````

**表示結果**

::: {.widequote frame=true colback=yellow!15}
背景色＋細い枠
:::

::: {.widequote frame=true colback=yellow!15 colframe=yellow!15 boxrule=0pt}
背景色だけ（枠色を背景色と同じにし、罫線を 0 に）
:::

::: {.note frame=true colback="#E8F4EA" colframe=teal boxrule=1pt}
#RRGGBB の背景色と、太めの teal の枠
:::

## width / center … 幅を狭めて中央に置く

`width` は `0.6\linewidth`（文字領域の幅の 60%）のような LaTeX 式の書き方と、`60%` / `120mm` のような書き方の両方を受け付けます。`\` を含む値は `"…"` で囲みます。

**書き方**

````markdown
::: {.widequote width="0.6\linewidth" frame=true center=true}
幅を 60% に狭め、中央に置いた囲み
:::

::: {.note width=80% frame=true}
幅 80%、左寄せのまま
:::
````

**表示結果**

::: {.widequote width="0.6\linewidth" frame=true center=true}
幅を 60% に狭め、中央に置いた囲み
:::

::: {.note width=80% frame=true}
幅 80%、左寄せのまま
:::

## left / right / top / bottom … 内側の余白

**書き方**

````markdown
::: {.widequote frame=true left=12mm right=12mm top=4mm bottom=4mm}
上下左右の内側の余白を広げた囲み
:::
````

**表示結果**

::: {.widequote frame=true left=12mm right=12mm top=4mm bottom=4mm}
上下左右の内側の余白を広げた囲み
:::

leadline は枠なしでも `left` が効くので、擬似見出しを少し字下げするのに使えます。

````markdown
::: {.leadline left=6mm}
字下げした擬似見出し
:::
````

::: {.leadline left=6mm}
字下げした擬似見出し
:::

## before_skip / after_skip … 囲みの前後の空き

**書き方**

````markdown
直前の段落です。

::: {.note frame=true before_skip=2pt after_skip=20mm}
前の空きを 2pt に詰め、後ろの空きを 20mm に広げた囲み
:::

直後の段落です。
````

**表示結果**

直前の段落です。

::: {.note frame=true before_skip=2pt after_skip=20mm}
前の空きを 2pt に詰め、後ろの空きを 20mm に広げた囲み
:::

直後の段落です。

## fontsize … 文字の大きさ

値は LaTeX のサイズ命令で書き、`"…"` で囲みます。Typst では本文に対する倍率に読み替えます。

| 命令 | 倍率 | 命令 | 倍率 |
|---|---|---|---|
| `\tiny` | 0.5 | `\large` | 1.2 |
| `\scriptsize` | 0.7 | `\Large` | 1.44 |
| `\footnotesize` | 0.8 | `\LARGE` | 1.73 |
| `\small` | 0.9 | `\huge` | 2.07 |
| `\normalsize` | 1.0 | `\Huge` | 2.49 |

**書き方**

````markdown
::: {.widequote fontsize="\small"}
small 指定の引用（0.9 倍）
:::

::: {.widequote frame=true colback=blue!8 fontsize="\large" left=6mm}
やや大きめ・淡い青背景・左 6mm 余白の引用
:::
````

**表示結果**

::: {.widequote fontsize="\small"}
small 指定の引用（0.9 倍）
:::

::: {.widequote frame=true colback=blue!8 fontsize="\large" left=6mm}
やや大きめ・淡い青背景・左 6mm 余白の引用
:::

::: {.note}
Typst では `fontsize=14pt` のような長さも受け付けますが、LaTeX エンジンではこの書き方は使えません。LaTeX の絶対サイズ指定 `"\fontsize{14pt}{17pt}\selectfont"` は逆に Typst では読み替えられず、警告を出して無視されます。両方のエンジンで使う原稿では、サイズ命令（`"\large"` など）を使ってください。
:::

## stretch … 行送り

複数行にわたる囲みの行送りを、倍率で指定します（本文の既定は 1.2）。

**書き方**

````markdown
::: {.note frame=true stretch=2}
stretch=2 にすると行送りが広がります。長い文章を囲みに入れたときに、
行と行の間がどれくらい空くかを確かめるための例文です。もう一行続けます。
:::
````

**表示結果**

::: {.note frame=true stretch=2}
stretch=2 にすると行送りが広がります。長い文章を囲みに入れたときに、
行と行の間がどれくらい空くかを確かめるための例文です。もう一行続けます。
:::

## 読み替えられない値

Typst に読み替えられない値（未知の色名、`\fontsize{…}` など）は、`[divboxes] .note の colback=… は Typst に読み替えられないので無視します` という警告を出して無視します。ビルドは止まりません。表にない属性（`style` など）は、警告なしで無視します。
