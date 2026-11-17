"""explain サブコマンド: 条件（when: / group / {{#if}}）を展開した結果を表示する。

ファイルは何も生成しない。レシピの「デバッガ」として、与えた ``--var`` のもとで
procedure のどの項目が採用／除外されるかを理由つきで一覧にする。

    pptmdmerge explain recipe.yaml --var TARGET=RECIPRO
    pptmdmerge explain recipe.yaml --matrix TARGET          # 値ごとに結果が変わる項目だけ
    pptmdmerge explain recipe.yaml --blocks                 # insertmd 内の {{#if}} の判定も

- ``--command NAME`` を付けると ``when.command`` / ``not_command`` もその名前で判定する。
  付けなければ command 条件は満たすものとして扱い、行末に ``(command 条件は未評価)`` と出す。
- ``--matrix NAME`` は ``params:`` の ``values`` / ``bool`` を値の一覧に使う。``params:`` に
  無い変数は ``--matrix NAME=a,b`` のように値を並べる。複数指定すると全組み合わせ。
- 出力は安定したテキストなので、ファイルに保存して git diff すれば、レシピの変更で
  意図しない項目が入った／消えたことを検出できる。
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import logging
from pathlib import Path

from md_merge._condblock import _RE_ELSE, _RE_ENDIF, _RE_FENCE, _RE_IF, eval_condition
from md_merge._conditions import WHEN_KEY, _as_list, _commands
from md_merge._output import EXIT_BAD_INPUT, EXIT_FAILURE, EXIT_NOT_FOUND, EXIT_OK, setup_logging
from md_merge._params import PARAMS_KEY, ParamsError, apply_params, condition_vars, param_domain
from md_merge._procedure import INHERITED_WHEN_KEY, PRIMARY_ARG, ProcedureNotationError, normalize_recipe
from md_merge.merge._recipe import cli_vars, load_yaml, resolve_input_path

_MAX_COMBINATIONS = 64


# ── 項目の判定 ──────────────────────────────────────────────────────────────


def describe_item(item: dict) -> str:
    """procedure 項目（内部表現）を 1 行で表す。"""
    op = item.get("operation", "insertpptx")
    key = PRIMARY_ARG.get(op)
    if op == "insertmd":
        key = "mdfilename"
    elif op == "insertpptx":
        key = "pptxfilename"
    arg = item.get(key) if key else None
    text = op if arg in (None, "") else f"{op} {arg}"
    if op == "insertpptx" and "slides" in item:
        slides = item["slides"]
        text += f" (slides: {','.join(map(str, slides)) if isinstance(slides, list) else slides})"
    if op in ("chapter", "section", "subsection") and item.get("title"):
        text += f" 「{item['title']}」"
    return text


def item_conditions(item: dict) -> list[tuple[str, dict]]:
    """項目に掛かる when: の一覧（group から引き継いだものを先に）。"""
    conds = [(label, w) for label, w in item.get(INHERITED_WHEN_KEY) or () if isinstance(w, dict)]
    if isinstance(item.get(WHEN_KEY), dict):
        conds.append(("", item[WHEN_KEY]))
    return conds


def judge(item: dict, vars_map: dict, command: str | None) -> tuple[bool, list[str], bool]:
    """(採用するか, 判定の理由, command 条件を評価しなかったか) を返す。"""
    reasons: list[str] = []
    unevaluated = False
    active = True
    for label, when in item_conditions(item):
        prefix = f"{label} " if label else ""
        for key in ("command", "not_command"):
            if key not in when:
                continue
            names = _commands(when[key])
            if command is None:
                unevaluated = True
                reasons.append(f"{prefix}{key}={','.join(names)}")
                continue
            ok = (command in names) if key == "command" else (command not in names)
            reasons.append(f"{prefix}{key}={','.join(names)} {'○' if ok else '×'}")
            active = active and ok
        if "var" in when:
            exprs = _as_list(when["var"])
            ok = any(eval_condition(e, vars_map) for e in exprs)
            reasons.append(f"{prefix}var {' or '.join(exprs)} {'○' if ok else '×'}")
            active = active and ok
    return active, reasons, unevaluated


# ── {{#if}} ブロックの判定 ─────────────────────────────────────────────────


def block_decisions(text: str, vars_map: dict) -> list[tuple[int, str, bool]]:
    """MD の ``{{#if}}`` / ``{{#else}}`` ごとに (行番号, タグ, その区間を残すか) を返す。

    外側のブロックが削られる区間の中は、内側の判定にかかわらず「削る」。
    """
    result: list[tuple[int, str, bool]] = []
    stack: list[tuple[bool, bool]] = []  # (外側が出力中か, 条件)
    fence: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        mf = _RE_FENCE.match(line)
        if fence is not None:
            if mf and mf.group(1)[0] == fence[0] and len(mf.group(1)) >= len(fence) \
                    and line.strip() == mf.group(1):
                fence = None
            continue
        if mf:
            fence = mf.group(1)
            continue
        outer = stack[-1][0] and stack[-1][1] if stack else True
        m_if = _RE_IF.match(line)
        if m_if:
            expr = line.strip()[len("{{#if:"):-2]
            cond = eval_condition(expr, vars_map)
            stack.append((outer, cond))
            result.append((lineno, line.strip(), outer and cond))
            continue
        if _RE_ELSE.match(line) and stack:
            parent, cond = stack[-1]
            stack[-1] = (parent, not cond)
            result.append((lineno, line.strip(), parent and not cond))
            continue
        if _RE_ENDIF.match(line) and stack:
            stack.pop()
    return result


# ── matrix ──────────────────────────────────────────────────────────────────


def matrix_axes(specs: list[str], recipe: dict) -> list[tuple[str, list[str]]]:
    """``--matrix`` の指定を (名前, 値の一覧) にする。不正なら ValueError。"""
    params = recipe.get(PARAMS_KEY) if isinstance(recipe.get(PARAMS_KEY), dict) else {}
    axes: list[tuple[str, list[str]]] = []
    for spec in specs:
        name, sep, values = spec.partition("=")
        name = name.strip()
        if sep:
            vals = [v.strip() for v in values.split(",") if v.strip()]
            if not vals:
                raise ValueError(f"--matrix {spec}: 値を 1 つ以上並べてください")
        else:
            spec_ = params.get(name)
            domain = param_domain(spec_) if isinstance(spec_, dict) else None
            if domain is None:
                raise ValueError(
                    f"--matrix {name}: 値を列挙できません（params: で values / type: bool を宣言するか、"
                    f"--matrix {name}=a,b のように値を並べてください）"
                )
            vals = list(domain)
        axes.append((name, vals))
    return axes


# ── 入口 ────────────────────────────────────────────────────────────────────


def _resolve(raw: dict, overrides: dict[str, str], yaml_path: Path) -> dict:
    recipe = copy.deepcopy(raw)
    recipe = apply_params(recipe, overrides)
    return normalize_recipe(recipe, yaml_path, warn_deprecated=False)


def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)

    yaml_path = resolve_input_path(args)
    if yaml_path is None:
        logging.error("入力ファイルが指定されていません")
        return EXIT_BAD_INPUT
    if not yaml_path.exists():
        logging.error("入力ファイルが見つかりません: %s", yaml_path)
        return EXIT_NOT_FOUND

    try:
        raw = load_yaml(yaml_path, normalize=False, apply_vars=False)
    except Exception as exc:  # noqa: BLE001
        logging.error("YAML 読み込みエラー: %s", exc)
        return EXIT_FAILURE
    if not isinstance(raw, dict):
        logging.error("レシピのトップレベルは辞書である必要があります: %s", yaml_path)
        return EXIT_FAILURE

    command = getattr(args, "for_command", None)
    base_vars = cli_vars()
    try:
        if getattr(args, "matrix", None):
            return _run_matrix(args, raw, base_vars, yaml_path, command)
        recipe = _resolve(raw, base_vars, yaml_path)
        return _run_single(args, recipe, yaml_path, command)
    except (ParamsError, ProcedureNotationError, ValueError) as exc:
        logging.error("%s", exc)
        return EXIT_FAILURE


def _run_single(args: argparse.Namespace, recipe: dict, yaml_path: Path, command: str | None) -> int:
    vars_map = condition_vars(recipe)
    rows = []
    for i, item in enumerate(recipe.get("procedure") or []):
        if not isinstance(item, dict):
            continue
        active, reasons, unevaluated = judge(item, vars_map, command)
        rows.append({"index": i, "item": describe_item(item), "active": active,
                     "conditions": reasons, "command_unevaluated": unevaluated, "_raw": item})

    blocks: dict[str, list] = {}
    if getattr(args, "blocks", False):
        blocks = _collect_blocks(recipe, rows, yaml_path, args, vars_map)

    shown_vars = {k: v for k, v in (recipe.get("vars") or {}).items()
                  if k in (recipe.get(PARAMS_KEY) or {}) or k in cli_vars()}

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok", "command": "explain", "input": str(yaml_path),
            "vars": shown_vars, "for_command": command,
            "items": [{k: v for k, v in r.items() if k != "_raw"} for r in rows],
            "blocks": {f: [{"line": n, "tag": t, "kept": k} for n, t, k in b] for f, b in blocks.items()},
        }, ensure_ascii=False, default=str))
        return EXIT_OK

    print(f"# explain: {yaml_path.name}")
    if shown_vars:
        print("# vars: " + " ".join(f"{k}={v}" for k, v in shown_vars.items()))
    if command:
        print(f"# command: {command}")
    width = len(str(len(rows)))
    for r in rows:
        mark = "✓" if r["active"] else "✗"
        line = f"{r['index']:>{width}} {mark} {r['item']}"
        if r["conditions"]:
            line += "   [" + "; ".join(r["conditions"]) + "]"
        if r["command_unevaluated"]:
            line += " (command 条件は未評価)"
        print(line)
        for n, tag, kept in blocks.get(r["_raw"].get("mdfilename", ""), []) if r["active"] else []:
            print(f"{'':>{width}}     line {n}: {tag} → {'残す' if kept else '削る'}")
    adopted = sum(r["active"] for r in rows)
    print(f"# 採用 {adopted} / 全 {len(rows)} 項目")
    return EXIT_OK


def _collect_blocks(recipe: dict, rows: list[dict], yaml_path: Path, args, vars_map) -> dict[str, list]:
    from md_merge.merge._recipe import iter_insertmd_entries, resolve_input_dirs

    active_items = [r["_raw"] for r in rows if r["active"]]
    workdir = Path(args.workdir).resolve() if getattr(args, "workdir", None) else None
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.ERROR)
    try:
        in_dirs = resolve_input_dirs(recipe, yaml_path, workdir)
        entries = iter_insertmd_entries({**recipe, "procedure": active_items}, in_dirs, yaml_path)
    finally:
        root.setLevel(level)
    blocks: dict[str, list] = {}
    for fname, path in entries:
        if path.is_file():
            decisions = block_decisions(path.read_text(encoding="utf-8-sig"), vars_map)
            if decisions:
                blocks[fname] = decisions
    return blocks


def _run_matrix(args, raw: dict, base_vars: dict, yaml_path: Path, command: str | None) -> int:
    axes = matrix_axes(args.matrix, raw)
    names = [n for n, _ in axes]
    combos = list(itertools.product(*(vals for _, vals in axes)))
    if len(combos) > _MAX_COMBINATIONS:
        raise ValueError(f"--matrix の組み合わせが多すぎます（{len(combos)} > {_MAX_COMBINATIONS}）")

    columns: list[str] = []
    results: list[list[bool]] = []
    labels: list[str] = []
    for combo in combos:
        overrides = {**base_vars, **dict(zip(names, combo))}
        recipe = _resolve(raw, overrides, yaml_path)
        vars_map = condition_vars(recipe)
        col: list[bool] = []
        items = [it for it in recipe.get("procedure") or [] if isinstance(it, dict)]
        for item in items:
            col.append(judge(item, vars_map, command)[0])
        if not labels:
            labels = [describe_item(it) for it in items]
        columns.append(",".join(f"{n}={v}" for n, v in zip(names, combo)))
        results.append(col)

    diff_rows = [i for i in range(len(labels)) if len({col[i] for col in results}) > 1]

    if getattr(args, "json", False):
        print(json.dumps({
            "status": "ok", "command": "explain", "input": str(yaml_path),
            "matrix": columns, "for_command": command,
            "items": [{"index": i, "item": labels[i], "active": [col[i] for col in results]}
                      for i in diff_rows],
            "total": len(labels),
        }, ensure_ascii=False))
        return EXIT_OK

    print(f"# explain --matrix: {yaml_path.name}")
    for c, col in enumerate(columns, start=1):
        print(f"# [{c}] {col}  （採用 {sum(results[c - 1])} 項目）")
    if command:
        print(f"# command: {command}")
    if not diff_rows:
        print(f"# どの組み合わせでも同じ {len(labels)} 項目（差はありません）")
        return EXIT_OK
    width = len(str(len(labels)))
    header = " ".join(f"[{c}]" for c in range(1, len(columns) + 1))
    print(f"{'':>{width}} {header}")
    for i in diff_rows:
        marks = " ".join(f" {'✓' if col[i] else '·'} " for col in results)
        print(f"{i:>{width}} {marks} {labels[i]}")
    print(f"# 値によって変わる項目 {len(diff_rows)} / 全 {len(labels)} 項目")
    return EXIT_OK
