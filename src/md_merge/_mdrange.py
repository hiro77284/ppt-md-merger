"""insertmd のファイル名に書く ``[from-to]`` レンジの展開。

merge（ファイル収集）・validate・procedure の正規化（insertmdpages の展開）で共用する。
"""

from __future__ import annotations

import re

_RANGE_RE = re.compile(r'\[([^\]]*)\]')


def expand_mdfilename(val: str) -> list[str]:
    """Expand a single ``[from-to]`` range in *val* and return the filename list.

    Raises ValueError for invalid range specifications.
    """
    m = _RANGE_RE.search(val)
    if m is None:
        return [val]

    spec = m.group(1)
    prefix = val[: m.start()]
    suffix = val[m.end() :]

    if not spec.isascii():
        raise ValueError(f"全角文字は使用できません: [{spec}]")

    parts = spec.split("-")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"[from-to] 形式で指定してください: [{spec}]")

    frm, to = parts

    if frm.isdigit() and to.isdigit():
        frm_i, to_i = int(frm), int(to)
        if frm.startswith("0") or to.startswith("0"):
            width = max(len(frm), len(to))
            fmt = lambda n: str(n).zfill(width)  # noqa: E731
        else:
            fmt = str
        step = 1 if frm_i <= to_i else -1
        return [prefix + fmt(n) + suffix for n in range(frm_i, to_i + step, step)]

    if len(frm) == 1 and len(to) == 1 and frm.isalpha() and to.isalpha():
        if frm.isupper() != to.isupper():
            raise ValueError(f"from と to の大文字小文字が一致しません: [{spec}]")
        step = 1 if frm <= to else -1
        return [prefix + chr(c) + suffix for c in range(ord(frm), ord(to) + step, step)]

    raise ValueError(
        f"from/to は数値または単一アルファベット文字で指定してください: [{spec}]"
    )
