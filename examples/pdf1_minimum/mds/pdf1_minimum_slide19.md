<!-- md_merge_rawtitle: pdf1_minimum 生成方法 -->
{{#id:section:pdf1_minimum:slide2}}
## pdf1_minimum 生成方法

examples\\pdf1_minimum フォルダのサンプル一式を参照してください。

{{vspace:1}}

![pdf1_minimum 生成方法](../images/pdf1_minimum_slide19.webp){ width=100% }

{{vspace:2}}

### 実行命令

以下の命令で実行します。サブコマンド pptmerge の引数に生成指示書を指定します。

```bash
cd examples\pdf1_minimum\src
pptmdmerge ppt_to_pdf pdf1_minimum_recipe.yaml
```

成果物は

PDFファイル： build/pdf1_minimum_target.pdf

です。　その他に、

```bash
pptmdmerge ppt_to_puremd src/pdf1_minimum_pdf_recipe.yaml --keep-work
```
で、

MDファイル： build/pdf1_minimum_target_puremd.md

を生成します。PDFではなくMDで配付したい場合はこれをbuild/images ディレクトリとともに配付します。

```bash
pptmdmerge ppt_to_githubmd src/pdf1_minimum_pdf_recipe.yaml --keep-work
```
で、

GitHub 仕様のMDファイル： build/pdf1_minimum_target_github.md

を生成します。