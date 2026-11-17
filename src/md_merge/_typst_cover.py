"""PDF（typst）の表紙の選び方。pandoc サブコマンドと validate で共有する。

- version 4: 表紙は ``cover-md`` を書いたときだけ付く。同梱の標準表紙は
  ``cover-md: cover_standard.md`` と書く（名前だけなら同梱 templates/ を探す）。
- version 3: 表紙は ``typst-cover-md`` を書いたときだけ付く。LaTeX 用の表紙
  （``cover-md`` / ``conditional-process-input``）は使わない（LaTeX は撤去済み）。
- version 2 以前: ``typst-cover-md`` が無く LaTeX 用の表紙があれば、同梱の標準表紙を暗黙に使う
  （LaTeX→Typst 移行のための旧仕様。非推奨の warning を出す）。
"""

from __future__ import annotations

from md_merge._pandoc_keys import pdf_cover_key, uses_plain_keys

# 同梱の標準表紙（src/md_merge/templates/ にある）
TYPST_DEFAULT_COVER = "cover_standard.md"

# 旧名（version 3 までの例やレシピが使っていた名前）。受け付けない（pandoc / validate がエラーにする。
# _pandoc_keys.RENAMED_BUILTIN_COVERS）。tools/convert_recipe_v4.py が新名に書き換える。
TYPST_DEFAULT_COVER_OLD = "cover_standard_typst.md"

# この version 以降は暗黙の標準表紙を使わない
EXPLICIT_COVER_VERSION = 3

_LATEX_COVER_KEYS = ("cover-md", "conditional-process-input")


def _latex_cover_keys(pandoc_section: dict) -> list[str]:
    return [k for k in _LATEX_COVER_KEYS if pandoc_section.get(k)]


def select_typst_cover(pandoc_section: dict, version: int) -> tuple[str | None, bool, str | None]:
    """PDF で使う表紙を決める。

    戻り値は ``(表紙, 同梱か, warning)``。表紙が無ければ ``None``。``同梱か`` が True のときは
    表紙の値が同梱 templates/ のファイル名（暗黙の標準表紙）。warning は利用者に知らせる文。
    """
    explicit = pandoc_section.get(pdf_cover_key(version))
    if explicit:
        return str(explicit), False, None
    if uses_plain_keys(version):
        return None, False, None
    latex_keys = _latex_cover_keys(pandoc_section)
    if not latex_keys:
        return None, False, None
    keys = " / ".join(f"pandoc.{k}" for k in latex_keys)
    if version < EXPLICIT_COVER_VERSION:
        return TYPST_DEFAULT_COVER, True, (
            f"PDF（typst）で pandoc.typst-cover-md が無く {keys}（LaTeX 用の表紙）があるので、"
            f"同梱の標準表紙 {TYPST_DEFAULT_COVER} を使います。この暗黙の切り替えは version 2 までの"
            f"仕様です。version: 4 では cover-md: {TYPST_DEFAULT_COVER} と明示してください"
            f"（変換は tools/convert_recipe_v4.py）"
        )
    return None, False, (
        f"PDF（typst）では {keys}（LaTeX 用の表紙）を使わないので、表紙は付きません。"
        f"表紙を付けるには pandoc.typst-cover-md を指定してください"
        f"（同梱の標準表紙は typst-cover-md: {TYPST_DEFAULT_COVER}）"
    )
