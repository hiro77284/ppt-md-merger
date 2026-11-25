"""validate の変数・条件・マーカーの静的検査（スパゲッティ化の予防）。

レシピだけでなく、procedure の insertmd が参照する MD と source.cropsrc の pptx ノートも
読んで、次を検査する。

- 未定義の変数の参照（when.var / ``{{#if}}`` / ``{{v:}}``）
- ``params:`` で宣言したのにどこからも参照されていない変数
- 宣言された値のどの組み合わせでも結果が変わらない ``when:``（常に適用／常に除外）
- 入れ子が深すぎる ``{{#if}}``（3 段以上）と ``group``（2 段以上）
- 番号マーカー（``{{nolabel}}`` / ``{{noref}}`` / ``{{nonum}}``）の置き場所・組み合わせの誤り
- 同じ ``when:`` を続けて何度も書いている箇所（group にまとめる提案。info）

ファイルが見つからない（まだ生成していない等）ものは飛ばす。
"""

from __future__ import annotations

import itertools
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from md_merge._condblock import _RE_ELSE, _RE_ENDIF, _RE_EXPR, _RE_FENCE, _RE_IF, eval_condition
from md_merge._conditions import WHEN_KEY, _as_list, iter_whens
from md_merge._noref import NOREF_BEGIN, NOREF_BEGIN_RE, NOREF_END, NOREF_END_RE
from md_merge._params import PARAMS_KEY, param_domain
from md_merge._procedure import GROUP_KEY, INHERITED_WHEN_KEY

# 入れ子の警告しきい値（この深さ以上で警告）
IF_DEPTH_LIMIT = 3
GROUP_DEPTH_LIMIT = 2
# 同じ when: がこの回数以上続いたら group を提案する
REPEATED_WHEN_LIMIT = 3
# 常に真／偽の判定で試す組み合わせの上限
_MAX_COMBINATIONS = 512

_VAR_REF_RE = re.compile(r"\{\{v:([A-Za-z0-9_]+)\}\}")
_ID_RE = re.compile(r"\{\{#id:")
_MARKER_RE = re.compile(r"\{\{(nolabel|noref|nonum)\}\}")


@dataclass
class Source:
    """検査対象のテキスト（MD ファイル 1 つ、またはノート 1 枚）。"""
    label: str
    text: str


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


@dataclass
class _Ref:
    name: str
    where: str
    expr: str | None = None  # 条件式（{{v:}} は None）


# ── 対象テキストの収集 ──────────────────────────────────────────────────────


def collect_sources(recipe: dict, yaml_path: Path, workdir: Path | None) -> tuple[list[Source], list[str]]:
    """insertmd の MD と cropsrc pptx のノートを集める。戻り値は (sources, 見つからなかったもの)。"""
    from md_merge._cropsrc import cropsrc_entries, resolve_cropsrc_path
    from md_merge.merge._recipe import iter_insertmd_entries, resolve_input_dirs

    sources: list[Source] = []
    missing: list[str] = []

    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.ERROR)  # fragment.dirs の推奨警告などは validate では出さない
    try:
        in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
        md_entries = iter_insertmd_entries(recipe, in_dirs, yaml_path)
    finally:
        root.setLevel(level)

    for fname, path in md_entries:
        if not path.is_file():
            missing.append(fname)
            continue
        sources.append(Source(fname, path.read_text(encoding="utf-8-sig")))

    # insertvar の値も MD と同じく {{#if}} / {{v:}} / マーカーを検査する
    vars_section = recipe.get("vars") if isinstance(recipe.get("vars"), dict) else {}
    seen_vars: set[str] = set()
    for name in insertvar_names(recipe):
        value = vars_section.get(name)
        if name in seen_vars or not isinstance(value, str):
            continue
        seen_vars.add(name)
        sources.append(Source(f"vars.{name}（insertvar）", value))

    for entry in cropsrc_entries(recipe):
        val = entry.get("pptx") if isinstance(entry, dict) else None
        if not val:
            continue
        path = resolve_cropsrc_path(str(val), yaml_path, workdir)
        if not path.is_file():
            missing.append(str(val))
            continue
        try:
            from pptx import Presentation
            prs = Presentation(str(path))
        except Exception as exc:  # noqa: BLE001 — 読めない pptx は検査対象外
            logging.debug("validate: pptx を開けません: %s: %s", path, exc)
            missing.append(str(val))
            continue
        for idx, slide in enumerate(prs.slides, start=1):
            if slide.has_notes_slide:
                text = slide.notes_slide.notes_text_frame.text
                if text.strip():
                    sources.append(Source(f"{path.name} スライド {idx} のノート", text))
    return sources, missing


def insertvar_names(normalized: dict) -> list[str]:
    """正規化後の procedure にある insertvar の変数名（登場順、重複あり）。"""
    return [
        str(item["varname"])
        for item in normalized.get("procedure") or []
        if isinstance(item, dict) and item.get("operation") == "insertvar" and item.get("varname")
    ]


# ── テキストの走査 ──────────────────────────────────────────────────────────


def _scan_source(src: Source, refs: list[_Ref], result: LintResult) -> None:
    depth = 0
    max_depth = 0
    fence: str | None = None
    noref_where: str | None = None  # 開いている {{noref:begin}} の位置
    for lineno, raw in enumerate(src.text.splitlines(), start=1):
        where = f"{src.label} line {lineno}"
        mf = _RE_FENCE.match(raw)
        if fence is not None:
            if mf and mf.group(1)[0] == fence[0] and len(mf.group(1)) >= len(fence) \
                    and raw.strip() == mf.group(1):
                fence = None
            continue
        if mf:
            fence = mf.group(1)
            continue

        m_if = _RE_IF.match(raw)
        if m_if:
            depth += 1
            if depth >= IF_DEPTH_LIMIT and depth > max_depth:
                result.warnings.append(
                    f"{where}: {{{{#if}}}} の入れ子が {depth} 段です（{IF_DEPTH_LIMIT - 1} 段までを推奨。"
                    "ページ単位の出し分けは procedure の when / group で）"
                )
            max_depth = max(max_depth, depth)
            refs.append(_Ref(m_if.group("name"), where, raw.strip()[len("{{#if:"):-2]))
            continue
        if _RE_ENDIF.match(raw):
            depth = max(0, depth - 1)
            continue
        if _RE_ELSE.match(raw):
            continue

        if NOREF_BEGIN_RE.match(raw):
            if noref_where is not None:
                result.warnings.append(
                    f"{where}: {NOREF_BEGIN} の範囲内で再び {NOREF_BEGIN} があります（入れ子はできません）"
                )
            noref_where = where
            continue
        if NOREF_END_RE.match(raw):
            if noref_where is None:
                result.warnings.append(f"{where}: {NOREF_END} に対応する {NOREF_BEGIN} がありません")
            noref_where = None
            continue

        if noref_where is None:  # 置換抑制範囲内の {{v:}} は置換されないので検査しない
            for m in _VAR_REF_RE.finditer(raw):
                refs.append(_Ref(m.group(1), where))

        markers = set(_MARKER_RE.findall(raw))
        if markers and not _ID_RE.search(raw):
            names = ", ".join(f"{{{{{m}}}}}" for m in sorted(markers))
            result.warnings.append(f"{where}: {names} は {{{{#id:}}}} と同じ行に書かないと効きません")
        elif {"nolabel", "nonum"} <= markers:
            result.warnings.append(
                f"{where}: {{{{nonum}}}} は採番しないので {{{{nolabel}}}} は不要です（どちらか一方に）"
            )
    if noref_where is not None:
        result.warnings.append(f"{noref_where}: {NOREF_BEGIN} の範囲が閉じていません（{NOREF_END} が必要）")


# ── procedure の検査 ────────────────────────────────────────────────────────


def _group_depth_warnings(procedure: object, prefix: str = "procedure", depth: int = 0) -> list[str]:
    warnings: list[str] = []
    if not isinstance(procedure, list):
        return warnings
    for i, item in enumerate(procedure):
        if not isinstance(item, dict) or not isinstance(item.get(GROUP_KEY), list):
            continue
        label = f"{prefix}[{i}]"
        if depth + 1 >= GROUP_DEPTH_LIMIT:
            warnings.append(
                f"{label}: group の入れ子が {depth + 1} 段です（入れ子にせず、条件ごとに group を並べることを推奨）"
            )
        warnings.extend(_group_depth_warnings(item[GROUP_KEY], f"{label}.{GROUP_KEY}", depth + 1))
    return warnings


def _repeated_when_info(procedure: object) -> list[str]:
    """同じ when: が続く箇所（group にまとめられる）を info で返す。

    区切りの操作（insertvfill / insertpagebreak / insertvspace）は連続を切らない。
    """
    if not isinstance(procedure, list):
        return []
    runs: list[tuple[str, int, int, int]] = []  # (when, 開始, 終了, 回数)
    for i, item in enumerate(procedure):
        if not isinstance(item, dict) or (WHEN_KEY not in item and _is_spacer(item)):
            continue
        key = json.dumps(item[WHEN_KEY], ensure_ascii=False, sort_keys=True) if WHEN_KEY in item else None
        if key is not None and runs and runs[-1][0] == key:
            when, start, _, count = runs[-1]
            runs[-1] = (when, start, i, count + 1)
        else:
            runs.append((key, i, i, 1))
    return [
        f"procedure[{start}]〜[{end}]: 同じ when: {when} が {count} 回続いています"
        "（- group: [...] にまとめると条件を 1 か所に書けます）"
        for when, start, end, count in runs
        if when is not None and count >= REPEATED_WHEN_LIMIT
    ]


def _is_spacer(item: dict) -> bool:
    spacer_ops = {"insertvfill", "insertpagebreak", "insertvspace"}
    return item.get("operation") in spacer_ops or bool(spacer_ops & set(item))


def _finite_domains(recipe: dict) -> dict[str, list]:
    """値を列挙できる param → 取りうる値（default が無ければ未定義 None も含む）。"""
    params = recipe.get(PARAMS_KEY)
    if not isinstance(params, dict):
        return {}
    result: dict[str, list] = {}
    for name, spec in params.items():
        if not isinstance(spec, dict):
            continue
        domain = param_domain(spec)
        if domain is None:
            continue
        values: list = list(domain)
        if "default" not in spec:
            values.append(None)
        result[str(name)] = values
    return result


def _constant_when_warnings(normalized: dict, domains: dict[str, list]) -> list[str]:
    """宣言された値のどの組み合わせでも結果が同じ（常に適用／常に除外）になる when.var。

    command 条件は見ない（var 条件だけの効き方を見る）。値を列挙できない変数を含む項目は省く。
    """
    if not domains:
        return []
    warnings: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(normalized.get("procedure") or []):
        if not isinstance(item, dict):
            continue
        whens = [w for _, w in item.get(INHERITED_WHEN_KEY) or ()] + [item.get(WHEN_KEY)]
        clauses = [_as_list(w.get("var")) for w in whens if isinstance(w, dict) and "var" in w]
        if not clauses:
            continue
        matches = [_RE_EXPR.fullmatch(e.strip()) for c in clauses for e in c]
        if not all(matches):
            continue
        names = sorted({m.group("name") for m in matches})
        if not all(n in domains for n in names):
            continue
        combos = list(itertools.islice(
            itertools.product(*(domains[n] for n in names)), _MAX_COMBINATIONS + 1))
        if len(combos) > _MAX_COMBINATIONS:
            continue
        results = set()
        for combo in combos:
            vars_map = {n: v for n, v in zip(names, combo) if v is not None}
            results.add(all(any(eval_condition(e, vars_map) for e in c) for c in clauses))
        if len(results) != 1:
            continue
        key = json.dumps(clauses, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        state = "常に適用されます" if results.pop() else "どの値の組み合わせでも適用されません"
        conds = " かつ ".join(" または ".join(c) for c in clauses)
        warnings.append(f"procedure[{i}]（group 展開後）: when.var {conds} は{state}（条件を見直してください）")
    return warnings


def _places(places: list[str], limit: int = 5) -> str:
    shown = ", ".join(places[:limit])
    return f"{shown} ほか計 {len(places)} か所" if len(places) > limit else shown


# ── 入口 ────────────────────────────────────────────────────────────────────


def lint(recipe: dict, normalized: dict, yaml_path: Path, workdir: Path | None,
         sources: "list[Source] | None" = None) -> LintResult:
    """*recipe* は正規化前（group 未展開）、*normalized* は正規化後のレシピ。"""
    result = LintResult()
    if sources is None:
        sources, missing = collect_sources(normalized, yaml_path, workdir)
        if missing:
            result.info.append(
                f"見つからないため変数・マーカー検査を省いたファイル {len(missing)} 件: "
                + ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
            )

    refs: list[_Ref] = []
    procedure = recipe.get("procedure")
    if isinstance(procedure, list):
        for label, when in iter_whens(procedure):
            if not isinstance(when, dict):
                continue
            for expr in _as_list(when.get("var")):
                m = _RE_EXPR.fullmatch(expr.strip())
                if m:
                    refs.append(_Ref(m.group("name"), f"{label}.when.var", expr))
    for src in sources:
        _scan_source(src, refs, result)

    params = recipe.get(PARAMS_KEY) if isinstance(recipe.get(PARAMS_KEY), dict) else {}
    vars_section = recipe.get("vars") if isinstance(recipe.get("vars"), dict) else {}
    item_vars: set[str] = set()
    for item in normalized.get("procedure") or []:
        if isinstance(item, dict) and isinstance(item.get("vars"), dict):
            item_vars.update(map(str, item["vars"]))
    known = set(map(str, params)) | set(map(str, vars_section)) | item_vars

    # 未定義の参照は名前ごとにまとめて報告する（場所は先頭の数件だけ並べる）
    undefined: dict[tuple[str, bool], list[str]] = {}
    for ref in refs:
        if ref.name not in known:
            places = undefined.setdefault((ref.name, ref.expr is not None), [])
            if ref.where not in places:
                places.append(ref.where)
    for (name, is_cond), places in undefined.items():
        where = _places(places)
        if is_cond and params:
            # params: のあるレシピでは実行時もエラーになる
            result.errors.append(f"{name} は未宣言の変数です（params: か vars: で宣言してください）: {where}")
        elif is_cond:
            result.warnings.append(
                f"条件の変数 {name} が vars: にありません（未定義は偽になります。--var で渡す前提なら"
                f" params: で宣言すると打ち間違いを検出できます）: {where}"
            )
        else:
            result.warnings.append(f"{{{{v:{name}}}}} の {name} が vars: にありません（置換されません）: {where}")

    # params: のあるレシピでは、条件式の比較値が取りうる値かも検査する
    if params:
        from md_merge._condblock import DeclaredVars
        from md_merge._params import declared_domains
        domains = declared_domains(recipe) or {}
        for ref in refs:
            if ref.expr is None or ref.name not in known or ref.where.endswith(".when.var"):
                continue  # when.var は check_params_errors が検査済み
            try:
                eval_condition(ref.expr, DeclaredVars({}, domains))
            except ValueError as exc:
                result.errors.append(f"{ref.where}: {exc}")

    # insertvar の変数名（値をそのまま挿入するので、vars: に無ければ何も入らない）
    insertvars = insertvar_names(normalized)
    for name in dict.fromkeys(insertvars):
        if name not in known:
            result.warnings.append(
                f"procedure の insertvar {name} が vars: / params: にありません"
                "（--var で渡さない限り何も挿入されません）"
            )

    used = {ref.name for ref in refs} | set(insertvars)
    for name in params:
        if str(name) not in used:
            result.warnings.append(
                f"params.{name}: どこからも参照されていません（when.var / insertvar / insertmd の MD / cropsrc のノートを検査。"
                "表紙テンプレート等でだけ使っているなら無視してかまいません）"
            )

    result.warnings.extend(_constant_when_warnings(normalized, _finite_domains(recipe)))
    result.warnings.extend(_group_depth_warnings(procedure))
    result.info.extend(_repeated_when_info(procedure))
    return result
