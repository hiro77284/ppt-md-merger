"""githubmd: puremd の出力（GFM）を GitHub 表示向けに仕上げる。

puremd の出力は Astro（transfer）・note.com（notecomexport）・その他ビューアと共有の
中間形式で、画像の pandoc 属性（``![](a.png){ width=40% }``）をそのまま残す（Astro 側は
属性記法で幅を効かせている）。GitHub は pandoc 属性を解釈せず ``{ width=40% }`` を文字列の
まま表示するため、GitHub 専用の変換はこのサブコマンドで行う。

変換内容（画像のみ）:
  - ``![alt](src){ width=40% }`` → ``<img src="src" alt="alt" width="40%">``
    （width / height のうち ``%`` か px の値だけを HTML 属性に移す）
  - 上記以外の属性（``8cm`` 等の単位、``#id``、``.class``、その他の key=value）は
    GitHub で表現できないので警告して捨てる。残る属性が無ければ ``![alt](src)`` に戻す
  - コードフェンス内・インラインコード内・YAML frontmatter 内は変換しない

入力は ``output.puremdfilename``、出力は ``output.githubmdfilename``。
"""

from __future__ import annotations

import argparse
import html
import logging
import re
import shlex
from pathlib import Path

from md_merge._imagerefs import FrontmatterTracker
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

# 属性付きの画像。属性は画像の直後（空白・タブのみ許容）に続くもの。
_IMAGE_ATTR_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)\)[ \t]*\{([^}\n]*)\}')

# コードフェンスの開始/終了行（行頭 0〜3 スペース＋ ``` / ~~~ 3 個以上）
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})')

# インラインコード（同じ長さのバッククォート列で閉じる）
_INLINE_CODE_RE = re.compile(r'(`+)(?:(?!\1).)+?\1')

# HTML の width / height 属性に移せる値（% または px / 単位なし）
_SIZE_RE = re.compile(r'^(\d+(?:\.\d+)?)(%|px)?$')

_SIZE_KEYS = ("width", "height")


def _parse_attrs(attr_text: str) -> list[str]:
    """``width=40% .cls #id key="a b"`` をトークンに分ける（引用符は shlex で解釈）。"""
    try:
        return shlex.split(attr_text)
    except ValueError:
        return attr_text.split()


def _convert_image(m: "re.Match[str]", where: str) -> str:
    alt, src, attr_text = m.group(1), m.group(2), m.group(3)
    html_attrs: list[tuple[str, str]] = []
    dropped: list[str] = []
    for tok in _parse_attrs(attr_text):
        key, sep, val = tok.partition("=")
        if sep and key in _SIZE_KEYS:
            sm = _SIZE_RE.match(val.strip())
            if sm:
                num, unit = sm.group(1), sm.group(2)
                html_attrs.append((key, f"{num}%" if unit == "%" else num))
                continue
        dropped.append(tok)
    if dropped:
        logging.warning(
            "githubmd: GitHub で表現できない画像属性を捨てました: %s (%s, %s)",
            " ".join(dropped), src, where,
        )
    if not html_attrs:
        return f"![{alt}]({src})"
    parts = [f'src="{html.escape(src, quote=True)}"', f'alt="{html.escape(alt, quote=True)}"']
    parts += [f'{k}="{v}"' for k, v in html_attrs]
    return "<img " + " ".join(parts) + ">"


def convert(text: str, source_name: str = "") -> tuple[str, int]:
    """puremd の MD を GitHub 向けに変換する。戻り値は (変換後のテキスト, 変換した画像数)。"""
    out: list[str] = []
    count = 0
    fence: str | None = None
    tracker = FrontmatterTracker()
    for lineno, line in enumerate(text.splitlines(keepends=True), start=1):
        if tracker.feed(line):
            out.append(line)
            continue
        m = _FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line[m.end():].strip():
                fence = None
            out.append(line)
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        where = f"{source_name}:{lineno}" if source_name else f"line {lineno}"

        def sub(seg: str) -> str:
            def one(mm: "re.Match[str]") -> str:
                nonlocal count
                new = _convert_image(mm, where)
                if new.startswith("<img "):
                    count += 1
                return new
            return _IMAGE_ATTR_RE.sub(one, seg)

        pieces: list[str] = []
        pos = 0
        for cm in _INLINE_CODE_RE.finditer(line):
            pieces += [sub(line[pos:cm.start()]), cm.group(0)]
            pos = cm.end()
        pieces.append(sub(line[pos:]))
        out.append("".join(pieces))
    return "".join(out), count


# ── subcommand entry point ────────────────────────────────────────────────────

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

    puremd_path = resolve_out_file(recipe, "puremdfilename", yaml_path, workdir)
    if puremd_path is None:
        logging.error("output.puremdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    githubmd_path = resolve_out_file(recipe, "githubmdfilename", yaml_path, workdir)
    if githubmd_path is None:
        logging.error("output.githubmdfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    logging.debug("puremd   : %s", puremd_path)
    logging.debug("githubmd : %s", githubmd_path)

    if args.dry_run:
        emit(args, "ok", "githubmd", puremd_path, githubmd_path, dry_run=True)
        return EXIT_OK

    if not puremd_path.exists():
        logging.error("puremd MD not found (run puremd first): %s", puremd_path)
        return EXIT_NOT_FOUND

    if githubmd_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", githubmd_path)
        return EXIT_FAILURE

    content = puremd_path.read_text(encoding="utf-8")
    content, n = convert(content, puremd_path.name)
    logging.info("githubmd: %d image(s) converted to <img>", n)

    try:
        githubmd_path.parent.mkdir(parents=True, exist_ok=True)
        githubmd_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logging.error("Failed to write %s: %s", githubmd_path, exc)
        return EXIT_FAILURE

    emit(args, "ok", "githubmd", puremd_path, githubmd_path)
    return EXIT_OK
