# 設計草案: 画像参照とディレクトリ規約の統一

> **ステータス:** 方針合意済み（2026-10-06、§6 で 5 件を決定）。実装は Step 1〜6 すべて完了（§5）。§2.1〜2.4 は**設計時点（リファクタ前）の棚卸し**で、現在の状態は §2.5 を参照。§3 以降が**合意済みの方針**。

## 1. 背景と経緯

画像の置き場とパス書き換えは、必要が生じるたびに段階的に足されてきた。経緯を順に示す。

1. **pptx から画像と MD を切り出す段で分離**: pptx とは別ディレクトリに出す方が扱いやすいので、`src/`（入力 pptx）・`images/`（切り出した画像）・`mds/`（切り出した MD）・`build/`（結合成果物）という構成を基本にした。`src/` 以外は生成物なので一括削除できる。
2. **`mds/images/` にするか迷ったが、しなかった**: MD から画像を参照するので MD の下に置く案もあったが、現時点では `images/` と `mds/` は兄弟のまま。
3. **build 成果物をひとまとめにしたい**: 結合後は `build/merged.md` と `build/{サブディレクトリ}/画像` の形にまとめると一括コピーできて扱いやすい。そこで `merge` に**画像コピー＋参照パス書き換え**を入れた。
4. **Web 記事化で命名衝突が問題になった**: すべての記事の画像を 1 つの `images/` に放り込むと名前が衝突しうる。そこで `transfer` に**画像ディレクトリを `{slug}` に改名**する処理を入れた。

この積み上げの結果、**同じ「ローカル画像参照の書き換え」が 4 箇所に別実装**で存在し、本文記法（`![alt](ref)`）と frontmatter 記法（`hero:` / `notecom_cover:`）で扱いが揃っていない。しかし本文であれ frontmatter であれ、**参照しているのは同一ソース pptx から切り出した同じ画像群**であり、扱いを分ける理由はない。

## 2. 現状の棚卸し（実装の事実）

### 2.1 パス書き換えの 4 実装

| 段 | 実装 | 対象記法 | frontmatter 検出 | コピー先 | 衝突回避 |
|---|---|---|---|---|---|
| `merge` | [merge/_images.py](../src/md_merge/merge/_images.py) | 本文 `![alt](ref)` ＋ `hero:` | **ソース MD の 1 行目が `---`**（[merge/_recipe.py:603](../src/md_merge/merge/_recipe.py)） | `<outdir>/<merge.image-dir>/`（既定は `<outdir>/` 直下） | `_1` 連番。`overwrite-images` で上書き（警告） |
| `puremd` | [puremd/__init__.py](../src/md_merge/puremd/__init__.py) | **なし（素通し）** | 認識しない | — | — |
| `transfer` | [transfer/__init__.py](../src/md_merge/transfer/__init__.py) | 本文 `![alt](ref){attr}` ＋ `hero:` | leadin（`<!-- source: -->`・空行）を許容 | `<dataentry_input>/<slug>/`（常にフラット） | `sanitize` 時は `_1` 連番、`preserve` 時は上書き（警告） |
| `notecomexport` | [notecomexport/__init__.py](../src/md_merge/notecomexport/__init__.py) | 本文画像 ＋ cover（`notecomexport.cover` → `notecom_cover` → `hero`） | パース済み frontmatter から取得 | **コピーしない**（相対パス計算のみ） | — |

同じ役割の正規表現が重複し、skip 判定は 3 通りある。

| 定義 | 内容 |
|---|---|
| `merge._images._SKIP_RE` / `transfer._SKIP_RE` | `scheme://` ・ `//` ・ `/` ・ `#` ・ `data:` |
| `notecomexport._SKIP_PREFIX` | `http://` ・ `https://` ・ `/` ・ `data:` ＋ 絶対パス判定（`//` と `#` を含まない） |

本文記法の正規表現も 2 種あり、`transfer` 版だけが pandoc 属性（`{ width=100% }`）を保持するグループを持つ。

### 2.2 frontmatter の画像キー

| キー | merge | transfer | notecomexport | 用途 |
|---|---|---|---|---|
| `hero` | ○（条件付き、§2.4 参照） | ○ | ○（cover の最終 fallback） | 自社サイトのキービジュアル |
| `notecom_cover` | **✗ 対象外** | **✗ 無視** | ○（cover の第 2 候補） | note.com 用カバー（1280×670 に切り抜かれるため hero と別画像にしたい） |

`notecom_cover` を拾う正規表現はどの段にも無いため、**コピーもパス書き換えも一度も行われない**。原稿に書いた相対パスが最終 MD まで素通しし、`notecomexport` が puremd MD のディレクトリ基準で解決を試みる。実在すれば通り、しなければ警告のみで、パスはそのまま YAML に出る。

### 2.3 基準ディレクトリが 2 系統ある

| 参照 | 基準ディレクトリ | 根拠 |
|---|---|---|
| `{{BLOCK:IMAGE}}` の切り出し先パス | **pptx ファイルのディレクトリ**（`src/`） | [pptimgexport/__init__.py:263](../src/md_merge/pptimgexport/__init__.py) |
| MD 本文・frontmatter の画像参照 | **MD ファイルのディレクトリ**（`mds/`） | [merge/_images.py](../src/md_merge/merge/_images.py) |

どちらも原稿では `../images/名前.png` と書くが、これは `src/` と `mds/` が**兄弟だから偶然一致している**だけで、片方の構成を変えると崩れる。

### 2.4 既知の不具合と不整合

- **ppt 系パイプラインでは `hero:` も書き換わらない**: `merge` の frontmatter 判定は「ソース MD の 1 行目が `---`」だが、`pptmdexport` は先頭に `<!-- md_merge_rawtitle: ... -->` を付ける（[pptmdexport/__init__.py:380](../src/md_merge/pptmdexport/__init__.py)）ため、`---` は 2 行目になり判定が外れる。`transfer` は同じ問題に `_FM_LEADIN_RE` で対処済みだが `merge` は未対応。
  → 実例: 作業ツリーの `markdown-walkthrough-tool_puremd.md` は本文画像だけが書き換わり、`hero:` / `notecom_cover:` は原稿のままの `../images/...` で残っている。`transfer` が自前で解決し直すため実害が出ておらず、気づかれていなかった。
- **`../` が最終 MD に残る**: 上の結果、「MD と画像は同階層」という暗黙の前提が frontmatter 側だけ破れている。
- **衝突回避ポリシーが段で違う**: `merge` は既定で連番回避、`transfer` は `preserve`（既定）で上書き。
- **ドキュメントが実装と不一致**: [spec/output_formats.md](spec/output_formats.md) の「`notecom_cover` は `hero` と同じく入力 MD 基準の相対パス」は、`hero` が書き換えられる前提のケースでは成り立たない。

### 2.5 Step 1 / 2 完了後の状態（2026-10-06）

§2.1〜2.4 は設計時点（リファクタ前）の棚卸し。[移行計画](#5-移行計画) の Step 1 / 2 を実施した結果、次のように変わった。

- **新規 [_imagerefs.py](../src/md_merge/_imagerefs.py)** が記法定義（本文正規表現・frontmatter 画像キー・skip 判定・frontmatter 範囲判定）を単独で持つ。重複していた正規表現 2 組と skip 判定 3 通りは解消。
- `merge` / `transfer` / `notecomexport` は resolver のみを実装する形になった。`puremd` は従来どおり素通し（走査しない）。
- **§2.4 の frontmatter 検出バグは解消**。`merge` も leadin（空行・HTML コメント）を許容するようになり、ppt 系パイプラインでも `hero:` がコピー＋書き換えされる。
- `notecomexport` の skip 判定が共通版に揃い、`//host/x` ・ `#anchor` ・ `ftp://` 等も書き換え対象外として扱われる（従来は相対パス扱いで不存在警告が出ていた）。
- `FRONTMATTER_IMAGE_KEYS` に `notecom_cover` を追加（Step 3、2026-10-06）。`merge` / `transfer` が `hero` と同じ規則でコピー＋書き換えするようになった。
- 命名変換・衝突回避も `_imagerefs` に集約（Step 4）。`sanitize_name` / `apply_naming` / `pick_destination` を `merge` / `transfer` が共有し、`transfer` 独自だった `_sanitize_name` / `_dedup_name` は撤去。衝突判定は同一実行内のみ（§4.3）。
- `merge.image-dir` の既定値 `images` を導入（Step 5）。`merge/_images.py` の `DEFAULT_IMAGE_DIR` が定義。

## 3. 設計原則

> **画像参照の「抽出」だけが記法ごとに異なり、「変換」は全段で共通にする。frontmatter の画像キー一覧は単一の真実源に置く。**

守るべき不変条件:

1. **MD と画像ディレクトリは常に同階層**。参照は常に `サブディレクトリ名/ファイル名` の**1 段の相対パス**。`../` も多段も最終 MD に残さない。
2. **本文と frontmatter で解決規則を分けない**。同一ソースの同じ画像群を指しているのだから、コピー先・命名・衝突回避・skip 判定はすべて同じ。
3. **画像をコピーする段は 2 つだけ**（`merge` と `transfer`）。`puremd` は素通し、`notecomexport` はパス計算のみ、という現在の役割分担は維持する。
4. **キーを増やす作業はリスト 1 行で済む**（将来 `og_image` 等を足す場合）。

## 4. 統一設計

### 4.1 共有モジュール `src/md_merge/_imagerefs.py`（新規）

画像参照の定義と走査を 1 箇所に集約する。

```python
FRONTMATTER_IMAGE_KEYS = ("hero", "notecom_cover")   # ← 単一の真実源
BODY_IMAGE_RE = ...   # 属性 {…} を保持する transfer 版を採用
SKIP_RE       = ...   # scheme:// ・ // ・ / ・ # ・ data: （最も広い版を採用）

def rewrite(content: str, resolve) -> tuple[str, list[Ref]]:
    """本文と frontmatter の全画像参照を走査し、resolve の戻り値で置換する。"""
```

- `resolve(ref, *, kind, key) -> str | None` を各段が渡す。`kind` は `"body"` / `"frontmatter"`、`key` は frontmatter のキー名。`None` を返せばその参照は変更しない（不存在・skip 時）。
- frontmatter 検出は leadin 許容版 1 本に統一（`transfer` の実装を共有ユーティリティへ移す）。引用符の有無の保持も共通化する。
- 各段が持つのは resolver だけになる。

| 段 | resolver の仕事 |
|---|---|
| `merge` | `<outdir>/<image-dir>/` にコピーし `<image-dir>/名前` を返す |
| `transfer` | `<dataentry_input>/<slug>/` にコピーし `<slug>/名前` を返す |
| `notecomexport` | コピーせず、出力 YAML から見た相対パスを返す |
| `puremd` | resolver を渡さない（＝走査しない） |

### 4.2 ディレクトリ規約（明文化する）

```
src/source.pptx                            # 入力（人が触る唯一の場所）
images/  mds/                              # pptimgexport / pptmdexport の中間生成物
                                           #   参照は ../images/名前（mds/ 基準）
build/merged.md  build/<image-dir>/名前     # merge が集約。参照は <image-dir>/名前
<dataentry_input>/<slug>.md  …/<slug>/名前  # transfer が改名。参照は <slug>/名前
```

`merge.image-dir` を省略すると画像が `build/` 直下に散り、不変条件 1 が崩れる。**既定値 `images` を持たせる**（決定事項 2）。

> **移行時の注意:** `clear-dir-before-merge` は既定 `true` だが、`image-dir` が空のときは何もしない（[merge/__init__.py:77](../src/md_merge/merge/__init__.py)）。既定値を入れると、これまで `image-dir` を指定していなかったレシピで **merge 前の `build/images/` 全削除が初めて有効になる**（削除前にフルパスを提示して確認する動作は変わらない）。併せて、それらのレシピの画像コピー先が `build/` 直下から `build/images/` に変わり、結合済み MD 内の参照パスもそれに追従する。

> 実装時に確認した挙動（2026-10-06）: 初回実行では `build/images/` が存在しないため確認は出ない。2 回目以降は中身があるので、単体 `merge` は `--force` で確認を省略でき、パイプラインは `--force` に関係なく毎回確認する（既に `image-dir` を明示していたレシピと同じ扱いになる）。確認を出したくない場合はレシピで `clear-dir-before-merge: false`。旧挙動（`outputdir` 直下に画像を置く）を維持したい場合は `image-dir: ""` と空文字を明示する。

### 4.3 命名と衝突回避の統一

2 つの直交した設定に整理する。`merge` はハイフン、`transfer` はアンダースコアという各セクション既存の命名規則に合わせる。

| 設定 | キー | 値 | 意味 |
|---|---|---|---|
| 命名変換 | `merge.image-naming` / `transfer.image_naming` | `preserve`（既定） / `sanitize` | コピー先ファイル名を元名のままにするか、ASCII スラグ化するか |
| 衝突時 | `merge.image-collision` / `transfer.image_collision` | `rename`（既定、`_1`/`_2` 連番） / `overwrite`（警告のうえ上書き） | 同名衝突の扱い |

`merge.overwrite-images`（および `--overwrite-images`）は `image-collision: overwrite` の非推奨エイリアスとして残す（実レシピが使用中のため。使用時は debug ログで知らせる）。

**「衝突」は同一実行内の事象と定義する。** 別のソース画像が同じコピー先になった場合だけが衝突で、前回実行で置かれた同名ファイルの上書きは衝突ではない（同じ原稿から同じ画像を出すのだから、上書きして再現するのが正しい）。この定義がないと、既定 `rename` の下で再実行ごとに `_1`, `_2` … が増殖してしまう。従来は `merge` が「ディスク上の存在」も衝突と見ていたため、`clear-dir-before-merge` を切った運用では連番が累積し、それを避けるために `overwrite-images: true` を指定する必要があった。この定義により**どちらの設定でも再実行が冪等**になる。

## 5. 移行計画

| Step | 内容 | 挙動変更 |
|---|---|---|
| 1 | `merge` の frontmatter 検出を leadin 許容に修正（§2.4 のバグ） | **あり**: ppt 系で `hero` が初めて書き換わる（**済: 2026-10-06**） |
| 2 | `_imagerefs.py` を切り出し、`merge` / `transfer` / `notecomexport` を置換 | なし（リファクタのみ。**済: 2026-10-06**） |
| 3 | `FRONTMATTER_IMAGE_KEYS` に `notecom_cover` を追加 | **あり**: `merge` / `transfer` の両方でコピー＋書き換えの対象になる（**済: 2026-10-06**、§5.1 で実レシピ検証） |
| 4 | 命名・衝突回避ポリシーの統一（§4.3） | **あり**: `transfer` の `preserve` 時の既定が上書き→連番に変わる。衝突判定が同一実行内のみになる（**済: 2026-10-06**） |
| 5 | `merge.image-dir` の既定値 `images` を導入 | **あり**: §4.2 の移行時の注意を参照（**済: 2026-10-06**） |
| 6 | 規約（§4.2 / 6.4）と非対応記法（6.5）のドキュメント化 | なし（**済: 2026-10-06**） |

Step 4 / 5 の実装後、§5.1 の実レシピで再度通し、出力が Step 3 時点と同一（タイムスタンプ以外）であることを確認済み。同レシピは `image-dir` を明示し `overwrite-images: true` を使っているため、どちらの既定値変更も影響しない。

Step 6 は実装に依存しないので先行して反映済み。

| 反映先 | 内容 |
|---|---|
| [spec/md_pipeline.md](spec/md_pipeline.md) の「非対応の記法」 | 6.5 の非対応一覧（merge の画像処理） |
| [spec/output_formats.md](spec/output_formats.md) の transfer | 認識する記法は merge と同じである旨と上記への参照 |
| [spec/pptx.md](spec/pptx.md) の `{{BLOCK:IMAGE}}` | 6.4 の基準ディレクトリ規約（`src/` と `mds/` を同階層に置く前提） |

### 5.1 Step 3 の実レシピ検証（2026-10-06）

作者の環境にあるブログ記事用レシピ `markdown-walkthrough-tool.yaml`（`image-dir: markdown-walkthrough-tool` / `flatten-images: true` / `slug` も同名）を scratchpad に複製し、`merge → idcollect → idresolve → render → puremd → notecomexport → transfer` を Step 3 の前後で実行して差分を取った。変わったのは `notecom_cover` の 1 行とそれに由来する note YAML の `cover` だけで、他の出力・生成ファイル一覧は完全に同一。

| 出力 | Step 3 前 | Step 3 後 |
|---|---|---|
| merged / rendered / puremd の `notecom_cover:` | `../images/…-cover.png`（原稿のまま） | `markdown-walkthrough-tool/…-cover.png` |
| note YAML の `meta.cover` | `../images/…-cover.png`（`build/` の外を指す） | `markdown-walkthrough-tool/…-cover.png`（`build/` 内で自己完結） |

この案件は `hero` と `notecom_cover` が同じ画像なので新たなコピーは発生しない。`notecom_cover` だけが参照する画像（`…-keyvisual.png`）に差し替えた変種でも検証し、**従来はどこにもコピーされなかった note 専用画像が `build/{image-dir}/` と `{dataentry_input}/{slug}/` に入る**ことを確認した。`tools/notecom_autopilot.py` の `resolve_image_path`（`asset_root` = note YAML のディレクトリ）は新旧どちらの綴りでも解決できるため、投入側の変更は不要。

## 6. 決定事項（2026-10-06）

§4 の方針に対する 5 件の判断。いずれも合意済みで、以後は本節を前提とする。

### 6.1 `transfer` でも `notecom_cover` をコピーする

frontmatter の画像キーは全段で同じ扱いにする（不変条件 2）。dataentry / 自社サイト側は `notecom_cover` を読まないので、`{slug}/` に画像 1 枚が余分に入るだけで無害。「自社サイトに不要だから除外する」という段ごとの例外を作らないことを優先する。

### 6.2 `merge.image-dir` に既定値 `images` を持たせる

未指定でも不変条件 1（MD と画像は同階層・参照は 1 段）が成立する状態を既定にする。`validate` 警告で済ませる案は採らない（警告は読まれなければ効果がなく、規約が破れた成果物が残る）。

移行時の影響は §4.2 の注意書きのとおり。要点は 2 つ。

- これまで `image-dir` 未指定だったレシピで `clear-dir-before-merge`（既定 `true`）が初めて作動し、merge 前に `build/images/` の中身を削除する（削除前の確認は従来どおり）
- 同レシピの画像コピー先が `build/` 直下 → `build/images/` に変わり、結合済み MD の参照もそれに追従する

### 6.3 `mds/images/` 構成には寄せない（現状維持）

`images/` は `pptimgexport`、`mds/` は `pptmdexport` と生成元が別で、一括削除の単位としても分かれている方が素直。`src/` ＋ `images/` ＋ `mds/` ＋ `build/` の兄弟構成を正式な規約とする。

### 6.4 `{{BLOCK:IMAGE}}` の切り出し先は pptx 基準のまま（現状維持・文書化のみ）

§2.3 の「基準ディレクトリ 2 系統」は解消せず、**規約として明記する**。

| 書く場所 | 基準ディレクトリ | 典型的な記述 |
|---|---|---|
| pptx ノートの `{{BLOCK:IMAGE}}` の切り出し先 | pptx ファイルのディレクトリ（`src/`） | `../images/名前.png` |
| pptx ノートの `{{BLOCK:MD}}` 内の画像参照 | 切り出された MD のディレクトリ（`mds/`） | `../images/名前.png` |

両者が同じ綴りになるのは `src/` と `mds/` が兄弟である規約（6.3）の帰結であり、偶然に依存している。**この 2 つのディレクトリは常に同じ階層に置く**ことを規約の一部とし、基準ディレクトリを変える改修は行わない（既存原稿すべての `../images/...` に影響するため）。

### 6.5 本文記法のカバー範囲は現状のまま、非対応を明記する

対応するのは `![alt](ref)` と、その直後に続く pandoc 属性（`{ width=100% }` 等）のみ。次は**非対応**として仕様書に明記する。

| 非対応の記法 | 例 |
|---|---|
| title 付き | `![alt](a.png "キャプション")` |
| パスにスペースを含む | `![alt](my image.png)` |
| `<...>` 囲みのパス | `![alt](<my image.png>)` |
| 参照リンク形式 | `![alt][ref]` ＋ `[ref]: a.png` |
| HTML の `<img>` タグ | `<img src="a.png">` |

これらはパス書き換えもコピーも行われず、原稿の記述がそのまま最終出力まで素通しする（警告も出ない）。画像は `![alt](パス)` 形式で、パスにスペースを含めずに書くこと。
