{{#id:section:simple_ppt_merge_guide:slide2}}
## pm1_simple_ppt_merge 概要

simple_ppt_merge_guide.pptx は、２つのpptxファイルを単に結合するだけの単純マージを行うサンプルです。

データフォルダ:  PROJECT_ROOT\\examples\\pm1_simple_ppt_merge

### サンプルファイル一覧

| 番号 | ファイル名         |          内容                |
| --- | --------------- | ------------------------ |
| 1 | simple_ppt_merge_recipe.yaml | 結合指示書：マージ処理の仕様を示す  |
| 2 | simple_ppt_merge_guide.pptx  |  このサンプルの説明書ソースpptx  |
| 3 | second.pptx                  | 結合元ファイルサンプル（3スライド）   |
| 4 | simple_ppt_merge_merged.pptx       | 2と3の結合結果   |

ファイル2 + ファイル3 → ファイル4 という結合処理を行います。

### 実行命令

ファイル1の結合指示書に結合対象ファイルを記載します（後述します）。

以下の命令で実行します。サブコマンド pptmerge の引数に結合指示書を指定します。途中、一時的に PowerPoint が起動します。 --force は既出力ファイルを上書きするオプションです。

```bash
pptmdmerge pptmerge PROJECT_ROOT\examples\pm1_simple_ppt_merge_recipe.yaml --force
```

結果、ファイル4が生成されれば成功です