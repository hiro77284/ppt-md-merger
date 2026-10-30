import argparse
import logging
import shutil
import sys
from pathlib import Path

from md_merge._fingerprint import load_check_map, verify_against_check
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._imagerefs import COLLISION_MODES, NAMING_MODES
from md_merge.merge._images import DEFAULT_IMAGE_DIR, ImageSourceCollector, make_image_copier
from md_merge.merge._recipe import (
    CircularIncludeError,
    IncludeNotFoundError,
    apply_recipe_force,
    collect_procedure_items,
    expand_md,
    iter_insertmd_entries,
    load_recipe,
    load_yaml,
    resolve_input_dirs,
    resolve_input_path,
    resolve_out_file,
    resolve_output_path,
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

    recipe = load_recipe(yaml_path, args)
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    setup_recipe_file_logging(recipe, yaml_path, workdir)

    apply_recipe_force(args, recipe)
    _apply_recipe_merge_opts(args, recipe.get("merge", {}))
    if args.image_naming not in NAMING_MODES:
        logging.error("merge.image-naming は %s のいずれかです: %s",
                      " / ".join(NAMING_MODES), args.image_naming)
        return EXIT_BAD_INPUT
    if args.image_collision not in COLLISION_MODES:
        logging.error("merge.image-collision は %s のいずれかです: %s",
                      " / ".join(COLLISION_MODES), args.image_collision)
        return EXIT_BAD_INPUT

    in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
    procedure_items = collect_procedure_items(recipe, in_dirs, yaml_path)

    if not any(isinstance(i, Path) for i in procedure_items):
        logging.warning("No insertmd entries found in procedure")

    check_problems = _verify_insertmd_check(args, recipe, in_dirs, yaml_path, workdir)
    if check_problems and getattr(args, "strict", False):
        logging.error("insertmd 整合性チェックで差異が検出されました（--strict）")
        return EXIT_FAILURE

    out_path = resolve_output_path(recipe, yaml_path, workdir)

    logging.debug("yaml    : %s", yaml_path)
    logging.debug("in_dirs : %s", [str(d) for d in in_dirs])
    logging.debug("files   : %s", [str(i) for i in procedure_items if isinstance(i, Path)])
    logging.debug("output  : %s", out_path)

    if args.dry_run:
        emit(args, "ok", "merge", yaml_path, out_path, dry_run=True)
        return EXIT_OK

    if out_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", out_path)
        return EXIT_FAILURE

    strict = getattr(args, "strict", False)

    # clear-dir-before-merge: wipe the image directory before merging when enabled
    # and an image-dir name is set. 削除前にフルパスを提示して確認する（中止なら merge 全体を止める）。
    image_dir_name = getattr(args, "image_dir", None)
    if getattr(args, "clear_dir_before_merge", False) and image_dir_name:
        sources = _collect_image_sources(procedure_items, yaml_path.parent)
        if not _clear_image_dir(out_path.parent, image_dir_name, args, sources=sources):
            logging.error("clear-dir-before-merge: 確認が得られなかったため merge を中止しました。")
            return EXIT_FAILURE

    image_copier = make_image_copier(args, out_path, in_dirs[0] if in_dirs else None)

    parts: list[str] = []
    for item in procedure_items:
        if isinstance(item, str):
            parts.append(item)
            continue
        p = item
        if not p.exists():
            if strict:
                logging.error("MD file not found: %s", p)
                return EXIT_NOT_FOUND
            logging.warning("MD file not found: %s — skipping", p)
            continue
        try:
            parts.append(expand_md(
                p, strict=strict, yaml_dir=yaml_path.parent,
                image_copier=image_copier,
            ))
        except CircularIncludeError as e:
            logging.error("Circular include detected: %s", e.path)
            return EXIT_FAILURE
        except IncludeNotFoundError as e:
            logging.error("Include target not found: %s", e.path)
            return EXIT_NOT_FOUND

    merged = "\n\n".join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(merged, encoding="utf-8")

    emit(args, "ok", "merge", yaml_path, out_path)
    return EXIT_OK


# ── helpers ────────────────────────────────────────────────────────────────


def _confirm_clear(target: Path, count: int, args: argparse.Namespace, *, ignore_force: bool = False) -> bool:
    """image-dir の全削除を確認する。True=削除実行 / False=中止。

    削除対象のフルパスと項目数を提示する。``--force`` 指定時は確認を省いて実行
    （ただし ``ignore_force=True`` の場合は ``--force`` があっても必ず確認する。
    パイプライン先頭の事前確認で使用）。
    非対話環境（stdin が TTY でない）では確認できないため中止する。
    """
    if getattr(args, "clear_dir_confirmed", False):
        return True  # パイプライン先頭で事前確認済み（再確認しない）
    print("\n⚠ clear-dir-before-merge: 次のディレクトリ内の全項目を削除します。", file=sys.stderr)
    print(f"    パス   : {target}", file=sys.stderr)
    print(f"    項目数 : {count}", file=sys.stderr)
    if not ignore_force and getattr(args, "force", False):
        logging.warning("clear-dir-before-merge: --force のため確認なしで削除します。")
        return True
    try:
        ans = input("全削除してよいですか？ [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        logging.error(
            "clear-dir-before-merge: 確認入力が得られないため中止します"
            "（承認するなら --force、無効化するなら recipe で clear-dir-before-merge: false）。",
        )
        return False
    return ans in ("y", "yes")


def _collect_image_sources(procedure_items: list, yaml_dir: Path) -> set[Path]:
    """Return the resolved image paths referenced by the merge inputs (includes too).

    読み込みや include の不備はここでは無視し、後段の本処理のエラー処理に任せる。
    """
    collector = ImageSourceCollector()
    for item in procedure_items:
        if not isinstance(item, Path) or not item.exists():
            continue
        try:
            expand_md(item, yaml_dir=yaml_dir, image_copier=collector)
        except (CircularIncludeError, IncludeNotFoundError, OSError, UnicodeDecodeError):
            continue
    return collector.sources


def _clear_image_dir(
    out_dir: Path,
    image_dir_name: str,
    args: argparse.Namespace,
    *,
    sources: "set[Path] | None" = None,
) -> bool:
    """Delete the contents of ``out_dir/image_dir_name`` before merging.

    Refuses to act unless the target is a proper subdirectory of *out_dir*, so a
    stray image-dir value (``.``, ``..``, an absolute path, …) cannot wipe the
    output directory or escape it. 削除対象があるときはフルパスを提示して確認する。

    *sources* (merge 入力が参照する画像の実パス) のどれかが image-dir 内にある場合は、
    merge 自身のコピー元を消してしまうため削除せず警告だけ出す（pptimgexport の
    書き出し先が image-dir と同じ構成など）。

    戻り値: True=処理続行可（削除実行 or 削除対象なし）/ False=ユーザーが中止。
    """
    out_dir = out_dir.resolve()
    target = (out_dir / image_dir_name).resolve()
    if target == out_dir or out_dir not in target.parents:
        logging.error(
            "clear-dir-before-merge: image-dir が出力ディレクトリ配下のサブディレクトリ"
            "ではないため削除を中止します: %s", target,
        )
        return True  # 削除しない（不正な指定）だけで、merge は続行させる
    if not target.exists():
        return True
    if not target.is_dir():
        logging.warning("clear-dir-before-merge: image-dir がディレクトリではありません: %s", target)
        return True
    entries = list(target.iterdir())
    if not entries:
        return True  # 空なので削除対象なし・確認不要
    inside = sorted(s for s in (sources or ()) if target in s.parents and s.exists())
    if inside:
        logging.warning(
            "clear-dir-before-merge: merge 入力が参照する画像 %d 件が image-dir 内にあるため"
            "削除をスキップします（例: %s）。image-dir: %s",
            len(inside), inside[0], target,
        )
        logging.warning(
            "clear-dir-before-merge: 画像の書き出し先（export-image）と merge の image-dir を"
            "分けるには output.outputdir（例: build）を指定してください。",
        )
        return True
    if not _confirm_clear(target, len(entries), args):
        return False
    for entry in entries:
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as e:
            logging.warning("clear-dir-before-merge: 削除に失敗: %s: %s", entry, e)
    logging.info("clear-dir-before-merge: image-dir を空にしました: %s", target)
    return True


def preflight_clear_confirm(args: argparse.Namespace) -> int:
    """パイプライン先頭で clear-dir-before-merge の確認を行う（実削除は後段 merge）。

    削除対象があれば解決済みフルパスを提示して確認し、承認されたら
    ``args.clear_dir_confirmed`` を立てて後段 merge の再確認を省く。これにより
    「全処理を始める前」に一度だけ確認できる。``--force`` の有無に関係なく
    必ず確認する（承認なしにパイプラインが image-dir を破壊しないため）。
    戻り値: EXIT_OK=続行（確認不要 or 承認）/ EXIT_FAILURE=中止。
    """
    if getattr(args, "dry_run", False):
        return EXIT_OK
    yaml_path = resolve_input_path(args)
    if yaml_path is None or not yaml_path.exists():
        return EXIT_OK  # 入力不正は後段の通常エラー処理に任せる
    try:
        recipe = load_yaml(yaml_path)
    except Exception:  # noqa: BLE001  読み込み失敗も後段に委ねる
        return EXIT_OK
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    _apply_recipe_merge_opts(args, recipe.get("merge", {}))
    if not getattr(args, "clear_dir_before_merge", False):
        return EXIT_OK
    image_dir_name = getattr(args, "image_dir", None)
    if not image_dir_name:
        return EXIT_OK
    out_path = resolve_output_path(recipe, yaml_path, workdir)
    out_dir = out_path.parent.resolve()
    target = (out_dir / image_dir_name).resolve()
    if target == out_dir or out_dir not in target.parents:
        return EXIT_OK  # 不正な image-dir は後段 merge が処理
    if not target.exists() or not target.is_dir():
        return EXIT_OK
    entries = list(target.iterdir())
    if not entries:
        return EXIT_OK
    if not _confirm_clear(target, len(entries), args, ignore_force=True):
        logging.error("clear-dir-before-merge: 確認が得られなかったためパイプラインを中止しました。")
        return EXIT_FAILURE
    args.clear_dir_confirmed = True
    return EXIT_OK


def _verify_insertmd_check(
    args: argparse.Namespace,
    recipe: dict,
    in_dirs: list[Path],
    yaml_path: Path,
    workdir: Path | None,
) -> list[tuple[str, list[str]]]:
    """Verify insertmd content against the check file (if present). Warn on drift.

    Skipped when --no-check is passed or the check file does not exist. Returns the
    list of (mdfilename, reasons) so the caller can escalate under --strict.
    """
    if getattr(args, "no_check", False):
        return []
    check_path = resolve_out_file(recipe, "checkfilename", yaml_path, workdir)
    if check_path is None or not check_path.exists():
        return []

    check_map = load_check_map(check_path)
    io_entries = iter_insertmd_entries(recipe, in_dirs, yaml_path)
    problems = verify_against_check(check_map, io_entries)
    for fname, reasons in problems:
        logging.warning("insertmd 整合性チェック: %s: %s", fname, "; ".join(reasons))
    if not problems:
        logging.debug("insertmd 整合性チェック: 差異なし (%s)", check_path.name)
    return problems


def _apply_recipe_merge_opts(args: argparse.Namespace, mc: dict) -> None:
    """Fill unset CLI boolean/string options from the recipe's merge section.

    CLI flags (store_true) default to False; a True value means the flag was
    explicitly passed, so recipe values only fill in when the flag is False.
    """
    if not args.no_copy_images:
        args.no_copy_images = bool(mc.get("no-copy-images", False))
    if not args.image_dir:
        # キー省略時は既定サブディレクトリ、空文字を明示したときは outputdir 直下（旧挙動）。
        val = mc.get("image-dir", None)
        args.image_dir = DEFAULT_IMAGE_DIR if val is None else str(val)
    if not args.flatten_images:
        args.flatten_images = bool(mc.get("flatten-images", False))
    if not getattr(args, "image_naming", None):
        args.image_naming = str(mc.get("image-naming") or "preserve").strip().lower()
    if not getattr(args, "image_collision", None):
        # overwrite-images は image-collision: overwrite の非推奨エイリアス。
        legacy = getattr(args, "overwrite_images", False) or bool(mc.get("overwrite-images", False))
        if legacy and not mc.get("image-collision"):
            logging.debug("overwrite-images は非推奨です。image-collision: overwrite を使用してください")
        args.image_collision = str(
            mc.get("image-collision") or ("overwrite" if legacy else "rename")
        ).strip().lower()
    if not getattr(args, "clear_dir_before_merge", False):
        # 既定 True。無効化するには recipe で clear-dir-before-merge: false を指定する。
        args.clear_dir_before_merge = bool(mc.get("clear-dir-before-merge", True))
    if not getattr(args, "strict", False):
        args.strict = bool(mc.get("strict", False))


