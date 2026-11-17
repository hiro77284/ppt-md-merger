"""pandoc セクションのキーの読み方（recipe version ごと）。pandoc サブコマンドと validate で共有する。

LaTeX（lualatex）を撤去したので、PDF は typst だけになった（docs/design_typst_migration.md Phase 7）。

- version 4: PDF 用のキーは接頭辞なし、HTML 用は ``html`` 付きにそろえた。
  PDF の表紙 = ``cover-md``、PDF の pandoc defaults = ``defaults``、HTML の表紙 = ``htmlcover``。
  LaTeX 専用だったキーと、version 3 までの typst 用の名前（``typst-cover-md`` / ``typstdefaults``）
  はエラー。
- version 3 以前: PDF の表紙 = ``typst-cover-md``、defaults = ``typstdefaults``。``cover-md`` と
  ``defaults`` は LaTeX 用の意味なので PDF では読まない。LaTeX 専用キーは警告して使わない。
"""

from __future__ import annotations

# この version から PDF 用のキーを接頭辞なしの名前で読む
PLAIN_KEYS_VERSION = 4

# LaTeX 専用だった pandoc キー（PDF は typst だけになったので読まない）。
REMOVED_LATEX_KEYS = (
    "template", "include-in-header", "include-before-body",
    "conditional-process-input", "conditional-process-output", "format",
)

# version 4 で使えなくなったキー → 移行先の案内
REMOVED_IN_V4: dict[str, str] = {
    "typst-cover-md": "pandoc.typst-cover-md は pandoc.cover-md に改名しました",
    "typstdefaults": "pandoc.typstdefaults は pandoc.defaults に改名しました",
    "engine": "pandoc.engine は廃止しました（PDF は常に typst）。消してください",
    "template": "pandoc.template は廃止しました（LaTeX 用）。typst のテンプレートは defaults ファイルの template: に書きます",
    "include-in-header": "pandoc.include-in-header は廃止しました（LaTeX 用）。typst では defaults ファイルの include-in-header: に書きます",
    "include-before-body": "pandoc.include-before-body は廃止しました（LaTeX 用）。表紙は pandoc.cover-md（PDF）/ pandoc.htmlcover（HTML）に書きます",
    "conditional-process-input": "pandoc.conditional-process-input は廃止しました（LaTeX 表紙用）。表紙は pandoc.cover-md に書きます",
    "conditional-process-output": "pandoc.conditional-process-output は廃止しました（LaTeX 表紙用）",
    "format": "pandoc.format は廃止しました（LaTeX 用）",
    "metadata-file": "pandoc.metadata-file は廃止しました。メタデータは defaults ファイルの metadata: に書きます（PDF は pandoc.defaults、HTML は htmldefaults / revealdefaults）",
}

# 改名した同梱 defaults（旧名 → 新名）。旧名は受け付けない（エイリアスなし）。
RENAMED_BUILTIN_DEFAULTS: dict[str, str] = {
    "typst_semantic_engine.yaml": "report_base_defaults.yaml",
}

# 改名した同梱の表紙（旧名 → 新名）。旧名は受け付けない（エイリアスなし）。
RENAMED_BUILTIN_COVERS: dict[str, str] = {
    "cover_standard_typst.md": "cover_standard.md",
}

# version 3 以前では使えるが非推奨のキー（version 4 で廃止）
DEPRECATED_BEFORE_V4 = ("metadata-file",)


def uses_plain_keys(version: int | None) -> bool:
    return version is not None and version >= PLAIN_KEYS_VERSION


def pdf_cover_key(version: int | None) -> str:
    """PDF の表紙を書くキー名。"""
    return "cover-md" if uses_plain_keys(version) else "typst-cover-md"


def pdf_defaults_key(version: int | None) -> str:
    """PDF の pandoc defaults を書くキー名。"""
    return "defaults" if uses_plain_keys(version) else "typstdefaults"


def engine_error(pandoc_section: dict) -> str | None:
    """pandoc.engine に typst 以外が書いてあればエラー文を返す（version 3 以前）。"""
    engine = pandoc_section.get("engine")
    if engine is None or str(engine).strip().lower() == "typst":
        return None
    return (
        f"pandoc.engine: {engine} は使えません。LaTeX（lualatex）は撤去しました。"
        "PDF は typst で出力します（engine キーは消してください）"
    )


def _basename(value: object) -> str:
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def renamed_cover_errors(pandoc_section: dict, version: int | None) -> list[str]:
    """PDF の表紙に改名前の同梱表紙の名前があればエラー文を返す（全 version）。

    ファイル名（basename）だけで判定する。レシピのフォルダなどに同じ名前のファイルを置いていても
    エラーにする（旧名は使わない）。
    """
    key = pdf_cover_key(version)
    val = pandoc_section.get(key)
    if not val:
        return []
    name = _basename(val)
    new = RENAMED_BUILTIN_COVERS.get(name)
    if not new:
        return []
    return [
        f"pandoc.{key}: 同梱の {name} は {new} に改名しました（旧名は使えません）。"
        f"{val} を {new} に書き換えてください"
    ]


def renamed_defaults_errors(pandoc_section: dict, version: int | None) -> list[str]:
    """PDF の defaults に改名前の同梱 defaults の名前があればエラー文を返す（全 version）。

    ファイル名（basename）だけで判定する。data-dir などに同じ名前のファイルを置いていても
    エラーにする（旧名は使わない）。
    """
    key = pdf_defaults_key(version)
    val = pandoc_section.get(key)
    items = val if isinstance(val, list) else ([val] if val else [])
    errors = []
    for item in items:
        name = _basename(item)
        new = RENAMED_BUILTIN_DEFAULTS.get(name)
        if new:
            errors.append(
                f"pandoc.{key}: 同梱の {name} は {new} に改名しました（旧名は使えません）。"
                f"{item} を {new} に書き換えてください"
            )
    return errors


def pandoc_key_errors(pandoc_section: object, version: int | None) -> list[str]:
    """pandoc セクションのキーの誤り（エラー）を列挙する。"""
    if not isinstance(pandoc_section, dict):
        return []
    if uses_plain_keys(version):
        errors = [msg for key, msg in REMOVED_IN_V4.items() if key in pandoc_section]
        if errors:
            errors.append("version 3 以前のレシピからの書き換えは tools/convert_recipe_v4.py でできます")
        return errors + renamed_defaults_errors(pandoc_section, version) + renamed_cover_errors(pandoc_section, version)
    err = engine_error(pandoc_section)
    return (
        ([err] if err else [])
        + renamed_defaults_errors(pandoc_section, version)
        + renamed_cover_errors(pandoc_section, version)
    )


def removed_latex_keys(pandoc_section: dict) -> list[str]:
    """version 3 以前のレシピに書いてある LaTeX 専用キーを返す。

    ``defaults``（LaTeX 用）は typstdefaults があるときだけ含める（無いときは
    pandoc の「typstdefaults が無い」警告が案内する）。
    """
    keys = [k for k in REMOVED_LATEX_KEYS if pandoc_section.get(k)]
    if pandoc_section.get("typstdefaults") and pandoc_section.get("defaults"):
        keys.insert(0, "defaults")
    return keys


def deprecated_keys_warning(pandoc_section: object, version: int | None = None) -> str | None:
    """version 3 以前で、version 4 で廃止したキー（まだ使える）があれば警告文を返す。"""
    if uses_plain_keys(version) or not isinstance(pandoc_section, dict):
        return None
    keys = [k for k in DEPRECATED_BEFORE_V4 if pandoc_section.get(k)]
    if not keys:
        return None
    return (
        " / ".join(f"pandoc.{k}" for k in keys)
        + f" は非推奨です（version {PLAIN_KEYS_VERSION} で廃止）。中身は defaults ファイルの metadata: に移してください"
    )


def removed_latex_keys_warning(pandoc_section: dict, version: int | None = None) -> str | None:
    """version 3 以前で LaTeX 専用キーがあれば警告文を返す（version 4 はエラー側で扱う）。"""
    if uses_plain_keys(version):
        return None
    keys = removed_latex_keys(pandoc_section)
    if not keys:
        return None
    return (
        "LaTeX（lualatex）は撤去したので、LaTeX 用の "
        + " / ".join(f"pandoc.{k}" for k in keys)
        + f" は使いません。消してください（version: {PLAIN_KEYS_VERSION} への変換は tools/convert_recipe_v4.py）"
    )
