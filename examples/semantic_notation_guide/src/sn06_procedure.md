# レシピから挿入するリーフ記法

MD ファイルどうしの間に行空けや改ページを入れたいときは、原稿 MD を書き換えずに、レシピの `procedure` に操作を書くこともできます。結合時に、その位置へリーフ記法が独立の段落として挿入されます。

| 操作 | 値 | 挿入されるマーカー |
|---|---|---|
| `insertvspace` | 数値（行数）または単位付き長さ。省略時 1 | `{{vspace:N}}` |
| `insertpagebreak` | なし | `{{pagebreak}}` |
| `insertvfill` | なし | `{{vfill}}` |

**書き方**（レシピ YAML）

```yaml
procedure:
  - insertmd: a.md
  - insertvspace: 0.5     # {{vspace:0.5}} を挿入
  - insertpagebreak       # {{pagebreak}} を挿入
  - insertmd: b.md
  - insertvfill           # {{vfill}} を挿入
```

値が数値でも単位付き長さでもない場合や負の値の場合は、警告を出して `1` を使います。

::: {.note}
旧来の `insertmd: ../../defaults/common_assets/tex_newpage.md`（中身が生 LaTeX の `\newpage`）は Typst エンジンでは効きません。`insertpagebreak` に置き換えてください。`tex_Nline.md` は `insertvspace: N`、`tex_vfill.md` は `insertvfill` に対応します。
:::

**表示結果**

本書のレシピ（`semantic_notation_recipe.yaml`）では、この段落を含む `sn06_procedure.md` と、次の段落を含む `sn06_procedure_after.md` の間に `insertvspace: 2` を書いています。この下に 2 行分の空きがあります。
