"""ローカル画像参照の走査と書き換え（全段共通の単一の真実源）。

`merge` / `transfer` / `notecomexport` はいずれも「MD 内のローカル画像参照を見つけ、
別の参照へ書き換える」処理を持つ。対象記法（本文 ``![alt](ref)`` と frontmatter の
画像キー）・skip 判定・frontmatter の範囲判定はこのモジュールだけが定義し、各段は
「その参照をどう解決するか」(resolver) のみを実装する。

設計の背景と移行計画は docs/design_image_refs.md を参照。
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

# frontmatter 内で画像パスとして扱うキー（単一の真実源）。
# キーを増やすのはこのタプルに 1 行足すだけでよい。
FRONTMATTER_IMAGE_KEYS: tuple[str, ...] = ("hero", "notecom_cover")

# 本文の画像参照。group 4 は直後に続く pandoc 属性（`{ width=100% }` 等）で、
# 書き換え時はそのまま再出力する。title 付き・スペース入りパス・`<...>` 囲み・
# 参照リンク形式・`<img>` タグは非対応（docs/spec/md_pipeline.md の「非対応の記法」）。
BODY_IMAGE_RE = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)(\))(\s*\{[^}]*\})?')

# githubmd が出力する HTML の ``<img src="...">``。transfer だけが ``html_img=True`` で
# 対象にする（merge 等の入力原稿に現れる ``<img>`` は従来どおり非対応のまま）。src 値は
# HTML エスケープされているので、解決前に戻し、書き換え後に再びエスケープする。
HTML_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\ssrc=")([^"]+)(")', re.IGNORECASE)

# frontmatter の画像キー行。group 2 = 引用符付きパス / group 3 = 引用符なしパス。
# 引用符の有無と行末の空白は書き換え後も保持する。
FRONTMATTER_IMAGE_RE = re.compile(
    r'^(' + '|'.join(re.escape(k) for k in FRONTMATTER_IMAGE_KEYS) + r')(:\s*)(?:"([^"]+)"|([^"\s]+))([ \t]*)$',
    re.IGNORECASE,
)

# 本文の YAML ファイルへのリンク（画像ではない ``[text](path.yaml)``）。merge が画像と
# 同じ規則でコピー＋パス書き換えする（merge.yaml-dir 等）。直前が ``!`` のもの（画像）は除く。
BODY_YAML_LINK_RE = re.compile(r'(?<!!)(\[[^\]]*\]\()([^)\s]+\.ya?ml)(\))', re.IGNORECASE)

# 書き換え対象外の参照（URL・プロトコル相対・絶対パス・アンカー・data URI）
SKIP_RE = re.compile(r'^(?:[a-zA-Z][a-zA-Z0-9+\-.]*://|//|/|#|data:)')

# frontmatter の開始 `---` より前に現れてよい行。merge は結合時に
# `<!-- source: ... -->` を、pptmdexport は `<!-- md_merge_rawtitle: ... -->` を
# 先頭に挿入するため、`---` は 1 行目に来るとは限らない。
FM_LEADIN_RE = re.compile(r'^\s*(?:<!--.*-->\s*)?$')


def should_skip(ref: str) -> bool:
    """*ref* が書き換え対象外（URL・絶対パス・アンカー・data URI）か。"""
    return bool(SKIP_RE.match(ref))


@dataclass
class Ref:
    """走査で見つかった 1 件の画像参照。"""

    ref: str              # 原稿に書かれていた参照文字列
    kind: str             # "body" | "frontmatter" | "yaml"（YAML ファイルへのリンク）
    key: str | None       # frontmatter のキー名（小文字化）。body では None


# resolver: 参照を受け取り、新しい参照文字列を返す。None を返すとその参照は変更しない。
Resolver = Callable[[Ref], "str | None"]


class FrontmatterTracker:
    """行を順に食わせて、その行が YAML frontmatter の内側かを判定する。

    先頭の空行と HTML コメント（`<!-- source: ... -->` 等）は frontmatter の前に
    来うるものとして読み飛ばす。本文が始まった後の `---` は frontmatter とみなさない。
    """

    def __init__(self) -> None:
        self._seeking = True   # まだ開始 `---` を探している
        self._inside = False

    def feed(self, line: str) -> bool:
        """*line* を 1 行進め、その行が frontmatter の内側かを返す。"""
        stripped = line.rstrip("\n\r")
        if self._seeking:
            if stripped == "---":
                self._inside = True
                self._seeking = False
            elif not FM_LEADIN_RE.match(stripped):
                self._seeking = False   # 本文が始まった → frontmatter なし
        elif self._inside and stripped == "---":
            self._inside = False
        return self._inside


def rewrite_line(line: str, *, in_frontmatter: bool, resolve: Resolver, html_img: bool = False) -> str:
    """1 行分の画像参照を *resolve* の戻り値で置き換える。

    frontmatter 内では画像キー行のみ、本文では ``![alt](ref)`` のみを対象とする。
    ``html_img=True`` のときは本文の ``<img src="...">`` も対象にする（githubmd の出力用）。
    """
    if in_frontmatter:
        return FRONTMATTER_IMAGE_RE.sub(lambda m: _sub_frontmatter(m, resolve), line)
    line = BODY_IMAGE_RE.sub(lambda m: _sub_body(m, resolve), line)
    if html_img:
        line = HTML_IMG_SRC_RE.sub(lambda m: _sub_html_img(m, resolve), line)
    return line


def rewrite_yaml_links(line: str, *, in_frontmatter: bool, resolve: Resolver) -> str:
    """1 行分の YAML ファイルへのリンク ``[text](x.yaml)`` を *resolve* の戻り値で置き換える。

    本文のみが対象（frontmatter 内は書き換えない）。Ref の kind は ``"yaml"``。
    """
    if in_frontmatter:
        return line

    def sub(m: "re.Match[str]") -> str:
        new_ref = resolve(Ref(ref=m.group(2), kind="yaml", key=None))
        return f"{m.group(1)}{new_ref or m.group(2)}{m.group(3)}"

    return BODY_YAML_LINK_RE.sub(sub, line)


def rewrite(content: str, resolve: Resolver, *, html_img: bool = False) -> str:
    """MD 全体（frontmatter ＋ 本文）の画像参照を *resolve* の戻り値で置き換える。"""
    tracker = FrontmatterTracker()
    parts: list[str] = []
    for line in content.splitlines(keepends=True):
        in_fm = tracker.feed(line)
        parts.append(rewrite_line(line, in_frontmatter=in_fm, resolve=resolve, html_img=html_img))
    return "".join(parts)


# 画像参照と pandoc 属性の間に空白がある形（``![](a.png) {width=80%}``）。pandoc は
# 属性を画像の直後（空白なし）にしか認めず、空白があると ``{width=80%}`` が本文の
# 文字列として出てしまう。空白・タブのみを対象にし、改行を挟むものは結合しない。
_SPACED_IMAGE_ATTR_RE = re.compile(r'(!\[[^\]]*\]\([^)\s]+\))[ \t]+(\{[^}\n]*\})')

# コードフェンスの開始/終了行（行頭 0〜3 スペース＋ ``` / ~~~ 3 個以上）
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})')

# インラインコード（同じ長さのバッククォート列で閉じる）
_INLINE_CODE_RE = re.compile(r'(`+)(?:(?!\1).)+?\1')


def join_image_attributes(text: str) -> tuple[str, int]:
    """``![alt](ref) {attrs}`` の空白を除き ``![alt](ref){attrs}`` にする。

    pandoc に渡す直前に使う。コードフェンス内とインラインコード内は変えない。
    戻り値は (変換後のテキスト, 結合した件数)。
    """
    out: list[str] = []
    count = 0
    fence: str | None = None   # 開いているフェンスの記号列
    for line in text.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if fence is not None:
            # 閉じフェンスは同じ記号で、開始以上の長さ（後ろは空白のみ）
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line[m.end():].strip():
                fence = None
            out.append(line)
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        pieces: list[str] = []
        pos = 0
        for cm in _INLINE_CODE_RE.finditer(line):
            seg, n = _SPACED_IMAGE_ATTR_RE.subn(r'\1\2', line[pos:cm.start()])
            pieces += [seg, cm.group(0)]
            count += n
            pos = cm.end()
        seg, n = _SPACED_IMAGE_ATTR_RE.subn(r'\1\2', line[pos:])
        pieces.append(seg)
        count += n
        out.append("".join(pieces))
    return "".join(out), count


# ── internals ──────────────────────────────────────────────────────────────

def _sub_body(m: "re.Match[str]", resolve: Resolver) -> str:
    prefix, ref, close = m.group(1), m.group(2), m.group(3)
    attr = m.group(4) or ""
    new_ref = resolve(Ref(ref=ref, kind="body", key=None))
    return f"{prefix}{new_ref or ref}{close}{attr}"


def _sub_html_img(m: "re.Match[str]", resolve: Resolver) -> str:
    ref = html.unescape(m.group(2))
    new_ref = resolve(Ref(ref=ref, kind="body", key=None))
    if new_ref is None:
        return m.group(0)
    return f"{m.group(1)}{html.escape(new_ref, quote=True)}{m.group(3)}"


def _sub_frontmatter(m: "re.Match[str]", resolve: Resolver) -> str:
    key, sep, trailing = m.group(1), m.group(2), m.group(5) or ""
    quoted = m.group(3) is not None
    ref = m.group(3) if quoted else m.group(4)
    new_ref = resolve(Ref(ref=ref, kind="frontmatter", key=key.lower()))
    if new_ref is None:
        return m.group(0)
    return f'{key}{sep}"{new_ref}"{trailing}' if quoted else f"{key}{sep}{new_ref}{trailing}"


# ── コピー名の決定（命名変換 × 衝突回避。merge / transfer 共通）─────────────
#
# 2 つの設定は直交する:
#   命名変換 naming    … preserve（元名のまま） / sanitize（ASCII スラグ化）
#   衝突時   collision … rename（_1 / _2 … を付けて回避） / overwrite（警告して上書き）
#
# 「衝突」は **同一実行内で別のソース画像が同じコピー先になること** を指す。前回実行で
# 置かれた同名ファイルの上書きは衝突ではない（同じ原稿から同じ画像を出すのだから、
# 上書きして再現するのが正しい）。この区別により、どちらの設定でも再実行は冪等になる。

NAMING_MODES = ("preserve", "sanitize")
COLLISION_MODES = ("rename", "overwrite")

_NONASCII_RUN_RE = re.compile(r'[^a-z0-9]+')


def sanitize_name(name: str) -> str:
    """ASCII-safe, web-friendly basename for a copied image.

    NFKC-normalize, lowercase, then collapse every run of non ``[a-z0-9]`` (Japanese,
    spaces, etc.) to a single ``-`` and trim edge hyphens. The extension is preserved
    (lowercased, non-alnum stripped). An empty stem (e.g. an all-Japanese name) falls
    back to ``img`` so the collision policy can still turn it into ``img_1`` etc.
    """
    p = PurePath(name)
    stem = _NONASCII_RUN_RE.sub("-", unicodedata.normalize("NFKC", p.stem).lower()).strip("-")
    if not stem:
        stem = "img"
    ext_raw = re.sub(r'[^a-z0-9]', '', p.suffix.lower())
    ext = f".{ext_raw}" if ext_raw else ""
    return stem + ext


def apply_naming(name: str, naming: str) -> str:
    """命名変換を適用したファイル名を返す（``preserve`` はそのまま）。"""
    return sanitize_name(name) if naming == "sanitize" else name


def pick_destination(candidate: Path, *, collision: str, taken: set[Path]) -> Path:
    """衝突（*taken* に既にある同じコピー先）を *collision* の方針で解消して返す。"""
    if candidate not in taken:
        return candidate
    if collision == "overwrite":
        logging.warning("画像ファイルを上書きします（同名の別画像）: %s", candidate)
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    i = 1
    while True:
        new = candidate.with_name(f"{stem}_{i}{suffix}")
        if new not in taken:
            return new
        i += 1
