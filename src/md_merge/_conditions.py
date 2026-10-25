"""procedure 項目の条件付き適用（``when:``）の判定（全段共通の単一の真実源）。

procedure の各項目は ``when:`` を持てる。条件を満たさない項目はレシピ読み込み直後に
procedure から取り除かれ、後段（merge / pptmerge / preprocess）は今までどおり
procedure を先頭から処理するだけでよい。

    when:
      command: [ppt_to_puremd, ppt_to_transfer]  # 起動したサブコマンドがどれかなら適用
      not_command: ppt_to_pdf                    # 起動したサブコマンドがどれかなら除外
      tag: blog                                  # --tag で指定したタグのどれかがあれば適用
      not_tag: draft                             # --tag で指定したタグのどれかがあれば除外

- キー同士は AND、値（文字列またはリスト）の中は OR。
- ``when:`` が無い項目は常に適用する。
- サブコマンドの照合はトップレベルで起動したコマンド名で行う。パイプラインは各段に同じ
  ``args`` を渡すので、``ppt_to_pdf`` 内の merge 段でも command は ``ppt_to_pdf`` になる。
- checkgen / checkverify / validate は条件を無視して全項目を対象にする。
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

WHEN_KEY = "when"

# when: に書けるキー
WHEN_KEYS: frozenset[str] = frozenset({"command", "not_command", "tag", "not_tag"})

# when.command / not_command に書けるサブコマンド名。__main__.py のサブコマンドと同期させる。
KNOWN_COMMANDS: frozenset[str] = frozenset({
    "merge", "idcollect", "checkgen", "checkverify", "idresolve", "pandoc", "render",
    "pptmerge", "crop", "crop_to_pdf", "pptimgexport", "pptmdexport", "pptyamlexport",
    "puremd", "ppt_to_pdf", "condblockprocess", "ppt_to_transfer", "ppt_to_puremd",
    "transfer", "notecomexport", "ppt_to_notecom", "validate", "pptpdfexport", "pptdeletecsl",
})

# サブコマンドの別名 → 正式名（照合は正式名で行う）
_COMMAND_ALIASES: dict[str, str] = {"githubmd": "puremd"}


@dataclass(frozen=True)
class Context:
    """条件判定に使う起動時の情報。"""
    command: str
    tags: frozenset[str]


def build_context(args: argparse.Namespace) -> Context:
    command = getattr(args, "subcommand", "") or ""
    return Context(
        command=_COMMAND_ALIASES.get(command, command),
        tags=frozenset(getattr(args, "tag", None) or ()),
    )


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def _commands(value: object) -> list[str]:
    return [_COMMAND_ALIASES.get(name, name) for name in _as_list(value)]


def is_active(item: dict, ctx: Context) -> bool:
    """*item* の ``when:`` を *ctx* が満たすか。``when:`` が無ければ True。"""
    when = item.get(WHEN_KEY)
    if not isinstance(when, dict):
        return True
    if "command" in when and ctx.command not in _commands(when["command"]):
        return False
    if "not_command" in when and ctx.command in _commands(when["not_command"]):
        return False
    if "tag" in when and not ctx.tags.intersection(_as_list(when["tag"])):
        return False
    if "not_tag" in when and ctx.tags.intersection(_as_list(when["not_tag"])):
        return False
    return True


def filter_procedure(recipe: dict, args: argparse.Namespace) -> dict:
    """条件を満たさない procedure 項目を除いた recipe を返す（*recipe* 自体は変更しない）。"""
    procedure = recipe.get("procedure")
    if not isinstance(procedure, list) or not any(
        isinstance(item, dict) and WHEN_KEY in item for item in procedure
    ):
        return recipe

    ctx = build_context(args)
    kept: list = []
    for i, item in enumerate(procedure):
        if isinstance(item, dict) and not is_active(item, ctx):
            logging.info(
                "procedure[%d] (%s) をスキップ: when=%s（command=%s, tags=%s）",
                i, item.get("operation", "insertpptx"), item[WHEN_KEY],
                ctx.command, ",".join(sorted(ctx.tags)) or "-",
            )
            continue
        kept.append(item)
    return {**recipe, "procedure": kept}


def check_when(when: object) -> list[str]:
    """``when:`` の書式を検査し、問題点のメッセージ一覧を返す（validate 用）。"""
    if not isinstance(when, dict):
        return ["when はマッピングで指定してください"]
    errors: list[str] = []
    for key in sorted(set(when) - WHEN_KEYS):
        errors.append(f"when の未知のキー: {key!r}（有効: {', '.join(sorted(WHEN_KEYS))}）")
    for key in sorted(set(when) & WHEN_KEYS):
        value = when[key]
        if not (isinstance(value, str) or (
            isinstance(value, list) and value and all(isinstance(v, str) for v in value)
        )):
            errors.append(f"when.{key} は文字列または文字列のリストで指定してください: {value!r}")
    for key in ("command", "not_command"):
        for name in _commands(when.get(key)):
            if name not in KNOWN_COMMANDS:
                errors.append(f"when.{key} に未知のサブコマンド: {name!r}")
    for pos, neg, norm in (("command", "not_command", _commands), ("tag", "not_tag", _as_list)):
        both = set(norm(when.get(pos))) & set(norm(when.get(neg)))
        if both:
            errors.append(f"when.{pos} と when.{neg} の両方に指定: {', '.join(sorted(both))}")
    return errors
