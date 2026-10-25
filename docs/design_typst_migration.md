# 設計草案: PDF 化を lualatex から Typst へ移行する

> **ステータス:** Phase 0〜5 完了（2026-10-22）、Phase 6（既定を Typst に）実施（2026-10-23）。lualatex は `engine: latex` でしばらく残し、問題が出なければ Phase 7（LaTeX の撤去）。§2 は**現在の実装の事実**（2026-10-21 時点の調査。2026-10-22 に前提を確認し §2.3 に反映）、§3 以降が**移行の方針と計画**。

## 1. 背景と目的

PDF 化の段は現在 `pandoc` → `lualatex` で組版している。LaTeX はエラーの解析が難しく、テンプレートやマクロ（titlesec / fancyhdr / tcolorbox / luatexja の設定、`\hdbreak` など）が積み重なって保守しづらい。これを Typst に移す。

Typst を選ぶ主な理由:

- エラーが `.typ` の行・列つきで出て、原因の特定が容易
- ページ設計（見出し・柱・目次・囲み）を show ルールと関数で素直に書ける
- コンパイルが速く、反復しやすい

HTML / GFM（puremd）系の出力は今回の対象外。lowering 規則（`semantics.yaml`）を共有しているだけなので影響を受けない。

## 2. 現状の LaTeX 依存（実装の事実）

### 2.1 LaTeX に依存しないもの

| 機能 | 実装 | 備考 |
| ---- | ---- | ---- |
| 章・節番号 | `idresolve` が番号を振り、`render` が見出しの文字列に書き込む | `number-sections: false` で pandoc / LaTeX の番号付けは使っていない |
| 章とびらの `{{sectionlist}}` | `render` が [_render.py:143](../src/md_merge/_render.py) で普通の Markdown 箇条書き（`- 2.1) 概要`）に展開 | とびらの**レイアウト**（`.center` / `.widequote` / `{{vspace}}`）は LaTeX 依存（§2.2） |
| `pptmdexport` の `\` / `&` エスケープ | `_filters.escape_backslash_smart` | Markdown の段階の処理なので Typst でも害はない |

### 2.2 LaTeX に依存するもの

| 項目                 | 現状                                                                                                                                                                                                                                                                                         | Typst での論点                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| セマンティック lowering   | `semantics.yaml` のブロック 8 種（note / warning / leadline / widequote / largefontblock / blockindent / keep-together / center）、インライン 6 種（term / keyword / path / kbd / emph / rightlabel）、リーフ 4 種（vspace / pagebreak / vfill / br）が `latex:` 規則を持つ。Lua フィルタの表は `tools/gen_lua_semantics.py` が生成 | `typst:` 列を足せば大半は表と生成で済む                                        |
| `divboxes.lua` の属性 | `colback` / `boxrule` / `width` など 14 キーを tcolorbox のオプションとして素通し                                                                                                                                                                                                                           | Typst の `block(fill:, stroke:, inset:, width:)` への対応表を手で作る必要がある |
| 原稿中の LaTeX 長さ      | `width="0.6\\linewidth"`（とびら）、`width=0.80\linewidth`（6 箇所）など                                                                                                                                                                                                                               | 幅は**おおまかに合えばよい**（確認済み）。フィルタで `\linewidth` 系を `%` に読み替えるだけで足り、厳密な換算は不要 |
| fenced div のクラス    | フィルタが LaTeX 環境に変換                                                                                                                                                                                                                                                                          | pandoc の Typst writer は Div のクラスをほぼ無視する。フィルタが出さないと**黙って**枠が消える  |
| 表紙                 | 現行レシピは `cover-md`（Markdown 表紙を本文と同じフィルタで LaTeX 断片に変換し `include-before-body` の先頭へ）。旧来の `conditional-process-input`（条件ブロック付き `.tex` 表紙）も残っている                                                                                                                                                | `cover-md` は変換先を typst にすれば流用できる。`.tex` 表紙テンプレートは書き直すか廃止        |
| 目次                 | `toc: true` / `toc-depth: 3`、`report_header.tex` で `\tableofcontents` を再定義                                                                                                                                                                                                                 | `#outline(depth: 3)`                                            |
| 見出し内改行 `{{br}}`    | `\hdbreak`（既定は空白、`\titleformat` 内だけ `\\`）で、見出し本体だけ改行し目次・柱・しおりは空白                                                                                                                                                                                                                           | 目次と柱の中だけ `linebreak` を空白にする show ルールで再現。PDF しおりの文字列は要確認         |
| 図・表の番号と参照          | **pandoc-crossref**（`figPrefix: 図` など）                                                                                                                                                                                                                                                     | **使っていない**（原稿に `{#fig:` / `@fig:` 等は 0 件。使っていても削除してよい）。Typst 側では pandoc-crossref を使わない |
| 画像の探索              | `resource-path`（build / shared_assets / common_assets / modules/images）を `\graphicspath` に変換して LaTeX に探させる                                                                                                                                                                              | Typst には複数ディレクトリ探索がなく、`--root` の外は読めない                          |
| ページ設計              | titlesec（章 `[display]`・ハイフン改行抑止）、fancyhdr（右柱に節タイトル、章開始・目次ページは `plain`）、geometry                                                                                                                                                                                                            | show ルールと `context` + `query` で作り直し                             |
| 日本語組版              | luatexja、`\gtfamily` で明朝／ゴシック切替、フォントは BIZ UDPMincho / BIZ UDPGothic / Consolas                                                                                                                                                                                                             | フォントはそのまま使える。切替は明示指定。禁則・和欧間の空きの細かさは luatexja に劣る                |
| 原稿中の生 LaTeX        | 2026-10-22 に原稿 pptx のノートを全部調べた結果（Phase 4 参照）: 使用中の pptx に `{=latex}` は 0 件。フェンスなしの LaTeX コマンドは、使用終了の部品 pptx（使わないファイルの置き場へ移動）と放置対象の古いメモ置き場にあるだけ。表紙の `common_assets/cover_type1.md` は LaTeX 用（Typst では同梱の表紙を使う）。vars の `TEX_*` は両基準文書のレシピから撤去済み（当初文書 A の生成 MD 9 ファイルを数えていたが、使っていない pptx からの古い出力だった） | pandoc は Typst 出力時に**黙って捨てる**                                   |
| QR コード             | `report_header.tex` / `book_header.tex` が `qrcode` を読み込む                                                                                                                                                                                                                                   | **不要**。QR コードは別途画像を生成して貼る |
| 数式                 | pandoc が TeX 数式を Typst 数式に変換                                                                                                                                                                                                                                                               | **使わない**。対応不要 |
| 画像形式               | pptimgexport の出力は PNG                                                                                                                                                                                                                                                                      | PNG は最初の実装でそうしただけで意図はない。**pptimgexport は再設計してよい**（§6） |

調査時の環境: pandoc 3.9、pandoc-crossref 0.3.23。typst は未導入。

### 2.3 確認済みの前提（2026-10-22）

- **幅の精度:** 原稿中の幅指定はおおまかに合っていればよい。
- **図・表の番号:** 使っていない。原稿を検索しても `{#fig:` / `{#tbl:` / `@fig:` などは 0 件。使っていても削除してよい。したがって pandoc-crossref は Typst 側の filters に入れない。
- **QR コード:** パッケージは不要。必要なら別途画像として生成して貼る。
- **数式:** 使わない。
- **画像形式:** pptimgexport が PNG を出すのは最初にそう作っただけで、意図はない。再設計してよい。

これで、当初 PoC で確かめる予定だった項目のうち「pandoc-crossref の互換性」はリスクから外れ、Typst パッケージのオフライン対応も不要になった。

## 3. 基本方針

1. **lualatex は最後まで既定のまま残す。** Typst は、レシピかコマンドで指定した文書だけに使う。どこかで失敗しても、lualatex に戻せば元どおり出力できるようにしておく。
2. **変換規則は `semantics.yaml` で一元管理する。** 各記法に `typst:` 列を足すだけにして、文書ごとに別の変換規則を持たない（原稿はセマンティック記述のみ、lowering 層で各形式へ変換するという既存の方針どおり）。
3. **原稿の修正は、どちらの方式でも正しく出る記法に置き換える。** `{=latex}` をセマンティックな記法に置き換えれば、Typst 対応の完成より先に原稿を直しても lualatex の出力は壊れない。共有 pptx をいくつ直しても安全。
4. **lualatex の出力が変わらないことを毎回確認する。** 基準文書の正解 PDF と `tools/pdfdiff.py` で比べ、差がないことを各段階の完了条件に含める。

## 4. 移行計画

### Phase 0: 準備

- typst のバージョンを決めて固定する（§6 で PDF 画像を使う場合は 0.14 以上）。pandoc は 3.9 で固定する。
  - **決定（2026-10-22）:** typst は最新版（winget `Typst.Typst` の 0.15.1）、pandoc は 3.9。pandoc 3.9 の Typst writer の出力が typst 0.15 で通るかは Phase 1 で確かめる。
- 比較の基準にする文書を選び、現行の lualatex で出力して正解 PDF として保存しておく。
- **決定（2026-10-22）:** 基準文書は次の 2 つ。生成コマンドは再生成と Typst 版との比較で同じ条件を使うために記録しておく。

  | 文書 | 確かめられること | 生成コマンド（作業ディレクトリ） | 生成物 |
  | ---- | ---- | ---- | ---- |
  | 文書 A | 別系統の文書（LaTeX 用の手書き表紙、表紙のフッタ画像） | `pptmdmerge ppt_to_pdf docA.yaml --keep-work` | `build\docA.pdf`（79 ページ） |
  | 文書 B | 章とびら、sectionlist、widequote、`{{br}}` | `pptmdmerge ppt_to_pdf docB.yaml --keep-work` | `build\docB.pdf`（115 ページ） |

- 正解 PDF は `build\` が再生成で上書きされるので、原稿フォルダとは別の場所（`_typst_baseline\2026-10-22\`）にコピーして保存した（2026-10-22 生成分）。
- 比較は `python tools/pdfdiff.py <正解 PDF> <新しい PDF>`。正解 PDF と生成直後の `build\` の PDF で、3 ページ分が `identical` になることを確かめた。

**完了条件:** 基準文書の正解 PDF がそろい、`tools/pdfdiff.py` で比較できる状態になっていること（2026-10-22 達成）。

### Phase 1: 併存の仕組み（PoC の前提）

- レシピに `pandoc.engine: latex | typst`（既定 `latex`）、CLI に `--engine` を追加する。CLI を優先。
- Typst 用の pandoc 設定は、`htmldefaults` と同じく `typstdefaults` キーで別に持つ。
- 併存期間中、Typst の出力は既定で `{base}_typst.pdf` にし、lualatex の PDF を上書きしない。
- **2 段構成にする。** pandoc で `.typ` まで出力して作業ファイルとして残し、そのあと `typst compile --root … --font-path …` を自前で呼ぶ。エラー位置が `.typ` の行番号で出て、そのまま開ける。
- `semantics.yaml` に `typst:` 列を足し、`tools/gen_lua_semantics.py` でその列も生成する。Lua フィルタは出力形式が typst のときだけその列を使う。
- `raw.allowed_formats` に `typst` を加える。

**完了条件:** `--engine typst` で（見た目は崩れていても）PDF が出ること。lualatex 側の出力が正解 PDF から変わっていないこと。

**実施結果（2026-10-22、完了）:**

- 実装: `pandoc.engine` / `--engine`（`pandoc`・`ppt_to_pdf`・`crop_to_pdf`）、`pandoc.typstdefaults`（省略時は同梱 `templates/typst_semantic_engine.yaml`）、`pandoc.typst-root`。`.typ` を残す 2 段構成。画像は同梱フィルタ `typst-images.lua` が resource-path から探して `.typ` 相対に書き換え、`--root` は既定で共通の上位ディレクトリ。`semantics.yaml` にインライン（`templates/semantic_macros.typ` の関数）とリーフ（`#v` / `#pagebreak` / `#v(1fr)`）の `typst:` 列を追加し、`raw.allowed_formats` と `raw.gfm.drop` に `typst` を追加。仕様は `docs/spec/output_formats.md` の「Typst エンジン」。
- 基準文書を Typst で生成（render 済み MD から `pptmdmerge pandoc <レシピ> --engine typst --force`）:

  | 文書 | lualatex | Typst | Typst の所要時間 |
  | ---- | ---- | ---- | ---- |
  | 文書 B | 115 ページ | 103 ページ | 約 3 秒 |
  | 文書 A | 79 ページ | 68 ページ | 約 2.5 秒 |

  typst の警告・エラーはなし。目次・本文・画像は出ている。表紙は `cover_type1.md` の中身が `{=latex}`（titlepage）なので空になる（Phase 3 / 4 で対応）。ブロック（枠・中央寄せ等）はまだ中身だけ。
- lualatex 側: 同じ render 済み MD から再生成し、`pdfdiff` で正解 PDF と比較して両文書とも全ページ `identical`（115/115、79/79）。lualatex の所要時間は文書 B で約 39 秒。

### Phase 2: PoC と続行判断

文書 B の 1 章分（とびら＋本文 1 節）を Typst で PDF にし、次の 3 点を確認する（図・表の番号は使っていないので確認しない。§2.3）。

1. 目次と柱で `{{br}}` を空白にできるか（show ルール）。PDF のしおりも確認
2. 複数のディレクトリにある画像を、パスの書き換えと `--root` で読めるか
3. 日本語の組版（禁則処理、和欧間の空き、明朝とゴシックの切り替え）が許容範囲か

**判断:** 3 が致命的なら、移行を止めるか範囲を絞る。止めても Phase 1 の仕組みはそのまま残しておける。

**実施結果（2026-10-22）:** 1 章分ではなく、基準文書 2 つの全体で確認した（Phase 1 で全体が通ったため）。

1. **`{{br}}`:** 確認できた。ただし途中で不具合が見つかり修正した。pandoc の `LineBreak` は Typst では「`\` ＋改行」になり、見出し `= …` がその改行で終わって**後半が本文に落ちていた**（PDF しおりも前半だけになっていた）。`semantic-break.lua` で `#linebreak();` を出すように直し、`semantic_macros.typ` に目次では消す show ルールを入れた。結果: 見出しは 2 行、目次は 1 行（空白なし）、PDF しおりは全文。柱は Phase 3 で同じ show ルールを使う。
2. **画像:** 確認できた。本文の画像は全部解決した（文書 B 121 / 121、文書 A 101 / 101）。lualatex 版との差の 1〜2 個は表紙の画像（表紙が未対応のため）。
3. **日本語の組版:** 致命的な問題はない。
   - 禁則処理: PDF のテキスト行から行頭・行末の禁則違反を数えたところ、lualatex 版と同等（文書 B は両方とも同じ箇所の 1 件、文書 A は両方 0 件）。
   - 和欧間の空き: Typst は既定で四分アキを入れる（`cjk-latin-spacing: auto`）。
   - 見た目の差はフォント設定によるもので、Phase 3 のテンプレートで調整できる:
     - **約物が詰まって見える**のは、BIZ UDPMincho がプロポーショナルフォントだから。luatexja は全角幅で組んでいる。非プロポーショナルの BIZ UDMincho にすると全角約物になる（試して確認）。ただし欧文も等幅になるので、欧文フォントを別に指定するのがよい。
     - **太字が出ない。** Typst は合成太字を作らず、BIZ UDPMincho には太字がない。luatexja と同じく太字をゴシック（BIZ UDGothic Bold）に切り替える show ルールが必要（試して確認）。
     - 行間・見出しのゴシック化・枠などはページ設計（Phase 3）。

**判断:** 続行（Phase 3 へ）を推奨。止める理由になる問題は見つからなかった。

### Phase 3: 機能をそろえる（Typst 側の実装）

- **変換規則:** semantics.yaml の全クラスに Typst での出力を定義する。
  - ブロック 8 種: 枠付きは `block`、keep-together は `block(breakable: false)`、center は `align`、blockindent は `pad`
  - インライン 6 種
  - リーフ 4 種: `pagebreak()`、`v(…)`、`v(1fr)`、`linebreak()`
- **divboxes の属性:** tcolorbox の 14 オプションを Typst の `fill` / `stroke` / `inset` / `width` などに対応させる。`0.6\linewidth` のような LaTeX の長さは `60%` に読み替えて、今の書き方も受け付ける（幅はおおまかに合えばよいので、`\linewidth` / `	extwidth` 系の係数を % にするだけでよい）。
- **ページのテンプレート（.typ）:**
  - 章の見出しと改ページ
  - 柱（`context` と `query` で見出しを探す）
  - 章の開始ページと目次ページでは柱を出さない
  - 目次（`outline(depth: 3)`、見出し「目次」）
  - フォントと余白（現行の style defaults に合わせる）
- **表紙:** `cover-md` の変換先に typst を加える。QR コードは画像として貼る（パッケージは使わない）。
- **画像パス:** `resource-path` を使って画像参照を解決済みのパスに書き換える（`_imagerefs.py` を流用）。`--root` には関係するディレクトリをすべて含む上位ディレクトリを使う。

**完了条件:** `{=latex}` を含まない文書なら、Typst で見た目までそろって出ること。

**実施結果（2026-10-22）:**

- 実装（すべてパッケージ同梱。仕様は `docs/spec/output_formats.md` の「Typst エンジン」）:
  - `templates/report_template.typst`: pandoc テンプレート（既定テンプレートの `conf()` は使わず、表紙 → 目次 → 本文の順に組む）
  - `templates/report_style.typ`: ページ設計（用紙・余白・フォント・行送り・章／節／項の見出し・柱・ノンブル・目次・表紙ページ）。寸法は `report_header.tex` と基準 PDF の実測から
  - `templates/semantic_macros.typ`: ブロックの関数を追加（`sem-box` で note / warning / leadline / widequote、`semcenter` / `semblockindent` / `semlargefontblock` / `semkeeptogether`）
  - フィルタの typst 分岐: `divboxes.lua`（属性の読み替え。`\linewidth` の係数 → %、xcolor の `blue!8` → 色の混合、`\large` などのサイズ命令 → 倍率、読み替えられない値は警告して無視）、`center.lua` / `blockindent.lua` / `largefontblock.lua` / `keep-together.lua`
  - 表紙: `pandoc.typst-cover-md`。省略時は LaTeX 用の表紙が指定されていれば同梱の `cover_standard_typst.md`（`COVER_*` を使う標準の表紙。QR などのフッタ画像も可）。表紙 Markdown で `{{#if:}}` が使えるようにした
  - `typst-images.lua` の不具合修正: `..` を含む相対パスを作れず絶対パスのまま残っていた（Typst は絶対パスを読めない）
  - `semantics.yaml` の blocks に typst 列（記録用）
- 結果:
  - フォント・行送り・見出し・柱・枠・中央寄せが基準 PDF とほぼ同じになった。柱の位置は 0.4pt 差、表紙の各行は 3pt 以内の差
  - ページ数は文書 B が 109（lualatex 115）、文書 A が 71（同 79）。33 ページ目付近まではページ単位で一致し、その後は Typst が 1 ページに少し多く詰めるのでずれていく（画像の大きさは同じ）。ページ送りまでは合わせていない
  - lualatex 側は今回も両文書とも正解 PDF と全ページ同一
- 残っている差・判断待ち:
  - ~~用紙は基準 PDF（LaTeX 版。report クラスの既定）と同じ US Letter にする（2026-10-22 決定。一度 A4 にしたが、基準 PDF とページ単位で比べられるよう戻した）~~ → 2026-10-25 に A4 へ変更（A4 しか使わないため。基準 PDF とはページ単位で一致しなくなる）
  - 章タイトルの折り返し位置が LaTeX と違うことがある（例「2) 論理構造図が必要な理由と / は？」）。気になる箇所は原稿に `{{br}}` を入れる

### Phase 4: 原稿から LaTeX を取り除く（Phase 2 以降、Phase 3 と並行可）

- `pptmdexport` の `latex_check` を `warn` で全部実行し、`{=latex}` の使用箇所の一覧を作る。
- 使われ方の種類ごとに、既存のセマンティック記法に置き換えるか、新しいクラスを足して置き換える。新しいクラスには latex と typst の両方の変換を定義する。
- vars の `TEX_*`（生 LaTeX の値）も同じように置き換える。
- 原稿の `width="…\linewidth"` は、触る機会があったときに `%` で書き直す（読み替えがあるので急がない）。
- 置き換えが終わった文書から順に `latex_check: error` にして後戻りを防ぐ。

**完了条件:** 基準文書で `latex_check: error` が通ること。

**実施結果（2026-10-22）:** 原稿 pptx の編集は作者が行う。ツール側では調査と検出の強化を行った。

- **調査:** 作者の原稿フォルダにある pptx 220 個（バックアップ・使わないファイル・前処理済みを除く）のノートを全部検査した。
  - `{=latex}`: **0 件**。残っていたのはある文書の移行前のバックアップだけ。当初文書 A で数えた 9 ファイルは、今は使っていない文書 A の旧版の pptx からの 6 月の古い出力だった（文書 A の render 済み MD には 0 件）。同様にブログ記事用の 4 つの build（6/28）も pptx を直す前の古い出力。
  - フェンスなしの LaTeX コマンド: 2 ファイル 3 スライド（下の表）。どちらも今後使わないファイルなので、**直す必要のある原稿は無い**。pptmdexport は本文のバックスラッシュをエスケープするので、これらは **LaTeX 版でも効かず文字どおり表示されている**。
  - `\linewidth` / `\Large` などは fenced div の属性値で、Typst 版はフィルタが読み替えるので対応不要。
  - vars の `TEX_*` は両基準文書のレシピから撤去済み。
  - **基準文書 2 つは、生 LaTeX を 1 つも含まない**（Phase 4 の作業は不要）。
- **検出の強化:** `latex_check` が `{=latex}` に加えて、フェンスなしの LaTeX コマンド（`\hspace` など。コード・属性値・Markdown のエスケープは除く）も見つけるようにした（`pptmdexport/__init__.py` の `_find_bare_latex`）。上のとびら・枠を多用する pptx で誤検出 0 件を確認。
- **見つかった箇所と扱い（2026-10-22 作者確認）:**

  | pptx | スライド | 記述 | 扱い |
  | ---- | ---- | ---- | ---- |
  | 使用終了の部品 pptx（文書 B の旧版だけが使用） | 16 | `\hspace*{4em}{\bfseries 複数出てくる同種の要素}` | **使用終了。** 使わないファイルの置き場へ移動済み。もし再利用するなら `::: {.blockindent indent=4em}` ／ `**…**` ／ `:::` に置き換える |
  | 同上 | 17 | `\vspace{5mm}` | 同上（再利用時は `{{vspace:5mm}}`） |
  | 古いメモ置き場の pptx | 1 | `\begin{list}…\end{list}`（ラベル付きの字下げリスト） | **放置。** 昔のファイルや走り書きメモ置き場で、使うときに精査して書き直す前提 |

  どちらのフォルダにも README.md がある。また文書 B ・C の旧版のフォルダは過去の記録で、今後の作業ベースは `shared_assets` と文書 B ・C の現行版。調査・修正はこの区別に従う。

- **表紙:** `common_assets/cover_type1.md` は LaTeX 用のまま残す（Typst では同梱の `cover_standard_typst.md` を使う）。LaTeX を撤去する Phase 7 で、表紙をどちらにするか決める。
- 基準文書のレシピに `pptmdexport.latex_check: error` を入れるかは作者の判断（レシピは作者のファイル）。

### Phase 5: 併存運用（文書ごとの切り替え）

- 実際に使う文書を lualatex と Typst の両方で出力して比べる。
  - `pdfdiff` でページ数とテキストの一致度（textsim）を確認
  - 見た目は目で確認
- 確認が通った文書から、レシピを `engine: typst` に切り替える。レシピ単位なので、まずければ 1 行戻すだけで済む。
- `ppt_to_pdf` などのパイプラインもレシピの `engine` に従う。

**併存期間中のルール:**

- 新しいセマンティッククラスを足すときは、latex と typst の両方の列を必ず定義する（`gen_lua_semantics.py --check` で確かめる）
- 新しく書く原稿には `{=latex}` を使わない

**完了条件:** 使っている文書がすべて `engine: typst` で出力されていること。

**実施状況（2026-10-22）:**

- 対象（作者が選定）: 基準文書の文書 B ・文書 A に加え、文書 C ・文書 D。その他の文書は今回の対象外。
- 比較（各文書の render 済み MD から両エンジンで出力。lualatex 側も同じ MD から作り直した）:

  | 文書 | lualatex | Typst | 禁則違反（lualatex / Typst） | 見た目 |
  | ---- | ---- | ---- | ---- | ---- |
  | 文書 B | 115 | 109 | 1 / 1 | Phase 3 で確認済み |
  | 文書 A | 79 | 71 | 0 / 0 | Phase 3 で確認済み |
  | 文書 C | 60 | 58 | 0 / 0 | 表紙・目次・本文・図・枠ともほぼ同じ |
  | 文書 D | 73 | 72 | 4 / 4（同じ箇所） | 表紙（QR 付き）・目次・本文・枠ともほぼ同じ。目次が 1 ページ短く、以降 1 ページずれる |

  Typst の警告・エラー、divboxes の読み替え不能の警告はどれも 0 件。
- 切り替え方: 文書 B ・C は共有の pandoc 設定ファイルを `!include` しているので、そこに `engine: typst` を書くと両方が切り替わる。文書 A ・D はレシピに pandoc セクションを直接書いているので、それぞれに書く。
- 切り替えた文書の PDF は併存期間中 `<名前>_typst.pdf` になる（lualatex 版の名前は Phase 6 で既定を切り替えるときに引き継ぐ）。
- **切り替え済み（2026-10-22）:** 共有の pandoc 設定ファイル（文書 B ・文書 C）、文書 D ・文書 A のレシピに `engine: typst` を追加。4 文書とも `--engine` なしで Typst 版が出ることを確認した。lualatex 版が必要なときは `--engine latex` で一時的に戻せる。
- 残り: その他の文書は今回の対象外（使うときに比較してから切り替える）。

### Phase 6: 既定を Typst に切り替える

- `pandoc.engine` の既定値を `typst` にし、出力ファイル名の `_typst` を外す。
- `engine: latex` はしばらく選べるようにしておき、指定時に廃止予定の警告を出す。
- 期間の目安は、1 回分の出版サイクルで大きな問題が出なくなるまで。

**実施結果（2026-10-23）:**

- `pandoc.engine` の既定を `typst` にした（`pandoc/__init__.py` の `_DEFAULT_ENGINE`）。PDF は `output.pdffilename` の名前で出し、同じ名前の `.typ` を残す（`_typst` の付加をやめた）。
- `engine: latex`（レシピ）か `--engine latex`（CLI）で lualatex に戻せる。PDF 出力で指定すると「廃止予定」の警告を出す。出力名は Typst 版と同じなので上書きする。
- その他の文書は比較していないが、作者の判断で既定どおり Typst にする（崩れていたらその時に直す）。
- 確認: 文書 B ・文書 A ・文書 E（engine の指定なし）が `--engine` なしで Typst 版の `<名前>.pdf` になり、文書 D に `--engine latex` を付けると警告が出て lualatex 版になることを確認した。
- 切り替え済みの 4 文書のレシピの `engine: typst` は既定と同じになったが、コメントを直して残した。
- 併存期間中に出した `<名前>_typst.pdf` / `_typst.typ` が各文書の `build/` に残っている（不要）。

### Phase 7: LaTeX を撤去する

- 削除するもの:
  - `templates/*.tex`（表紙を含む）、`semantic_macros.tex`、`report_header.tex`
  - `semantics.yaml` の `latex:` 列と、Lua フィルタの latex 分岐
  - `\hdbreak`、`resourcepathfilename`（`\graphicspath` の出力）
  - 条件ブロック方式の表紙経路（`conditional-process-*`）
  - pandoc の defaults の `pandoc-crossref` と `figPrefix` などのメタデータ（図・表の番号は使っていない）
  - テンプレートの `qrcode` パッケージ読み込み
- ドキュメントと 作者の環境の pandoc data-dirの LaTeX 用 defaults を整理する。

## 5. リスク

| リスク | 判明する段階 | 対処 |
| ---- | ---- | ---- |
| 日本語の組版が許容できない | Phase 2 | 移行を止める、または用途を絞る |
| `{=latex}` の置き換えが想定より重い | Phase 4 | 調査の結果、使用中の pptx に `{=latex}` は無く、フェンスなしのコマンドが 3 スライドだけだった（解消済みのリスク）。表紙は Typst 用の同梱表紙で対応済み |
| 共有 pptx への影響が広い | Phase 4 | どちらの方式でも出る記法にだけ置き換えるので、lualatex の出力は壊れない |

## 6. 移行後の改善候補: pptimgexport の再設計

PNG 出力に意図はないので（§2.3）、Typst 移行に合わせて画像形式を見直せる。移行そのものとは切り離し、Phase 3 以降に別作業として扱う。

- **PDF 版は画像をベクターにできる。** 今は pptpdfexport の PDF をラスタライズして PNG を切り出している。Typst 0.14 以上は PDF 画像を貼れるので、PDF のページを矩形で切り出した PDF（pymupdf で作れる）をそのまま使えば、拡大しても劣化せず、DPI の調整も要らない。
- **Web 系の出力にはラスター画像が要る。** puremd / transfer / notecomexport の出力（ブログ、note.com）は PDF 画像を表示できない。形式を出力先ごとに分ける（PDF 版は PDF、Web 版は PNG または WebP）か、両方を書き出す。
- **論点:** 同じ画像参照を出力先ごとに別の形式へ差し替える仕組み（拡張子の切り替えを `_imagerefs.py` に持たせる、など）と、`{{BLOCK:IMAGE}}` の `export-image` の書き方を変えるかどうか。

