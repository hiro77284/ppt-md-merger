from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import yaml
from pptx import Presentation

from md_merge._filters import escape_backslash_smart, replace_slide_placeholders
from md_merge._fingerprint import extract_headings
from md_merge._note_parser import parse_note_md_blocks
from md_merge._cropsrc import cropsrc_entries, resolve_cropsrc_path
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._preprocess import cropsrc_read_path
from md_merge._procedure import LATEST_VERSION, recipe_version, to_notation
from md_merge.merge._recipe import load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

_VAR_RE = re.compile(r"\{\{v:([A-Za-z0-9_]+)\}\}")

# pptmerge idresolve のノート専用参照マーカー。MD には不要なのでエクスポート時に
# 除去する（結合済み pptx のノート原文は別アーティファクトとして残るため、
# pptmerge のタイトル付番には影響しない）。{{#id:}} / {{nolabel}} 等は MD 側で
# idcollect / render が使うので除去しない。
_NOTE_REF_MARKER_RE = re.compile(r"\{\{(?:enclosenum|titlelabel):[^}]+\}\}")

# pandoc の raw attribute（`` ```{=latex} `` フェンスや行内 `` `…`{=latex} ``）。
# これは「特定の出力形式専用の生コード」を意味するため、セマンティックな原稿には
# 書かれるべきでない。原稿 pptx の MD ブロック内にこの記法があれば検出する。
_RAW_ATTR_RE = re.compile(r"\{=([A-Za-z0-9-]+)\}")

_LATEX_CHECK_MODES = ("off", "warn", "error")
_LATEX_CHECK_DEFAULT = "warn"

# フェンスなしで本文に書かれた LaTeX コマンド（\hspace*{4em} / {\bfseries …} / \vspace{5mm} 等）。
# pptmdexport は本文のバックスラッシュをエスケープするので、これらはどの出力形式でも
# 効かず文字どおり表示される。Markdown のエスケープ（\* \_ \\ など）は英字が続かないので
# 当たらない。fenced div / span の属性（{.widequote width="0.6\linewidth"} 等）は
# フィルタが読み替えるので対象外にする。
_BARE_LATEX_RE = re.compile(r"\\[A-Za-z]+")
_ATTR_GROUP_RE = re.compile(r"\{[.#][^{}]*\}|\{[^{}]*=[^{}]*\}")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _find_raw_blocks(md_text: str) -> list[tuple[int, str]]:
    """Return (line_number, format) for each pandoc raw-attribute marker.

    Detects both fenced raw blocks (``` ```{=latex} ```) and inline raw spans
    (`` `code`{=latex} ``); any ``{=FORMAT}`` attribute counts as target-specific
    raw passthrough. Line numbers are 1-based within md_text.
    """
    found: list[tuple[int, str]] = []
    for i, line in enumerate(md_text.splitlines(), start=1):
        for m in _RAW_ATTR_RE.finditer(line):
            found.append((i, m.group(1)))
    return found


def _find_bare_latex(md_text: str) -> list[tuple[int, str]]:
    """Return (line_number, command) for LaTeX commands written without a raw fence.

    Code blocks (``` … ```), inline code and pandoc attribute groups are skipped.
    Line numbers are 1-based within md_text.
    """
    found: list[tuple[int, str]] = []
    in_code = False
    for i, line in enumerate(md_text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        body = _ATTR_GROUP_RE.sub("", _INLINE_CODE_RE.sub("", line))
        for m in _BARE_LATEX_RE.finditer(body):
            found.append((i, m.group(0)))
    return found


def _resolve_latex_check(args: argparse.Namespace, recipe: dict) -> str:
    """Resolve the raw-latex check mode (off|warn|error). CLI overrides recipe.

    Falls back to recipe ``pptmdexport.latex_check`` then the built-in default.
    """
    cli = getattr(args, "latex_check", None)
    if cli in _LATEX_CHECK_MODES:
        return cli
    val = (recipe.get("pptmdexport") or {}).get("latex_check")
    if isinstance(val, str) and val.strip().lower() in _LATEX_CHECK_MODES:
        return val.strip().lower()
    return _LATEX_CHECK_DEFAULT


def _sub_vars(text: str, vars_map: dict[str, str]) -> str:
    """Replace {{v:NAME}} with vars_map[NAME]; leave undefined names unchanged."""
    if not vars_map:
        return text
    return _VAR_RE.sub(lambda m: vars_map.get(m.group(1), m.group(0)), text)


def _strip_note_ref_markers(md_text: str) -> str:
    """Remove pptmerge-only reference markers ({{enclosenum:}}/{{titlelabel:}}).

    Lines that become blank after removal (i.e. held only such markers) are
    dropped; other lines keep their remaining content.
    """
    out: list[str] = []
    for line in md_text.splitlines():
        if not _NOTE_REF_MARKER_RE.search(line):
            out.append(line)
            continue
        stripped = _NOTE_REF_MARKER_RE.sub("", line)
        if stripped.strip() == "":
            continue  # line held only reference markers → drop it
        out.append(stripped.rstrip())
    return "\n".join(out)


def _indent2(text: str) -> str:
    """Indent every non-blank line by 2 spaces (for pasting under procedure:)."""
    return "".join(("  " + ln if ln.strip() else ln) for ln in text.splitlines(keepends=True))


def _dump_block(entries: list[dict], version: int = LATEST_VERSION) -> str:
    """Dump procedure entries (internal form) in the notation of recipe *version*."""
    if not entries:
        return ""
    entries = [to_notation(e, version) for e in entries]
    return _indent2(yaml.dump(entries, allow_unicode=True, default_flow_style=False, sort_keys=False))


def _write_insert_sample(
    sample_path: "Path | None", slide_groups: list[dict], version: int = LATEST_VERSION
) -> None:
    """Write the combined procedure-paste sample with 3 blocks.

    Block 1: insertpptx (every slide), block 2: insertmd (every exported MD),
    block 3: mixed per slide (insertpptx followed by that slide's insertmd). Within
    each block entries follow cropsrc order, then slide order. Lines are indented by
    2 spaces. Every block gets a "NEW PPTX" separator comment at each pptx boundary,
    and block 3 additionally gets a per-slide separator (slide number + pptx
    filename). Entries use the procedure notation of the source recipe *version*.
    Does nothing when the path is unset or there is nothing to write.
    """
    if sample_path is None:
        logging.debug("output.insertsamplefilename / targetbasefilename 未設定のため サンプルは生成しません")
        return

    pptx_block = [g["pptx"] for g in slide_groups]
    md_block = [e for g in slide_groups for e in g["md"]]
    if not pptx_block and not md_block:
        return

    def _pptx_name(g: dict) -> str:
        return Path(str(g["pptx"].get("pptxfilename", ""))).name

    def _new_pptx_sep(name: str) -> str:
        return f"  # __________ NEW PPTX: {name} __________\n"

    # Block 1: insertpptx per slide, with a NEW PPTX separator at each pptx boundary.
    b1_parts: list[str] = []
    prev: str | None = None
    for g in slide_groups:
        name = _pptx_name(g)
        if name != prev:
            b1_parts.append(_new_pptx_sep(name))
            prev = name
        b1_parts.append(_dump_block([g["pptx"]], version))

    # Block 2: insertmd, NEW PPTX separator before each pptx that has md entries.
    b2_parts: list[str] = []
    prev = None
    for g in slide_groups:
        if not g["md"]:
            continue
        name = _pptx_name(g)
        if name != prev:
            b2_parts.append(_new_pptx_sep(name))
            prev = name
        b2_parts.append(_dump_block(g["md"], version))

    # Block 3: NEW PPTX separator at each pptx boundary, then a per-slide separator
    # ("# ----------- slide N deck.pptx -----------") before each slide group.
    b3_parts: list[str] = []
    prev = None
    for g in slide_groups:
        name = _pptx_name(g)
        if name != prev:
            b3_parts.append(_new_pptx_sep(name))
            prev = name
        slide_n = g["pptx"].get("slides")
        b3_parts.append(f"  # ----------- slide {slide_n} {name} -----------\n")
        b3_parts.append(_dump_block([g["pptx"], *g["md"]], version))

    parts = [
        "  # ===== ブロック1: insertpptx サンプル =====\n",
        "".join(b1_parts),
        "\n  # ===== ブロック2: insertmd サンプル =====\n",
        "".join(b2_parts),
        "\n  # ===== ブロック3: insertpptx + insertmd ミックス（スライド単位） =====\n",
        "".join(b3_parts),
    ]
    try:
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        with sample_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write("".join(parts))
        logging.info(
            "insert サンプルを書き出しました: %s (insertpptx %d / insertmd %d)",
            sample_path, len(pptx_block), len(md_block),
        )
    except OSError as e:
        logging.warning("insert サンプルの書き出しに失敗: %s: %s", sample_path, e)


def _sample_entry(task: dict, vars_map: dict[str, str]) -> dict:
    """Build a procedure insertmd sample entry (description = first heading).

    The md_text already has <__...__> placeholders substituted; here {{v:NAME}}
    variables are additionally resolved. {{#id reference conversion is NOT done.
    """
    headings = extract_headings(task["md_text"])
    description = _sub_vars(headings[0], vars_map) if headings else ""
    return {
        "operation": "insertmd",
        "mdfilename": task["output"].name,
        "description": description,
    }


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
    entries = cropsrc_entries(recipe)
    output_section = recipe.get("output") or {}
    cli_workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    workdir = resolve_workdir(recipe, yaml_path, cli_workdir)
    setup_recipe_file_logging(recipe, yaml_path, workdir)
    recipe_force = bool(output_section.get("force"))
    force = getattr(args, "force", False) or recipe_force
    dry_run = getattr(args, "dry_run", False)
    json_mode = getattr(args, "json", False)
    vars_map = {str(k): str(v) for k, v in (recipe.get("vars") or {}).items()}
    sample_path = resolve_out_file(recipe, "insertsamplefilename", yaml_path, workdir)
    latex_check = _resolve_latex_check(args, recipe)
    logging.debug("pptmdexport: latex_check=%s", latex_check)

    if not entries:
        logging.error("input.cropsrc が指定されていません: %s", yaml_path)
        return EXIT_BAD_INPUT

    # ── 全エントリのパス解決と存在確認（fail fast）────────────────────────
    resolved_pptx_paths: list[tuple[str, Path]] = []
    for i, entry in enumerate(entries):
        label = f"input.cropsrc[{i}]" if len(entries) > 1 else "input.cropsrc"
        pptx_val = entry.get("pptx")

        if not pptx_val:
            logging.error("%s.pptx が指定されていません: %s", label, yaml_path)
            return EXIT_BAD_INPUT

        pptx_path = resolve_cropsrc_path(str(pptx_val), yaml_path, workdir)
        if not pptx_path.exists():
            logging.error("PPTX ファイルが見つかりません: %s", pptx_path)
            return EXIT_NOT_FOUND

        resolved_pptx_paths.append((str(pptx_val), pptx_path))

    # ── エントリごとに処理 ────────────────────────────────────────────────
    errors = 0
    json_entries: list[dict] = []
    # Per (cropsrc, slide) groups for the combined insert sample.
    slide_groups: list[dict] = []

    for pptx_val, pptx_path in resolved_pptx_paths:
        # --preprocess 時は前処理済み pptx から読む。export-note 出力先や
        # プレースホルダーの解決は元の pptx_path のまま維持する。
        read_pptx_path = cropsrc_read_path(args, pptx_path)
        try:
            prs = Presentation(str(read_pptx_path))
        except Exception as e:
            logging.error("PPTX ファイルを開けません: %s: %s", read_pptx_path, e)
            errors += 1
            continue

        tasks: list[dict] = []
        for slide_idx, slide in enumerate(prs.slides, start=1):
            note_text = ""
            if slide.has_notes_slide:
                tf = slide.notes_slide.notes_text_frame
                note_text = (tf.text or "") if tf else ""

            title_shape = slide.shapes.title
            slide_title = title_shape.text if title_shape is not None else ""

            # サンプル用: このスライドの insertpptx エントリ＋このスライド由来の
            # insertmd エントリをまとめて収集（全スライド対象、cropsrc 登場順）。
            pptx_entry = {
                "operation": "insertpptx",
                "pptxfilename": pptx_val,
                "slides": slide_idx,
                "description": _sub_vars(slide_title, vars_map),
            }
            md_entries_for_slide: list[dict] = []

            note_text = replace_slide_placeholders(note_text, pptx_path, slide_title, slide_idx)

            for body in parse_note_md_blocks(note_text):
                lines = body.splitlines()
                if not lines:
                    continue

                # 1行目: export-note 指示
                first_line = lines[0]
                if not first_line.startswith("export-note:"):
                    logging.warning(
                        "スライド %d: export-note が1行目にありません: %s", slide_idx, first_line
                    )
                    continue

                _, _, export_note_val = first_line.partition(":")
                export_note_val = export_note_val.strip()

                if not export_note_val.lower().endswith(".md"):
                    logging.warning(
                        "スライド %d: export-note のファイル名が .md ではありません: %s",
                        slide_idx, export_note_val,
                    )
                    continue

                # 2行目以降: MD テキスト。ノート専用参照マーカーは MD から除去する。
                md_text = _strip_note_ref_markers("\n".join(lines[1:]))
                md_lines = md_text.splitlines()
                display_line = md_lines[0] if md_lines else ""

                export_path = Path(export_note_val)
                out_path = export_path if export_path.is_absolute() else (pptx_path.parent / export_path).resolve()

                # Raw slide title (title placeholder shape) — collapse to one
                # line and neutralize any '-->' so it can ride in an HTML comment.
                raw_title = " ".join(slide_title.split()).replace("-->", "--")

                task = {
                    "slide": slide_idx,
                    "output": out_path,
                    "md_text": md_text,
                    "display_line": display_line,
                    "rawtitle": raw_title,
                }
                tasks.append(task)
                md_entries_for_slide.append(_sample_entry(task, vars_map))

            slide_groups.append({"pptx": pptx_entry, "md": md_entries_for_slide})

        if not tasks:
            if not json_mode:
                print(f"export-note を持つスライドが見つかりません: {pptx_path}")
            json_entries.append({"pptx": str(pptx_path), "tasks": [], "writes": []})
            continue

        if not json_mode:
            print(f"対象スライド ({len(tasks)} 件): {pptx_path}")
            for task in tasks:
                print(f"  スライド {task['slide']:>4}: {task['output']}  {task['display_line']}")

        write_results: list[dict] = []

        for task in tasks:
            slide_n: int = task["slide"]
            out_path: Path = task["output"]

            # 原稿に紛れ込んだ生 raw コード（`{=latex}` 等）の検出。warn は警告のみ、
            # error は当該ファイルを書き出さず非ゼロ終了させる。
            if latex_check != "off":
                details: list[str] = []
                raw_hits = _find_raw_blocks(task["md_text"])
                if raw_hits:
                    fmts = "/".join(sorted({f for _, f in raw_hits}))
                    details.append(
                        f"スライド {slide_n}: 生 raw コード {{={fmts}}} を {len(raw_hits)} 個検出"
                        f"（最初: {raw_hits[0][0]} 行目）: {out_path.name}"
                    )
                bare_hits = _find_bare_latex(task["md_text"])
                if bare_hits:
                    cmds = " ".join(sorted({c for _, c in bare_hits}))
                    details.append(
                        f"スライド {slide_n}: フェンスなしの LaTeX コマンド {cmds} を {len(bare_hits)} 個検出"
                        f"（最初: {bare_hits[0][0]} 行目。どの出力形式でも文字どおり表示される）: {out_path.name}"
                    )
                if details:
                    log = logging.error if latex_check == "error" else logging.warning
                    for detail in details:
                        log("%s", detail)
                    if latex_check == "error":
                        errors += 1
                        continue  # 生コードを含む MD は書き出さない

            if out_path.exists() and not force:
                logging.error("出力ファイルが既に存在します (--force で上書き): %s", out_path)
                errors += 1
                continue

            if dry_run:
                emit(args, "ok", "pptmdexport", pptx_path, out_path, dry_run=True)
                write_results.append({"slide": slide_n, "output": str(out_path), "display_line": task["display_line"]})
                continue

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                content = escape_backslash_smart(task["md_text"])
                # Carry the raw slide title for idcollect to capture into the
                # inventory's 'rawtitle' field. Prepended after escaping so the
                # title text itself is not backslash-escaped.
                if task.get("rawtitle"):
                    content = f"<!-- md_merge_rawtitle: {task['rawtitle']} -->\n" + content
                with out_path.open("w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                emit(args, "ok", "pptmdexport", pptx_path, out_path)
                write_results.append({"slide": slide_n, "output": str(out_path), "display_line": task["display_line"]})
            except Exception as e:
                logging.error("書き込み失敗: slide %d: %s", slide_n, e)
                errors += 1

        if getattr(args, "closepptx", False):
            del prs

        json_entries.append({
            "pptx": str(pptx_path),
            "tasks": [{"slide": t["slide"], "output": str(t["output"]), "display_line": t["display_line"]} for t in tasks],
            "writes": write_results,
        })

    # procedure 貼り付け用のサンプル（insertpptx / insertmd / ミックスの3ブロック）を書き出す
    if not dry_run:
        _write_insert_sample(sample_path, slide_groups, recipe_version(recipe))

    if json_mode:
        print(json.dumps({
            "status": "ok" if errors == 0 else "error",
            "command": "pptmdexport",
            "entries": json_entries,
        }, ensure_ascii=False, indent=2))

    return EXIT_OK if errors == 0 else EXIT_FAILURE
