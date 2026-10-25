import argparse
import datetime
import logging
import re
import tomllib
from pathlib import Path

import yaml

from md_merge._conditions import filter_procedure
from md_merge._imagerefs import FrontmatterTracker
from md_merge._procedure import normalize_recipe

_INCLUDE_RE = re.compile(r'^!include\s+(.+?)\s*$')
_RANGE_RE = re.compile(r'\[([^\]]*)\]')

_AUTO_FILENAMES: dict[str, str] = {
    "mdfilename":           "work_{base}_merged.md",
    "idcollectfilename":    "work_{base}_idcollect.yaml",
    "idresolvedfilename":   "work_{base}_idresolve.yaml",
    "renderedfilename":     "{base}_rendered.md",
    "resourcepathfilename": "work_{base}_resourcepath.tex",
    "pdffilename":          "{base}.pdf",
    "texfilename":          "{base}.tex",
    "htmlfilename":         "{base}.html",
    "revealfilename":       "{base}_reveal.html",
    "puremdfilename":       "{base}_puremd.md",
    "notecomyamlfilename":  "{base}_notecom.yaml",
    "pptxfilename":         "{base}.pptx",
    "checkfilename":        "{base}_check.yaml",
    "insertsamplefilename": "{base}_insertsample.yaml",
}


# ── exceptions ─────────────────────────────────────────────────────────────


class CircularIncludeError(Exception):
    def __init__(self, path: Path, chain: frozenset[Path]) -> None:
        self.path = path
        self.chain = chain
        super().__init__(f"Circular include: {path}")


class IncludeNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Include target not found: {path}")


# ── range expansion ────────────────────────────────────────────────────────


def _expand_mdfilename(val: str) -> list[str]:
    """Expand a single ``[from-to]`` range in *val* and return the filename list.

    Raises ValueError for invalid range specifications.
    """
    m = _RANGE_RE.search(val)
    if m is None:
        return [val]

    spec = m.group(1)
    prefix = val[: m.start()]
    suffix = val[m.end() :]

    if not spec.isascii():
        raise ValueError(f"全角文字は使用できません: [{spec}]")

    parts = spec.split("-")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"[from-to] 形式で指定してください: [{spec}]")

    frm, to = parts

    if frm.isdigit() and to.isdigit():
        frm_i, to_i = int(frm), int(to)
        if frm.startswith("0") or to.startswith("0"):
            width = max(len(frm), len(to))
            fmt = lambda n: str(n).zfill(width)  # noqa: E731
        else:
            fmt = str
        step = 1 if frm_i <= to_i else -1
        return [prefix + fmt(n) + suffix for n in range(frm_i, to_i + step, step)]

    if len(frm) == 1 and len(to) == 1 and frm.isalpha() and to.isalpha():
        if frm.isupper() != to.isupper():
            raise ValueError(f"from と to の大文字小文字が一致しません: [{spec}]")
        step = 1 if frm <= to else -1
        return [prefix + chr(c) + suffix for c in range(ord(frm), ord(to) + step, step)]

    raise ValueError(
        f"from/to は数値または単一アルファベット文字で指定してください: [{spec}]"
    )


# ── public API ─────────────────────────────────────────────────────────────

# パッケージ同梱の LaTeX テンプレート/ヘッダ/cover/マクロの正本ディレクトリ。
# template / include-in-header / conditional-process-input などが data-dir・workdir で
# 見つからない場合、basename でここ(正本)にフォールバックする。
_BUILTIN_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def resolve_from_datadir(
    val: str | None,
    data_dir: Path | None,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """*val* を data_dir を優先しつつ解決し、正規化した Path を返す。

    解決順:
    1. 絶対パス — そのまま。
    2. data_dir 直下に存在すれば data_dir 基準。
    3. workdir / yaml_path.parent 基準に存在すれば それ。
    4. 無ければ パッケージ同梱 templates に basename でフォールバック。
    5. いずれにも無ければ 3 のパスを返す(存在チェックは後段に委ねる)。

    data_dir / workdir 側に同名ファイルを置けば 4 より優先されるため、シリーズ別の
    フォーク(テンプレート差し替え)はそちらに置くだけで上書きできる(cascade)。
    """
    if not val:
        return None
    p = Path(val)
    if p.is_absolute():
        return p.resolve()
    if data_dir is not None:
        candidate = (data_dir / p).resolve()
        if candidate.exists():
            return candidate
    base = workdir if workdir else yaml_path.parent
    local = (base / p).resolve()
    if local.exists():
        return local
    builtin = _BUILTIN_TEMPLATES_DIR / p.name
    if builtin.exists():
        return builtin
    return local


def resolve_condblock_output(
    pandoc_section: dict,
    recipe: dict,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """Resolve conditional-process-output path.

    When conditional-process-output is absent/empty, auto-generates
    outputdir/work_<basename(conditional-process-input)>.
    Returns None when conditional-process-input is not set.
    """
    input_val = pandoc_section.get("conditional-process-input")
    if not input_val:
        return None
    output_val = pandoc_section.get("conditional-process-output")
    base = _base_dir(yaml_path, workdir)
    if output_val:
        p = Path(str(output_val))
        return p if p.is_absolute() else base / p
    out_section = recipe.get("output", {})
    outdir_val = out_section.get("outputdir")
    if outdir_val:
        p = Path(str(outdir_val))
        out_dir = p if p.is_absolute() else base / p
    else:
        out_dir = base
    return out_dir / ("work_" + Path(str(input_val)).name)


def get_targetbasefilename(out_section: dict) -> str | None:
    """Return output.targetbasefilename with extension stripped (warns if extension present)."""
    val = out_section.get("targetbasefilename")
    if not val:
        return None
    val = str(val)
    p = Path(val)
    if p.suffix:
        logging.warning(
            "output.targetbasefilename に拡張子が含まれています。拡張子を除去します: '%s' → '%s'",
            val, p.stem,
        )
        val = p.stem
    return val


# ── YAML special constants ─────────────────────────────────────────────────

_SESSION_CONSTANTS: dict[str, str] | None = None
_CLI_CONSTANTS: dict[str, str] = {}


def _get_yaml_constants() -> dict[str, str]:
    """Return built-in __NAME__ → value mapping (session-cached). Add new entries here."""
    global _SESSION_CONSTANTS
    if _SESSION_CONSTANTS is None:
        now = datetime.datetime.now()
        _SESSION_CONSTANTS = {
            "__DATE__":     now.strftime("%Y-%m-%d"),
            "__TIME__":     now.strftime("%H:%M:%S"),
            "__DATETIME__": now.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    return _SESSION_CONSTANTS


def init_cli_constants(paths: "list[str | Path]") -> None:
    """Load TOML constant files specified via --constants CLI arguments (appends/overrides)."""
    global _CLI_CONSTANTS
    for p in paths:
        filepath = Path(p).resolve()
        try:
            with filepath.open("rb") as f:
                data = tomllib.load(f)
            _CLI_CONSTANTS.update({k: str(v) for k, v in data.items()})
            logging.debug("CLI constants loaded: %s (%d entries)", filepath, len(data))
        except FileNotFoundError:
            logging.error("--constants ファイルが見つかりません: %s", filepath)
        except Exception as e:
            logging.error("--constants ファイルの読み込みエラー: %s: %s", filepath, e)


def _load_constants_files(collected: "list[tuple[Path, str]]") -> dict[str, str]:
    """Load TOML files gathered from !constants directives."""
    result: dict[str, str] = {}
    for base_dir, filename in collected:
        filepath = (base_dir / filename).resolve()
        try:
            with filepath.open("rb") as f:
                data = tomllib.load(f)
            result.update({k: str(v) for k, v in data.items()})
            logging.debug("!constants loaded: %s (%d entries)", filepath, len(data))
        except FileNotFoundError:
            logging.error("!constants ファイルが見つかりません: %s", filepath)
        except Exception as e:
            logging.error("!constants ファイルの読み込みエラー: %s: %s", filepath, e)
    return result


def _apply_yaml_constants(text: str, file_constants: "dict[str, str] | None" = None) -> str:
    """Replace __CONSTANT__ placeholders in preprocessed YAML text.

    Priority (low → high): built-in → --constants CLI → !constants file.
    Constants whose values contain newlines replace the entire line they appear on;
    single-line constants are substituted inline anywhere they occur.
    """
    constants = dict(_get_yaml_constants())
    constants.update(_CLI_CONSTANTS)
    if file_constants:
        constants.update(file_constants)

    inline = {k: v for k, v in constants.items() if '\n' not in v}
    block  = {k: v for k, v in constants.items() if '\n' in v}

    if block:
        result_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            raw = line.rstrip('\r\n')
            handled = False
            for ph, val in block.items():
                stripped = raw.lstrip()
                after = stripped[len(ph):]
                if stripped.startswith(ph) and (not after or after.lstrip().startswith('#')):
                    indent = raw[: len(raw) - len(stripped)]
                    for vl in val.strip('\n').splitlines():
                        result_lines.append(indent + vl + '\n')
                    handled = True
                    break
            if not handled:
                result_lines.append(line)
        text = ''.join(result_lines)

    for ph, val in inline.items():
        text = text.replace(ph, val)

    return text


# ── !include / !constants preprocessing ────────────────────────────────────

_CONSTANTS_RE = re.compile(r'^!constants[ \t]+(\S+?)[ \t]*(?:#.*)?$')
_STANDALONE_INCLUDE_RE = re.compile(r'^(\s*)!include[ \t]+(\S+?)[ \t]*(?:#.*)?$')
_INLINE_INCLUDE_RE = re.compile(r'!include[ \t]+(\S+?)(?=[ \t]*(?:#.*)?$)')


def _comment_start(s: str) -> int:
    """Return the index of the first YAML comment '#' (preceded by whitespace), or len(s)."""
    for i, c in enumerate(s):
        if c == '#' and (i == 0 or s[i - 1] in (' ', '\t')):
            return i
    return len(s)


def _read_yaml_include(filepath: Path) -> str:
    """Read a YAML !include target, logging at debug and raising a clear error if missing."""
    try:
        text = filepath.read_text(encoding='utf-8')
    except FileNotFoundError:
        logging.error("!include ファイルが見つかりません: %s", filepath)
        raise
    logging.debug("!include expanded: %s", filepath)
    return text


def _preprocess_yaml(
    text: str,
    base_dir: Path,
    _seen: frozenset[Path] = frozenset(),
    _constants_collect: "list[tuple[Path, str]] | None" = None,
) -> str:
    """Expand !include and collect !constants directives before YAML parsing."""
    if _constants_collect is None:
        _constants_collect = []
    result: list[str] = []
    for line in text.splitlines(keepends=True):
        raw = line.rstrip('\r\n')

        # Skip comment-only lines
        if raw.lstrip().startswith('#'):
            result.append(line)
            continue

        # !constants directive — record path, remove line from text
        m = _CONSTANTS_RE.match(raw)
        if m:
            _constants_collect.append((base_dir, m.group(1)))
            continue

        # Standalone !include
        m = _STANDALONE_INCLUDE_RE.match(raw)
        if m:
            indent, filename = m.group(1), m.group(2)
            filepath = (base_dir / filename).resolve()
            if filepath in _seen:
                raise ValueError(f"Circular !include: {filepath}")
            inc = _preprocess_yaml(
                _read_yaml_include(filepath),
                filepath.parent, _seen | {filepath},
                _constants_collect,
            )
            for inc_line in inc.splitlines(keepends=True):
                result.append(indent + inc_line)
            if inc and not inc.endswith('\n'):
                result.append('\n')
            continue

        # Inline: search only in the non-comment portion of the line
        m = _INLINE_INCLUDE_RE.search(raw[:_comment_start(raw)])
        if m:
            filename = m.group(1)
            filepath = (base_dir / filename).resolve()
            if filepath in _seen:
                raise ValueError(f"Circular !include: {filepath}")
            inc = _preprocess_yaml(
                _read_yaml_include(filepath),
                filepath.parent, _seen | {filepath},
                _constants_collect,
            ).rstrip('\n')
            before = raw[:m.start()]
            line_indent = ' ' * (len(raw) - len(raw.lstrip()))
            if '\n' in inc:
                inner = line_indent + '  '
                indented = '\n'.join(inner + l for l in inc.splitlines())
                result.append(before.rstrip() + '\n' + indented + '\n')
            else:
                result.append(before + inc + '\n')
            continue

        result.append(line)
    return ''.join(result)


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that emits a warning on duplicate mapping keys."""
    def construct_mapping(self, node, deep=False):
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=False)
            if key in seen:
                logging.warning(
                    "YAML 重複キー: %r (行 %d) — 後の定義で上書きされます",
                    key, key_node.start_mark.line + 1,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


# ── _include / _constants (plain-YAML keys) ────────────────────────────────

INCLUDE_KEY = "_include"
CONSTANTS_KEY = "_constants"

_CONSTANTS_KEY_RE = re.compile(r'^_constants[ \t]*:')


def _has_legacy_directives(text: str) -> bool:
    """旧書式（行頭/値位置の ``!include`` / ``!constants``）を含むか。"""
    for line in text.splitlines():
        raw = line.rstrip('\r\n')
        if raw.lstrip().startswith('#'):
            continue
        body = raw[:_comment_start(raw)]
        if (_CONSTANTS_RE.match(raw) or _STANDALONE_INCLUDE_RE.match(raw)
                or _INLINE_INCLUDE_RE.search(body)):
            return True
    return False


def _extract_constants_key(text: str) -> list[str]:
    """トップレベルの ``_constants:`` を、定数置換より前に取り出す。

    定数（複数行の値は行ごと置換される）を当てる前の本文は YAML として
    読めるとは限らないので、``_constants:`` のブロックだけを切り出して読む。
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not _CONSTANTS_KEY_RE.match(line):
            continue
        block = [line]
        for nxt in lines[i + 1:]:
            if nxt.strip() == '' or nxt[:1] in (' ', '\t', '-') or nxt.lstrip().startswith('#'):
                block.append(nxt)
                continue
            break
        val = yaml.safe_load('\n'.join(block)).get(CONSTANTS_KEY)
        if val is None:
            return []
        if isinstance(val, str):
            return [val]
        if isinstance(val, list) and all(isinstance(v, str) for v in val):
            return val
        raise ValueError(f"{CONSTANTS_KEY} はパス文字列かそのリストで指定してください: {val!r}")
    return []


def _include_list(val, where: Path) -> list[str]:
    if isinstance(val, str):
        return [val]
    if isinstance(val, list) and all(isinstance(v, str) for v in val):
        return val
    raise ValueError(f"{INCLUDE_KEY} はパス文字列かそのリストで指定してください: {val!r} ({where})")


def _merge_included(parts: list, siblings: dict, where: Path):
    """``_include`` で読んだ内容 *parts* と同じ階層の兄弟キー *siblings* を合成する。

    マッピング同士は浅くマージし、後に読んだもの・兄弟キーが勝つ。
    兄弟キーが無ければ、リスト同士は連結、単独の値はそのまま置き換える。
    """
    if all(isinstance(p, dict) for p in parts):
        merged: dict = {}
        for p in parts:
            merged.update(p)
        merged.update(siblings)
        return merged
    if siblings:
        raise ValueError(f"{INCLUDE_KEY} の読み込み先がマッピングでないため、兄弟キーと併用できません ({where})")
    if all(isinstance(p, list) for p in parts):
        return [x for p in parts for x in p]
    if len(parts) == 1:
        return parts[0]
    raise ValueError(f"{INCLUDE_KEY} で複数のファイルを読む場合は、すべてマッピングかすべてリストにしてください ({where})")


def _resolve_includes(node, base_dir: Path, seen: frozenset[Path], constants: dict[str, str]):
    if isinstance(node, list):
        return [_resolve_includes(v, base_dir, seen, constants) for v in node]
    if not isinstance(node, dict):
        return node
    resolved = {k: _resolve_includes(v, base_dir, seen, constants)
                for k, v in node.items() if k != INCLUDE_KEY}
    if INCLUDE_KEY not in node:
        return resolved
    where = base_dir
    parts = []
    for ref in _include_list(node[INCLUDE_KEY], where):
        filepath = (base_dir / ref).resolve()
        if filepath in seen:
            raise ValueError(f"Circular {INCLUDE_KEY}: {filepath}")
        parts.append(_load_yaml_file(filepath, seen | {filepath}, constants, label=INCLUDE_KEY))
    return _merge_included(parts, resolved, where)


def _load_yaml_doc(
    text: str,
    base_dir: Path,
    seen: frozenset[Path] = frozenset(),
    inherited_constants: "dict[str, str] | None" = None,
    source: "Path | None" = None,
):
    """YAML 本文を読み、``_include`` / ``_constants``（と旧書式）を解決したデータを返す。

    定数の有効範囲は、そのファイルと、そこから ``_include`` で読むファイル。
    """
    if _has_legacy_directives(text):
        logging.warning(
            "!include / !constants は非推奨です。%s: / %s: キーに書き換えてください: %s",
            INCLUDE_KEY, CONSTANTS_KEY, source or base_dir,
        )
    constants_collect: list[tuple[Path, str]] = []
    text = _preprocess_yaml(text, base_dir, seen, _constants_collect=constants_collect)
    constants_collect += [(base_dir, ref) for ref in _extract_constants_key(text)]
    constants = dict(inherited_constants or {})
    constants.update(_load_constants_files(constants_collect))
    data = yaml.load(_apply_yaml_constants(text, constants), Loader=_DuplicateKeyLoader)
    if isinstance(data, dict):
        data.pop(CONSTANTS_KEY, None)
    return _resolve_includes(data, base_dir, seen, constants)


def _load_yaml_file(filepath: Path, seen: frozenset[Path], constants: dict[str, str], label: str):
    try:
        text = filepath.read_text(encoding='utf-8')
    except FileNotFoundError:
        logging.error("%s ファイルが見つかりません: %s", label, filepath)
        raise
    logging.debug("%s expanded: %s", label, filepath)
    return _load_yaml_doc(text, filepath.parent, seen, constants, source=filepath)


def load_yaml_text(text: str, base_dir: Path):
    """レシピ以外の YAML 本文（ノート YAML など）を、レシピと同じ規則で読む。"""
    return _load_yaml_doc(text, base_dir)


def load_yaml(yaml_path: Path, normalize: bool = True) -> dict:
    """レシピを読み込む。*normalize* が真なら procedure を内部表現（operation 記法）へ正規化する。"""
    path = yaml_path.resolve()
    data = _load_yaml_file(path, frozenset({path}), {}, label="recipe")
    return normalize_recipe(data, yaml_path) if normalize else data


def load_recipe(yaml_path: Path, args: argparse.Namespace) -> dict:
    """load_yaml に加え、procedure から when: 条件を満たさない項目を除く。

    procedure を「実行する」段（merge / pptmerge / preprocess / ドリフトゲート）はこれを使う。
    checkgen / checkverify / validate は全項目が対象なので load_yaml のまま。
    """
    return filter_procedure(load_yaml(yaml_path), args)


def resolve_input_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "input", None)
    return Path(raw).resolve() if raw else None


def _find_in_dirs(fname: str, in_dirs: list[Path]) -> Path | None:
    """Search *in_dirs* for *fname*; warn and return first if found in multiple."""
    found_dirs = [d for d in in_dirs if (d / fname).exists()]
    if not found_dirs:
        return None
    found = [(d / fname).resolve() for d in found_dirs]
    unique = list(dict.fromkeys(found))
    if len(unique) > 1:
        logging.warning(
            "insertmd: '%s' が複数のディレクトリに存在します。最初に見つかったものを使用します: %s\n  発見: %s",
            fname, found[0], ", ".join(str(d) for d in found_dirs),
        )
    return found[0]


def iter_insertmd_entries(
    recipe: dict, in_dirs: list[Path], yaml_path: Path
) -> list[tuple[str, Path]]:
    """Return ``(mdfilename, resolved_path)`` for each insertmd file (deduped, in order).

    Resolution mirrors :func:`collect_procedure_items` (range expansion + input.dirs
    search). Used by ``checkgen`` (fingerprint generation) and merge-time verification.
    """
    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for item in recipe.get("procedure", []):
        if item.get("operation") != "insertmd":
            continue
        val = item.get("mdfilename")
        if not val:
            continue
        try:
            filenames = _expand_mdfilename(val)
        except ValueError:
            continue
        for fname in filenames:
            if fname in seen:
                continue
            seen.add(fname)
            p = Path(fname)
            if p.is_absolute():
                resolved = p
            elif in_dirs:
                found = _find_in_dirs(fname, in_dirs)
                resolved = found if found is not None else (in_dirs[0] / fname).resolve()
            else:
                resolved = yaml_path.parent / p
            result.append((fname, resolved))
    return result


def iter_insertpptx_entries(recipe: dict, input_dirs: list[Path]) -> list[tuple[str, Path]]:
    """Return ``(pptxfilename, resolved_path)`` for each insertpptx entry (deduped, in order).

    Resolution uses pptmerge's input.dirs search (resolve_file_in_dirs). Used by
    ``checkgen`` and ``pptmerge``-time verification of the insertpptx fingerprint.
    """
    from md_merge.pptmerge._config import resolve_file_in_dirs  # lazy — avoid import cycle

    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for item in recipe.get("procedure", []):
        if item.get("operation", "insertpptx") != "insertpptx":
            continue
        fname = item.get("pptxfilename")
        if not fname:
            continue
        fname = str(fname)
        if fname in seen:
            continue
        seen.add(fname)
        result.append((fname, resolve_file_in_dirs(fname, input_dirs)))
    return result


# insertvspace の lines に単位付き長さ（5mm / 1.5cm / .5em 等）を許可するための判定。
_VSPACE_UNIT_RE = re.compile(r"^[0-9]*\.?[0-9]+[a-zA-Z]+$")

# chapter/section/subsection operation の id キー: PART:LOCAL 形式（各部は空・コロン・波括弧・
# 空白を含まない）。{{#id:TYPE:PART:LOCAL}} の PART/LOCAL に埋め込む。
_CHAPTER_ID_RE = re.compile(r"^[^:{}\s]+:[^:{}\s]+$")


def _normalize_vspace_arg(raw: object) -> str:
    """insertvspace の ``lines`` をリーフ引数へ正規化する。

    単位付き長さ（``"5mm"`` 等）はそのまま返す。数値は baselineskip 単位の倍として
    そのまま渡す（整数は ``2``、小数は ``0.5`` 表記）。不正値は警告して ``1``。
    """
    if isinstance(raw, str) and _VSPACE_UNIT_RE.match(raw.strip()):
        return raw.strip()
    try:
        n = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logging.warning("insertvspace: 'lines' が数値でも単位付き長さでもありません: %r — 1 を使用します", raw)
        n = 1.0
    if n < 0:
        logging.warning("insertvspace: 'lines' が負の値です: %r — 1 を使用します", raw)
        n = 1.0
    return str(int(n)) if n == int(n) else repr(n)


def collect_procedure_items(recipe: dict, in_dirs: list[Path], yaml_path: Path) -> list[Path | str]:
    items: list[Path | str] = []
    auto_id_counter = 0
    for item in recipe.get("procedure", []):
        op = item.get("operation")
        if op == "insertmd":
            val = item.get("mdfilename")
            if not val:
                logging.warning("insertmd entry missing 'mdfilename' field — skipping")
                continue
            try:
                filenames = _expand_mdfilename(val)
            except ValueError as e:
                logging.warning("insertmd mdfilename range error: %s — skipping", e)
                continue
            for fname in filenames:
                p = Path(fname)
                logging.debug("collect_procedure_items: %s", p)
                if p.is_absolute():
                    items.append(p)
                elif in_dirs:
                    found = _find_in_dirs(fname, in_dirs)
                    items.append(found if found is not None else (in_dirs[0] / fname).resolve())
                else:
                    items.append(yaml_path.parent / p)
        elif op in ("chapter", "section", "subsection"):
            value = str(item.get(op, "")).strip("\"'")
            title = item.get("title") or ""
            hashes = {"chapter": "#", "section": "##", "subsection": "###"}[op]
            # id: PART:LOCAL を指定すると {{#id:TYPE:PART:LOCAL}} を生成（安定参照用）。
            # 省略・不正時は従来どおり AUTOCHAPTER:AUTOID_<連番> に自動採番する。
            id_val = str(item.get("id") or "").strip()
            if id_val and _CHAPTER_ID_RE.match(id_val):
                id_part = id_val
            else:
                if id_val:
                    logging.warning(
                        "%s.id が PART:LOCAL 形式ではありません: %r — 自動採番にフォールバックします",
                        op, id_val,
                    )
                auto_id_counter += 1
                id_part = f"AUTOCHAPTER:AUTOID_{auto_id_counter}"
            items.append(
                f"<!-- md_merge {{{{{op}:{value}}}}} {{{{title:{title}}}}} -->\n"
                f"{{{{#id:{op}:{id_part}}}}}\n"
                f"{hashes} {title}"
            )
        elif op == "insertvspace":
            # semantic リーフ記法 {{vspace:N}} を独立段落として挿入する。
            # lines は baselineskip 単位の数値（整数/小数、省略時 1）、または
            # 単位付き長さ（例 "5mm" / "1.5cm"）。単位付きはそのまま渡す。
            items.append(f"{{{{vspace:{_normalize_vspace_arg(item.get('lines', 1))}}}}}")
        elif op == "insertpagebreak":
            items.append("{{pagebreak}}")
        elif op == "insertvfill":
            items.append("{{vfill}}")
    return items


def expand_md(
    path: Path,
    chain: frozenset[Path] = frozenset(),
    strict: bool = False,
    yaml_dir: Path | None = None,
    image_copier=None,
    file_log: "list[Path] | None" = None,
) -> str:
    """Read *path* and recursively expand any ``!include`` directives.

    *chain* holds the resolved paths of all ancestors in the current call
    stack.  The same file may appear in sibling branches (parallel includes),
    but appearing in *chain* means a circular dependency.

    Each expanded file is preceded by an HTML comment recording its path
    relative to *yaml_dir* (falls back to absolute when outside *yaml_dir*).

    If *image_copier* is provided, local image references on each line are
    copied to the output directory and their paths rewritten.

    If *file_log* is provided, the resolved path of every expanded file
    (including recursively included ones) is appended to it in processing order.
    The same file is recorded each time it appears (duplicates allowed).
    """
    path = path.resolve()
    new_chain = chain | {path}

    if file_log is not None:
        file_log.append(path)

    try:
        display = path.relative_to(yaml_dir).as_posix() if yaml_dir else path.as_posix()
    except ValueError:
        display = path.as_posix()

    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    parts: list[str] = [f"<!-- source: {display} -->\n"]
    # frontmatter の範囲判定は _imagerefs に集約（先頭の `<!-- source: -->` /
    # `<!-- md_merge_rawtitle: -->` コメントと空行は開始 `---` の前に来うる）。
    fm_tracker = FrontmatterTracker()
    for line in lines:
        in_frontmatter = fm_tracker.feed(line)
        m = _INCLUDE_RE.match(line)
        if not m:
            if image_copier is not None:
                line = image_copier.rewrite_line(line, path, in_frontmatter=in_frontmatter)
            parts.append(line)
            continue
        ref_path = _resolve_include_ref(path, m.group(1))
        if ref_path in new_chain:
            raise CircularIncludeError(ref_path, new_chain)
        if not ref_path.exists():
            if strict:
                raise IncludeNotFoundError(ref_path)
            logging.warning("Include target not found: %s — skipping", ref_path)
            continue
        parts.append(expand_md(
            ref_path, new_chain,
            strict=strict, yaml_dir=yaml_dir,
            image_copier=image_copier, file_log=file_log,
        ))
    return "".join(parts)


def resolve_workdir(recipe: dict, yaml_path: Path, cli_workdir: Path | None) -> Path | None:
    """Return effective workdir: CLI arg > recipe 'workdir' key > None (yaml parent is default)."""
    if cli_workdir is not None:
        return cli_workdir
    val = recipe.get("workdir")
    if val:
        p = Path(str(val))
        return p.resolve() if p.is_absolute() else (yaml_path.parent / p).resolve()
    return None


def resolve_out_file(
    recipe: dict,
    filename_key: str,
    yaml_path: Path,
    workdir: Path | None,
) -> Path | None:
    """Resolve output.<filename_key> under output.outputdir from *recipe*.

    When the key is absent/empty and output.targetbasefilename is set,
    the filename is auto-generated from targetbasefilename.
    Returns None when neither the key nor targetbasefilename is set.
    """
    out_section = recipe.get("output", {})
    filename = out_section.get(filename_key)
    if not filename:
        base_name = get_targetbasefilename(out_section)
        if base_name and filename_key in _AUTO_FILENAMES:
            filename = _AUTO_FILENAMES[filename_key].format(base=base_name)
        else:
            return None
    base = _base_dir(yaml_path, workdir)
    outdir_val = out_section.get("outputdir")
    out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else base / outdir_val) if outdir_val else base
    return out_dir / filename


def setup_recipe_file_logging(recipe: dict, yaml_path: Path, workdir: Path | None) -> None:
    """Add a FileHandler to the root logger when log.filename is set in recipe.

    Directory resolution: log.dir > output.outputdir > base.
    Level: log.level from recipe, else the root logger's current level.
    Already-attached handlers for the same file are not duplicated (safe for pipelines).
    """
    log_cfg = recipe.get("log") or {}
    filename = log_cfg.get("filename")
    if not filename:
        return

    base = _base_dir(yaml_path, workdir)
    log_dir_val = log_cfg.get("dir")
    if log_dir_val:
        p = Path(str(log_dir_val))
        log_dir = p if p.is_absolute() else (base / p).resolve()
    else:
        out_section = recipe.get("output") or {}
        outdir_val = out_section.get("outputdir")
        if outdir_val:
            p = Path(str(outdir_val))
            log_dir = p if p.is_absolute() else (base / p).resolve()
        else:
            log_dir = base

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / str(filename)).resolve()

    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == log_path:
            return  # already attached (pipeline re-entry guard)

    level_val = log_cfg.get("level")
    file_level = getattr(logging, str(level_val).upper(), logging.INFO) if level_val else (root.level or logging.INFO)

    # If file level is more verbose than root logger, lower root logger's level
    # and pin existing StreamHandlers to the current level so console output
    # is not affected.
    if file_level < root.level:
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                if h.level == logging.NOTSET:
                    h.setLevel(root.level)
        root.setLevel(file_level)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(file_level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    root.addHandler(handler)
    logging.debug("log file: %s", log_path)


def apply_recipe_force(args: argparse.Namespace, recipe: dict) -> None:
    """Apply output.force from recipe when --force was not passed on the CLI."""
    if not getattr(args, "force", False):
        args.force = bool((recipe.get("output") or {}).get("force", False))


def resolve_input_dirs(recipe: dict, yaml_path: Path, workdir: Path | None) -> list[Path]:
    """Return the unified input file search path list from input.dirs.

    Relative paths (including '.') are resolved relative to the YAML file's directory.
    input.mddir / input.pptxdir are accepted but deprecated: a recommendation
    is logged and their entries are appended after input.dirs entries.
    Falls back to [workdir or yaml_path.parent] when nothing is specified.
    """
    section = recipe.get("input", {})
    yaml_dir = yaml_path.parent
    base = _base_dir(yaml_path, workdir)
    result: list[Path] = []

    dirs_val = section.get("dirs")
    if dirs_val is None:
        logging.warning(
            "input.dirs が指定されていません。input.dirs の指定を推奨します。"
        )
    else:
        entries = dirs_val if isinstance(dirs_val, list) else [dirs_val]
        for entry in entries:
            p = Path(str(entry))
            result.append((yaml_dir / p).resolve() if not p.is_absolute() else p.resolve())
        if not entries or str(entries[0]).strip() != ".":
            logging.warning(
                "input.dirs の先頭に '.' がありません。"
                "通常は先頭に '.' (recipe YAML のあるディレクトリ) を指定します。"
            )

    mddir_val = section.get("mddir")
    if mddir_val:
        logging.warning(
            "input.mddir は非推奨です。input.dirs の使用を推奨します。"
            "mddir の内容を dirs の末尾に追加します。"
        )
        for entry in (mddir_val if isinstance(mddir_val, list) else [mddir_val]):
            p = Path(str(entry))
            result.append(p if p.is_absolute() else (base / p).resolve())

    pptxdir_val = section.get("pptxdir")
    if pptxdir_val:
        logging.warning(
            "input.pptxdir は非推奨です。input.dirs の使用を推奨します。"
            "pptxdir の内容を dirs の末尾に追加します。"
        )
        for entry in (pptxdir_val if isinstance(pptxdir_val, list) else [pptxdir_val]):
            p = Path(str(entry))
            result.append(p if p.is_absolute() else (base / p).resolve())

    if not result:
        result = [base]
    return result


def resolve_output_path(
    recipe: dict,
    yaml_path: Path,
    workdir: Path | None,
) -> Path:
    out_section = recipe.get("output", {})
    base = _base_dir(yaml_path, workdir)

    outdir_val = out_section.get("outputdir")
    out_dir = (Path(outdir_val) if Path(outdir_val).is_absolute() else base / outdir_val) if outdir_val else base

    filename = out_section.get("mdfilename")
    if not filename:
        base_name = get_targetbasefilename(out_section)
        filename = _AUTO_FILENAMES["mdfilename"].format(base=base_name) if base_name else (yaml_path.stem + "_merge.md")
    return out_dir / filename


# ── internal helpers ───────────────────────────────────────────────────────


def _resolve_include_ref(current_file: Path, ref: str) -> Path:
    p = Path(ref)
    return p.resolve() if p.is_absolute() else (current_file.parent / p).resolve()


def _base_dir(yaml_path: Path, workdir: Path | None) -> Path:
    return workdir if workdir else yaml_path.parent
