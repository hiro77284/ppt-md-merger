{{#id:section:simple_numbering_guide:slide2}}
## simple_numbering サンプル実行例

simple_numbering_guide.pptx は、２つのpptxファイルを結合して簡易ナンバリングを行うサンプルです。

データフォルダ:  PROJECT_ROOT/examples/pm2_simple_numbering
### サンプルファイル一覧

| 番号 | ファイル名         |          内容                |
| --- | --------------- | ------------------------ |
| 1 | simple_numbering_recipe.yaml | 結合指示書：簡易ナンバリング処理の仕様を示す  |
| 2 | simple_numbering_guide.pptx  |  このサンプルの説明書ソースpptx  |
| 3 | second.pptx                  | 結合元ファイルサンプル（3スライド）   |
| 4 | simple_numbering_merged.pptx       | 2と3の結合結果   |

ファイル2 + ファイル3 → ファイル4 という結合処理を行い、スライドタイトルに章・節番号をつけます。

### 実行命令

ファイル1の結合指示書に結合対象ファイルを記載します（後述します）。

以下の命令で実行します。サブコマンド pptmerge の引数に結合指示書を指定します。途中、一時的に PowerPoint が起動します。 --force は既出力ファイルを上書きするオプションです。

```bash
pptmdmerge pptmerge PROJECT_ROOT/examples/pm2_simple_numbering_recipe.yaml --force
```

結果、ファイル4が生成されれば成功です