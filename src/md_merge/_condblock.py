"""行単位の条件ブロック（IF ブロック）処理（全段共通の単一の真実源）。

テキスト中の単独行タグで囲んだ行を、変数（レシピ ``vars:`` ＋ CLI ``--var``）の値に
応じて残す／削る。タグ行自体は出力しない。

    {{#if:NAME}}          NAME が真なら残す
    {{#if:!NAME}}         NAME が偽なら残す
    {{#if:NAME=VALUE}}    NAME の値（文字列）が VALUE と一致すれば残す
    {{#if:NAME!=VALUE}}   一致しなければ残す（未定義も「一致しない」）
    {{#else:NAME}}        直前の {{#if:NAME…}} の逆（任意）
    {{#endif:NAME}}       ブロック終了（変数名は開始タグと一致させる）

- 偽 = 未定義 / null / 空文字 / YAML の false / 文字列 false・0・no・off（大小無視）。
- ネスト可。ただし同じ変数名のブロックの入れ子はエラー（endif の対応が曖昧になるため）。
- ``markdown=True`` のときは ``` / ~~~ のフェンスコード内のタグを解釈しない（記法の説明を
  コードブロックで書けるように）。フェンス自体は外側のブロック判定に従って残す／削る。

使う段: merge（insertmd 原稿）/ pptmdexport（ノート MD ブロック）/
pptyamlexport（ノート YAML ブロック）/ condblockprocess・pandoc 表紙テンプレ。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME = r"[A-Za-z0-9_]+"
_VALUE = r"[A-Za-z0-9_.\-]*"

# 条件式（{{#if:…}} の中身、procedure の when.var と共通）
_EXPR = (
    r"(?P<neg>!)?(?P<name>" + _NAME + r")"
    r"(?:(?P<op>!=|=)(?P<value>" + _VALUE + r"))?"
)
_RE_IF = re.compile(r"^\s*\{\{#if:" + _EXPR + r"\}\}\s*$")
_RE_EXPR = re.compile(_EXPR)
_RE_ELSE = re.compile(r"^\s*\{\{#else:(?P<name>" + _NAME + r")\}\}\s*$")
_RE_ENDIF = re.compile(r"^\s*\{\{#endif:(?P<name>" + _NAME + r")\}\}\s*$")
# タグらしいが文法に合わない行（誤記の検出用）。{{#elseif:…}} / {{#elif:…}} / {{#end:…}}
# など未定義のタグも拾うため、if / el / end で始まる {{#… はすべて対象にする
# （{{#id:…}} などの他の記法は対象外）。
_RE_TAG_LIKE = re.compile(r"^\s*\{\{#(?:if|el|end)")
_RE_ELSEIF_LIKE = re.compile(r"^\s*\{\{#el(?:se\s*if|if|sif)\b")
_RE_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

_FALSY_STRINGS = frozenset({"", "false", "0", "no", "off", "none", "null"})


def is_truthy(val: object) -> bool:
    """条件ブロックの真偽判定。"""
    if val is None or val is False:
        return False
    if isinstance(val, str):
        return val.strip().lower() not in _FALSY_STRINGS
    return True


def _as_str(val: object) -> str:
    if val is True:
        return "true"
    if val is False:
        return "false"
    return "" if val is None else str(val)


@dataclass
class _Frame:
    name: str
    cond: bool          # if の条件そのもの
    parent_active: bool  # 外側が出力中か
    in_else: bool = False

    @property
    def active(self) -> bool:
        return self.parent_active and (self.cond != self.in_else)


class DeclaredVars(dict):
    """変数の値に「宣言済みの名前と取りうる値」を添えた dict（レシピに ``params:`` があるとき）。

    条件式の評価時に、宣言されていない名前や、取りうる値の外の比較値をエラーにする。
    *domains* は 名前 → 取りうる値のタプル（None は任意の値）。``params:`` と ``vars:`` の
    両方の名前を含む。
    """

    def __init__(self, values: dict, domains: "dict[str, tuple[str, ...] | None]"):
        super().__init__(values)
        self.domains = dict(domains)

    def check_reference(self, name: str, value: "str | None") -> "str | None":
        if name not in self.domains:
            return (f"未宣言の変数です: {name}（params: か vars: で宣言してください。"
                    f"宣言済み: {', '.join(sorted(self.domains)) or 'なし'}）")
        domain = self.domains[name]
        if value is not None and domain is not None and value not in domain:
            return f"{name} の取りうる値ではありません: {value!r}（{', '.join(domain)}）"
        return None


def _eval(m: re.Match, vars_map: dict) -> bool:
    name = m.group("name")
    op = m.group("op")
    if isinstance(vars_map, DeclaredVars):
        problem = vars_map.check_reference(name, m.group("value") if op else None)
        if problem:
            raise ValueError(problem)
    defined = name in vars_map
    val = vars_map.get(name)
    if op is None:
        result = is_truthy(val)
        return not result if m.group("neg") else result
    if m.group("neg"):
        raise ValueError("否定 '!' と比較 '=' / '!=' は併用できません")
    equal = defined and _as_str(val) == m.group("value")
    return equal if op == "=" else not equal


def eval_condition(expr: str, vars_map: dict | None) -> bool:
    """条件式 ``NAME`` / ``!NAME`` / ``NAME=VALUE`` / ``NAME!=VALUE`` を評価する。

    ``{{#if:…}}`` の中身と同じ文法・真偽判定。不正な式は ValueError。
    """
    m = _RE_EXPR.fullmatch(expr.strip())
    if m is None:
        raise ValueError(f"条件式が不正です（NAME / !NAME / NAME=VALUE / NAME!=VALUE）: {expr!r}")
    return _eval(m, {} if vars_map is None else vars_map)


def check_condition(expr: str) -> str | None:
    """条件式の書式を検査し、問題があればメッセージを返す（validate 用）。"""
    m = _RE_EXPR.fullmatch(expr.strip())
    if m is None:
        return f"条件式が不正です（NAME / !NAME / NAME=VALUE / NAME!=VALUE）: {expr!r}"
    if m.group("neg") and m.group("op"):
        return f"否定 '!' と比較 '=' / '!=' は併用できません: {expr!r}"
    return None


def process_conditionals(
    lines: list[str],
    vars_map: dict | None,
    *,
    markdown: bool = False,
    where: str = "",
) -> list[str]:
    """*lines*（改行付き可）から条件ブロックを展開した行リストを返す。

    文法エラーは ``ValueError``（メッセージに *where* と行番号を含む）。
    """
    if vars_map is None:
        vars_map = {}
    prefix = f"{where}: " if where else ""
    out: list[str] = []
    stack: list[_Frame] = []
    fence: str | None = None  # markdown モードで開いているフェンス記号

    def active() -> bool:
        return stack[-1].active if stack else True

    for lineno, line in enumerate(lines, start=1):
        stripped = line.rstrip("\r\n")

        if markdown:
            mf = _RE_FENCE.match(stripped)
            if fence is not None:
                if mf and mf.group(1)[0] == fence[0] and len(mf.group(1)) >= len(fence) \
                        and stripped.strip() == mf.group(1):
                    fence = None
                if active():
                    out.append(line)
                continue
            if mf:
                fence = mf.group(1)
                if active():
                    out.append(line)
                continue

        try:
            m_if = _RE_IF.match(stripped)
            if m_if:
                name = m_if.group("name")
                if any(f.name == name for f in stack):
                    raise ValueError(
                        f"同じ変数名の条件ブロックを入れ子にはできません: {{{{#if:{name}}}}}"
                    )
                stack.append(_Frame(name, _eval(m_if, vars_map), active()))
                continue

            m_else = _RE_ELSE.match(stripped)
            if m_else:
                name = m_else.group("name")
                if not stack or stack[-1].name != name:
                    raise ValueError(f"対応する {{{{#if:{name}}}}} のない {{{{#else:{name}}}}} です")
                if stack[-1].in_else:
                    raise ValueError(f"{{{{#else:{name}}}}} が重複しています")
                stack[-1].in_else = True
                continue

            m_end = _RE_ENDIF.match(stripped)
            if m_end:
                name = m_end.group("name")
                if not stack:
                    raise ValueError(f"対応する開始タグのない終了タグです: {{{{#endif:{name}}}}}")
                if stack[-1].name != name:
                    raise ValueError(
                        f"終了タグの変数名 '{name}' が開始タグの '{stack[-1].name}' と一致しません"
                    )
                stack.pop()
                continue

            if _RE_ELSEIF_LIKE.match(stripped):
                raise ValueError(
                    f"{{{{#elseif}}}} は未対応です（{{{{#else:NAME}}}} か、"
                    f"{{{{#if}}}} の入れ子を使ってください）: {stripped.strip()}"
                )
            if _RE_TAG_LIKE.match(stripped):
                raise ValueError(f"条件ブロックのタグとして解釈できません: {stripped.strip()}")
        except ValueError as exc:
            raise ValueError(f"{prefix}line {lineno}: {exc}") from None

        if active():
            out.append(line)

    if stack:
        name = stack[-1].name
        raise ValueError(f"{prefix}{{{{#if:{name}}}}} に対応する {{{{#endif:{name}}}}} がありません")
    return out


def process_text(text: str, vars_map: dict | None, *, markdown: bool = False, where: str = "") -> str:
    """文字列版。タグが無ければそのまま返す。"""
    if "{{#" not in text:
        return text
    return "".join(process_conditionals(
        text.splitlines(keepends=True), vars_map, markdown=markdown, where=where,
    ))


# ── CLI --var ───────────────────────────────────────────────────────────────


def parse_cli_vars(items: "list[str] | None") -> dict[str, str]:
    """``--var NAME=VALUE`` / ``--var NAME``（= true）を辞書にする。不正な名前は ValueError。"""
    result: dict[str, str] = {}
    for item in items or ():
        name, sep, value = item.partition("=")
        name = name.strip()
        if not re.fullmatch(_NAME, name):
            raise ValueError(f"--var の変数名が不正です（英数字と _ のみ）: {item!r}")
        result[name] = value if sep else "true"
    return result
