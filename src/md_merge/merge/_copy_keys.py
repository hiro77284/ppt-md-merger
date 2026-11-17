"""merge セクションのコピー有無キー（肯定形 copy-* が標準、否定形 no-copy-* も許容）。

- ``copy-images`` / ``copy-yamls``: 既定 true。false でコピー・パス書き換えを行わない。
- ``no-copy-images`` / ``no-copy-yamls``: 旧来の否定形。引き続き受け付ける。
- 両方を指定して意味が食い違う（例: ``copy-images: true`` と ``no-copy-images: true``）場合はエラー。
  意味が一致する指定（``copy-images: false`` と ``no-copy-images: true``）は許容する。
"""

from __future__ import annotations

# (肯定形キー, 否定形キー)
COPY_KEY_PAIRS: tuple[tuple[str, str], ...] = (
    ("copy-images", "no-copy-images"),
    ("copy-yamls", "no-copy-yamls"),
)


class CopyKeyConflictError(ValueError):
    """copy-* と no-copy-* の指定が矛盾している。"""


def _flag(value: object) -> bool:
    return bool(value)


def resolve_no_copy(mc: dict, positive: str, negative: str) -> bool:
    """merge セクション ``mc`` から「コピーしない」なら True を返す。

    どちらのキーも無ければ False（＝コピーする）。矛盾時は CopyKeyConflictError。
    """
    if not isinstance(mc, dict):
        return False
    has_pos = positive in mc
    has_neg = negative in mc
    if has_pos and has_neg:
        no_copy_from_pos = not _flag(mc[positive])
        no_copy_from_neg = _flag(mc[negative])
        if no_copy_from_pos != no_copy_from_neg:
            raise CopyKeyConflictError(
                f"merge.{positive}: {mc[positive]!r} と merge.{negative}: {mc[negative]!r} が矛盾しています"
                f"（{positive} に一本化してください）"
            )
        return no_copy_from_neg
    if has_pos:
        return not _flag(mc[positive])
    if has_neg:
        return _flag(mc[negative])
    return False


def copy_key_errors(mc: object) -> list[str]:
    """validate 用: merge セクションの copy-* / no-copy-* の矛盾をエラーメッセージで返す。"""
    if not isinstance(mc, dict):
        return []
    errors: list[str] = []
    for positive, negative in COPY_KEY_PAIRS:
        try:
            resolve_no_copy(mc, positive, negative)
        except CopyKeyConflictError as exc:
            errors.append(str(exc))
    return errors
