"""``{{#id:TYPE:PART:LOCAL}}`` マーカーの形式チェック。

正しい形式は ``{{#id:TYPE:PART:LOCAL}}``（3 部とも空でない）。TYPE と PART には ``:`` を
含められないが、LOCAL は ``:`` を含んでよい（最初の 2 つの ``:`` で区切る）。

形式が崩れたマーカー（``{{#id:section:PART}}`` のような 2 部だけのもの、空の部があるもの）は
ID として登録されず、本文にそのまま残る。気づけるよう、各段で警告を出すために使う。
"""

from __future__ import annotations

import re

# 正しい形式（idcollect / render が ID として扱うもの）
ID_MARKER_RE = re.compile(r"\{\{#id:([^:}]+):([^:}]+):([^}]+)\}\}")
# {{#id: で始まり }} で閉じるもの全部（形式の正否を問わない）
_ANY_ID_MARKER_RE = re.compile(r"\{\{#id:([^}]*)\}\}")


def malformed_reason(body: str) -> str | None:
    """``{{#id:BODY}}`` の BODY が不正なら理由を返す。正しければ None。"""
    parts = body.split(":", 2)
    if len(parts) < 3:
        return f"部が {len(parts)} つしかありません（TYPE:PART:LOCAL の 3 つが必要）"
    empty = [name for name, p in zip(("TYPE", "PART", "LOCAL"), parts) if not p]
    if empty:
        return f"{'/'.join(empty)} が空です"
    return None


def find_malformed_id_markers(line: str) -> list[tuple[str, str]]:
    """行内の形式不正な ``{{#id:...}}`` を (マーカー文字列, 理由) のリストで返す。"""
    result: list[tuple[str, str]] = []
    for m in _ANY_ID_MARKER_RE.finditer(line):
        reason = malformed_reason(m.group(1))
        if reason is not None:
            result.append((m.group(0), reason))
    return result
