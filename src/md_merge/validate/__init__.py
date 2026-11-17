from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from md_merge._conditions import WHEN_KEY, check_when, check_when_errors
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, setup_logging
from md_merge._procedure import (
    DEFAULT_OP_V1,
    GROUP_KEY,
    INHERITED_WHEN_KEY,
    LATEST_VERSION,
    PROCEDURE_ITEM_KEYS,
    PROCEDURE_OPS,
    ProcedureNotationError,
    check_procedure_notation,
    normalize_recipe,
    recipe_version,
)
from md_merge._condblock import is_truthy
from md_merge._pandoc_keys import deprecated_keys_warning, pandoc_key_errors, removed_latex_keys_warning
from md_merge._typst_cover import select_typst_cover
from md_merge._params import PARAMS_KEY, check_params_errors, param_domain
from md_merge.merge._copy_keys import copy_key_errors
from md_merge.merge._recipe import _expand_mdfilename, cli_vars, load_yaml, resolve_input_path
from md_merge.validate._lint import lint


# ── known key schemas ────────────────────────────────────────────────────────

_TOP_LEVEL_KEYS = frozenset({
    "version",
    "workdir", "input", "output", "procedure",
    "merge", "pandoc", "puremd", "indexer", "vars", "params", "log",
    "pptmerge", "pptmdexport", "separator", "transfer", "notecomexport",
})

_INPUT_KEYS = frozenset({
    "dirs",       # merge / pptmerge (統合ファイル探索パス)
    "mddir",      # merge (非推奨。input.dirs を推奨)
    "imagesdir",  # crop
    "cropsrc",    # pptimgexport / pptmdexport / pptpdfexport
    "pptxdir",    # pptmerge (非推奨。input.dirs を推奨)
})

_OUTPUT_KEYS = frozenset({
    "outputdir", "force",
    "targetbasefilename",
    "mdfilename", "idcollectfilename", "idresolvedfilename",
    "renderedfilename", "pdffilename", "htmlfilename",
    "revealfilename", "puremdfilename", "notecomyamlfilename", "pptxfilename",
    "checkfilename", "insertsamplefilename",
})

_MERGE_KEYS = frozenset({
    "strict", "copy-images", "no-copy-images", "image-dir", "flatten-images",
    "image-naming", "image-collision", "clear-dir-before-merge",
    "overwrite-images",   # 非推奨: image-collision: overwrite のエイリアス
    "copy-yamls", "no-copy-yamls", "yaml-dir", "flatten-yamls", "overwrite-yamls",
})

_PANDOC_KEYS = frozenset({
    "format", "defaults", "htmldefaults", "revealdefaults",
    "filters", "metadata-file", "template", "include-in-header",
    "data-dir", "syntax-highlighting", "include-before-body",
    "resource-path", "conditional-process-input", "conditional-process-output",
    "htmlcover", "cover-md",
    "engine", "typstdefaults", "typst-root", "typst-cover-md",
})

_PUREMD_KEYS = frozenset({
    "strip_config",
    "fenced_div",
})

_INDEXER_KEYS = frozenset({
    "delimiter", "separator", "pptxnumbering", "deletecsl", "deletecsp",
    "chapter_marker", "section_marker", "subsection_marker", "stay_marker",
})

_LOG_KEYS = frozenset({
    "duplicate", "filename", "dir", "level",
})

_PPTMERGE_KEYS = frozenset({
    "stylebase",
})

_PPTMDEXPORT_KEYS = frozenset({
    "latex_check",
})

_SEPARATOR_KEYS = frozenset({
    "enabled",
})

_TRANSFER_KEYS = frozenset({
    "inputmd", "outputmd", "dataentry_input", "slug", "image_naming",
    "image_collision",
})

_NOTECOMEXPORT_KEYS = frozenset({
    "inputmd", "hashtags", "cover", "inline", "quote_labels", "link_base",
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
    "pptmdexport": _PPTMDEXPORT_KEYS,
    "separator": _SEPARATOR_KEYS,
    "transfer": _TRANSFER_KEYS,
    "notecomexport": _NOTECOMEXPORT_KEYS,
}

# procedure.operation の有効値と、各 operation で使えるキー（内部表現）
_PROCEDURE_OPS = PROCEDURE_OPS
_PROCEDURE_ITEM_KEYS = PROCEDURE_ITEM_KEYS

# operation キーがない場合の既定値 (version 1 の pptmerge レシピの慣習)
_DEFAULT_OP = DEFAULT_OP_V1


# ── validation logic ─────────────────────────────────────────────────────────

_COMMON_KEYS = frozenset({"description"})  # any level: human memo, not processed

# vars 値に含まれてはいけない生 LaTeX の検出（制御綴り \cmd / {=fmt} raw attribute）。
# {{v:}} は実データ置換専用で、生 latex はセマンティックマーカー（{{vspace}} 等）へ
# 移行する方針。値がこれにマッチしたら警告する。
_RAW_LATEX_IN_VALUE_RE = re.compile(r"\\[a-zA-Z]|\{=[a-zA-Z]")


def _unknown(actual: set[str], known: frozenset[str]) -> list[str]:
    return sorted(actual - known - _COMMON_KEYS)


def validate_recipe(recipe: dict) -> list[str]:
    """レシピ dict を検査し、未知のキーに関する警告メッセージのリストを返す。"""
    warnings: list[str] = []

    # version チェック
    # （未対応の値は check_procedure_notation がエラーにする）
    version = recipe.get("version")
    if version is None:
        warnings.append(f"version が指定されていません (1 とみなします。推奨値: {LATEST_VERSION})")
    elif version == 1:
        warnings.append(
            f"version 1 の operation 記法は非推奨です (推奨値: {LATEST_VERSION}。"
            "例: - insertpptx: a.pptx)"
        )

    # PDF（typst）の表紙（version 2 以前の暗黙の標準表紙 / version 3 で使われない LaTeX 表紙）
    pandoc_section = recipe.get("pandoc")
    if isinstance(pandoc_section, dict):
        try:
            _ver = recipe_version(recipe)
        except ProcedureNotationError:
            _ver = None
        if _ver is not None:
            _cover_warn = select_typst_cover(pandoc_section, _ver)[2]
            if _cover_warn:
                warnings.append(_cover_warn)
    if isinstance(pandoc_section, dict):
        try:
            _ver = recipe_version(recipe)
        except ProcedureNotationError:
            _ver = None
        _latex_warn = removed_latex_keys_warning(pandoc_section, _ver)
        if _latex_warn:
            warnings.append(_latex_warn)
        _deprecated = deprecated_keys_warning(pandoc_section, _ver)
        if _deprecated:
            warnings.append(_deprecated)

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
            known_keys = _PROCEDURE_ITEM_KEYS.get(op, frozenset()) | {WHEN_KEY, INHERITED_WHEN_KEY}
            for k in _unknown(set(item.keys()), known_keys):
                warnings.append(f"未知のキー: procedure[{i}]({op}).{k!r}")
            if WHEN_KEY in item:
                for msg in check_when(item[WHEN_KEY]):
                    warnings.append(f"procedure[{i}]({op}): {msg}")

    # vars: 値に生 LaTeX（\cmd や {=fmt}）が無いか。{{v:}} は実データ置換専用。
    vars_section = recipe.get("vars")
    if isinstance(vars_section, dict):
        for name, value in vars_section.items():
            if isinstance(value, str) and _RAW_LATEX_IN_VALUE_RE.search(value):
                warnings.append(
                    f"vars.{name}: 値に生 LaTeX が含まれています（{{{{v:}}}} は実データ置換専用。"
                    f"生 latex はセマンティックマーカー等へ移行してください）: {value!r}"
                )

    return warnings


def check_group_when(procedure: object, prefix: str = "procedure") -> list[str]:
    """未展開の procedure にある ``- group:`` の ``when:`` を検査し、警告一覧を返す。

    group は正規化で展開されて validate_recipe からは見えないため、展開前に検査する。
    """
    warnings: list[str] = []
    if not isinstance(procedure, list):
        return warnings
    for i, item in enumerate(procedure):
        if not isinstance(item, dict) or GROUP_KEY not in item:
            continue
        label = f"{prefix}[{i}]"
        if WHEN_KEY in item:
            warnings.extend(f"{label}(group): {msg}" for msg in check_when(item[WHEN_KEY]))
        warnings.extend(check_group_when(item[GROUP_KEY], f"{label}.{GROUP_KEY}"))
    return warnings


# ── cropsrc 未使用 / cropsrc 未登録チェック ───────────────────────────────────

# MD 命名規則 <BASEFILENAME>_slide<SLIDENUM>_md.md（前方の stem を捕捉）
_SLIDE_MD_RE = re.compile(r"^(.+)_slide\d+_md\.md$")


def _cropsrc_stems(recipe: dict) -> list[str]:
    """input.cropsrc[].pptx の stem を登場順（重複除去）で返す。"""
    cropsrc = (recipe.get("input") or {}).get("cropsrc") or {}
    entries = cropsrc if isinstance(cropsrc, list) else [cropsrc]
    stems: list[str] = []
    seen: set[str] = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        v = e.get("pptx")
        if not v:
            continue
        stem = Path(str(v)).stem
        if stem not in seen:
            seen.add(stem)
            stems.append(stem)
    return stems


def _procedure_refs(recipe: dict) -> tuple[list[str], list[str]]:
    """procedure から (insertpptx の stem 一覧, insertmd の basename 一覧) を返す。

    insertmd の `[from-to]` レンジは展開する。パス解決はしない（名前のみ）。
    """
    pptx_stems: list[str] = []
    md_names: list[str] = []
    for item in recipe.get("procedure", []) or []:
        if not isinstance(item, dict):
            continue
        op = item.get("operation", _DEFAULT_OP)
        if op == "insertpptx":
            v = item.get("pptxfilename")
            if v:
                pptx_stems.append(Path(str(v)).stem)
        elif op == "insertmd":
            v = item.get("mdfilename")
            if not v:
                continue
            try:
                names = _expand_mdfilename(str(v))
            except ValueError:
                names = [str(v)]
            md_names.extend(Path(n).name for n in names)
    return pptx_stems, md_names


def check_cropsrc_usage(recipe: dict) -> list[str]:
    """cropsrc と procedure の対応を検査し、info メッセージ一覧を返す（破壊なし・助言のみ）。

    - 未使用の可能性: cropsrc の pptx が procedure で参照されていない
      （insertpptx は stem 完全一致、insertmd は `^<stem>_slide\\d+_md\\.md$` 一致）。
    - cropsrc 未登録: procedure が参照する pptx（insertpptx / スライド命名規則の insertmd）が
      cropsrc に無い。
    """
    source_stems = _cropsrc_stems(recipe)
    if not source_stems:
        return []
    source_set = set(source_stems)

    insertpptx_stems, insertmd_names = _procedure_refs(recipe)
    pptx_stem_set = set(insertpptx_stems)

    messages: list[str] = []

    # 順方向: 未使用の可能性
    for stem in source_stems:
        if stem in pptx_stem_set:
            continue
        md_re = re.compile(r"^" + re.escape(stem) + r"_slide\d+_md\.md$")
        if any(md_re.match(name) for name in insertmd_names):
            continue
        messages.append(
            f"未使用の可能性: cropsrc の {stem}.pptx は procedure（insertpptx/insertmd）で参照されていません"
        )

    # 逆方向: cropsrc 未登録
    for stem in dict.fromkeys(insertpptx_stems):
        if stem not in source_set:
            messages.append(
                f"cropsrc 未登録: insertpptx で {stem}.pptx を参照していますが cropsrc にありません"
            )
    reverse_seen: set[str] = set()
    for name in insertmd_names:
        m = _SLIDE_MD_RE.match(name)
        if not m:
            continue  # 規則外の名前（手書き MD 等）は対象外
        stem = m.group(1)
        if stem in source_set or stem in reverse_seen:
            continue
        reverse_seen.add(stem)
        messages.append(
            f"cropsrc 未登録: insertmd ({name}) は {stem}.pptx 由来のようですが cropsrc にありません"
        )

    return messages


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
        recipe = load_yaml(yaml_path, normalize=False, apply_vars=False)
    except Exception as exc:
        logging.error("YAML 読み込みエラー: %s", exc)
        return EXIT_FAILURE

    if not isinstance(recipe, dict):
        logging.error("レシピのトップレベルは辞書である必要があります: %s", yaml_path)
        return EXIT_FAILURE

    json_mode = getattr(args, "json", False)

    if getattr(args, "list_params", False):
        return _print_params(recipe, json_mode)

    # version と procedure 記法の不整合・params: の誤りはエラー（他のサブコマンドは読み込み時に停止する）
    notation_errors = (
        check_procedure_notation(recipe) + check_when_errors(recipe)
        + check_params_errors(recipe, cli_vars()) + _pandoc_errors(recipe)
        + copy_key_errors(recipe.get("merge"))
    )
    if notation_errors:
        return _report_errors(yaml_path, notation_errors, [], json_mode)
    group_warnings = check_group_when(recipe.get("procedure"))
    normalized = normalize_recipe(dict(recipe), warn_deprecated=False)  # 非推奨は validate_recipe が警告

    workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    lint_result = lint(recipe, normalized, yaml_path, workdir)

    warnings = validate_recipe(normalized) + group_warnings + lint_result.warnings
    cropsrc_usage = check_cropsrc_usage(normalized)
    suggestions = lint_result.info

    if lint_result.errors:
        return _report_errors(yaml_path, lint_result.errors, warnings, json_mode)

    if json_mode:
        print(json.dumps({
            "status": "ok" if not warnings else "warn",
            "command": "validate",
            "input": str(yaml_path),
            "warnings": warnings,
            "cropsrc_usage": cropsrc_usage,
            "suggestions": suggestions,
        }, ensure_ascii=False))
        return EXIT_OK if not warnings else (EXIT_FAILURE if getattr(args, "strict", False) else EXIT_OK)

    # cropsrc 使用状況・提案は info（終了コードには影響しない）
    for msg in cropsrc_usage + suggestions:
        logging.info("%s", msg)

    if not warnings:
        print(f"OK: {yaml_path} -- 警告はありません")
        return EXIT_OK

    for w in warnings:
        logging.warning("%s", w)

    print(f"\n{len(warnings)} 件の警告があります: {yaml_path}")

    if getattr(args, "strict", False):
        return EXIT_FAILURE
    return EXIT_OK


def _pandoc_errors(recipe: dict) -> list[str]:
    """pandoc セクションの廃止キー（version 4）・engine の誤り。"""
    try:
        version = recipe_version(recipe)
    except ProcedureNotationError:
        return []  # version の誤りは check_procedure_notation が報告する
    return pandoc_key_errors(recipe.get("pandoc"), version)


def _report_errors(yaml_path: Path, errors: list[str], warnings: list[str], json_mode: bool) -> int:
    if json_mode:
        print(json.dumps({
            "status": "error",
            "command": "validate",
            "input": str(yaml_path),
            "errors": errors,
            "warnings": warnings,
        }, ensure_ascii=False))
        return EXIT_FAILURE
    for w in warnings:
        logging.warning("%s", w)
    for e in errors:
        logging.error("%s", e)
    print(f"\n{len(errors)} 件のエラーがあります: {yaml_path}")
    return EXIT_FAILURE


def _print_params(recipe: dict, json_mode: bool) -> int:
    """``--list-params``: このレシピの切り替え（params:）の一覧を表示する。"""
    params = recipe.get(PARAMS_KEY)
    rows = []
    if isinstance(params, dict):
        for name, spec in params.items():
            spec = spec if isinstance(spec, dict) else {}
            domain = param_domain(spec)
            default = spec.get("default")
            if spec.get("type") == "bool" and default is not None:
                default = "true" if is_truthy(default) else "false"
            rows.append({
                "name": str(name),
                "values": list(domain) if domain is not None else None,
                "default": default,
                "description": spec.get("description", ""),
            })
    if json_mode:
        print(json.dumps({"status": "ok", "command": "validate", "params": rows}, ensure_ascii=False))
        return EXIT_OK
    if not rows:
        print("params: がありません（--var で切り替える変数は params: で宣言できます）")
        return EXIT_OK
    for r in rows:
        values = " / ".join(r["values"]) if r["values"] is not None else "任意の文字列"
        default = "（なし＝未定義）" if r["default"] is None else r["default"]
        print(f"--var {r['name']}=…  値: {values}  既定: {default}")
        if r["description"]:
            print(f"    {r['description']}")
    return EXIT_OK
