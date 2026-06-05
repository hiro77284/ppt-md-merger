from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, setup_logging
from md_merge.merge._recipe import load_yaml, resolve_input_path


# ── known key schemas ────────────────────────────────────────────────────────

_TOP_LEVEL_KEYS = frozenset({
    "version",
    "workdir", "input", "output", "procedure",
    "merge", "pandoc", "puremd", "indexer", "vars", "log",
    "pptmerge", "separator",
})

_INPUT_KEYS = frozenset({
    "mddir",      # merge
    "imagesdir",  # crop
    "cropsrc",    # pptimgexport / pptmdexport / pptpdfexport
    "pptxdir",    # pptmerge
})

_OUTPUT_KEYS = frozenset({
    "outputdir", "force",
    "targetbasefilename",
    "mdfilename", "idcollectfilename", "idresolvedfilename",
    "renderedfilename", "pdffilename", "texfilename", "htmlfilename",
    "revealfilename", "puremdfilename", "pptxfilename",
    "resourcepathfilename",
})

_MERGE_KEYS = frozenset({
    "strict", "no-copy-images", "image-dir", "flatten-images",
})

_PANDOC_KEYS = frozenset({
    "format", "defaults", "htmldefaults", "revealdefaults",
    "filters", "metadata-file", "template", "include-in-header",
    "data-dir", "syntax-highlighting", "include-before-body",
    "resource-path", "conditional-process-input", "conditional-process-output",
})

_PUREMD_KEYS = frozenset({
    "strip_config",
})

_INDEXER_KEYS = frozenset({
    "delimiter", "separator", "pptxnumbering", "deletecsl", "deletecsp",
})

_LOG_KEYS = frozenset({
    "duplicate", "filename", "dir", "level",
})

_PPTMERGE_KEYS = frozenset({
    "stylebase",
})

_SEPARATOR_KEYS = frozenset({
    "enabled",
})

_SECTION_SCHEMAS: dict[str, frozenset] = {
    "input": _INPUT_KEYS,
    "output": _OUTPUT_KEYS,
    "merge": _MERGE_KEYS,
    "pandoc": _PANDOC_KEYS,
    "puremd": _PUREMD_KEYS,
    "indexer": _INDEXER_KEYS,
    "log": _LOG_KEYS,
    "pptmerge": _PPTMERGE_KEYS,
    "separator": _SEPARATOR_KEYS,
}

# procedure.operation の有効値と、各 operation で使えるキー
_PROCEDURE_OPS = frozenset({
    "insertmd", "insertpptx",
    "chapter", "section", "subsection",
    "beginstay", "endstay",
})

_PROCEDURE_ITEM_KEYS: dict[str, frozenset] = {
    "insertmd":    frozenset({"operation", "mdfilename"}),
    "insertpptx":  frozenset({"operation", "pptxfilename", "slides", "separator_before", "vars"}),
    "chapter":     frozenset({"operation", "chapter", "section", "title", "note"}),
    "section":     frozenset({"operation", "section", "chapter", "title", "note"}),
    "subsection":  frozenset({"operation", "subsection", "title"}),
    "beginstay":   frozenset({"operation"}),
    "endstay":     frozenset({"operation"}),
}

# operation キーがない場合の既定値 (pptmerge レシピの慣習)
_DEFAULT_OP = "insertpptx"


# ── validation logic ─────────────────────────────────────────────────────────

_COMMON_KEYS = frozenset({"description"})  # any level: human memo, not processed


def _unknown(actual: set[str], known: frozenset[str]) -> list[str]:
    return sorted(actual - known - _COMMON_KEYS)


def validate_recipe(recipe: dict) -> list[str]:
    """レシピ dict を検査し、未知のキーに関する警告メッセージのリストを返す。"""
    warnings: list[str] = []

    # version チェック
    version = recipe.get("version")
    if version is None:
        warnings.append("version が指定されていません (推奨値: 1)")
    elif version != 1:
        warnings.append(f"version が 1 ではありません: {version!r} (期待値: 1)")

    # トップレベル
    for k in _unknown(set(recipe.keys()), _TOP_LEVEL_KEYS):
        warnings.append(f"未知のトップレベルキー: {k!r}")

    # 各セクション
    for section, schema in _SECTION_SCHEMAS.items():
        val = recipe.get(section)
        if not isinstance(val, dict):
            continue
        for k in _unknown(set(val.keys()), schema):
            warnings.append(f"未知のキー: {section}.{k!r}")

    # procedure アイテム
    procedure = recipe.get("procedure")
    if isinstance(procedure, list):
        for i, item in enumerate(procedure):
            if not isinstance(item, dict):
                warnings.append(f"procedure[{i}] が辞書ではありません")
                continue
            op = item.get("operation", _DEFAULT_OP)
            if op not in _PROCEDURE_OPS:
                warnings.append(
                    f"procedure[{i}].operation が未知の値です: {op!r}"
                    f"  (有効値: {', '.join(sorted(_PROCEDURE_OPS))})"
                )
                continue
            known_keys = _PROCEDURE_ITEM_KEYS.get(op, frozenset())
            for k in _unknown(set(item.keys()), known_keys):
                warnings.append(f"未知のキー: procedure[{i}]({op}).{k!r}")

    return warnings


# ── subcommand entry point ───────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)

    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("入力ファイルが指定されていません")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("入力ファイルが見つかりません: %s", yaml_path)
        return EXIT_NOT_FOUND

    try:
        recipe = load_yaml(yaml_path)
    except Exception as exc:
        logging.error("YAML 読み込みエラー: %s", exc)
        return EXIT_FAILURE

    if not isinstance(recipe, dict):
        logging.error("レシピのトップレベルは辞書である必要があります: %s", yaml_path)
        return EXIT_FAILURE

    warnings = validate_recipe(recipe)

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok" if not warnings else "warn",
            "command": "validate",
            "input": str(yaml_path),
            "warnings": warnings,
        }, ensure_ascii=False))
        return EXIT_OK if not warnings else (EXIT_FAILURE if getattr(args, "strict", False) else EXIT_OK)

    if not warnings:
        print(f"OK: {yaml_path} -- 未知のキーはありません")
        return EXIT_OK

    for w in warnings:
        logging.warning("%s", w)

    print(f"\n{len(warnings)} 件の未知のキーが見つかりました: {yaml_path}")

    if getattr(args, "strict", False):
        return EXIT_FAILURE
    return EXIT_OK
