# はじめての pptmdmerge

**1 つの pptx から、番号付きの PDF と Markdown を出すまで**を一本道で通す。所要 15 分程度。

このツールの発想は一言でいうと「**pptx を原稿置き場として使う**」。スライド本体は図になり、**スライドのノートに書いた Markdown が文章になる**。図と文章が 1 画面に並んだまま書けて、そこから PDF・Markdown・HTML・結合 pptx を生成する。

ここで覚える記法は 3 つだけ。残りは必要になってから [notation_reference.md](notation_reference.md) を引けばよい。

---

## 0. 準備

| 必要なもの | 用途 | 省略できるか |
|---|---|---|
| Python 3.11 以上 | 本体 | 不可 |
| Windows + PowerPoint | pptx → PDF 変換（`pptpdfexport`）に COM を使う | 不可（この一本道では） |
| pandoc | PDF / HTML 生成 | MD だけなら不要 |
| LuaLaTeX（TeX Live 等） | PDF 生成 | MD だけなら不要 |

```bash
pip install -e .
```

> PowerPoint にアドインを入れる必要はない。外部プロセスから COM で操作するだけで、マクロのセキュリティ設定もそのままでよい。

## 1. ディレクトリを用意する

```
myproject/
├── src/          ← 原稿 pptx（人が触る唯一の場所）
├── images/       ← 切り出された図（自動生成）
├── mds/          ← 切り出された MD（自動生成）
└── build/        ← 成果物（自動生成）
```

`src/` 以外はすべて生成物なので、迷ったら消して作り直せる。`images/` と `mds/` は `src/` と**同じ階層**に置くこと（ノートに書く相対パスがこの構成を前提にしている）。

```bash
mkdir -p myproject/src myproject/images myproject/mds myproject/build
```

## 2. pptx を作る

`src/sample.pptx` を作り、スライドを 2 枚用意する。各スライドで次の 2 つをやる。

**(1) 図にしたい範囲に名前を付ける**

図として切り出したい範囲を覆う図形（透明な四角形など）を置き、**シェイプ名を `exportrange` にする**。ホーム → 選択 → オブジェクトの選択と表示（選択ウィンドウ）で名前を変更できる。

**(2) ノートに原稿を書く**

スライドのノートに次を書く。これがこのツールの中心。

```text
NOTE_CONTENT_FORMAT: 1.0

===BLOCK===
{{BLOCK:IMAGE}}

export-image-mode: slide_with_rectpct
export-image-target: exportrange
export-image: ../images/<__BASEFILENAME__>_slide<__SLIDENUM__>_fig.png

===BLOCK===
{{BLOCK:MD}}

export-note: ../mds/<__BASEFILENAME__>_slide<__SLIDENUM__>.md
{{#id:section:sample:slide<__SLIDENUM__>}}
## <__TITLE__>

ここに本文を書く。普通の Markdown。

![](../images/<__BASEFILENAME__>_slide<__SLIDENUM__>_fig.png){ width=100% }
```

読み方:

| 部分 | 意味 |
|---|---|
| `NOTE_CONTENT_FORMAT: 1.0` | この行が無いとノートは無視される。**1 行目に必須** |
| `===BLOCK===` | ブロックの区切り |
| `{{BLOCK:IMAGE}}` | 図の切り出し指示ブロック。`exportrange` の範囲を `../images/` に PNG で出す |
| `{{BLOCK:MD}}` | 原稿ブロック。1 行目の `export-note:` が切り出し先 |
| `{{#id:section:...}}` | **ID マーカー**。直後の見出しが採番の対象になる |
| `<__BASEFILENAME__>` `<__SLIDENUM__>` `<__TITLE__>` | pptx 名・スライド番号・スライドタイトルに自動置換される |

相対パスは **pptx のあるディレクトリ（`src/`）基準**なので `../images/` `../mds/` になる。

> 全スライドでノートの中身は**同じで構わない**。プレースホルダーがスライドごとに展開されるので、コピペでよい。

## 3. レシピを書く

`myproject/sample_recipe.yaml`:

```yaml
version: 2

output:
  outputdir: build
  targetbasefilename: sample_doc   # 成果物のベース名。pptx 名と変えておく（後述）
  force: true                      # 既存の成果物を上書きする

input:
  dirs:
    - .
    - mds                          # 切り出された MD を探す場所
  cropsrc:
    pptx: src/sample.pptx          # 図と原稿の供給元

merge:
  flatten-images: true             # 画像を build/images/ に平らに集める

pandoc:
  defaults: pandoc_defaults.yaml   # PDF を出さないなら不要

indexer:
  pptxnumbering: idresolve         # 章・節番号を付ける

procedure:
  - chapter: "+"  # 章見出しを 1 つ挿入
    title: サンプル章
  - insertmd: sample_slide[1-2].md  # 切り出された MD を順に結合
```

`procedure` が文書の構成そのもので、**ここに書いた順**に結合される。`sample_slide[1-2].md` はレンジ展開で `sample_slide1.md` と `sample_slide2.md` になる。

PDF を出すなら `myproject/pandoc_defaults.yaml` も作る。

```yaml
pdf-engine: lualatex
standalone: true
toc: true
variables:
  papersize: a4
  documentclass: report
  mainfont: "BIZ UDPMincho"
  sansfont: "BIZ UDPGothic"
  geometry:
    - top=20mm
    - bottom=20mm
    - left=20mm
    - right=20mm
```

## 4. 実行する

Markdown だけなら pandoc も LaTeX も要らない。まずはこちらで一周するのがよい。

```bash
pptmdmerge ppt_to_puremd sample_recipe.yaml --force
```

PDF まで出すなら:

```bash
pptmdmerge ppt_to_pdf sample_recipe.yaml --force
```

どちらも 1 コマンドで、内部では `pptpdfexport → pptimgexport → pptmdexport → merge → idcollect → idresolve → render → …` が順に走る。

## 5. 出てくるもの

```
mds/sample_slide1.md          ← ノートから切り出された原稿
images/sample_slide1_fig.png  ← exportrange の範囲が図になったもの
build/sample.pdf              ← pptx をそのまま PDF 化したもの（図の切り出し元）
build/images/                 ← 文書で使う画像を集めたもの
build/sample_doc_puremd.md    ← 完成した Markdown（ppt_to_puremd）
build/sample_doc.pdf          ← 完成した PDF（ppt_to_pdf）
```

`build/sample_doc_puremd.md` の中身はこうなる。

```markdown
<!-- source: mds/sample_slide1.md -->
<!-- #id:section:sample:slide1 -->
## 1.1) はじめての結合

このスライドのノートに原稿を書きます。スライド本体は図として切り出されます。

![](images/sample_slide1_fig.png){ width=100% }
```

**番号が自動で振られている**のがポイント。`# 1) サンプル章` → `## 1.1)` → `## 1.2)` と、`procedure` の順に採番される。スライドを入れ替えれば番号は自動で付け直される。

## 6. 最初につまずくところ

| 症状 | 原因と対処 |
|---|---|
| `export-note を持つスライドが見つかりません` | ノートの 1 行目が `NOTE_CONTENT_FORMAT: 1.0` になっていない。または `{{BLOCK:MD}}` の本文 1 行目が `export-note:` でない |
| `MD file not found: ..._slide1.md — skipping` | `mds/` に切り出せていない（上と同じ原因）か、`input.dirs` に `mds` が入っていない |
| `シェイプ 'exportrange' が見つかりません` | 図形の**名前**が `exportrange` になっていない（表示テキストではなく選択ウィンドウ上の名前） |
| `シェイプ 'exportrange' はグループ内にあります` | 対象の図形が他の図形とグループ化されている。**グループを解除する**（グループ内の座標は親の子座標系になるため使えない） |
| 2 回目の実行で「全削除してよいですか？」と聞かれる | `build/images/` を merge 前に空にする確認（既定で有効）。`y` で続行。確認を出したくなければレシピに `merge: clear-dir-before-merge: false` |
| `build/sample.pdf` が文書 PDF で上書きされる | pptx 名と `targetbasefilename` が同じだと衝突する。**違う名前にする**（例 pptx が `sample.pptx` なら `sample_doc`） |
| 見出しに番号が付かない | `indexer.pptxnumbering: idresolve` を書き忘れている（既定は `no` ＝番号を付けない） |

## 7. 次の一歩

ここまでで「pptx 1 つ → 文書 1 つ」が通った。次はこのあたり。

| やりたいこと | 見るもの |
|---|---|
| 複数の pptx を結合する | `procedure` に `insertpptx` / `insertmd` を並べる → [spec/md_pipeline.md](spec/md_pipeline.md#merge) |
| 結合した pptx 自体も出力する | [spec/pptx.md](spec/pptx.md#pptmerge)、`examples/` の 11 サンプル |
| 注意書きボックスや中央寄せを使う | `::: {.note}` などのセマンティック記法 → [notation_reference.md](notation_reference.md#3-セマンティック構造原稿-md) |
| Web 記事として出す | `ppt_to_transfer` / `ppt_to_notecom` → [spec/pipelines.md](spec/pipelines.md) |
| 体裁を本格的に整える | `defaults/pandoc/` 一式と `examples/standard_pandocsettings.yaml` を出発点にする（pandoc-crossref と BIZ UD フォントが前提） |
| 使える記法を一覧したい | [notation_reference.md](notation_reference.md) |
| レシピのキーを調べたい | [recipe_key_reference.md](recipe_key_reference.md) |

---

## 付録: この手順の検証について

本書のレシピとノート記法は、2 枚のスライドを持つサンプル pptx で `ppt_to_puremd` と `ppt_to_pdf` の両方を実行し、警告ゼロで PDF（目次＋採番つき 2 ページ）と Markdown が生成されることを確認している（2026-10-21）。
