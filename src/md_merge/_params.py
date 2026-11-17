"""レシピの ``params:``（分岐に使う変数の宣言）。

``vars:`` は文字を埋める置換用、``params:`` はビルドの切り替え（when.var / ``{{#if}}``）用の
変数を、型・取りうる値・既定値つきで宣言する。

    params:
      TARGET:
        values: [PDF, RECIPRO]     # 取りうる値（文字列）
        default: PDF
        description: 最終出力
      MULTISTEP:
        type: bool                 # true / false
        default: false
      AUDIENCE:
        type: string               # 任意の文字列（値の検査なし）

レシピに ``params:`` があると、読み込み時（load_yaml）に次を検査し、違反はエラーにする。

- ``params:`` の書式（未知のキー、型、既定値が取りうる値に入っているか）。
- 同じ名前を ``vars:`` と ``params:`` の両方に書いていないか。
- ``--var`` の名前が ``params:`` か ``vars:`` にあるか、値が取りうる値か。
- procedure の ``when.var`` が宣言済みの名前だけを参照し、比較値が取りうる値か。

``--var`` で渡されなかった param は ``default`` を値とする（``default`` が無ければ未定義＝偽）。
bool の値は ``"true"`` / ``"false"`` に正規化する。

MD / ノートの ``{{#if}}`` は、各段が :func:`condition_vars` で得た :class:`DeclaredVars`
を使って評価するので、同じ検査がかかる。``params:`` が無いレシピの動作は従来どおり。
"""

from __future__ import annotations

from md_merge._condblock import _FALSY_STRINGS, DeclaredVars, check_condition, eval_condition, is_truthy
from md_merge._procedure import ProcedureNotationError

PARAMS_KEY = "params"
PARAM_SPEC_KEYS = frozenset({"type", "values", "default", "description"})
PARAM_TYPES = frozenset({"bool", "string"})

BOOL_DOMAIN: tuple[str, ...] = ("true", "false")
_BOOL_WORDS = frozenset({"true", "yes", "on", "1"}) | (_FALSY_STRINGS - {""})


class ParamsError(ProcedureNotationError):
    """``params:`` の宣言、または宣言に反する変数の使い方。"""


def _yaml_bool_hint(value: object) -> str:
    if isinstance(value, bool):
        return "（ON / OFF / yes / no などを引用符なしで書くと YAML の真偽値になります。'ON' のように引用符で囲んでください）"
    return ""


def check_params_schema(params: object) -> list[str]:
    """``params:`` の書式エラーを列挙する。"""
    if params is None:
        return []
    if not isinstance(params, dict):
        return ["params はマッピング（名前: 宣言）で指定してください"]
    errors: list[str] = []
    for name, spec in params.items():
        label = f"params.{name}"
        if not isinstance(name, str) or not name.replace("_", "a").isalnum() or not name.isascii():
            errors.append(f"{label}: 変数名は英数字と _ だけにしてください")
            continue
        if not isinstance(spec, dict):
            errors.append(f"{label}: 宣言はマッピング（type / values / default / description）で書いてください")
            continue
        for key in sorted(set(spec) - PARAM_SPEC_KEYS):
            errors.append(f"{label}: 未知のキー {key!r}（有効: {', '.join(sorted(PARAM_SPEC_KEYS))}）")
        ptype = spec.get("type")
        values = spec.get("values")
        if ptype is not None and ptype not in PARAM_TYPES:
            errors.append(f"{label}.type: {ptype!r} は使えません（{', '.join(sorted(PARAM_TYPES))}）")
        if values is not None:
            if ptype is not None:
                errors.append(f"{label}: type と values は同時に書けません（values を書けば値の列挙になります）")
            if not isinstance(values, list) or not values:
                errors.append(f"{label}.values: 1 つ以上の値のリストで指定してください")
            else:
                for v in values:
                    if not isinstance(v, str):
                        errors.append(f"{label}.values: 値は文字列で書いてください: {v!r}{_yaml_bool_hint(v)}")
                if len(set(map(str, values))) != len(values):
                    errors.append(f"{label}.values: 値が重複しています")
        if "default" in spec:
            default = spec["default"]
            if isinstance(values, list) and values and default not in values:
                errors.append(
                    f"{label}.default: {default!r} は values に含まれていません{_yaml_bool_hint(default)}"
                )
            if ptype == "bool" and not isinstance(default, bool) and str(default).lower() not in _BOOL_WORDS:
                errors.append(f"{label}.default: bool の既定値は true / false で書いてください: {default!r}")
    return errors


def param_domain(spec: dict) -> "tuple[str, ...] | None":
    """取りうる値（文字列のタプル）。任意の値なら None。"""
    if spec.get("type") == "bool":
        return BOOL_DOMAIN
    values = spec.get("values")
    if isinstance(values, list):
        return tuple(str(v) for v in values)
    return None


def _normalize(spec: dict, value: object) -> object:
    if spec.get("type") == "bool":
        return "true" if is_truthy(value) else "false"
    return value


def declared_domains(recipe: dict) -> "dict[str, tuple[str, ...] | None] | None":
    """宣言済みの名前 → 取りうる値。``params:`` が無ければ None（宣言を強制しない）。

    ``vars:`` の名前も宣言済みとみなす（値は任意）。
    """
    params = recipe.get(PARAMS_KEY)
    if not isinstance(params, dict):
        return None
    domains: dict[str, tuple[str, ...] | None] = {}
    vars_section = recipe.get("vars")
    if isinstance(vars_section, dict):
        domains.update({str(k): None for k in vars_section})
    for name, spec in params.items():
        domains[str(name)] = param_domain(spec) if isinstance(spec, dict) else None
    return domains


def condition_vars(recipe: dict) -> dict:
    """``{{#if}}`` の評価に使う変数。``params:`` があれば宣言の検査つき（DeclaredVars）。"""
    values = dict(recipe.get("vars") or {})
    domains = declared_domains(recipe)
    return values if domains is None else DeclaredVars(values, domains)


def check_reference(expr: str, domains: "dict[str, tuple[str, ...] | None]") -> "str | None":
    """条件式 *expr* が宣言済みの名前・取りうる値だけを使っているか。"""
    problem = check_condition(expr)
    if problem:
        return problem
    try:
        eval_condition(expr, DeclaredVars({}, domains))
    except ValueError as exc:
        return str(exc)
    return None


def apply_params(recipe: dict, cli_vars: "dict[str, str] | None" = None) -> dict:
    """``params:`` を検査し、既定値と ``--var`` を ``vars:`` へ反映した recipe を返す。

    *recipe* の ``vars:`` は ``--var`` 上書き前の値、*cli_vars* は ``--var`` の値。
    ``params:`` が無ければ ``--var`` を上書きマージするだけ（従来どおり）。
    違反は :class:`ParamsError`。
    """
    cli_vars = dict(cli_vars or {})
    params = recipe.get(PARAMS_KEY)
    if params is None:
        if cli_vars:
            recipe["vars"] = {**(recipe.get("vars") or {}), **cli_vars}
        return recipe

    errors = check_params_errors(recipe, cli_vars)
    if errors:
        raise ParamsError("params: の宣言・変数の使い方に誤りがあります\n  " + "\n  ".join(errors))

    merged = dict(recipe.get("vars") or {})
    for name, spec in params.items():
        if name in cli_vars:
            merged[name] = _normalize(spec, cli_vars.pop(name))
        elif "default" in spec:
            merged[name] = _normalize(spec, spec["default"])
    merged.update(cli_vars)  # 残りは vars: の上書き
    recipe["vars"] = merged
    return recipe


def check_params_errors(recipe: dict, cli_vars: "dict[str, str] | None" = None) -> list[str]:
    """``params:`` があるレシピの宣言・``--var``・``when.var`` の誤りを列挙する（validate 兼用）。"""
    params = recipe.get(PARAMS_KEY)
    if params is None:
        return []
    errors = check_params_schema(params)
    if errors:
        return errors
    vars_section = recipe.get("vars") or {}
    if not isinstance(vars_section, dict):
        vars_section = {}
    for name in sorted(set(map(str, params)) & set(map(str, vars_section))):
        errors.append(
            f"{name} が vars: と params: の両方にあります（置換用は vars:、切り替え用は params: のどちらかに）"
        )
    domains = declared_domains(recipe) or {}
    for name, value in (cli_vars or {}).items():
        if name not in domains:
            errors.append(
                f"--var {name}: 未宣言の変数です（params: か vars: で宣言してください。"
                f"params: {', '.join(map(str, params)) or 'なし'}）"
            )
            continue
        spec = params.get(name)
        if not isinstance(spec, dict):
            continue
        if spec.get("type") == "bool":
            if str(value).lower() not in _BOOL_WORDS:
                errors.append(f"--var {name}={value}: bool の値は true / false で指定してください")
        else:
            domain = param_domain(spec)
            if domain is not None and value not in domain:
                errors.append(f"--var {name}={value}: 取りうる値ではありません（{', '.join(domain)}）")
    errors.extend(check_when_references(recipe, domains))
    return errors


def check_when_references(recipe: dict, domains: "dict[str, tuple[str, ...] | None]") -> list[str]:
    """procedure の ``when.var`` が宣言済みの名前・値だけを使っているか。"""
    from md_merge._conditions import iter_whens  # lazy — _conditions は _procedure に依存

    procedure = recipe.get("procedure")
    if not isinstance(procedure, list):
        return []
    errors: list[str] = []
    seen: set[str] = set()
    for label, when in iter_whens(procedure):
        if label in seen or not isinstance(when, dict):
            continue
        seen.add(label)
        var = when.get("var")
        for expr in [var] if isinstance(var, str) else (var if isinstance(var, list) else []):
            if not isinstance(expr, str):
                continue
            problem = check_reference(expr, domains)
            if problem:
                errors.append(f"{label}: when.var: {problem}")
    return errors
