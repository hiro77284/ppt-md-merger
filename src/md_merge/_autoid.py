"""``indexer.autoid``: #id の無い見出しに ``{{#id:}}`` マーカーを自動で付ける（merge 段）。

結合済み MD の ``#`` / ``##`` / ``###`` 見出しのうち、直前の行に ``{{#id:...}}`` が無いものに
``{{#id:chapter|section|subsection:AUTOHEAD:N}}`` を挿入する（N は出現順の連番、1 始まり）。
以後は通常どおり idcollect → idresolve → render が番号を振る。原稿 MD は書き換えない。

対象外:

- ``####`` 以下の見出し
- ``` ``` ``` / ``~~~`` フェンス内の行
- 複数行の HTML コメント（``<!--`` … ``-->``）の中の行
- YAML frontmatter（文書先頭・``<!-- source: -->`` 行の直後の ``---`` … ``---``）の中の行
- 直前の行に ``{{#id:...}}`` がある見出し（手書きの ID・procedure の chapter/section/subsection）

PART 名 ``AUTOHEAD`` は予約語。原稿に ``{{#id:TYPE:AUTOHEAD:...}}`` があればエラー。
"""

from __future__ import annotations

import logging
import re

AUTOID_PART = "AUTOHEAD"

_HEADING_RE = re.compile(r"^(#{1,3})\s+\S")
_ID_RE = re.compile(r"\{\{#id:[^:}]+:[^:}]+:[^}]+\}\}")
_RESERVED_RE = re.compile(r"\{\{#id:[^:}]+:" + AUTOID_PART + r":[^}]+\}\}")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_SOURCE_MARKER_PREFIX = "<!-- source:"
_LEVEL_TYPE = {1: "chapter", 2: "section", 3: "subsection"}


class AutoIdError(ValueError):
    """予約 PART 名 AUTOHEAD が原稿で使われている。"""


def autoid_enabled(recipe: dict) -> bool:
    indexer = recipe.get("indexer") or {}
    return isinstance(indexer, dict) and indexer.get("autoid") is True


def _is_leadin(stripped: str) -> bool:
    return stripped == "" or (stripped.startswith("<!--") and stripped.endswith("-->"))


def _skip_mask(lines: list[str]) -> list[bool]:
    """見出し判定の対象外にする行（フェンス・HTML コメント・frontmatter の中）を True にする。"""
    n = len(lines)
    mask = [False] * n
    fence: str | None = None
    in_comment = False
    seeking_fm = True  # 文書先頭 or source マーカー直後で、frontmatter の開始 --- を探している
    i = 0
    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if fence is not None:
            mask[i] = True
            mf = _FENCE_RE.match(raw)
            if mf and mf.group(1)[0] == fence[0] and len(mf.group(1)) >= len(fence) \
                    and stripped == mf.group(1):
                fence = None
            i += 1
            continue
        if in_comment:
            mask[i] = True
            if "-->" in raw:
                in_comment = False
            i += 1
            continue
        if stripped.startswith(_SOURCE_MARKER_PREFIX) and stripped.endswith("-->"):
            seeking_fm = True
            i += 1
            continue
        if seeking_fm:
            if stripped == "---":
                end = next((j for j in range(i + 1, n) if lines[j].strip() == "---"), -1)
                if end >= 0:
                    for j in range(i, end + 1):
                        mask[j] = True
                    i = end + 1
                    seeking_fm = False
                    continue
                seeking_fm = False
            elif not _is_leadin(stripped):
                seeking_fm = False
        mf = _FENCE_RE.match(raw)
        if mf:
            fence = mf.group(1)
            mask[i] = True
            i += 1
            continue
        start = raw.find("<!--")
        if start >= 0 and "-->" not in raw[start + 4:]:
            in_comment = True
        i += 1
    return mask


def add_auto_ids(text: str) -> tuple[str, int]:
    """*text* の #id の無い見出しに ``{{#id:...:AUTOHEAD:N}}`` を付け、(新しい本文, 付けた数) を返す。"""
    if _RESERVED_RE.search(text):
        m = _RESERVED_RE.search(text)
        raise AutoIdError(
            f"PART 名 {AUTOID_PART} は indexer.autoid の予約語です（原稿で使えません）: {m.group(0)}"
        )
    lines = text.split("\n")
    mask = _skip_mask(lines)
    out: list[str] = []
    counter = 0
    seen_chapter = False
    warned_orphan = False
    for i, line in enumerate(lines):
        if not mask[i]:
            m = _HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                if level == 1:
                    seen_chapter = True
                has_id = i > 0 and _ID_RE.search(lines[i - 1]) is not None
                if not has_id:
                    if level >= 2 and not seen_chapter and not warned_orphan:
                        logging.warning(
                            "indexer.autoid: 章（#）より前に節（%s）があります。番号は 0.1 のように"
                            " 0 章から始まります: %s",
                            m.group(1), line.strip(),
                        )
                        warned_orphan = True
                    counter += 1
                    out.append(f"{{{{#id:{_LEVEL_TYPE[level]}:{AUTOID_PART}:{counter}}}}}")
        out.append(line)
    return "\n".join(out), counter
