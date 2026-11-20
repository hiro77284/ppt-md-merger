# user_settings

利用者が自分の文書群のために用意する設定・素材の置き場の**サンプル**です。`examples/` のレシピは `../../user_settings/...` でここを参照しています。

| ディレクトリ | 中身 |
|---|---|
| `common_assets/` | 複数の文書で共通に使う pptx（章扉・スタイルベース等）、画像、`puremd_strip.yaml` |
| `pandoc/` | pandoc の `data-dir` として指定する HTML / reveal 用 defaults と CSS |

ツール本体（`md_merge` パッケージ）はこのディレクトリに依存しません。PDF（Typst）用の同梱既定（`report_base_defaults.yaml`・`cover_standard.md` 等）はパッケージ内の `src/md_merge/templates/` にあります。自分の環境では、このディレクトリを好きな場所にコピーし、レシピからの相対パスを合わせて使ってください。
