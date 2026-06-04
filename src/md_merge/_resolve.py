import logging
import re
from datetime import datetime
from pathlib import Path

import yaml


_DEFAULT_DELIMITER = "."
_DEFAULT_SEPARATOR = ") "

_REF_RE = re.compile(r'\{\{(num|title|label):([^:}]+:[^:}]+:[^}]+)\}\}')


def get_indexer(recipe: dict) -> tuple[str, str]:
    """Return (delimiter, separator) from recipe's indexer section."""
    idx = recipe.get("indexer", {})
    delimiter = idx.get("delimiter", _DEFAULT_DELIMITER)
    separator = idx.get("separator", _DEFAULT_SEPARATOR)
    return delimiter, separator


def resolve_entries(entries: list[dict], delimiter: str, separator: str) -> list[dict]:
    """Add 'number' and 'label' to each entry in-place and return the list."""
    cnum = snum = ssnum = fnum = 0

    for entry in entries:
        id_type = entry.get("identifier_type", "")
        title = entry.get("title", "")

        if id_type == "chapter":
            cnum += 1
            snum = 0
            ssnum = 0
            number = str(cnum)
        elif id_type == "section":
            snum += 1
            ssnum = 0
            number = f"{cnum}{delimiter}{snum}"
        elif id_type == "subsection":
            ssnum += 1
            number = f"{cnum}{delimiter}{snum}{delimiter}{ssnum}"
        elif id_type == "figure":
            fnum += 1
            number = str(fnum)
        else:
            entry["number"] = ""
            entry["label"] = ""
            continue

        entry["number"] = number
        entry["label"] = f"{number}{separator}{title}"

    return entries


def expand_title_label_refs(entries: list[dict], separator: str) -> None:
    """Expand {{num/title/label:FULL_ID}} references in title and label fields (single pass).

    Must be called after resolve_entries() so all number/label values are populated.
    resolved_map values are the same dict objects as entries, so expansions made earlier
    in the loop are visible to later entries that reference them.
    """
    resolved_map = {e["full_id"]: e for e in entries if e.get("full_id")}
    for entry in entries:
        title = entry.get("title", "")
        if not _REF_RE.search(title):
            continue
        new_title = _expand_ref_in_str(title, resolved_map)
        entry["title"] = new_title
        number = entry.get("number", "")
        if number:
            entry["label"] = f"{number}{separator}{new_title}"


def _expand_ref_in_str(text: str, resolved_map: dict[str, dict]) -> str:
    def replace(m: re.Match) -> str:
        ref_type, full_id = m.group(1), m.group(2)
        entry = resolved_map.get(full_id)
        if entry is None:
            logging.warning(
                "idresolve: 参照 {{%s:%s}} が見つかりません — そのまま残します",
                ref_type, full_id,
            )
            return m.group(0)
        if ref_type == "num":
            return entry.get("number", "")
        if ref_type == "title":
            return entry.get("title", "")
        return entry.get("label", "")
    return _REF_RE.sub(replace, text)


def write_resolved(
    resolved_path: Path,
    entries: list[dict],
    yaml_path: Path,
    yaml_dir: Path,
    inventory_path: Path,
    delimiter: str,
    separator: str,
) -> None:
    try:
        config_yaml_display = yaml_path.relative_to(yaml_dir).as_posix()
    except ValueError:
        config_yaml_display = yaml_path.as_posix()

    try:
        inventory_display = inventory_path.relative_to(yaml_dir).as_posix()
    except ValueError:
        inventory_display = inventory_path.as_posix()

    data = {
        "schema_version": 1,
        "kind": "id_map",
        "document": {
            "document_id": "<DUMMY>",
            "title": "<DUMMY>",
        },
        "generated": {
            "by": "md-merge",
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "source": {
            "config_yaml": config_yaml_display,
            "id_inventory_yaml": inventory_display,
        },
        "numbering": {
            "profile": "default",
            "chapter_enabled": True,
            "section_numbering": "chapter_section",
            "image_numbering": "global",
        },
        "entries": entries,
    }
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
