"""version 2 / 3 のレシピを version 4 へ書き換える（pandoc セクションのキーの整理）。

LaTeX（lualatex）の撤去に合わせて、version 4 では PDF 用の pandoc キーを接頭辞なしの名前にした
（docs/md_merge_spec.md の 5.3）。このツールはその書き換えをする。

    typst-cover-md: X        →   cover-md: X
    typstdefaults: X         →   defaults: X
      （値の同梱 typst_semantic_engine.yaml は report_base_defaults.yaml に改名）
    cover-md / defaults（LaTeX 用）、engine、template、include-in-header、include-before-body、
    conditional-process-input / -output、format   →   削除
    output.texfilename / output.resourcepathfilename（LaTeX 用の出力）   →   削除
    version: 2 / 3           →   version: 4

version 2 で ``typst-cover-md`` が無く LaTeX 用の表紙（``cover-md`` / ``conditional-process-input``）
がある場合は、同梱の標準表紙が暗黙に付いていたので、レシピに ``cover-md: cover_standard.md`` を
書き足して同じ PDF になるようにする。

YAML を読み書きするとコメントが失われるため、行単位のテキスト置換で変換する（キー名の行と、
その値の行だけを書き換える。コメント行には触らない）。

pandoc セクションの ``_include`` 先（共有の pandoc 設定ファイル）も一緒に書き換える。共有ファイルの
キーの意味は読み込むレシピの version で決まるので、同じファイルを読むレシピはまとめて version 4 に
する必要がある。共有ファイルを読む他のレシピ（共有ファイルのフォルダ以下、または --scan-root 以下を
探す）が変換対象に入っていなければ、何も書き換えずに一覧を出して止まる。``--with-includers`` を
付けると、それらも一緒に変換する。

使い方:
    python tools/convert_recipe_v4.py [--check] [--with-includers] [--scan-root DIR] [--no-backup] RECIPE...

--check は書き換えずに変更内容だけを表示する。既定では書き換える前のファイルを
``<名前>.before_v4`` として残す（--no-backup で残さない）。
version 1 のレシピは先に tools/convert_procedure_v2.py で version 2 にすること。
旧書式の ``!include`` は先に tools/convert_include_keys.py で ``_include`` にすること。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from md_merge.merge._recipe import load_yaml  # noqa: E402
from md_merge._pandoc_keys import RENAMED_BUILTIN_DEFAULTS  # noqa: E402
from md_merge._typst_cover import (  # noqa: E402
    TYPST_DEFAULT_COVER,
    TYPST_DEFAULT_COVER_OLD,
    select_typst_cover,
)

TARGET_VERSION = 4

# 消すキー（LaTeX 専用、または廃止）。cover-md / defaults は version 3 までは LaTeX 用の意味。
_DELETE_KEYS = (
    "engine", "template", "include-in-header", "include-before-body",
    "conditional-process-input", "conditional-process-output", "format",
    "cover-md", "defaults", "metadata-file",
)
_RENAME_KEYS = {"typst-cover-md": "cover-md", "typstdefaults": "defaults"}

_VERSION_RE = re.compile(r"^version:[ \t]*(?P<v>\S+?)(?P<rest>[ \t]*(?:#.*)?)$")
_TOP_KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):(?P<rest>.*)$")
_KEY_RE = re.compile(r"^(?P<ind>[ \t]*)(?P<key>[A-Za-z_][\w-]*):(?P<rest>.*)$")
_BANG_INCLUDE_RE = re.compile(r"!include\b")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return s == "" or s.startswith("#")


@dataclass
class _Region:
    """書き換える範囲（レシピの pandoc: の中、または共有設定ファイル全体）。"""
    start: int          # 最初の行（含む）
    end: int            # 最後の行の次
    indent: int | None  # 子キーの字下げ（キーが無ければ None）


def _pandoc_region(lines: list[str], section: str = "pandoc") -> _Region | None:
    for i, line in enumerate(lines):
        m = _TOP_KEY_RE.match(line)
        if m and m.group("key") == section:
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or _indent(lines[j]) > 0 or lines[j].lstrip().startswith("#")):
                if not lines[j].strip() == "" and _indent(lines[j]) == 0 and lines[j].startswith("#"):
                    # 字下げなしのコメントは次のトップレベルの説明とみなす
                    k = j
                    while k < len(lines) and (lines[k].strip() == "" or lines[k].startswith("#")):
                        k += 1
                    if k >= len(lines) or _TOP_KEY_RE.match(lines[k]):
                        break
                j += 1
            indent = None
            for k in range(i + 1, j):
                if not _is_blank_or_comment(lines[k]) and _KEY_RE.match(lines[k]):
                    indent = _indent(lines[k])
                    break
            return _Region(i + 1, j, indent)
    return None


def _key_blocks(lines: list[str], region: _Region) -> dict[str, tuple[int, int]]:
    """region 直下のキー → (キー行, 値ブロックの終わり) 。"""
    blocks: dict[str, tuple[int, int]] = {}
    if region.indent is None:
        return blocks
    i = region.start
    while i < region.end:
        line = lines[i]
        m = _KEY_RE.match(line)
        if m and not _is_blank_or_comment(line) and _indent(line) == region.indent:
            j = i + 1
            while j < region.end:
                nxt = lines[j]
                if nxt.strip() == "":
                    break
                ind = _indent(nxt)
                if ind > region.indent:
                    j += 1
                    continue
                if ind == region.indent and nxt.lstrip().startswith("- "):
                    j += 1
                    continue
                break
            blocks.setdefault(m.group("key"), (i, j))
            i = j
            continue
        i += 1
    return blocks


@dataclass
class _Plan:
    path: Path
    lines: list[str]
    new_lines: list[str] = field(default_factory=list)
    nl: str = "\n"
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.lines != self.new_lines


def _rewrite_region(lines: list[str], region: _Region, notes: list[str], add_cover: bool) -> list[str]:
    blocks = _key_blocks(lines, region)
    drop: set[int] = set()
    replace: dict[int, str] = {}
    insert_at: int | None = None
    for key in _DELETE_KEYS:
        if key in blocks:
            a, b = blocks[key]
            drop.update(range(a, b))
            notes.append(f"削除: {key}（{a + 1} 行目）")
            if key == "metadata-file":
                _val = _KEY_RE.match(lines[a]).group("rest").split("#", 1)[0].strip()
                notes.append(
                    f"  要手作業: metadata-file（{_val}）は version 4 で廃止。"
                    "中身を defaults ファイルの metadata: に移してください"
                )
            if key in ("cover-md", "conditional-process-input") and insert_at is None:
                insert_at = a
    for old, new in _RENAME_KEYS.items():
        if old in blocks:
            a, b = blocks[old]
            line = lines[a]
            m = _KEY_RE.match(line)
            rest = m.group("rest")
            if old == "typst-cover-md":
                rest = rest.replace(TYPST_DEFAULT_COVER_OLD, TYPST_DEFAULT_COVER)
            replace[a] = f"{m.group('ind')}{new}:{rest}"
            drop.discard(a)
            for k in range(a + 1, b):
                drop.discard(k)
            notes.append(f"改名: {old} → {new}（{a + 1} 行目）")
            if old == "typstdefaults":
                for k in range(a, b):
                    text = replace.get(k, lines[k])
                    for old_name, new_name in RENAMED_BUILTIN_DEFAULTS.items():
                        if old_name in text:
                            text = text.replace(old_name, new_name)
                            notes.append(f"改名: {old_name} → {new_name}（{k + 1} 行目）")
                    if k != a and text != lines[k]:
                        replace[k] = text
                    elif k == a:
                        replace[a] = text
    out: list[str] = []
    ind = " " * (region.indent if region.indent is not None else 2)
    cover_line = f"{ind}cover-md: {TYPST_DEFAULT_COVER}  # version 2 の暗黙の標準表紙を明示（convert_recipe_v4）"
    if add_cover and insert_at is None:
        insert_at = region.end
    for i, line in enumerate(lines):
        if add_cover and i == insert_at:
            out.append(cover_line)
        if i in drop:
            continue
        out.append(replace.get(i, line))
    if add_cover and insert_at == len(lines):
        out.append(cover_line)
    if add_cover:
        notes.append(f"追加: cover-md: {TYPST_DEFAULT_COVER}（version 2 で暗黙に付いていた標準表紙）")
    return out


# output: から消すキー（LaTeX 用の出力）
_OUTPUT_DELETE_KEYS = ("texfilename", "resourcepathfilename")


def _drop_output_keys(lines: list[str], notes: list[str]) -> list[str]:
    region = _pandoc_region(lines, "output")
    if region is None:
        return lines
    blocks = _key_blocks(lines, region)
    drop: set[int] = set()
    for key in _OUTPUT_DELETE_KEYS:
        if key in blocks:
            a, b = blocks[key]
            drop.update(range(a, b))
            notes.append(f"削除: output.{key}（{a + 1} 行目）")
    return [line for i, line in enumerate(lines) if i not in drop]


def _load(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def _newline(path: Path) -> str:
    return "\r\n" if b"\r\n" in path.read_bytes() else "\n"


def _includes_of(path: Path) -> list[Path]:
    """レシピの pandoc: 直下の _include 先（テキストから読む。_constants 付きのレシピは YAML として読めないため）。"""
    try:
        lines = _load(path)
    except (OSError, UnicodeDecodeError):
        return []
    region = _pandoc_region(lines)
    if region is None:
        return []
    blocks = _key_blocks(lines, region)
    if "_include" not in blocks:
        return []
    a, b = blocks["_include"]
    rest = _KEY_RE.match(lines[a]).group("rest")
    try:
        val = yaml.safe_load("v:" + rest + "\n" + "\n".join(lines[a + 1:b]))["v"]
    except yaml.YAMLError:
        return []
    items = val if isinstance(val, list) else ([val] if val else [])
    return [(path.parent / str(x)).resolve() for x in items]


def _version_of(lines: list[str]) -> int | str | None:
    for line in lines:
        m = _VERSION_RE.match(line)
        if m:
            v = m.group("v")
            return int(v) if v.isdigit() else v
    return None


def _merged_pandoc(path: Path) -> dict:
    """_include・_constants を展開したレシピの pandoc セクション。"""
    try:
        data = load_yaml(path, normalize=False, apply_vars=False)
    except Exception:  # noqa: BLE001  読めないレシピは表紙の判定だけ諦める
        return {}
    pandoc = data.get("pandoc") if isinstance(data, dict) else None
    return pandoc if isinstance(pandoc, dict) else {}


def _find_includers(settings: Path, roots: list[Path]) -> set[Path]:
    found: set[Path] = set()
    for root in roots:
        for p in root.rglob("*.yaml"):
            if any(part.startswith(".") or part == "build" for part in p.relative_to(root).parts[:-1]):
                continue
            if p.name.endswith(".before_v4"):
                continue
            if settings in _includes_of(p):
                found.add(p.resolve())
    return found


def _convert(paths: list[Path], scan_roots: list[Path], with_includers: bool) -> tuple[list[_Plan], list[str]]:
    errors: list[str] = []
    recipes = [p.resolve() for p in paths]

    # 共有設定ファイルと、それを読む他のレシピ。version 4 のレシピは変換済みなので数えない
    # （その共有ファイルも変換済みとみなす。もう一度書き換えると cover-md / defaults を消してしまう）。
    recipes = [r for r in recipes if _version_of(_load(r)) != TARGET_VERSION]
    settings_files: dict[Path, set[Path]] = {}
    for r in recipes:
        for inc in _includes_of(r):
            settings_files.setdefault(inc, set()).add(r)
    for s in list(settings_files):
        roots = scan_roots or [s.parent]
        includers = _find_includers(s, roots) | settings_files[s]
        done = {p for p in includers if _version_of(_load(p)) == TARGET_VERSION}
        if done:
            errors.append(
                f"{s} は version 4 のレシピからも読まれています（変換済み）。version 3 以前のレシピと"
                "共有したままにはできないので、手で直してください:\n    "
                + "\n    ".join(str(p) for p in sorted(done))
            )
            continue
        others = {p for p in includers if p not in recipes}
        if others:
            if with_includers:
                recipes.extend(sorted(others))
                settings_files[s].update(others)
            else:
                errors.append(
                    f"{s} は次のレシピからも読まれています。まとめて変換してください"
                    "（--with-includers で一緒に変換します）:\n    " + "\n    ".join(str(p) for p in sorted(others))
                )
    if errors:
        return [], errors

    plans: list[_Plan] = []
    for r in recipes:
        lines = _load(r)
        text = "\n".join(lines)
        if _BANG_INCLUDE_RE.search(text):
            errors.append(f"{r}: 旧書式の !include があります。先に tools/convert_include_keys.py を使ってください")
            continue
        version = _version_of(lines) or 1
        if version not in (2, 3):
            errors.append(f"{r}: version {version!r} は変換できません（version 1 は先に tools/convert_procedure_v2.py で 2 にします）")
            continue
        plan = _Plan(r, lines, nl=_newline(r))
        # version 2 の暗黙の標準表紙は、レシピ側に cover-md を書き足して残す
        _cover, builtin, _warn = select_typst_cover(_merged_pandoc(r), version)
        region = _pandoc_region(lines)
        new = list(lines)
        if region is not None:
            new = _rewrite_region(lines, region, plan.notes, add_cover=builtin)
        elif builtin:
            errors.append(f"{r}: pandoc: が見つからないので標準表紙を書き足せません")
            continue
        new = _drop_output_keys(new, plan.notes)
        for i, line in enumerate(new):
            m = _VERSION_RE.match(line)
            if m:
                new[i] = f"version: {TARGET_VERSION}{m.group('rest')}"
                plan.notes.append(f"version: {version} → {TARGET_VERSION}")
                break
        plan.new_lines = new
        plans.append(plan)

    for s in settings_files:
        lines = _load(s)
        plan = _Plan(s, lines, nl=_newline(s))
        region = _Region(0, len(lines), 0)
        plan.new_lines = _rewrite_region(lines, region, plan.notes, add_cover=False)
        plans.append(plan)
    return plans, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipes", nargs="+", type=Path, metavar="RECIPE")
    ap.add_argument("--check", action="store_true", help="書き換えずに変更内容だけを表示する")
    ap.add_argument("--with-includers", action="store_true", help="共有の pandoc 設定を読む他のレシピも一緒に変換する")
    ap.add_argument("--scan-root", action="append", type=Path, default=[], metavar="DIR",
                    help="共有の pandoc 設定を読むレシピを探すフォルダ（既定: 設定ファイルのフォルダ）")
    ap.add_argument("--no-backup", action="store_true", help="<名前>.before_v4 を残さない")
    args = ap.parse_args(argv)

    plans, errors = _convert(args.recipes, [p.resolve() for p in args.scan_root], args.with_includers)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors:
        return 1
    for plan in plans:
        if not plan.changed:
            continue
        print(f"{plan.path}:")
        for n in plan.notes:
            print(f"  {n}")
        if args.check:
            continue
        if not args.no_backup:
            shutil.copy2(plan.path, plan.path.with_name(plan.path.name + ".before_v4"))
        with open(plan.path, "w", encoding="utf-8", newline="") as f:
            f.write(plan.nl.join(plan.new_lines) + plan.nl)
    if not any(p.changed for p in plans):
        print("変換するものはありません")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
