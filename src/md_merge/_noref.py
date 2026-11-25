"""置換抑制範囲 ``{{noref:begin}}`` … ``{{noref:end}}`` の判定（全段共通）。

範囲内の行は、スライドの ``#NOREPLACE#`` と同様に文字列置換の対象外になる:

- pptmerge のノート置換（``<__TITLE__>`` 等・``{{v:}}``・``{{num/title/label:}}``）
- pptmdexport / pptimgexport のプレースホルダー置換（``<__TITLE__>`` 等）
- render の参照変換・変数置換・``{{sectionlist}}`` 展開（``{{#id:}}`` 行は
  ``{{noref}}`` 付きと同じ扱いで、見出しの番号付けは行う）

マーカーは行単独で書く。pptmerge / pptmdexport は残し、render が取り除く。
`````` ``` `````` / ``~~~`` フェンス内のマーカーは記法の例示とみなして無視する
（フェンス自体は範囲内に置ける）。
"""

from __future__ import annotations

import logging
import re
from typing import Callable

NOREF_BEGIN = "{{noref:begin}}"
NOREF_END = "{{noref:end}}"

NOREF_BEGIN_RE = re.compile(r"^\s*\{\{noref:begin\}\}\s*$")
NOREF_END_RE = re.compile(r"^\s*\{\{noref:end\}\}\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

# 行の種別
PLAIN = 0  # 通常行（置換する）
PROTECTED = 1  # 範囲内の行（置換しない）
MARKER = 2  # begin / end マーカー行そのもの


def classify_lines(lines: list[str], where: str = "") -> list[int]:
    """各行を PLAIN / PROTECTED / MARKER に分類する（*lines* は改行付きでも可）。

    閉じ忘れの begin は末尾まで範囲とみなし、対応の無い end は無視する（いずれも警告）。
    範囲の入れ子は無い（範囲内の begin は警告して無視）。
    """
    kinds: list[int] = []
    inside = False
    begin_lineno = 0
    fence: str | None = None
    suffix = f" ({where})" if where else ""
    for lineno, line in enumerate(lines, start=1):
        raw = line.rstrip("\n\r")
        mf = _FENCE_RE.match(raw)
        if fence is not None:
            if mf and mf.group(1)[0] == fence[0] and len(mf.group(1)) >= len(fence) \
                    and raw.strip() == mf.group(1):
                fence = None
            kinds.append(PROTECTED if inside else PLAIN)
            continue
        if mf:
            fence = mf.group(1)
            kinds.append(PROTECTED if inside else PLAIN)
            continue
        if NOREF_BEGIN_RE.match(raw):
            if inside:
                logging.warning(
                    "%s: %d 行目 — 範囲内の %s は無視します（入れ子はできません）%s",
                    NOREF_BEGIN, lineno, NOREF_BEGIN, suffix,
                )
            inside = True
            begin_lineno = lineno
            kinds.append(MARKER)
            continue
        if NOREF_END_RE.match(raw):
            if not inside:
                logging.warning(
                    "%s: %d 行目 — 対応する %s がありません（無視します）%s",
                    NOREF_END, lineno, NOREF_BEGIN, suffix,
                )
            inside = False
            kinds.append(MARKER)
            continue
        kinds.append(PROTECTED if inside else PLAIN)
    if inside:
        logging.warning(
            "%s: %d 行目の範囲が閉じていません — 末尾まで置換を抑制します%s",
            NOREF_BEGIN, begin_lineno, suffix,
        )
    return kinds


def has_noref_range(text: str) -> bool:
    return NOREF_BEGIN in text


def apply_outside_noref(text: str, fn: Callable[[str], str], where: str = "") -> str:
    """*text* のうち範囲外の部分にだけ *fn* を適用する（範囲内とマーカー行はそのまま）。

    範囲外の連続行はまとめて *fn* に渡す。マーカーが無ければ ``fn(text)`` と同じ。
    """
    if not has_noref_range(text):
        return fn(text)
    lines = text.splitlines(keepends=True)
    kinds = classify_lines(lines, where)
    out: list[str] = []
    chunk: list[str] = []
    for line, kind in zip(lines, kinds):
        if kind == PLAIN:
            chunk.append(line)
            continue
        if chunk:
            out.append(fn("".join(chunk)))
            chunk = []
        out.append(line)
    if chunk:
        out.append(fn("".join(chunk)))
    return "".join(out)
