"""insertmd のファイル名に書く ``[from-to]`` レンジの展開。

merge（ファイル収集）・validate・procedure の正規化（insertmdpages の展開）で共用する。

to に ``END`` を書くと「残り全部」（終端開放レンジ）。from から 1 ずつ数え、
存在するファイルだけを採用する（無い番号は飛ばす）。数える上限は procedure 項目の
``range-max`` キー（省略時 :data:`DEFAULT_RANGE_MAX`）。存在判定はファイル解決を
知っている呼び出し側が *exists* で渡す。
"""

from __future__ import annotations

import logging
import re
from typing import Callable

_RANGE_RE = re.compile(r'\[([^\]]*)\]')

# 終端開放レンジの to に書くキーワード（大文字小文字は区別しない）
END_KEYWORD = "END"
# 終端開放レンジの上限を指定する procedure 項目キー
RANGE_MAX_KEY = "range-max"
# range-max 省略時の上限
DEFAULT_RANGE_MAX = 99


def _split_range(val: str):
    """``(prefix, spec, suffix)`` を返す。レンジが無ければ None。"""
    m = _RANGE_RE.search(val)
    if m is None:
        return None
    return val[: m.start()], m.group(1), val[m.end() :]


def is_open_range(val: object) -> bool:
    """*val* が ``[from-END]`` の終端開放レンジなら True（from の妥当性は問わない）。"""
    if not isinstance(val, str):
        return False
    parts = _split_range(val)
    if parts is None:
        return False
    spec = parts[1].split("-")
    return len(spec) == 2 and spec[1].upper() == END_KEYWORD


def parse_range_max(raw: object) -> int:
    """``range-max`` の値を整数にする。省略（None）は既定値。不正なら ValueError。"""
    if raw is None:
        return DEFAULT_RANGE_MAX
    if isinstance(raw, bool):
        raise ValueError(f"{RANGE_MAX_KEY} は 1 以上の整数で指定してください: {raw!r}")
    if isinstance(raw, int):
        n = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        n = int(raw.strip())
    else:
        raise ValueError(f"{RANGE_MAX_KEY} は 1 以上の整数で指定してください: {raw!r}")
    if n < 1:
        raise ValueError(f"{RANGE_MAX_KEY} は 1 以上の整数で指定してください: {raw!r}")
    return n


def _format_numbers(nums: list[int]) -> str:
    """[4, 6, 7, 8, 10] → ``4, 6-8, 10``。"""
    out: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def _expand_open(
    val: str,
    prefix: str,
    frm: str,
    suffix: str,
    exists: "Callable[[str], bool] | None",
    range_max: object,
    log: bool,
) -> list[str]:
    if not frm.isdigit():
        raise ValueError(f"[from-{END_KEYWORD}] の from は数値で指定してください: [{frm}-{END_KEYWORD}]")
    frm_i = int(frm)
    max_i = parse_range_max(range_max)
    if max_i < frm_i:
        raise ValueError(f"{RANGE_MAX_KEY} ({max_i}) が from ({frm_i}) より小さいです: {val}")
    if frm.startswith("0"):
        width = len(frm)
        fmt = lambda n: str(n).zfill(width)  # noqa: E731
    else:
        fmt = str
    candidates = [(n, prefix + fmt(n) + suffix) for n in range(frm_i, max_i + 1)]
    if exists is None:
        return [name for _, name in candidates]
    found = [(n, name) for n, name in candidates if exists(name)]
    if log:
        if not found:
            logging.warning(
                "insertmd: %s に該当するファイルが 1 つもありません（%d〜%d を探索）",
                val, frm_i, max_i,
            )
        else:
            last = found[-1][0]
            found_nums = {n for n, _ in found}
            skipped = [n for n in range(frm_i, last + 1) if n not in found_nums]
            logging.info(
                "insertmd: %s → %d 件（見つかった最大番号 %d、探索上限 %d）",
                val, len(found), last, max_i,
            )
            if skipped:
                logging.info("insertmd: %s でスキップした番号: %s", val, _format_numbers(skipped))
    return [name for _, name in found]


def expand_mdfilename(
    val: str,
    exists: "Callable[[str], bool] | None" = None,
    range_max: object = None,
    log: bool = True,
) -> list[str]:
    """Expand a single ``[from-to]`` range in *val* and return the filename list.

    ``[from-END]`` counts up from *from* to *range_max* (default
    :data:`DEFAULT_RANGE_MAX`) and keeps only the names for which *exists*
    returns True. Without *exists* every candidate up to *range_max* is returned
    (name-only callers). With *log*, skipped numbers and the largest number found
    are logged.

    Raises ValueError for invalid range specifications.
    """
    parts = _split_range(val)
    if parts is None:
        return [val]
    prefix, spec, suffix = parts

    if not spec.isascii():
        raise ValueError(f"全角文字は使用できません: [{spec}]")

    pair = spec.split("-")
    if len(pair) != 2 or not pair[0] or not pair[1]:
        raise ValueError(f"[from-to] 形式で指定してください: [{spec}]")

    frm, to = pair

    if to.upper() == END_KEYWORD:
        return _expand_open(val, prefix, frm, suffix, exists, range_max, log)

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
