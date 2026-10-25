<!--
engine: typst の既定の表紙（パッケージ同梱）。standard_cover_wideimage(_with_footerimage).tex と
同じ構成を、Typst 用に書き起こしたもの。

pandoc.typst-cover-md を省略し、cover-md か conditional-process-input（LaTeX 用の表紙）が
指定されているレシピでは、engine: typst のときにこれを使う。
レシピ vars の COVER_* を使い、{{#if:NAME}} … {{#endif:NAME}} で値が空の項目を省く。
画像は Markdown の画像記法で書く（typst-images.lua が resource-path から探す）。
文字の大きさは LaTeX 版（\Huge / \LARGE / \large）を和文スケール 0.962 で縮めた値。
空き（#v）は基準 PDF（lualatex 版）の位置に合わせて調整してある。
-->

```{=typst}
#v(16mm)
```

{{#if:COVER_IMAGE}}
::: {.center}
![]({{v:COVER_IMAGE}}){width=80%}
:::

```{=typst}
#v(22.7mm)
```
{{#endif:COVER_IMAGE}}

```{=typst}
#align(center, text(font: sem-fonts.sans, weight: "bold", size: 23.9pt)[
```

{{v:COVER_TITLE}}

```{=typst}
])
```

{{#if:COVER_SUBTITLE}}
```{=typst}
#v(-1mm)
#align(center, text(size: 16.6pt)[
```

{{v:COVER_SUBTITLE}}

```{=typst}
])
```
{{#endif:COVER_SUBTITLE}}

```{=typst}
#v(7.4mm)
#align(center, text(size: 11.5pt)[
```

作成日：{{v:COVER_DATE}}

```{=typst}
])
#v(6mm)
#align(center, text(size: 11.5pt)[
```

著者：{{v:COVER_AUTHOR}}

{{#if:COVER_AFFILIATION}}
所属：{{v:COVER_AFFILIATION}}
{{#endif:COVER_AFFILIATION}}

```{=typst}
])
```

{{#if:COVER_CONTACT}}
```{=typst}
#v(6mm)
#align(center, text(size: 11.5pt)[
```

{{v:COVER_CONTACT}}

```{=typst}
])
```
{{#endif:COVER_CONTACT}}

{{#if:COVER_NOTE}}
```{=typst}
#v(10mm)
```

{{v:COVER_NOTE}}
{{#endif:COVER_NOTE}}

{{#if:COVER_FOOTERIMAGE}}
```{=typst}
#v(10mm)
```

::: {.center}
![]({{v:COVER_FOOTERIMAGE}}){width=80%}
:::
{{#endif:COVER_FOOTERIMAGE}}
