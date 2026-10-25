import argparse
import logging
from datetime import datetime
from pathlib import Path

import yaml

from md_merge._fingerprint import fingerprint, pptx_fingerprint, read_slide_titles
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import (
    iter_insertmd_entries,
    iter_insertpptx_entries,
    load_yaml,
    resolve_input_dirs,
    resolve_input_path,
    resolve_out_file,
    resolve_workdir,
    setup_recipe_file_logging,
)


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

    check_path = resolve_out_file(recipe, "checkfilename", yaml_path, workdir)
    if check_path is None:
        logging.error("output.checkfilename または output.targetbasefilename が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    io_entries = iter_insertmd_entries(recipe, in_dirs, yaml_path)
    pptx_io_entries = iter_insertpptx_entries(recipe, in_dirs)

    logging.debug("yaml  : %s", yaml_path)
    logging.debug("check : %s", check_path)
    logging.debug("insertmd entries: %d / insertpptx entries: %d", len(io_entries), len(pptx_io_entries))

    if not io_entries and not pptx_io_entries:
        logging.warning("procedure に insertmd / insertpptx エントリがありません")

    if args.dry_run:
        emit(args, "ok", "checkgen", yaml_path, check_path, dry_run=True)
        return EXIT_OK

    if check_path.exists() and not getattr(args, "force", False):
        logging.error("チェックデータが既に存在します (--force で上書き): %s", check_path)
        return EXIT_FAILURE

    entries: list[dict] = []
    for fname, path in io_entries:
        if not path.exists():
            logging.warning("md ファイルが見つかりません — スキップ: %s", path)
            continue
        text = path.read_text(encoding="utf-8-sig")
        entries.append({"mdfilename": fname, **fingerprint(text)})

    pptx_entries: list[dict] = []
    for fname, path in pptx_io_entries:
        if not path.exists():
            logging.warning("pptx ファイルが見つかりません — スキップ: %s", path)
            continue
        try:
            titles = read_slide_titles(path)
        except Exception as e:  # noqa: BLE001
            logging.warning("pptx を読めません — スキップ: %s: %s", path, e)
            continue
        pptx_entries.append({"pptxfilename": fname, **pptx_fingerprint(titles)})

    try:
        config_yaml_display = yaml_path.relative_to(yaml_path.parent).as_posix()
    except ValueError:
        config_yaml_display = yaml_path.as_posix()

    data = {
        "schema_version": 1,
        "kind": "insert_check",
        "generated": {
            "by": "md-merge",
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "source": {"config_yaml": config_yaml_display},
        "entries": entries,
        "pptx_entries": pptx_entries,
    }

    check_path.parent.mkdir(parents=True, exist_ok=True)
    with check_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logging.info(
        "checkgen: insertmd %d 件 / insertpptx %d 件のフィンガープリントを書き出しました",
        len(entries), len(pptx_entries),
    )
    emit(args, "ok", "checkgen", yaml_path, check_path)
    return EXIT_OK
