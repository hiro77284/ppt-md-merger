# 設計草案: セマンティック記述と lowering 層

> **ステータス:** 草案（2026-06-30）。方針合意済み・実装は段階移行中。確定済みの部分と未決事項を本書で区別する。

## 1. 背景と問題

`pptmdmerge` は当初 `pptx → md → pandoc → pdf` を一貫処理する目的で作られ、原稿には PDF（LaTeX）出力を前提とした**生 LaTeX 記法**が混在していた。その後 MD / HTML も第一級の出力ターゲットになり、同じ原稿から 3 形式すべてを出すことが多くなった結果、原稿中の記法が **2 つの抽象度レベル**にまたがる状態になった。

| レベル | 例 | 問題 |
|---|---|---|
| リテラル（出力形式の実装コード） | `\par\vspace{1\baselineskip}`、` ```{=latex} `、`tex_*.md` | LaTeX 専用。MD/HTML では lowering できず**意図ごと失われる** |
| セマンティック（意図） | `::: {.note}`、`::: {.widequote}` | 形式非依存。各形式へ lower 可能 ✅ |

`puremd` の `fenced_block` / `fenced_div` という命名の紛らわしさも、この抽象度混在の表面的な症状にすぎない。

**重要な事実:** 原稿中の生 LaTeX（pptx ノートの MD ブロック内）は**人が書いたもの**で、`pptmdexport` はそれを切り出しているだけ。手書きの MD（fixtures / docs / examples の src）は既に純セマンティックである。したがって本設計の対象は「大量の人手原稿の移行」ではなく、**①原稿に書ける語彙をセマンティックに限定し、②各形式への lowering をそろえ、③既存の生 LaTeX を別途一括変換する**ことに集約される。

## 2. 設計原則

> **人間が原稿（pptx ノート内 MD）に書くのはセマンティック層だけ。リテラル（LaTeX/HTML）は最後の lowering 段でのみ生成する。生コードは明示的な escape hatch に限定し、非対象形式では警告して破棄する。**

- 新しい中間フォーマットは発明しない。**pandoc 拡張 Markdown ＋ fenced div / bracketed span** を “その IR” として据える。
- 出力ターゲットは **PDF（LaTeX）/ MD（GFM）/ HTML** の 3 つすべて第一級。
- `{{v:}}` 変数は**実データ置換専用**。値にリテラル LaTeX を入れることは禁止。

## 3. セマンティック語彙

原稿に書ける構造は次の 3 カテゴリのみ。

### 3.A ブロック構造（fenced div `::: {.class}`）

既存 7 クラスに加え、生 LaTeX から昇格させる 4 クラスを定義する。lowering 規則:

| クラス | 意味 | LaTeX へ | HTML へ | GFM-md へ（puremd） | 由来 |
|---|---|---|---|---|---|
| `.note` / `.warning` / `.leadline` | 注意喚起ボックス | tcolorbox 環境 | `<div class>`＋CSS | `> [!NOTE]` / `[!WARNING]` / `[!IMPORTANT]` | 既存 |
| `.widequote` | 幅広引用 | tcolorbox 環境 | `<div class>`＋CSS | 素の blockquote | 既存 |
| `.largefontblock` | 大きい文字ブロック | 専用環境 | `<div class>`＋CSS(font-size) | ラベル付き blockquote（lossy） | 既存 |
| `.blockindent` | 字下げブロック（属性 `indent=3em` で量指定可、既定 2em） | 専用環境 `\begin{blockindent}[indent]` | `<div class>`＋CSS/inline margin | ラベル付き blockquote（indent は無視・lossy） | 既存 |
| `.keep-together` | 改ページ抑制（ブロックを分割しない） | `\begin{minipage}{\linewidth}…\end{minipage}`（分割不可ボックス） | CSS `break-inside:avoid` | unwrap | 既存 |
| **`.center`** | 中央寄せブロック | `\begin{center}…\end{center}` | CSS `text-align:center` | unwrap | `\begin{center}` を昇格 |

中身を持たない垂直系（vspace / pagebreak / vfill）は fenced div では冗長なため、**1 行リーフ記法**で書く（下表）。`render` 段は素通しし、ターゲット段（pandoc Lua フィルタ / puremd）で lower する。

| リーフ記法（案） | 意味 | LaTeX へ | HTML へ | GFM-md へ（puremd） | 由来 |
|---|---|---|---|---|---|
| **`{{vspace:N}}`** | 垂直スペース（N は数値=既定単位の倍、例 `0.5`。または単位付き長さ `5mm` / `1.5cm`） | 数値: `\vspace{N\baselineskip}` ／ 単位付き: `\vspace{5mm}` | 数値: `<div class="vspace" style="height:Nem">` ／ 単位付き: `height:5mm` ＋CSS | 空行 or 破棄 | `\par\vspace` / `tex_Nline` |
| **`{{pagebreak}}`** | 改ページ | `\newpage` | `<div class="pagebreak">`（CSS `break-after:page`） | `---` or 破棄 | `tex_newpage` |
| **`{{vfill}}`** | 残り高を埋める | `\vspace*{\fill}`（* 付き=ページ先頭でも破棄されない） | flex spacer | 破棄 | `tex_vfill` |

> リーフ記法の正確な綴り（`{{vspace:N}}` 等）は既存マーカー族（`{{#id:}}` / `{{v:}}` / `{{num:}}`）と衝突しない前提の**提案**。`render` / `idcollect` 段がこれらを処理対象外として素通しすること、pandoc 側は `FORMAT` を見て RawBlock を出し分ける Lua フィルタ（`semantic-leaf.lua`）で lower することを想定。最終綴りは §8 で確定する。

- HTML は pandoc が fenced div を `<div class="…">` として**ネイティブ出力**するため、HTML バックエンドは大半が **CSS だけ**で済む（Lua フィルタはほぼ不要）。リーフ記法だけは pandoc が素のテキストとして見るため、HTML/LaTeX とも Lua フィルタで拾う。
- divbox 属性（`frame` / `colback` / `left` / `center` 等）は LaTeX(tcolorbox) では効くが、MD では破棄、HTML では CSS にマップ（または破棄）。puremd は現在「黙って破棄」だが、損失する装飾は **warn** する方針に変える。

### 3.B インライン構造（bracketed span `[text]{.class}`）

担い手は pandoc の bracketed span。原稿では `[語句]{.term}` のように書く。確定した 5 クラス:

| クラス | 意味 | LaTeX へ | HTML へ | GFM-md へ（puremd） |
|---|---|---|---|---|
| `.term` | 専門用語・定義語 | `\semterm{…}` | `<span class="term">`＋CSS | `**…**`（太字・lossy） |
| `.keyword` | キーワード・重要語 | `\semkeyword{…}` | `<span class="keyword">`＋CSS | `**…**`（太字・lossy） |
| `.path` | ファイル名・パス | `\sempath{…}`（等幅マクロ） | `<code class="path">` | `` `…` ``（インラインコード） |
| `.kbd` | キー入力 | `\semkbd{…}` | `<kbd>…</kbd>` | `<kbd>…</kbd>`（GFM は raw HTML 可） |
| `.emph` | 意味付き強調 | `\emph{…}` | `<em>` または `<span class>` | `*…*`（斜体） |
| `.rightlabel` | 行末ラベルの右寄せ（旧 `\hfill` 用途） | `\semrightlabel{…}`（=`\hfill`＋内容） | `<span class="rightlabel">`＋CSS `float:right` | テキスト素通し（右寄せは失う・lossy） |

```
原稿:   この [メモリリーク]{.term} を [config.yaml]{.path} で確認し [Ctrl+C]{.kbd} で停止
  ↓ lowering
LaTeX:  この \semterm{メモリリーク} を \sempath{config.yaml} で確認し \semkbd{Ctrl+C} で停止
HTML:   この <span class="term">…</span> を <code class="path">…</code> で確認し <kbd>…</kbd> で停止
MD:     この **メモリリーク** を `config.yaml` で確認し <kbd>Ctrl+C</kbd> で停止
```

- **LaTeX 側は「マクロ定義＋Lua フィルタ」の両方が必要。** pandoc の LaTeX writer は `[x]{.term}` の span クラスを既定で捨てるため、(a) `\newcommand{\term}…` を `src/md_merge/templates/semantic_macros.tex` に定義し `include-in-header` で取り込み、(b) `[x]{.term}` → `\term{x}` に変換する Lua フィルタ（`semantic-spans.lua`、divboxes.lua のインライン版）で呼び出す。マクロ定義だけでは効かない。
- **HTML 側は CSS のみで完結。** pandoc が `[x]{.term}` を `<span class="term">` としてネイティブ出力するので、`defaults/pandoc/semantic.css` を `css:` リストに足すだけ。`.kbd` は `<kbd>` 化、`.path` は `<code>` 化したい場合のみ軽い Lua フィルタを足す。
- `.term` と `.keyword` は GFM ではどちらも**単なる太字**となり意味の区別が失われる（lossy・許容）。
- ⚠️ **新規工数:** `puremd` は現在ブロック fenced div しか変換しない。**インライン span の lowering を puremd に新規追加**する必要がある（カテゴリBの最大の実装項目）。

### 3.C 変数（`{{v:}}`）

実データ置換専用。**値にリテラル LaTeX を入れるのは禁止**（`\` 始まり・`{=latex}` 混入を validate で lint）。cover 等のテンプレートへの代入はテンプレート＝各形式の lowering 物なので対象外（HTML 用は `cover.html` を別に持つ）。

## 4. エスケープハッチ方針

どうしても生コードが要る場合のみ、pandoc 標準の **target-tag 付き raw attribute** を使う。

- ` ```{=latex} ` / ` ```{=html} `（ブロック）、`` `…`{=latex} ``（行内）。
- **非対象形式では警告して破棄**（現在の puremd の LaTeX 破棄を、全形式対応・警告付きに一般化）。
- 原稿での使用は**非推奨**。混入検出は実装済み（次節）。

### 4.1 実装済み: pptmdexport の `latex_check`

`pptmdexport` は抽出した各 MD ブロックに raw attribute `{=FORMAT}` が含まれていないか走査する（[spec/pptx.md 生 raw コードの検出](spec/pptx.md#生-raw-コードの検出latex_check)）。

| モード | 動作 |
|---|---|
| `off` | 検出しない |
| `warn`（既定） | スライド番号・出力ファイル名・個数・最初の行番号を警告 |
| `error` | 同内容をエラーにし、当該 MD を書き出さず非ゼロ終了 |

移行期は `warn` で可視化 → 一括変換完了後に `error` で再混入を防ぐ運用を想定。

## 5. lowering バックエンドのアーキテクチャ

### 5.1 現状（構造定義の三重散在）

セマンティック構造の定義が 3 箇所にハードコードされている:

- `src/md_merge/filters/*.lua`（divboxes / largefontblock / blockindent / keep-together）→ LaTeX 環境
- `src/md_merge/puremd/__init__.py` の `_DEFAULT_ALERTS` / `_DEFAULT_PLAIN_QUOTES` → 素 MD
- `src/md_merge/validate/__init__.py` のホワイトリスト → 検証

新クラスを 1 つ足すたびに 3 箇所を直す必要があり、被覆漏れ（puremd が装飾を黙って捨てる等）が生じやすい。

### 5.2 目標（単一レジストリ＋形式別バックエンド）

**構造レジストリを単一の真実源**にする（`src/md_merge/semantics.yaml`、パッケージ同梱。filters/templates と同様に `package-data` で同梱）。各バックエンド・validate がこれを読む。

```
src/md_merge/semantics.yaml        ← クラス × 形式の lowering 規則の単一定義
  ├─ LaTeX backend  (Lua filters)  ← fenced div / span → 環境・マクロ
  ├─ HTML backend   (native + CSS) ← pandoc ネイティブ <div>/<span> ＋ スタイルシート
  └─ MD backend     (puremd)       ← GFM alert / blockquote / code / 太字斜体へ降格
```

これにより 3.A / 3.B の表が単一ファイルで管理され、**冒頭の `fenced_block` 命名問題も自然に解消**する（語彙が block class / inline class / variable に整理され、raw は escape hatch へ格下げ）。

### 5.3 被覆ギャップ（要対応）

| 構造 | LaTeX | HTML | puremd(MD) | 対応 |
|---|---|---|---|---|
| 既存ブロック装飾属性 | ✅ | △(CSS) | ✗ 黙って破棄 | warn 化 |
| `.keep-together` | ✅ | 未 | unwrap | HTML に CSS 追加 |
| `.center`/`.vspace`/`.pagebreak`/`.vfill` | 新規 | 新規(CSS) | 新規 | 3 形式とも追加 |
| インライン span（term/keyword/path/kbd/emph） | 新規(マクロ) | △(native+CSS) | **✗ 未対応** | **puremd にインライン lowering 新規追加** |

## 6. 移行マップとフェーズ

| 現在 | 移行先 | 後方互換 |
|---|---|---|
| `\par\vspace{N\baselineskip}` / `tex_Nline.md` / `TEX_*_SKIP` | `::: {.vspace lines=N}` | `tex_*.md` の中身をセマンティックマーカーへ差し替え（ファイル名は include として残す） |
| `tex_newpage.md` | `::: {.pagebreak}` | 同上 |
| `tex_vfill.md` / `tex_vfill_newpage.md` | `::: {.vfill}`（＋`.pagebreak`） | 同上 |
| ` ```{=latex} \begin{center} ` | `::: {.center}` | 一括変換（別途） |
| 原稿 pptx 内のその他生 LaTeX | 対応するセマンティック構造 | 一括変換（別途）。`latex_check` で可視化 |

**フェーズ案（段階移行・低リスク）:**

0. **語彙凍結（実装中）** — `src/md_merge/semantics.yaml`（パッケージ同梱）に 3.A/3.B/leaves/raw を定義し、Python ローダー `_semantics.py`（validate/puremd 用）を実装。**完了済み**。命名整理（`fenced_code` 等）はフェーズ 5。
1. **検出で可視化（実装済み）** — `pptmdexport latex_check: warn`。
2. **lowering 被覆を完成** — 新ブロック（center/vspace/pagebreak/vfill）＋インライン span を **3 形式すべて**に実装。
   - **MD（puremd）: 完了・検証済み**。`_semantics` レジストリに配線（`_DEFAULT_*` を撤去）、インライン span（`[x]{.term}`→`**`/`*`/`` ` ``/`<kbd>`）とリーフ記法（`{{vspace:N}}`/`{{pagebreak}}`→`---`/`{{vfill}}`）を実装。既存クラス（note/warning/leadline/widequote/largefontblock/blockindent）は挙動不変。`center`/`keep-together` は設計どおり unwrap に変更。
   - **LaTeX / HTML: 資産作成・検証済み**。`src/md_merge/filters/center.lua`（`.center`→`\begin{center}`／HTML は inline `text-align:center`）、`semantic-spans.lua`（span→マクロ／HTML は kbd・path 要素化）、`semantic-leaf.lua`（リーフ→`FORMAT` 別 RawBlock）、`src/md_merge/templates/semantic_macros.tex`（マクロ）、`defaults/pandoc/semantic.css`（CSS）を作成。**実 pandoc で LaTeX/HTML 出力を検証、pdflatex でマクロのコンパイルも確認済み**（CSS の見た目のみ未検証）。`.center` はフィルタが必要（`\begin{center}` 環境で包む。pandoc は `.center` div を自動では中央寄せしない）。
   - **残り: pandoc defaults へのフィルタ／include-in-header／css の配線**（ユーザーの defaults YAML は環境依存・絶対パスのため自動編集せず、追加スニペットを提示）。LaTeX defaults: `filters:` に semantic-spans.lua / semantic-leaf.lua、`include-in-header:` に semantic_macros.tex。HTML defaults: `filters:` に両 lua、`css:` に semantic.css。
   - **解消済み**: `semantic-spans.lua`（インライン）/ `semantic-leaf.lua`（リーフ）/ `divboxes.lua`（box 系 block の class→env）のルックアップ表は `tools/gen_lua_semantics.py` が `semantics.yaml` からコード生成（`-- >>> GENERATED` 区画、`--check` でドリフト検知）。手動同期は不要。divboxes は `latex.box: true` の 4 クラス（note/warning/leadline/widequote）のみ生成対象で、属性→tcolorbox オプション変換（build_options 等）は手維持。largefontblock/blockindent/center 等の env は各専用フィルタで手維持。詳細は docs §10.2。
3. **`tex_*.md` 資産の差し替え**＋HTML 用 CSS/テンプレート整備。
4. **一括変換** — 既存 pptx 原稿の生 LaTeX をセマンティック構造へ変換。
5. **強制** — `latex_check: error` ＋ `{{v:}}` の LaTeX 値 lint を有効化。命名整理（`fenced_block` → `fenced_code`＋エイリアス）をここで実施。

## 7. 命名整理（保留）

`puremd.strip_config` の判別子 `type: fenced_block` は ` ```lang…``` `（fenced **code** block）の意で、pandoc の `:::`（fenced **div**）と紛らわしい。`fenced_div` 側は pandoc 公式どおりで問題なし。

→ `fenced_block` → `fenced_code` に改名し、旧名は deprecation 警告付きエイリアスとして受理（後方互換）。**実施済み（2026-07-02）**：`_compile_pattern` が `fenced_code` を正式・`fenced_block` を警告付きエイリアスとして扱い、同梱 `puremd_strip.yaml`・仕様書も更新。

## 8. 決定事項と未決事項

### 8.1 決定済み（2026-06-30）

- **GFM フォールバック**: `.term`/`.keyword`=単なる太字、`.kbd`=`<kbd>`、`.path`=インラインコード、`.emph`=斜体。
- **`.vspace`/`.pagebreak`/`.vfill`**: 1 行リーフ記法（`{{vspace:N}}` / `{{pagebreak}}` / `{{vfill}}`、§3.A）。
- **レジストリ形式**: 宣言的 YAML（`src/md_merge/semantics.yaml`、パッケージ同梱）。ローダーは `_semantics.py`。
- **インライン span 略記**: 当面不要（標準の `[x]{.class}` を使う）。
- **HTML CSS の取り込み**: 単独 CSS ファイルを pandoc defaults の `css:` リストで取り込む（既存 `html_pandoc_defaults.yaml` と同方式）。`standalone: true` で `<link>` 生成。1 ファイル完結が要るなら `embed-resources: true` でインライン化。新規 `defaults/pandoc/semantic.css` を**リポジトリ相対**で追加（既存の絶対パスは 2026-10-25 に `${.}` 相対へ修正済み）。
- **LaTeX マクロの取り込み**: 単独 `src/md_merge/templates/semantic_macros.tex` に `\newcommand` を定義し、LaTeX/PDF defaults の `include-in-header:` リストで取り込む（PDF/LaTeX モード専用）。span→マクロ変換の Lua フィルタ（`semantic-spans.lua`）と**セット**で機能する。

- **リーフ記法の綴り**: `{{vspace:N}}` / `{{pagebreak}}` / `{{vfill}}` で確定。既存マーカー族（`{{#id:}}` / `{{v:}}` / `{{num|title|label|rawtitle:}}` / `{{nolabel}}` / `{{noref}}` / `{{enclosenum|titlelabel:}}`）の正規表現はいずれも特定キーワード＋直後コロンを要求するため**衝突しない**（`{{v:` は `v` の直後にコロンが必要で `vspace` は非該当）。render / idcollect / pptmdexport を素通りすることを確認済み。
- **LaTeX マクロの見た目**: §9 に草案。
- **`semantics.yaml` スキーマ**: §10 に草案。

### 8.2 未決

- **LaTeX マクロの最終スタイル**: §9 の色・装飾の具体値（用語集リンクの要否等）。
- ~~**`{{v:}}` LaTeX 値 lint** の実装（validate に追加。フェーズ 5）。~~ → 実装済み（validate が vars 値の生 LaTeX を警告）。
- ~~**Lua への registry 受け渡し**~~ → 決着: `tools/gen_lua_semantics.py` による生成 Lua テーブル方式（§10.2）。メタデータ注入は不採用（フィルタが standalone で動かなくなる・Lua 側の MetaMap 解体が煩雑なため）。

## 9. LaTeX マクロ草案（`src/md_merge/templates/semantic_macros.tex`）

`include-in-header` で取り込む（PDF/LaTeX 専用）。`[x]{.term}` → `\semterm{x}` 等の変換は Lua フィルタ `semantic-spans.lua` が担い、本ファイルは見た目だけを定義する。

**重要な設計上の注意（実装で判明）:**
- **マクロ名は `sem` 接頭辞で名前空間化**する。素の `\term` / `\path` / `\kbd` は他パッケージや文書クラスと衝突し `Command \term already defined` を起こす（実際に発生）。
- **`\def` で定義**して冪等化する。`include-in-header` が二重に効いても（recipe と defaults の両方で指定した等）`already defined` にならない。
- xcolor は `\@ifpackageloaded` で未読込のときのみ自動ロード。

```latex
% semantic_macros.tex（抜粋。実ファイルが正）
\makeatletter\@ifpackageloaded{xcolor}{}{\usepackage{xcolor}}\makeatother
\definecolor{TermColor}{HTML}{1A5FB4}
\definecolor{KeywordBG}{HTML}{FFF3B0}
\def\semterm#1{\textcolor{TermColor}{\textbf{#1}}}     % .term
\def\semkeyword#1{\colorbox{KeywordBG}{\textbf{#1}}}   % .keyword
\def\sempath#1{\texttt{#1}}                            % .path
\def\semkbd#1{\fbox{\small\ttfamily #1}}               % .kbd
% .emph は LaTeX ネイティブ \emph を使用（定義しない）
```

Lua フィルタ側のクラス→マクロ表（`semantic-spans.lua` の `LATEX_MACRO`）と名前を一致させること: term→`semterm` / keyword→`semkeyword` / path→`sempath` / kbd→`semkbd` / emph→`emph`。

リーフ記法（vspace/pagebreak/vfill）は本ファイルではなく Lua フィルタ `semantic-leaf.lua` が `FORMAT=='latex'` のとき `\par\vspace{N\baselineskip}` / `\newpage` / `\vspace*{\fill}` を RawBlock で出力する。

## 10. `semantics.yaml` スキーマ草案

### 10.1 構造

クラス × 出力形式 × 変換規則を 1 ファイルに集約する単一の真実源。`blocks`（fenced div）/ `inlines`（bracketed span）/ `leaves`（リーフ記法）/ `raw`（escape hatch）の 4 セクション。

```yaml
version: 1

# ── ブロック構造（fenced div ::: {.class}）─────────────────────────
blocks:
  note:
    latex: { env: notebox }              # tcolorbox 環境
    html:  { tag: div }                  # <div class="note">（ネイティブ。class は名前と同じ）
    gfm:   { alert: NOTE }               # > [!NOTE]
    attrs: [frame, fontsize, colback, colframe, left, right, center]  # 許可属性（validate/Lua 共有）
  warning:  { latex: { env: warningbox },  gfm: { alert: WARNING },   attrs: [frame, fontsize, colback] }
  leadline: { latex: { env: leadlinebox }, gfm: { alert: IMPORTANT }, attrs: [frame, fontsize, colback] }
  widequote:      { latex: { env: widequotebox },   gfm: { blockquote: plain } }
  largefontblock: { latex: { env: largefontblock }, gfm: { blockquote: labelled } }
  blockindent:    { latex: { env: blockindent },    gfm: { blockquote: labelled } }
  keep-together:
    latex: { wrap: minipage }   # \begin{minipage}{\linewidth}…\end{minipage}（分割抑制）
    html:  { style: "break-inside:avoid" }
    gfm:   { unwrap: true }
  center:
    latex: { env: center }
    html:  { style: "text-align:center" }
    gfm:   { unwrap: true }

# ── インライン構造（bracketed span [text]{.class}）────────────────
inlines:
  term:    { latex: { macro: semterm },    gfm: { wrap: "**" } }
  keyword: { latex: { macro: semkeyword }, gfm: { wrap: "**" } }
  path:    { latex: { macro: sempath },    html: { tag: code }, gfm: { wrap: "`" } }
  kbd:     { latex: { macro: semkbd },     html: { tag: kbd },  gfm: { html: kbd } }
  emph:    { latex: { macro: emph },     gfm: { wrap: "*" } }

# ── リーフ記法（{{name}} / {{name:arg}}）──────────────────────────
leaves:
  vspace:
    arg: dimension                                 # {{vspace:N}} 数値=既定単位の倍、または単位付き（5mm 等）
    latex: { tmpl: "\\par\\vspace{%{arg}}", unit: "\\baselineskip" }  # 純数値なら末尾に unit を付す
    html:  { tag: div, class: vspace, style: "height:%{arg}", unit: em }
    gfm:   { drop: true }                          # MD では破棄
  pagebreak:
    latex: "\\newpage"
    html:  { tag: div, class: pagebreak }          # CSS break-after:page
    gfm:   { text: "---" }
  vfill:
    latex: "\\vspace*{\\fill}"   # * 付き=ページ先頭でも破棄されない
    html:  { tag: div, class: vfill }
    gfm:   { drop: true }

# ── escape hatch（raw passthrough）────────────────────────────────
raw:
  allowed_formats: [latex, html]   # ` ```{=latex} ` / ` ```{=html} ` のみ許可
  nontarget: warn_drop             # 非対象形式では警告して破棄
  gfm:                             # puremd(GFM)での生ブロックの扱い
    drop: [latex]                  # drop に挙げた形式の raw ブロックを破棄。html 等は GFM がそのまま解釈するので残す
```

`raw.gfm.drop` は生 raw ブロック除去の単一の真実源。puremd は `strip_config` の有無に依らず、このリスト（既定 `latex`）から ` ```{=FMT} ` 除去パターンを生成して**常に**適用する。`puremd.strip_config` はプロジェクト独自の追加除去専用に格下げされ、そこに `lang: "{=latex}"` の `fenced_code` を書くと冗長として警告される（旧ハードコード `_DEFAULT_STRIP_PATTERNS` は撤去。実施 2026-07-12）。

規約: `%{arg}` / `%{lines}` は引数・属性値の差し込みプレースホルダ。`html` を省略したクラスは pandoc ネイティブ出力（`<div class>` / `<span class>`）＋ `semantic.css` に委ねる。`gfm` を省略したクラスは puremd で unwrap。

### 10.2 各バックエンドの消費方法

| バックエンド | 言語 | 読み方 |
|---|---|---|
| validate | Python | `semantics.yaml` を直接読み、既知クラス名・許可属性（`attrs`）を検証に使用 |
| puremd | Python | 直接読み、`blocks.*.gfm` / `inlines.*.gfm` / `leaves.*.gfm` 規則で素 MD へ降格 |
| pandoc(LaTeX/HTML) | Lua | **Lua は YAML 非対応**。`tools/gen_lua_semantics.py` が `semantics.yaml` から Lua ルックアップ表を **コード生成**し、各フィルタの `-- >>> GENERATED ... -- <<< GENERATED` 区画へ埋め込む。対象: `semantic-spans.lua`（`LATEX_MACRO`/`HTML_TAG` ← `inlines`）、`semantic-leaf.lua`（`LEAF_LATEX`/`LEAF_LATEX_UNIT`/`LEAF_HTML` ← `leaves`）、`divboxes.lua`（`BLOCK_ENV` ← `blocks` のうち `latex.box: true`）。フィルタは表を読むだけの汎用実装で standalone でも動く。`--check` でドリフト検知（CI/pre-commit 向け）。divboxes の属性→tcolorbox オプション変換（build_options 等）と、largefontblock/blockindent/center の env は単純表でないため手維持。 |

これにより、`inlines` / `leaves` / box 系 `blocks` の新クラス追加は **`semantics.yaml` 1 箇所＋`python tools/gen_lua_semantics.py` 再生成＋必要なら LaTeX マクロ/CSS の見た目**で完結し、Lua への手動同期が解消する（divboxes の属性変換ロジックと非 box 系 block の env は手維持）。`type: fenced_block` の命名問題もこの集約に伴い整理する（フェーズ 5）。

### 10.3 実装状況（フェーズ 0 完了）

- `src/md_merge/semantics.yaml`（パッケージ同梱、pyproject `package-data` に登録）に上記スキーマを定義済み。LaTeX 環境名（`notebox` 等）・GFM アラート種別は既存 Lua フィルタ／puremd デフォルトと一致を確認済み。
- ローダー `src/md_merge/_semantics.py` を実装。`load_semantics(path=None) -> Semantics`（同梱版を既定、パス指定で上書き可、キャッシュ付き、構造検証あり）。アクセサ: `block_classes()` / `inline_classes()` / `leaf_names()` / `allowed_attrs(name)` / `gfm_alerts()` / `gfm_plain_blockquotes()` 等。
- **まだ配線していない（=非破壊）**: puremd / validate / pandoc はまだこのレジストリを参照していない。既存挙動は不変。配線はフェーズ 2 以降で行い、その時点で puremd の `_DEFAULT_ALERTS` 等を `_semantics` 由来に置換する（既存クラスは一致確認済みなので挙動不変）。
