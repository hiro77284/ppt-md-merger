import argparse
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from md_merge._cover_images import body_image_targets, copy_cover_images, cover_image_settings
from md_merge._filters import strip_frontmatter
from md_merge._imagerefs import join_image_attributes
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, emit, setup_logging
from md_merge._condblock import process_conditionals as _process_conditionals
from md_merge._pdf_metadata import collect_metadata, document_properties, typst_document_code
from md_merge._pandoc_keys import deprecated_keys_warning, pandoc_key_errors, pdf_defaults_key, removed_latex_keys_warning, uses_plain_keys
from md_merge._procedure import ProcedureNotationError, recipe_version
from md_merge._typst_cover import select_typst_cover
from md_merge.merge._recipe import apply_recipe_force, load_yaml, resolve_from_datadir, resolve_input_path, resolve_out_file, resolve_workdir, setup_recipe_file_logging

# Built-in Lua filters shipped with this package
_BUILTIN_FILTERS_DIR = Path(__file__).parent.parent / "filters"

# cover-md 変換で適用するセマンティック lua フィルタ（本文と同じ lowering を表紙にも効かせる）。
# pandoc-crossref 等の外部フィルタは表紙では不要なので含めない。存在するものだけ使う。
_COVER_SEMANTIC_FILTERS = [
    "semantic-spans.lua",
    "semantic-leaf.lua",
    "semantic-break.lua",
    "center.lua",
    "divboxes.lua",
    "blockindent.lua",
    "largefontblock.lua",
    "keep-together.lua",
]

# PDF は pandoc で .typ を書き出し typst compile で PDF にする 2 段構成。lualatex の経路は
# 撤去した（docs/design_typst_migration.md Phase 7）。pandoc.engine は typst 以外をエラーにする。

# PDF で defaults（version 3 以前は typstdefaults）を省略したときに使う同梱 defaults（templates/ にある）。
_TYPST_DEFAULT_DEFAULTS = "report_base_defaults.yaml"

# PDF（typst）で常に適用する同梱フィルタ（画像を resource-path から探して .typ 相対にする）。
_TYPST_IMAGES_FILTER = "typst-images.lua"

# 同梱テンプレート（表紙を名前だけ書いたときのフォールバック先など）。
_BUILTIN_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _warn_latex_defaults_ignored(pandoc_section: dict) -> bool:
    """PDF（typst）で typstdefaults が無く、LaTeX 用の defaults だけがあるときに警告する。

    typst では pandoc.defaults（LaTeX 用）を読まないため、そこに書いた toc-depth などは
    黙って効かず、同梱 report_base_defaults.yaml（toc-depth: 3）が使われてしまう。
    警告したら True を返す。
    """
    if pandoc_section.get("typstdefaults") or not pandoc_section.get("defaults"):
        return False
    logging.warning(
        "PDF（typst）では pandoc.defaults（LaTeX 用）を読みません。同梱の %s を使います"
        "（toc-depth: 3 など）。typst 用の設定は pandoc.typstdefaults（version 4 では pandoc.defaults）に書いてください。"
        "例: typstdefaults: [%s, <上書き用 defaults>]（後勝ち）",
        _TYPST_DEFAULT_DEFAULTS, _TYPST_DEFAULT_DEFAULTS,
    )
    return True


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

    pandoc_section = recipe.get("pandoc", {})

    try:
        version = recipe_version(recipe)
    except ProcedureNotationError:
        version = 1
    _key_errors = pandoc_key_errors(pandoc_section, version)
    if _key_errors:
        for _msg in _key_errors:
            logging.error("%s", _msg)
        return EXIT_BAD_INPUT
    _deprecated = deprecated_keys_warning(pandoc_section, version)
    if _deprecated:
        logging.warning("%s", _deprecated)

    typst_mode = False
    if getattr(args, "html", False):
        out_key = "htmlfilename"
        pandoc_format = "html"
        defaults_key = "htmldefaults"
        simple_mode = True
    elif getattr(args, "reveal", False):
        out_key = "revealfilename"
        pandoc_format = "revealjs"
        defaults_key = "revealdefaults"
        simple_mode = True
    else:
        out_key = "pdffilename"
        pandoc_format = "typst"
        defaults_key = pdf_defaults_key(version)
        simple_mode = False
        typst_mode = True

    rendered_path = resolve_out_file(recipe, "renderedfilename", yaml_path, workdir)
    if rendered_path is None:
        logging.error("output.renderedfilename is not specified in %s", yaml_path)
        return EXIT_BAD_INPUT

    pdf_path = resolve_out_file(recipe, out_key, yaml_path, workdir)
    if pdf_path is None:
        logging.error("output.%s is not specified in %s", out_key, yaml_path)
        return EXIT_BAD_INPUT
    typ_path: Path | None = None
    if typst_mode:
        # 中間の .typ は PDF と同じ場所・同じ名前で残す（typst compile のエラー位置はこのファイルの行番号）。
        typ_path = pdf_path.with_suffix(".typ")

    # Resolve data-dir first — used as base for defaults / template / include-in-header
    data_dir: Path | None = None
    _data_dir_val = pandoc_section.get("data-dir")
    if _data_dir_val:
        _p = _resolve_path(_data_dir_val, yaml_path, workdir)
        if _p is not None:
            data_dir = _p.resolve()

    # defaults / htmldefaults / revealdefaults: 単一ファイル または ファイルのリスト。
    # リストの場合は複数の -d として順に pandoc へ渡す（後勝ちでマージ。共有ベース＋
    # 文書ごとの上書きに分割する用途）。各要素を data-dir 基準で解決する。
    _defaults_val = pandoc_section.get(defaults_key)
    _defaults_items = _defaults_val if isinstance(_defaults_val, list) else ([_defaults_val] if _defaults_val else [])
    if typst_mode and not _defaults_items:
        if not uses_plain_keys(version):
            _warn_latex_defaults_ignored(pandoc_section)
        _defaults_items = [_TYPST_DEFAULT_DEFAULTS]
    defaults_paths: list[Path] = []
    for _dv in _defaults_items:
        _dp = resolve_from_datadir(_dv, data_dir, yaml_path, workdir)
        if _dp is not None:
            defaults_paths.append(_dp)

    filter_paths, missing = _resolve_filters(
        pandoc_section.get("filters") or [], yaml_path, workdir
    )

    # metadata-file: resolved from workdir (not data-dir)。version 3 以前だけ（version 4 で廃止）
    # template / include-in-header は defaults ファイル側に書く（_rewrite_defaults_paths が解決）
    # data-dir: already resolved above, appended last with canonical path
    path_opts: list[tuple[str, Path]] = []
    _metadata = _resolve_path(pandoc_section.get("metadata-file"), yaml_path, workdir)
    if _metadata is not None:
        path_opts.append(("metadata-file", _metadata.resolve()))
    if data_dir is not None:
        path_opts.append(("data-dir", data_dir))

    highlight_style = pandoc_section.get("syntax-highlighting") or None

    # 本文前に挿入する表紙。HTML/reveal は pandoc.htmlcover（変数置換した HTML）、
    # PDF は cover-md（version 3 以前は typst-cover-md。下で typst 断片に変換）。
    include_before_body: list[Path] = []
    if simple_mode:
        _htmlcover = pandoc_section.get("htmlcover")
        if _htmlcover and not args.dry_run:
            _cover_src = resolve_from_datadir(_htmlcover, data_dir, yaml_path, workdir)
            if _cover_src is not None and _cover_src.exists():
                _cover_out = _render_html_cover(_cover_src, recipe.get("vars") or {}, pdf_path.parent)
                if _cover_out is not None:
                    include_before_body = [_cover_out]
            else:
                logging.warning("pandoc.htmlcover が見つかりません: %s", _htmlcover)
    if typst_mode:
        _latex_warn = removed_latex_keys_warning(pandoc_section, version)
        if _latex_warn:
            logging.warning("%s", _latex_warn)

    # resource-path: semicolon-separated string or YAML list。typst-images.lua が画像を探す。
    # HTML では使わない。
    if simple_mode:
        resource_paths = []
    else:
        resource_paths = _resolve_resource_paths(pandoc_section.get("resource-path"), yaml_path, None)

    # PDF（typst）の表紙は cover-md（version 3 は typst-cover-md。どちらも明示したときだけ）。
    # version 2 以前は、省略時に LaTeX 用の表紙があれば同梱の標準表紙を暗黙に使う（_typst_cover.py）。
    # HTML/reveal では、version 3 以前だけ cover-md（LaTeX 用の Markdown 表紙）も HTML に変換する。
    # version 4 の cover-md は PDF 専用（中身が typst の生コードなので HTML では崩れる）。
    _cover_md = None if uses_plain_keys(version) else pandoc_section.get("cover-md")
    if typst_mode:
        _cover_md, _builtin, _cover_warn = select_typst_cover(pandoc_section, version)
        if _cover_warn:
            logging.warning("%s", _cover_warn)
        if _cover_md and _builtin:
            _cover_md = str(_BUILTIN_TEMPLATES_DIR / _cover_md)
    if _cover_md and not args.dry_run:
        _cover_frag = _build_cover_from_md(
            _cover_md, recipe.get("vars") or {}, yaml_path, workdir,
            pdf_path.parent, pandoc_format, simple_mode, resource_paths,
            cover_image_opts=_cover_image_opts(recipe, yaml_path, workdir, rendered_path),
        )
        if _cover_frag is None:
            return EXIT_FAILURE
        include_before_body = [_cover_frag] + include_before_body

    # typst --root: 画像などを読めるのはこの下だけ。指定が無ければ .typ の場所・render 済み MD の
    # 場所・resource-path をすべて含む共通の上位ディレクトリにする。
    typst_root: Path | None = None
    if typst_mode:
        typst_root = _resolve_path(pandoc_section.get("typst-root"), yaml_path, workdir)
        if typst_root is None:
            try:
                typst_root = Path(os.path.commonpath(
                    [str(p.resolve()) for p in (pdf_path.parent, rendered_path.parent, *resource_paths)]
                ))
            except ValueError:
                logging.error("typst の --root を決められません（ドライブが異なる）。pandoc.typst-root を指定してください")
                return EXIT_BAD_INPUT

    logging.debug("yaml     : %s", yaml_path)
    logging.debug("rendered : %s", rendered_path)
    logging.debug("output   : %s", pdf_path)
    if typst_mode:
        logging.debug("typ      : %s", typ_path)
        logging.debug("typst-root: %s", typst_root)
    for _dp in defaults_paths:
        logging.debug("defaults : %s", _dp)
    logging.debug("filters  : %s", filter_paths)
    for key, p in path_opts:
        logging.debug("%-16s: %s", key, p)
    if highlight_style:
        logging.debug("syntax-highlighting : %s", highlight_style)
    if include_before_body:
        logging.debug("include-before-body: %s", include_before_body)
    if resource_paths:
        logging.debug("resource-path   : %s", resource_paths)

    if args.dry_run:
        emit(args, "ok", "pandoc", yaml_path, pdf_path, dry_run=True)
        return EXIT_OK

    if not rendered_path.exists():
        logging.error("Rendered MD not found: %s", rendered_path)
        return EXIT_NOT_FOUND

    for _dp in defaults_paths:
        if not _dp.exists():
            logging.error("Pandoc defaults file not found: %s", _dp)
            return EXIT_NOT_FOUND

    for key, p in path_opts:
        if not p.exists():
            logging.error("Pandoc option --%s file not found: %s", key, p)
            return EXIT_NOT_FOUND

    for p in include_before_body:
        if not p.exists():
            logging.error("Pandoc option --include-before-body file not found: %s", p)
            return EXIT_NOT_FOUND

    for p in resource_paths:
        if not p.exists():
            logging.error("resource-path directory not found: %s", p)
            return EXIT_NOT_FOUND

    if missing:
        for name in missing:
            logging.error("Filter not found: %s", name)
        return EXIT_NOT_FOUND

    if pdf_path.exists() and not getattr(args, "force", False):
        logging.error("Output file already exists (use --force to overwrite): %s", pdf_path)
        return EXIT_FAILURE

    if shutil.which("pandoc") is None:
        logging.error("pandoc not found on PATH")
        return EXIT_FAILURE
    if typst_mode and shutil.which("typst") is None:
        logging.error("typst not found on PATH（PDF 出力に必要）")
        return EXIT_FAILURE

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # defaults ファイルの filters / include-in-header / template を tool 側で解決
    # （bare 名→パッケージ同梱）。解決済みパスに置換した一時 defaults を pandoc に渡す。
    # 複数指定時は各ファイルを個別に一時化し、順に -d で渡す。
    temp_defaults_files: list[Path] = []
    final_defaults: list[Path] = []
    for _dp in defaults_paths:
        rewritten, temp = _rewrite_defaults_paths(_dp, data_dir, yaml_path, workdir)
        final_defaults.append(rewritten)
        if temp is not None:
            temp_defaults_files.append(temp)

    # YAML frontmatter（transfer / notecomexport 用の title・hero 等）は PDF などの本文に出さない。
    # merge 後は frontmatter の直前に <!-- source: --> 等のコメントが来るため pandoc は
    # メタデータとして読まず本文に漏らす（2 ファイル目以降は文書の途中に来る）。
    # 取り除いた本文を標準入力で渡す。frontmatter が無ければ従来どおりファイルを渡す。
    rendered_text = rendered_path.read_text(encoding="utf-8-sig")
    stripped_text, fm_count = strip_frontmatter(rendered_text)
    if fm_count:
        logging.info("frontmatter を %d 件取り除いて pandoc に渡します: %s", fm_count, rendered_path)
    # `![](a.png) {width=80%}` のように画像と属性の間に空白があると pandoc は属性と
    # みなさず文字列で出すため、空白を詰めてから渡す（コードブロック内は変えない）。
    stripped_text, attr_count = join_image_attributes(stripped_text)
    if attr_count:
        logging.info("画像参照と属性の間の空白を %d 件詰めて pandoc に渡します: %s", attr_count, rendered_path)
    pandoc_stdin: str | None = None
    if fm_count or attr_count:
        pandoc_stdin = stripped_text
        cmd = ["pandoc", "-o", str(typ_path if typst_mode else pdf_path)]
    else:
        cmd = ["pandoc", str(rendered_path), "-o", str(typ_path if typst_mode else pdf_path)]
    for _dp in final_defaults:
        cmd += ["-d", str(_dp)]
    for fp in filter_paths:
        cmd += ["-L", str(fp)]
    if typst_mode:
        cmd += ["-L", str(_BUILTIN_FILTERS_DIR / _TYPST_IMAGES_FILTER)]
    cmd += ["-t", pandoc_format]
    for key, p in path_opts:
        cmd += [f"--{key}", str(p)]
    if highlight_style:
        cmd += [f"--syntax-highlighting={highlight_style}" ]
    for p in include_before_body:
        cmd += ["--include-before-body", str(p)]
    if typst_mode:
        # PDF の文書プロパティ: COVER_* を流用し、defaults の metadata: で上書き（_pdf_metadata.py）
        _doc_code = typst_document_code(document_properties(
            recipe.get("vars") or {},
            collect_metadata(defaults_paths, _metadata.resolve() if _metadata is not None else None),
        ))
        if _doc_code:
            # -V だと非 UTF-8 ロケールで pandoc が引数の日本語を化かすので、一時 defaults の
            # variables: で渡す（defaults ファイルは常に UTF-8 で読まれる）
            _vars_tmp = _write_document_vars(_doc_code, pdf_path.parent)
            temp_defaults_files.append(_vars_tmp)
            cmd += ["-d", str(_vars_tmp)]

    cmd += ["--resource-path", _resource_path_arg(resource_paths)]

    logging.debug("cmd:\n%s", "\n".join(cmd))
    _orig_cwd = Path.cwd()
    os.chdir(pdf_path.parent)
    try:
        result = subprocess.run(
            cmd, input=pandoc_stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        os.chdir(_orig_cwd)
        for temp in temp_defaults_files:
            try:
                temp.unlink()
            except OSError:
                pass

    if result.stdout:
        logging.info("%s", result.stdout.rstrip())
    if result.stderr:
        (logging.error if result.returncode != 0 else logging.warning)("%s", result.stderr.rstrip())

    if result.returncode != 0:
        logging.error("pandoc exited with code %d", result.returncode)
        return EXIT_FAILURE

    if typst_mode:
        code = _compile_typst(typ_path, pdf_path, typst_root)
        if code != EXIT_OK:
            return code

    emit(args, "ok", "pandoc", yaml_path, pdf_path)
    return EXIT_OK


# ── helpers ────────────────────────────────────────────────────────────────


def _write_document_vars(code: str, out_dir: Path) -> Path:
    """PDF の文書プロパティの typst コードを variables: に持つ一時 defaults を書く。"""
    import tempfile

    fd, name = tempfile.mkstemp(prefix=".sem_document_", suffix=".yaml", dir=str(out_dir))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump({"variables": {"sem-document": code}}, f, allow_unicode=True)
    return Path(name)


def _compile_typst(typ_path: Path, pdf_path: Path, root: Path) -> int:
    """``typst compile`` で .typ を PDF にする。エラー位置は .typ の行番号で出る。"""
    cmd = ["typst", "compile", "--root", str(root), str(typ_path), str(pdf_path)]
    logging.debug("cmd:\n%s", "\n".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        logging.info("%s", result.stdout.rstrip())
    if result.stderr:
        (logging.error if result.returncode != 0 else logging.warning)("%s", result.stderr.rstrip())
    if result.returncode != 0:
        logging.error("typst compile exited with code %d（中間ファイル: %s）", result.returncode, typ_path)
        return EXIT_FAILURE
    return EXIT_OK


def _render_html_cover(cover_src: Path, vars_section: dict, out_dir: Path) -> "Path | None":
    """HTML 表紙テンプレの ``{{v:NAME}}`` をレシピ ``vars`` で置換し cover-processed.html を書き出す。

    未定義の変数は空文字にする（表紙は欠落しても致命ではないため寛容に扱う）。
    戻り値は生成した HTML のパス（失敗時は None）。
    """
    try:
        content = cover_src.read_text(encoding="utf-8")
    except OSError as e:
        logging.warning("htmlcover の読み込みに失敗しました: %s: %s", cover_src, e)
        return None
    content = re.sub(
        r"\{\{v:([A-Za-z0-9_]+)\}\}",
        lambda m: str(vars_section.get(m.group(1), "") or ""),
        content,
    )
    try:
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "cover-processed.html"
        out.write_text(content, encoding="utf-8")
    except OSError as e:
        logging.warning("htmlcover の書き出しに失敗しました: %s", e)
        return None
    logging.debug("htmlcover を生成: %s", out)
    return out


def _build_cover_from_md(
    cover_md_val: str,
    vars_section: dict,
    yaml_path: Path,
    workdir: "Path | None",
    out_dir: Path,
    pandoc_format: str,
    simple_mode: bool,
    resource_paths: "list[Path] | None" = None,
    cover_image_opts: "dict | None" = None,
) -> "Path | None":
    """markdown 表紙を pandoc で typst/html 断片へ変換して返す（失敗時 None）。

    手順: ``{{#if:NAME}}`` … ``{{#endif:NAME}}`` を _condblock の規則で展開
    （値が空のブロックを省く）→ ``{{v:NAME}}`` をレシピ vars で置換（未定義は空文字＝寛容）→ 中間 md を
    書き出し → セマンティック lua フィルタ付きで pandoc により断片（standalone なし）へ
    変換。生成断片は本文前に ``--include-before-body`` で挿入される想定なので、内部で
    参照する画像やマクロは本体 pandoc 実行時の resource-path / プリアンブルで解決される。

    出力形式は PDF なら typst（.typ）、
    HTML/reveal なら該当形式（.html）。typst では画像の参照が本体の .typ と同じ場所からの
    相対になるよう、out_dir を作業ディレクトリにして typst-images.lua と resource-path を渡す。
    """
    p = Path(cover_md_val)
    if p.is_absolute():
        cover_src = p
    else:
        cover_src = yaml_path.parent / p
        if not cover_src.exists() and workdir is not None and (workdir / p).exists():
            cover_src = workdir / p
        # どこにも無ければ同梱 templates に basename でフォールバック（cover_standard.md 等）。
        # 旧名 cover_standard_typst.md は読み替えない（pandoc_key_errors が先にエラーにする）。
        if not cover_src.exists() and (_BUILTIN_TEMPLATES_DIR / p.name).exists():
            cover_src = _BUILTIN_TEMPLATES_DIR / p.name
    if not cover_src.exists():
        logging.error("表紙の Markdown（pandoc.cover-md / typst-cover-md）が見つかりません: %s", cover_src)
        return None
    if shutil.which("pandoc") is None:
        logging.error("pandoc not found on PATH (cover-md の変換に必要)")
        return None
    try:
        content = cover_src.read_text(encoding="utf-8")
    except OSError as e:
        logging.error("cover-md の読み込みに失敗しました: %s: %s", cover_src, e)
        return None

    try:
        content = "".join(_process_conditionals(content.splitlines(keepends=True), vars_section))
    except ValueError as e:
        logging.error("cover-md の条件ブロックが不正です: %s: %s", cover_src, e)
        return None

    # {{v:NAME}} 置換。未定義変数は空文字（表紙は欠落しても致命ではないため寛容）。
    content = re.sub(
        r"\{\{v:([A-Za-z0-9_]+)\}\}",
        lambda m: str(vars_section.get(m.group(1), "") or ""),
        content,
    )

    # 表紙の画像（COVER_IMAGE など）は merge を通らないので、ここでレシピ基準に解決して
    # merge.image-dir にコピーする（merge.copy-images が有効なとき。_cover_images.py）。
    if cover_image_opts is not None:
        try:
            content = copy_cover_images(
                content,
                bases=[*cover_image_opts["bases"], cover_src.parent],
                img_dir=cover_image_opts["img_dir"],
                ref_base=out_dir,
                naming=cover_image_opts["naming"],
                collision=cover_image_opts["collision"],
                taken=cover_image_opts["taken"],
            )
        except OSError as e:
            logging.error("表紙の画像のコピーに失敗しました: %s", e)
            return None

    if simple_mode:
        to_fmt, ext = pandoc_format, ".html"
    else:
        to_fmt, ext = "typst", ".typ"

    try:
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        processed = out_dir / (cover_src.stem + "_cover_processed.md")
        processed.write_text(content, encoding="utf-8")
    except OSError as e:
        logging.error("cover-md の中間ファイル書き出しに失敗しました: %s", e)
        return None

    cover_out = out_dir / (cover_src.stem + "_cover" + ext)

    cmd = ["pandoc", str(processed), "-o", str(cover_out), "-t", to_fmt]
    for name in _COVER_SEMANTIC_FILTERS:
        fp = _BUILTIN_FILTERS_DIR / name
        if fp.exists():
            cmd += ["-L", str(fp)]
    if to_fmt == "typst":
        cmd += ["-L", str(_BUILTIN_FILTERS_DIR / _TYPST_IMAGES_FILTER)]
        cmd += ["--resource-path", _resource_path_arg(resource_paths or [])]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=out_dir)
    if result.stderr:
        (logging.error if result.returncode != 0 else logging.warning)("%s", result.stderr.rstrip())
    if result.returncode != 0:
        logging.error("cover-md の pandoc 変換に失敗しました (exit %d): %s", result.returncode, cover_src)
        return None
    logging.debug("cover-md を生成: %s -> %s", cover_src, cover_out)
    return cover_out


def _cover_image_opts(
    recipe: dict, yaml_path: Path, workdir: "Path | None", rendered_path: Path,
) -> "dict | None":
    """表紙画像のコピー設定（merge.copy-images が無効なら None）。

    コピー先は merge と同じ image-dir（結合済み MD の場所基準）。探す基準はレシピの
    ディレクトリ → workdir（表紙 MD のディレクトリは呼び出し側で足す）。
    """
    copy, image_dir, naming, collision = cover_image_settings(recipe.get("merge"))
    if not copy:
        return None
    md_path = resolve_out_file(recipe, "mdfilename", yaml_path, workdir) or rendered_path
    img_dir = (md_path.parent / image_dir).resolve()
    bases = [yaml_path.parent.resolve()]
    if workdir is not None and workdir.resolve() not in bases:
        bases.append(workdir.resolve())
    return {
        "bases": bases,
        "img_dir": img_dir,
        "naming": naming,
        "collision": collision,
        "taken": body_image_targets(rendered_path, img_dir),
    }


def _resource_path_arg(paths: "list[Path]") -> str:
    """pandoc の --resource-path に渡す値（先頭に "."）を作る。

    pandoc はこの値を OS のパス区切り（Windows は ";"、それ以外は ":"）で分割するため
    os.pathsep で連結する。レシピ側の resource-path 記法（";" 区切り）とは別物。
    """
    return os.pathsep.join([".", *[str(p) for p in paths]])


def _resolve_resource_paths(
    val: "str | list | None",
    yaml_path: Path,
    workdir: Path | None,
) -> list[Path]:
    """Resolve resource-path (semicolon-separated string or YAML list) to a list of Paths."""
    if not val:
        return []
    entries = val if isinstance(val, list) else str(val).split(";")
    result = []
    for entry in entries:
        entry = str(entry).strip()
        if entry:
            p = _resolve_path(entry, yaml_path, workdir)
            if p is not None:
                result.append(p)
    return result


def _resolve_path(val: str | None, yaml_path: Path, workdir: Path | None) -> Path | None:
    if not val:
        return None
    p = Path(val)
    result = p if p.is_absolute() else (workdir if workdir else yaml_path.parent) / p
    if ".." in result.parts:
        return result.resolve()
    return result


# _resolve_from_datadir は merge/_recipe.py の resolve_from_datadir にある。同梱テンプレへの basename フォールバックもそちらに実装。


def _resolve_filters(
    names: list[str],
    yaml_path: Path,
    workdir: Path | None,
) -> tuple[list[Path], list[str]]:
    """Resolve filter names to paths.

    Resolution order per entry:
    1. Absolute path — used as-is.
    2. Relative path resolved against yaml_dir (or workdir) — custom filter.
    3. Name looked up in the built-in filters directory.

    Returns (resolved_paths, missing_names).
    """
    resolved: list[Path] = []
    missing: list[str] = []
    base = workdir if workdir else yaml_path.parent

    for name in names:
        p = Path(name)
        if p.is_absolute():
            if p.exists():
                resolved.append(p)
            else:
                missing.append(name)
            continue

        custom = base / p
        if custom.exists():
            resolved.append(custom)
            continue

        builtin = _BUILTIN_FILTERS_DIR / p.name
        if builtin.exists():
            resolved.append(builtin)
            continue

        missing.append(name)

    return resolved, missing


def _rewrite_defaults_paths(
    defaults_path: Path,
    data_dir: Path | None,
    yaml_path: Path,
    workdir: Path | None,
) -> tuple[Path, Path | None]:
    """defaults ファイルの ``filters`` / ``include-in-header`` / ``template`` を解決する。

    pandoc は defaults ファイル内のこれらをパッケージ同梱にフォールバックできない
    （filters はスラッシュ付き=CWD 相対、bare 名=data-dir/filters のみ／template・
    include-in-header の bare 名も同様に見つけられない）。そこで tool が読み取り、
    filters は ``_resolve_filters``、include-in-header/template は ``resolve_from_datadir``
    （どちらも basename でパッケージ同梱にフォールバック）で解決した絶対パスに置換した
    **一時 defaults** を生成して pandoc に渡す。これにより defaults に ``center.lua`` /
    ``semantic_macros.typ`` 等の bare 名を書けば同梱の正本に解決される。

    解決できないエントリ（``pandoc-crossref`` 等の外部フィルタ、実在しないパス）と並び順は
    そのまま保持する。戻り値: (pandoc に渡す defaults パス, 後始末する一時ファイル or None)。
    """
    try:
        data = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        logging.warning("defaults の読み込み/解析に失敗、パス解決をスキップ: %s: %s", defaults_path, e)
        return defaults_path, None
    if not isinstance(data, dict):
        return defaults_path, None

    changed = False

    # filters: Lua は _resolve_filters(basename→パッケージ)、外部(pandoc-crossref 等)は温存
    if data.get("filters"):
        new_filters: list = []
        for f in data["filters"]:
            name = f if isinstance(f, str) else (f.get("path") if isinstance(f, dict) else None)
            if isinstance(name, str):
                resolved, _missing = _resolve_filters([name], defaults_path, None)
                if resolved:
                    rp = str(resolved[0])
                    if rp != name:
                        changed = True
                    if isinstance(f, str):
                        new_filters.append(rp)
                    else:
                        f = dict(f)
                        f["path"] = rp
                        new_filters.append(f)
                    continue
            new_filters.append(f)
        data["filters"] = new_filters

    # include-in-header: str または list。各要素を resolve_from_datadir で解決（実在時のみ置換）
    iih = data.get("include-in-header")
    if iih:
        items = iih if isinstance(iih, list) else [iih]
        new_iih: list = []
        for v in items:
            if isinstance(v, str):
                r = resolve_from_datadir(v, data_dir, yaml_path, workdir)
                if r is not None and r.exists():
                    if str(r) != v:
                        changed = True
                    new_iih.append(str(r))
                    continue
            new_iih.append(v)
        data["include-in-header"] = new_iih if isinstance(iih, list) else new_iih[0]

    # template: 単一。resolve_from_datadir で解決（実在時のみ置換）
    tmpl = data.get("template")
    if isinstance(tmpl, str):
        r = resolve_from_datadir(tmpl, data_dir, yaml_path, workdir)
        if r is not None and r.exists() and str(r) != tmpl:
            data["template"] = str(r)
            changed = True

    if not changed:
        return defaults_path, None

    tmp = defaults_path.with_name(f".{defaults_path.stem}.__resolved__.yaml")
    try:
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except OSError as e:
        logging.warning("解決済み defaults の一時書き出しに失敗、元の defaults を使用: %s", e)
        return defaults_path, None
    logging.debug("defaults のパス(filters/include-in-header/template)を解決した一時ファイルを使用: %s", tmp)
    return tmp, tmp
