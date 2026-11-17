"""procedure 項目の条件付き適用（``when:``）の判定（全段共通の単一の真実源）。

procedure の各項目は ``when:`` を持てる。条件を満たさない項目はレシピ読み込み直後に
procedure から取り除かれ、後段（merge / pptmerge / preprocess）は今までどおり
procedure を先頭から処理するだけでよい。

    when:
      command: [ppt_to_puremd, ppt_to_transfer]  # 起動したサブコマンドがどれかなら適用
      not_command: ppt_to_pdf                    # 起動したサブコマンドがどれかなら除外
      var: [EDITION=print, extra]                # 変数（レシピ vars: ＋ --var）の条件のどれかが真なら適用

- キー同士は AND、値（文字列またはリスト）の中は OR。
- ``var`` の各要素は ``{{#if:…}}`` と同じ条件式（``NAME`` / ``!NAME`` / ``NAME=VALUE`` /
  ``NAME!=VALUE``）で、真偽判定も同じ（_condblock.py）。変数はレシピ ``vars:`` を
  ``--var`` で上書きしたもの。
- 旧 ``tag`` / ``not_tag``（``--tag``）は廃止。書かれていればエラーにする。
- ``when:`` が無い項目は常に適用する。
- ``- group: [...]`` に付けた ``when:`` は配下の全項目に掛かる（項目自身の ``when:`` とは
  AND）。group は読み込み時（_procedure.py）に展開され、各項目は引き継いだ条件を
  ``_group_when`` に持つ。filter_procedure はこのキーを取り除いてから後段に渡す。
- サブコマンドの照合はトップレベルで起動したコマンド名で行う。パイプラインは各段に同じ
  ``args`` を渡すので、``ppt_to_pdf`` 内の merge 段でも command は ``ppt_to_pdf`` になる。
- checkgen / checkverify / validate は条件を無視して全項目を対象にする。
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field

from md_merge._condblock import check_condition, eval_condition
from md_merge._procedure import GROUP_KEY, INHERITED_WHEN_KEY, ProcedureNotationError

WHEN_KEY = "when"

# when: に書けるキー
WHEN_KEYS: frozenset[str] = frozenset({"command", "not_command", "var"})

# 廃止した when: キー → 移行先の案内
REMOVED_WHEN_KEYS: dict[str, str] = {
    "tag": "when.tag は廃止しました。when.var: NAME と --var NAME を使ってください",
    "not_tag": "when.not_tag は廃止しました。when.var: '!NAME' と --var NAME を使ってください",
}

# when.command / not_command に書けるサブコマンド名。__main__.py のサブコマンドと同期させる。
KNOWN_COMMANDS: frozenset[str] = frozenset({
    "merge", "idcollect", "checkgen", "checkverify", "idresolve", "pandoc", "render",
    "pptmerge", "crop", "crop_to_pdf", "pptimgexport", "pptmdexport", "pptyamlexport",
    "puremd", "ppt_to_pdf", "ppt_to_transfer", "ppt_to_puremd",
    "transfer", "notecomexport", "ppt_to_notecom", "validate", "pptpdfexport", "pptdeletecsl",
})

# 廃止したサブコマンド → 案内
REMOVED_COMMANDS: dict[str, str] = {
    "condblockprocess": "condblockprocess は廃止しました（LaTeX 表紙用。LaTeX は撤去済み）",
}

# サブコマンドの別名 → 正式名（照合は正式名で行う）
_COMMAND_ALIASES: dict[str, str] = {"githubmd": "puremd"}


@dataclass(frozen=True)
class Context:
    """条件判定に使う起動時の情報。"""
    command: str
    vars: dict = field(default_factory=dict)


def build_context(args: argparse.Namespace, vars_map: dict | None = None) -> Context:
    """*vars_map* はレシピの ``vars:``（load_yaml で ``--var`` 上書き済み）。"""
    command = getattr(args, "subcommand", "") or ""
    return Context(
        command=_COMMAND_ALIASES.get(command, command),
        vars=dict(vars_map or {}),
    )


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def _commands(value: object) -> list[str]:
    return [_COMMAND_ALIASES.get(name, name) for name in _as_list(value)]


def is_active(item: dict, ctx: Context) -> bool:
    """*item* の ``when:``（と group から引き継いだ条件）をすべて *ctx* が満たすか。"""
    whens = [w for _, w in item.get(INHERITED_WHEN_KEY) or ()]
    whens.append(item.get(WHEN_KEY))
    return all(_when_matches(w, ctx) for w in whens)


def _when_matches(when: object, ctx: Context) -> bool:
    """1 つの ``when:`` を *ctx* が満たすか。``when:`` が無ければ True。"""
    if not isinstance(when, dict):
        return True
    if "command" in when and ctx.command not in _commands(when["command"]):
        return False
    if "not_command" in when and ctx.command in _commands(when["not_command"]):
        return False
    if "var" in when and not any(eval_condition(e, ctx.vars) for e in _as_list(when["var"])):
        return False
    return True


def filter_procedure(recipe: dict, args: argparse.Namespace) -> dict:
    """条件を満たさない procedure 項目を除いた recipe を返す（*recipe* 自体は変更しない）。"""
    procedure = recipe.get("procedure")
    if not isinstance(procedure, list) or not any(
        isinstance(item, dict) and (WHEN_KEY in item or INHERITED_WHEN_KEY in item)
        for item in procedure
    ):
        return recipe

    errors = check_when_errors(recipe)
    if errors:
        raise ProcedureNotationError("procedure の when: が不正です\n  " + "\n  ".join(errors))

    vars_map = recipe.get("vars")
    ctx = build_context(args, vars_map if isinstance(vars_map, dict) else None)
    kept: list = []
    for i, item in enumerate(procedure):
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if not is_active(item, ctx):
            conds = [f"group {label} の when={w}" for label, w in item.get(INHERITED_WHEN_KEY) or ()]
            if WHEN_KEY in item:
                conds.append(f"when={item[WHEN_KEY]}")
            logging.info(
                "procedure[%d] (%s) をスキップ: %s（command=%s）",
                i, item.get("operation", "insertpptx"), ", ".join(conds), ctx.command,
            )
            continue
        if INHERITED_WHEN_KEY in item:
            item = {k: v for k, v in item.items() if k != INHERITED_WHEN_KEY}
        kept.append(item)
    return {**recipe, "procedure": kept}


def _unknown_key_message(key: object) -> str:
    msg = f"when の未知のキー: {key!r}（有効: {', '.join(sorted(WHEN_KEYS))}）"
    if isinstance(key, str) and key.lower() in WHEN_KEYS:
        msg += f"。キーは小文字で {key.lower()!r} と書いてください"
    return msg


def check_when_errors(recipe: dict) -> list[str]:
    """procedure の ``when:`` のうち実行できない誤り（未知キー・廃止キー・不正な条件式）を列挙する。

    validate はこれをエラー、merge / pptmerge は読み込み時に停止する。
    """
    procedure = recipe.get("procedure")
    if not isinstance(procedure, list):
        return []
    errors: list[str] = []
    seen: set[str] = set()
    for label, when in iter_whens(procedure):
        # group の条件は展開後の各項目が同じものを持つので、位置ごとに 1 回だけ検査する
        if label in seen or not isinstance(when, dict):
            continue
        for key in sorted(set(when) - WHEN_KEYS - set(REMOVED_WHEN_KEYS), key=str):
            errors.append(f"procedure[{i}]: {_unknown_key_message(key)}")
        for key, msg in REMOVED_WHEN_KEYS.items():
            if key in when:
                errors.append(f"{label}: {msg}")
        for expr in _as_list(when.get("var")):
            problem = check_condition(expr)
            if problem:
                errors.append(f"{label}: when.var: {problem}")
    return errors


def iter_whens(procedure: list, prefix: str = "procedure"):
    """procedure 中の ``when:`` を (位置ラベル, when) で列挙する。

    未展開の ``group:`` は子へ再帰し、展開済みの項目は引き継いだ条件（``_group_when``）も返す。
    """
    for i, item in enumerate(procedure):
        if not isinstance(item, dict):
            continue
        label = f"{prefix}[{i}]"
        yield from (tuple(pair) for pair in item.get(INHERITED_WHEN_KEY) or ())
        if WHEN_KEY in item:
            yield label, item[WHEN_KEY]
        children = item.get(GROUP_KEY)
        if isinstance(children, list):
            yield from iter_whens(children, f"{label}.{GROUP_KEY}")


def check_when(when: object) -> list[str]:
    """``when:`` の書式を検査し、問題点のメッセージ一覧を返す（validate 用）。"""
    if not isinstance(when, dict):
        return ["when はマッピングで指定してください"]
    errors: list[str] = []
    for key in sorted(set(when) & WHEN_KEYS):
        value = when[key]
        if not (isinstance(value, str) or (
            isinstance(value, list) and value and all(isinstance(v, str) for v in value)
        )):
            errors.append(f"when.{key} は文字列または文字列のリストで指定してください: {value!r}")
    for key in ("command", "not_command"):
        for name in _commands(when.get(key)):
            if name in REMOVED_COMMANDS:
                errors.append(f"when.{key}: {REMOVED_COMMANDS[name]}")
            elif name not in KNOWN_COMMANDS:
                errors.append(f"when.{key} に未知のサブコマンド: {name!r}")
    both = set(_commands(when.get("command"))) & set(_commands(when.get("not_command")))
    if both:
        errors.append(f"when.command と when.not_command の両方に指定: {', '.join(sorted(both))}")
    return errors
