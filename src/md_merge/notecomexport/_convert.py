"""puremd（frontmatter 付き GFM）→ note.com 投稿用ブロック列 への変換コア。

入力は puremd サブコマンドが生成した「YAML frontmatter ＋ 素の GFM」の MD。
出力は notecom_autopilot（tools/notecom_autopilot.py）が読むブロック列で、
ブロック種別は次の 10 種に限定する（note.com エディタで入力できる要素に対応）。

    paragraph / heading1 / heading2 / heading3 / unordered_list / ordered_list /
    quote / code / image / horizontal_rule

旧ツール（webs/scripts/composed_to_ir_converter.py + ir_to_noteyaml_converter.py）の
行指向パーサを移植し、IR 段を省いて直接 note ブロックを吐く。puremd 固有の記法
（frontmatter、画像行末の ``{ width=95% }`` 属性、``> [!NOTE]`` / ``> **QUOTE**`` の
ラベル行、``<!-- source: -->`` コメント、先頭空白付きリスト項目）を吸収する。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── 行パターン ─────────────────────────────────────────────────────────────

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# ![caption](path){ width=95% }  … 末尾の pandoc 属性 { ... } は任意
IMAGE_RE = re.compile(r"^!\[(.*?)\]\(([^)\s]+)\)\s*(\{[^}]*\})?\s*$")
# [![caption](path){ attrs }](url)  … 画像全体をリンクにしたもの（画像 ＋ リンク段落に分解する）
LINKED_IMAGE_RE = re.compile(r"^\[!\[(.*?)\]\(([^)\s]+)\)\s*(\{[^}]*\})?\]\(([^)\s]+)\)\s*$")
# puremd は ' - item' のように先頭空白付きで出すことがあるので先頭空白を許容する
ULIST_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
OLIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")
QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
CODE_FENCE_START_RE = re.compile(r"^\s*(```+|~~~+)\s*([^\s`]*)\s*$")
HR_LINE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
FENCED_DIV_RE = re.compile(r"^\s*:::+")
# > [!NOTE] / > **QUOTE** のようなブロック引用のラベル行（puremd の alert / labelled 降格）
QUOTE_LABEL_RE = re.compile(r"^\s*(?:\[![A-Za-z]+\]|\*\*[^*]+\*\*)\s*$")
RAWTITLE_RE = re.compile(r"<!--\s*md_merge_rawtitle:\s*(.*?)\s*-->")

# ── インライン記法（inline: plain のときに素のテキストへ落とす）──────────────

_INLINE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<br\s*/?>", re.IGNORECASE), "\n"),
    (re.compile(r"<kbd>(.*?)</kbd>", re.IGNORECASE | re.DOTALL), r"\1"),
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    # 日本語文中でも効くよう境界は * と空白だけで判定する（\w は CJK にも一致してしまう）
    (re.compile(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)"), r"\1"),
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
    # 残存 bracketed span [text]{.class} → text
    (re.compile(r"\[([^\]]+)\]\{[^}]*\}"), r"\1"),
]
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")
_ABS_URL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+\-.]*:|//)")
_LEAF_RE = re.compile(r"\{\{[^}]*\}\}")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!&<>~|\"'])")

INLINE_MODES = ("plain", "markdown")
QUOTE_LABEL_MODES = ("drop", "keep")


class ParseError(Exception):
    pass


@dataclass
class Block:
    kind: str
    line_no: int
    data: dict[str, Any] = field(default_factory=dict)


# ── frontmatter ──────────────────────────────────────────────────────────────

def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """先頭の YAML frontmatter を辞書として取り出し、残りの本文を返す。

    merge は先頭ファイルの frontmatter より前に ``<!-- source: ... -->`` を挿入するので、
    開始 ``---`` の前には空行と HTML コメント行だけを許容する。frontmatter が無ければ
    ``({}, text)`` を返す。
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or re.fullmatch(r"\s*<!--.*?-->\s*", lines[i])):
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return {}, text
    j = i + 1
    while j < len(lines) and lines[j].strip() != "---":
        j += 1
    if j >= len(lines):
        return {}, text  # 閉じ --- が無い → frontmatter とみなさない
    fm_text = "\n".join(lines[i + 1 : j])
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        raise ParseError(f"frontmatter の YAML を解析できません: {e}") from e
    if not isinstance(fm, dict):
        raise ParseError("frontmatter がマッピングではありません")
    body = "\n".join(lines[:i] + lines[j + 1 :])
    return fm, body


def first_rawtitle(text: str) -> str | None:
    m = RAWTITLE_RE.search(text)
    return m.group(1) if m else None


# ── HTML コメント除去（コードフェンス外のみ）─────────────────────────────────

def strip_html_comments(text: str) -> str:
    """コードフェンスの外側にある ``<!-- ... -->``（複数行可）を除去する。"""
    out: list[str] = []
    in_fence: str | None = None
    in_comment = False
    for line in text.splitlines():
        if in_comment:
            end = line.find("-->")
            if end < 0:
                continue
            line = line[end + 3 :]
            in_comment = False
        m = CODE_FENCE_START_RE.match(line)
        if in_fence is None and m:
            in_fence = m.group(1)[0]
            out.append(line)
            continue
        if in_fence is not None:
            out.append(line)
            if re.match(rf"^\s*{re.escape(in_fence)}{{3,}}\s*$", line):
                in_fence = None
            continue
        # フェンス外: 1 行内で完結するコメントを除去し、開きっぱなしなら続行
        line = re.sub(r"<!--.*?-->", "", line)
        start = line.find("<!--")
        if start >= 0:
            line = line[:start]
            in_comment = True
        out.append(line)
    return "\n".join(out)


# ── パーサ ───────────────────────────────────────────────────────────────────

class GfmBlockParser:
    def __init__(self, text: str, source_name: str = "<memory>") -> None:
        self.lines = text.splitlines()
        self.source_name = source_name
        self.index = 0
        self.blocks: list[Block] = []

    def parse(self) -> list[Block]:
        while self.index < len(self.lines):
            line = self._current()
            if line.strip() == "":
                self.index += 1
                continue
            line_no = self.index + 1

            if FENCED_DIV_RE.match(line):
                # puremd が unwrap しなかった fenced div の囲い行は捨てる（中身は残る）
                logging.warning("%s:%d: fenced div の囲い行を無視します: %s", self.source_name, line_no, line.strip())
                self.index += 1
                continue

            m = HEADING_RE.match(line)
            if m:
                self.blocks.append(Block("heading", line_no, {"level": len(m.group(1)), "text": m.group(2)}))
                self.index += 1
                continue

            m = LINKED_IMAGE_RE.match(line.strip())
            if m:
                self.blocks.append(Block("image", line_no, {
                    "caption": m.group(1).strip(), "path": m.group(2).strip(), "link": m.group(4).strip(),
                }))
                self.index += 1
                continue

            m = IMAGE_RE.match(line.strip())
            if m:
                self.blocks.append(Block("image", line_no, {"caption": m.group(1).strip(), "path": m.group(2).strip()}))
                self.index += 1
                continue

            m = CODE_FENCE_START_RE.match(line)
            if m:
                self._emit_code_block(m)
                continue

            if ULIST_RE.match(line) and not HR_LINE_RE.match(line):
                self._emit_list(ordered=False)
                continue
            if OLIST_RE.match(line):
                self._emit_list(ordered=True)
                continue
            if QUOTE_RE.match(line):
                self._emit_quote_block()
                continue
            if self._is_blank_bounded_horizontal_rule(self.index):
                self.blocks.append(Block("horizontal_rule", line_no))
                self.index += 1
                continue
            if TABLE_LINE_RE.match(line):
                self._emit_table()
                continue

            self._emit_paragraph()
        return self.blocks

    def _current(self) -> str:
        return self.lines[self.index]

    def _is_blank_bounded_horizontal_rule(self, idx: int) -> bool:
        """idx 行が「空行に挟まれた --- / *** / ___」として区切り線になるか。"""
        if idx < 0 or idx >= len(self.lines) or not HR_LINE_RE.match(self.lines[idx]):
            return False
        prev_blank = idx == 0 or self.lines[idx - 1].strip() == ""
        next_blank = idx + 1 >= len(self.lines) or self.lines[idx + 1].strip() == ""
        return prev_blank and next_blank

    def _emit_list(self, ordered: bool) -> None:
        """リスト 1 ブロックを切り出す。

        note.com のリストは 1 階層しか無いので、インデントされた子項目（同種・異種を
        問わず）は同じ階層に平坦化し、警告を出す。項目直後のインデントされた通常行は
        直前項目への継続行として連結する。
        """
        start_line = self.index + 1
        items: list[str] = []
        pat = OLIST_RE if ordered else ULIST_RE
        other = ULIST_RE if ordered else OLIST_RE
        base_indent: int | None = None
        nested = False
        while self.index < len(self.lines):
            line = self._current()
            if line.strip() == "":
                break
            indent = len(line) - len(line.lstrip())
            m = pat.match(line) or (other.match(line) if base_indent is not None and indent > base_indent else None)
            if m is None:
                if items and indent > 0:
                    items[-1] = items[-1] + " " + line.strip()  # 継続行
                    self.index += 1
                    continue
                break
            if base_indent is None:
                base_indent = indent
            elif indent > base_indent:
                nested = True
            items.append(m.group(1).strip())
            self.index += 1
        if nested:
            logging.warning("%s:%d: ネストしたリストは平坦化します（note.com は 1 階層のみ）", self.source_name, start_line)
        self.blocks.append(Block("list", start_line, {"ordered": ordered, "items": items}))

    def _emit_quote_block(self) -> None:
        start_line = self.index + 1
        lines: list[str] = []
        while self.index < len(self.lines):
            line = self._current()
            if line.strip() == "":
                break
            m = QUOTE_RE.match(line)
            if not m:
                break
            lines.append(m.group(1))
            self.index += 1
        self.blocks.append(Block("quote", start_line, {"lines": lines}))

    def _emit_code_block(self, start_match: re.Match[str]) -> None:
        start_line = self.index + 1
        fence = start_match.group(1)
        lang = start_match.group(2).strip() or None
        close_re = re.compile(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$")
        self.index += 1
        buf: list[str] = []
        while self.index < len(self.lines):
            line = self._current()
            if close_re.match(line):
                self.index += 1
                self.blocks.append(Block("code", start_line, {"lang": lang, "text": "\n".join(buf)}))
                return
            buf.append(line)
            self.index += 1
        raise ParseError(f"{self.source_name}:{start_line}: unclosed code fence")

    def _emit_table(self) -> None:
        """GFM 表は note.com に無いので等幅（code ブロック）として出す。"""
        start_line = self.index + 1
        buf: list[str] = []
        while self.index < len(self.lines) and TABLE_LINE_RE.match(self._current()):
            buf.append(self._current().rstrip())
            self.index += 1
        logging.warning("%s:%d: 表は code ブロックとして出力します（note.com に表はありません）", self.source_name, start_line)
        self.blocks.append(Block("code", start_line, {"lang": None, "text": "\n".join(buf)}))

    def _emit_paragraph(self) -> None:
        start_line = self.index + 1
        buf: list[str] = []
        while self.index < len(self.lines):
            line = self._current()
            stripped = line.strip()
            if stripped == "":
                break
            if HEADING_RE.match(line) or IMAGE_RE.match(stripped) or LINKED_IMAGE_RE.match(stripped):
                break
            if CODE_FENCE_START_RE.match(line):
                break
            if ULIST_RE.match(line) or OLIST_RE.match(line) or QUOTE_RE.match(line):
                break
            if self._is_blank_bounded_horizontal_rule(self.index) or FENCED_DIV_RE.match(line):
                break
            buf.append(line.rstrip())
            self.index += 1
        text = "\n".join(buf).strip()
        if not text:
            raise ParseError(f"{self.source_name}:{start_line}: empty paragraph")
        self.blocks.append(Block("paragraph", start_line, {"text": text}))


# ── インライン変換 ───────────────────────────────────────────────────────────

def _strip_markup(text: str) -> str:
    """リンク以外のインライン記法（強調・コード・kbd・<br>・エスケープ）を素のテキストに落とす。"""
    for pat, repl in _INLINE_RULES:
        text = pat.sub(repl, text)
    return _ESCAPE_RE.sub(r"\1", text)


def link_text_form(text: str, url: str) -> str:
    """リンクを 1 本のテキストで表すときの形: ``text（url）``。text と url が同じなら url だけ。"""
    return text if text.strip() == url.strip() else f"{text}（{url}）"


class InlineConverter:
    """インライン記法を note 用に変換する。

    ``text(s)``  … 1 本の素のテキスト（inline: plain）。リンクは ``text（url）`` 形。
    ``runs(s)``  … リンクを保った run 列 ``[{"text": ..}, {"text": .., "url": ..}, ..]``。
                   リンクが 1 つも無ければ None（YAML には runs を出さない）。
    inline: markdown のときは記法をそのまま残し、runs も作らない。

    相対 URL（``/blog/...``）は ``link_base`` があれば絶対 URL にし、無ければリンクを
    外して素のテキストにする（警告）。``#anchor`` は常に素のテキスト。
    """

    def __init__(self, mode: str = "plain", link_base: str | None = None, source_name: str = "<memory>") -> None:
        self.mode = mode
        self.link_base = (link_base or "").rstrip("/")
        self.source_name = source_name

    # ── URL 解決 ──────────────────────────────────────────────────────
    def resolve_url(self, url: str, line_no: int) -> str | None:
        url = url.strip()
        if url.startswith("#"):
            logging.warning("%s:%d: ページ内リンク %s はテキストに落とします", self.source_name, line_no, url)
            return None
        if _ABS_URL_RE.match(url):
            return url
        if self.link_base:
            return self.link_base + (url if url.startswith("/") else "/" + url)
        logging.warning("%s:%d: 相対リンク %s は notecomexport.link_base が無いためテキストに落とします",
                        self.source_name, line_no, url)
        return None

    # ── 前処理（両モード共通） ────────────────────────────────────────
    def _pre(self, text: str, line_no: int) -> str:
        if _LEAF_RE.search(text):
            logging.warning("%s:%d: 未処理のリーフ記法 %s を削除します",
                            self.source_name, line_no, _LEAF_RE.search(text).group(0))
            text = _LEAF_RE.sub("", text)
        return text

    # ── 変換本体 ──────────────────────────────────────────────────────
    def convert(self, text: str, line_no: int = 0) -> tuple[str, list[dict[str, str]] | None]:
        """``(素のテキスト, runs)`` を返す。runs はリンクが 1 つも無ければ None。

        強調・コード等の記法はリンク分割の前に全体へ適用する（``**[text](url)**`` の
        ように記法がリンクをまたぐことがあるため）。``\\_`` 等のエスケープ解除もこの
        段階で済むので、URL 中の ``\\_`` も素の ``_`` になる。
        """
        text = self._pre(text, line_no)
        if self.mode != "plain":
            return re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE), None
        text = _strip_markup(text)

        runs: list[dict[str, str]] = []
        has_link = False
        pos = 0

        def add_text(s: str) -> None:
            if not s:
                return
            if runs and "url" not in runs[-1]:
                runs[-1]["text"] += s
            else:
                runs.append({"text": s})

        for m in _LINK_RE.finditer(text):
            add_text(text[pos : m.start()])
            label, raw_url = m.group(1), m.group(2)
            url = self.resolve_url(raw_url, line_no)
            if url is None:
                add_text(label if raw_url.startswith("#") else link_text_form(label, raw_url))
            else:
                runs.append({"text": label, "url": url})
                has_link = True
            pos = m.end()
        add_text(text[pos:])

        plain = "".join(link_text_form(r["text"], r["url"]) if "url" in r else r["text"] for r in runs)
        return plain, (runs if has_link else None)

    def text(self, text: str, line_no: int = 0) -> str:
        return self.convert(text, line_no)[0]

    def item(self, text: str, line_no: int = 0) -> Any:
        """リスト項目・引用行用: リンクが無ければ str、あれば {"text", "runs"}。"""
        plain, runs = self.convert(text, line_no)
        return plain if runs is None else {"text": plain, "runs": runs}


# ── note ブロックへの変換 ────────────────────────────────────────────────────

def _clean_lines(lines: list[str]) -> list[str]:
    """引用ブロックの前後の空行を落とし、内部の連続空行は 1 行に詰める。"""
    out: list[str] = []
    for ln in lines:
        if ln.strip() == "" and (not out or out[-1].strip() == ""):
            continue
        out.append(ln.rstrip())
    while out and out[-1].strip() == "":
        out.pop()
    return out


def blocks_to_note(
    blocks: list[Block],
    *,
    inline: str = "plain",
    quote_labels: str = "drop",
    source_name: str = "<memory>",
    image_path_fn=None,
    link_base: str | None = None,
) -> list[dict[str, Any]]:
    cv = InlineConverter(inline, link_base, source_name)
    out: list[dict[str, Any]] = []
    for b in blocks:
        ln = b.line_no
        if b.kind == "paragraph":
            plain, runs = cv.convert(b.data["text"], ln)
            entry: dict[str, Any] = {"type": "paragraph", "text": plain}
            if runs:
                entry["runs"] = runs
            out.append(entry)
        elif b.kind == "heading":
            # note.com の見出しは大（heading1/2）と小（heading3）の 2 段階。H4 以下は小に丸める
            level = min(b.data["level"], 3)
            text = cv.text(b.data["text"], ln).replace("\n", " ")
            out.append({"type": f"heading{level}", "text": text})
        elif b.kind == "list":
            items = []
            for i in b.data["items"]:
                it = cv.item(i, ln)
                items.append(it.replace("\n", " ") if isinstance(it, str) else it)
            out.append({"type": "ordered_list" if b.data["ordered"] else "unordered_list", "items": items})
        elif b.kind == "image":
            path = b.data["path"]
            if image_path_fn is not None:
                path = image_path_fn(path, ln)
            entry = {"type": "image", "path": path}
            caption = cv.text(b.data.get("caption") or "", ln).replace("\n", " ")
            entry["caption"] = caption
            # 画像リンク [![..](img)](url) → note の画像ブロックのリンク設定（ツールバーのチェーン）
            if b.data.get("link"):
                url = cv.resolve_url(b.data["link"], ln)
                if url is not None:
                    entry["link"] = url
            out.append(entry)
        elif b.kind == "quote":
            lines = b.data["lines"]
            if quote_labels == "drop" and lines and QUOTE_LABEL_RE.match(lines[0]):
                lines = lines[1:]
            lines = _clean_lines(lines)
            if not lines:
                logging.warning("%s:%d: 空の引用ブロックを無視します", source_name, ln)
                continue
            out.append({"type": "quote", "lines": [cv.item(x, ln) for x in lines]})
        elif b.kind == "code":
            lang = b.data.get("lang")
            if lang and lang.startswith("{="):
                logging.warning("%s:%d: raw ブロック %s は note.com に出力できないため削除します", source_name, ln, lang)
                continue
            entry = {"type": "code", "code": b.data["text"]}
            if lang:
                entry["lang"] = lang
            out.append(entry)
        elif b.kind == "horizontal_rule":
            out.append({"type": "horizontal_rule"})
        else:  # pragma: no cover
            raise ParseError(f"{source_name}:{ln}: unsupported block kind {b.kind!r}")
    return out


def build_meta(
    fm: dict[str, Any],
    *,
    fallback_title: str | None,
    hashtags: list[str] | None,
    cover: str | None,
    image_path_fn=None,
) -> dict[str, Any]:
    """frontmatter から note 用 meta を組み立てる。

    title  … frontmatter.title → md_merge_rawtitle → "無題"
    cover  … notecomexport.cover → frontmatter.notecom_cover → frontmatter.hero
             （note.com のカバーは 1280×670 に切り抜かれるため、自社サイト用の hero とは
             別画像を notecom_cover で指定できる。hero への fallback は info ログで知らせる）
    hashtags … notecomexport.hashtags → frontmatter.tags（各要素に # を前置）
    author / date … frontmatter.author / published_at（日付部分）
    """
    meta: dict[str, Any] = {}
    title = str(fm.get("title") or "").strip() or (fallback_title or "").strip() or "無題"
    meta["title"] = title

    cover_val = (cover or "").strip()
    if not cover_val:
        cover_val = str(fm.get("notecom_cover") or "").strip()
    if not cover_val:
        cover_val = str(fm.get("hero") or "").strip()
        if cover_val:
            logging.info("notecom_cover が無いので hero をカバー画像に使います: %s", cover_val)
    if cover_val:
        meta["cover"] = image_path_fn(cover_val, 0) if image_path_fn else cover_val

    tags: list[str] = []
    if hashtags:
        tags = [str(t) for t in hashtags]
    else:
        raw = fm.get("tags") or []
        if isinstance(raw, str):
            raw = [t for t in re.split(r"[,、\s]+", raw) if t]
        tags = [str(t) for t in raw]
    tags = [t if t.startswith("#") else f"#{t}" for t in (t.strip() for t in tags) if t]
    if tags:
        meta["hashtags"] = tags

    if fm.get("author"):
        meta["author"] = str(fm["author"])
    pub = fm.get("published_at") or fm.get("date")
    if pub is not None:
        meta["date"] = str(pub)[:10]
    if fm.get("excerpt"):
        meta["excerpt"] = str(fm["excerpt"])
    return meta


def convert_markdown(
    text: str,
    *,
    source_name: str = "<memory>",
    inline: str = "plain",
    quote_labels: str = "drop",
    hashtags: list[str] | None = None,
    cover: str | None = None,
    image_path_fn=None,
    link_base: str | None = None,
) -> dict[str, Any]:
    """puremd テキスト全体を ``{"meta": ..., "blocks": [...]}`` に変換する。"""
    fallback_title = first_rawtitle(text)
    fm, body = split_frontmatter(text)
    body = strip_html_comments(body)
    blocks = GfmBlockParser(body, source_name).parse()
    meta = build_meta(fm, fallback_title=fallback_title, hashtags=hashtags, cover=cover, image_path_fn=image_path_fn)
    note_blocks = blocks_to_note(
        blocks, inline=inline, quote_labels=quote_labels, source_name=source_name,
        image_path_fn=image_path_fn, link_base=link_base,
    )
    return {"meta": meta, "blocks": note_blocks}


# ── YAML 出力 ────────────────────────────────────────────────────────────────

class _IndentDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):  # type: ignore[override]
        return super().increase_indent(flow, False)


def _str_representer(dumper: yaml.SafeDumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def dump_note_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_IndentDumper, allow_unicode=True, sort_keys=False, width=4096)


def write_text_lf(path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
