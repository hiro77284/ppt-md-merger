from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from md_merge._filters import escape_backslash_smart
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_condblock_output, resolve_input_path, resolve_workdir, setup_recipe_file_logging

_RE_VAR = re.compile(r'\{\{v:([A-Za-z0-9_]+)\}\}')
_RE_IF = re.compile(r'^\s*\{\{#if:([A-Za-z0-9_]+)\}\}\s*$')
_RE_ENDIF = re.compile(r'^\s*\{\{#endif:([A-Za-z0-9_]+)\}\}\s*$')
_RE_ANY_VAR_REF = re.compile(r'\{\{v:[^}]*\}\}')


def _is_truthy(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return val != ""
    return True


def _process_conditionals(lines: list[str], vars: dict) -> list[str]:
    output: list[str] = []
    in_block: str | None = None
    block_active = False

    for lineno, line in enumerate(lines, start=1):
        stripped = line.rstrip("\r\n")

        m_if = _RE_IF.match(stripped)
        if m_if:
            var = m_if.group(1)
            if in_block is not None:
                raise ValueError(
                    f"line {lineno}: ネストされた条件ブロックは非対応です "
                    f"({{{{#if:{var}}}}} が {{{{#if:{in_block}}}}} の内側にあります)"
                )
            in_block = var
            block_active = _is_truthy(vars.get(var))
            continue

        m_end = _RE_ENDIF.match(stripped)
        if m_end:
            var = m_end.group(1)
            if in_block is None:
                raise ValueError(
                    f"line {lineno}: 対応する開始タグのない終了タグです: {{{{#endif:{var}}}}}"
                )
            if in_block != var:
                raise ValueError(
                    f"line {lineno}: 終了タグの変数名 '{var}' が開始タグの '{in_block}' と一致しません"
                )
            in_block = None
            block_active = False
            continue

        if in_block is None or block_active:
            output.append(line)

    if in_block is not None:
        raise ValueError(
            f"{{{{#if:{in_block}}}}} に対応する {{{{#endif:{in_block}}}}} がありません"
        )

    return output


def _replace_vars(content: str, vars: dict) -> str:
    undefined: list[str] = []

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        if key not in vars:
            undefined.append(key)
            return m.group(0)
        return escape_backslash_smart(str(vars[key]))

    result = _RE_VAR.sub(replacer, content)

    if undefined:
        raise ValueError(f"未定義の変数参照: {', '.join(undefined)}")

    malformed = _RE_ANY_VAR_REF.findall(result)
    if malformed:
        raise ValueError(
            f"変数名に使用不可能な文字が含まれます: {', '.join(malformed)}"
        )

    return result


def _resolve_path(val: str | None, yaml_path: Path, workdir: Path | None) -> Path | None:
    if not val:
        return None
    p = Path(val)
    if p.is_absolute():
        return p
    base = workdir if workdir else yaml_path.parent
    return (base / p).resolve()


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)

    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("No input file specified")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("Input file not found: %s", yaml_path)
        return EXIT_NOT_FOUND

    recipe = load_yaml(yaml_path)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    apply_recipe_force(args, recipe)

    pandoc_section = recipe.get("pandoc") or {}
    vars_section = recipe.get("vars") or {}

    input_val = pandoc_section.get("conditional-process-input")
    if not input_val:
        logging.error("pandoc.conditional-process-input が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    # Resolve conditional-process-input preferring pandoc.data-dir
    _in_p = Path(str(input_val))
    if _in_p.is_absolute():
        in_path = _in_p.resolve()
    else:
        _data_dir_val = pandoc_section.get("data-dir")
        _base = workdir if workdir else yaml_path.parent
        if _data_dir_val:
            _dd = Path(str(_data_dir_val))
            _data_dir = _dd.resolve() if _dd.is_absolute() else (_base / _dd).resolve()
            _candidate = (_data_dir / _in_p).resolve()
            in_path = _candidate if _candidate.exists() else (_base / _in_p).resolve()
        else:
            in_path = (_base / _in_p).resolve()
    out_path = resolve_condblock_output(pandoc_section, recipe, yaml_path, workdir)
    if not pandoc_section.get("conditional-process-output"):
        logging.debug("conditional-process-output: 自動生成 %s", out_path)

    logging.debug("input  : %s", in_path)
    logging.debug("output : %s", out_path)
    logging.debug("vars   : %s", vars_section)

    if args.dry_run:
        emit(args, "ok", "condblockprocess", in_path, out_path, dry_run=True)
        return EXIT_OK

    if not in_path.exists():
        logging.error("入力ファイルが見つかりません: %s", in_path)
        return EXIT_NOT_FOUND

    force = getattr(args, "force", False)
    if out_path.exists() and not force:
        logging.error("出力ファイルが既に存在します (--force で上書き): %s", out_path)
        return EXIT_FAILURE

    content = in_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    try:
        lines = _process_conditionals(lines, vars_section)
        content = "".join(lines)
        content = _replace_vars(content, vars_section)
    except ValueError as exc:
        logging.error("condblockprocess: %s", exc)
        return EXIT_FAILURE

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logging.error("書き込み失敗: %s: %s", out_path, exc)
        return EXIT_FAILURE

    emit(args, "ok", "condblockprocess", in_path, out_path)
    return EXIT_OK
