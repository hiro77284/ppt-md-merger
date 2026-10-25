import argparse
import json
import logging
import os
import sys
from pathlib import Path

from md_merge._fingerprint import load_check_map, verify_against_check
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, setup_logging
from md_merge.merge._recipe import (
    iter_insertmd_entries,
    load_recipe,
    load_yaml,
    resolve_input_dirs,
    resolve_input_path,
    resolve_out_file,
    resolve_workdir,
    setup_recipe_file_logging,
)


def run(args: argparse.Namespace) -> int:
    """Verify insertmd content against the check file without running the merge.

    Returns EXIT_OK when every stamped insertmd file is within tolerance, or
    EXIT_FAILURE when any significant drift (or missing file) is detected.
    """
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

    check_path = resolve_out_file(recipe, "checkfilename", yaml_path, workdir)
    if check_path is None:
        logging.error("output.checkfilename または output.targetbasefilename が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT
    if not check_path.exists():
        logging.error("チェックデータがありません。checkgen で生成してください: %s", check_path)
        return EXIT_NOT_FOUND

    in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    check_map = load_check_map(check_path)
    io_entries = iter_insertmd_entries(recipe, in_dirs, yaml_path)
    problems = verify_against_check(check_map, io_entries)

    unstamped = [fname for fname, _ in io_entries if fname not in check_map]

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok" if not problems else "drift",
            "command": "checkverify",
            "checked": len(io_entries),
            "unstamped": unstamped,
            "problems": [{"mdfilename": f, "reasons": r} for f, r in problems],
        }, ensure_ascii=False))
    else:
        for fname, reasons in problems:
            logging.warning("insertmd 整合性チェック: %s: %s", fname, "; ".join(reasons))
        if unstamped:
            logging.info(
                "チェックデータ未登録（checkgen 以降に追加）: %d 件 — %s",
                len(unstamped), ", ".join(unstamped),
            )
        if problems:
            logging.error("insertmd 整合性チェック: %d 件で差異を検出しました", len(problems))
        else:
            logging.info("insertmd 整合性チェック: 差異なし (%d 件)", len(io_entries))

    return EXIT_OK if not problems else EXIT_FAILURE


def gate(args: argparse.Namespace) -> int:
    """Pre-merge insertmd drift gate for pipelines.

    Verifies insertmd content against the check file and prompts for confirmation
    when significant drift **or** an unstamped insertmd (one absent from the check
    data) is found. Returns EXIT_OK to proceed (no check file, nothing flagged, or
    user confirmed) or EXIT_FAILURE to abort (declined, or non-interactive while
    something is flagged). Intended to run immediately before the merge step; the
    merge step itself should run with the check disabled.
    """
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return EXIT_OK

    recipe = load_recipe(yaml_path, args)  # 直後に merge する項目だけを検査する
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)

    check_path = resolve_out_file(recipe, "checkfilename", yaml_path, workdir)
    if check_path is None or not check_path.exists():
        logging.debug("insertmd ドリフトゲート: チェックデータなし — スキップ")
        return EXIT_OK

    in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    check_map = load_check_map(check_path)
    io_entries = iter_insertmd_entries(recipe, in_dirs, yaml_path)
    problems = verify_against_check(check_map, io_entries)
    unstamped = [fname for fname, _ in io_entries if fname not in check_map]

    if not problems and not unstamped:
        logging.info("insertmd 整合性チェック: 差異なし (%d 件)", len(io_entries))
        return EXIT_OK

    for fname, reasons in problems:
        logging.warning("insertmd 整合性チェック: %s: %s", fname, "; ".join(reasons))
    if unstamped:
        logging.warning(
            "insertmd 整合性チェック: チェックデータ未登録（checkgen 以降に追加）: %s",
            ", ".join(unstamped),
        )

    return EXIT_OK if _prompt_continue(args, len(problems) + len(unstamped)) else EXIT_FAILURE


def _prompt_continue(args: argparse.Namespace, n: int) -> bool:
    """Ask the user whether to continue after drift. False in non-interactive contexts.

    On POSIX a non-TTY stdin is treated as non-interactive (avoids hangs in CI).
    On Windows, isatty() is unreliable under Git Bash/mintty (reports False even on
    an interactive terminal), so the prompt is attempted regardless and a closed
    stdin surfaces as EOFError -> abort.
    """
    interactive = sys.stdin is not None and (os.name == "nt" or sys.stdin.isatty())
    if getattr(args, "json", False) or not interactive:
        logging.error(
            "insertmd の変化・未登録を %d 件検出しましたが対話できません。確認のうえ checkgen で"
            "チェックデータを更新するか、--no-check でスキップしてください",
            n,
        )
        return False
    try:
        print(
            f"insertmd の変化・未登録を {n} 件検出しました。処理を続行しますか? [y/N]: ",
            end="", flush=True,
        )
        answer = input().strip().lower()
    except EOFError:
        logging.error("入力が読み取れませんでした（EOF）。--no-check でスキップできます")
        return False
    return answer in ("y", "yes")
