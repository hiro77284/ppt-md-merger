import logging
import re
from datetime import datetime
from pathlib import Path

import yaml

_ID_RE = re.compile(r'\{\{#id:([^:}]+):([^:}]+):([^}]+)\}\}')
_SOURCE_COMMENT_RE = re.compile(r'^<!-- source: (.+) -->$')
_HEADING_RE = re.compile(r'^(#{1,3})\s+(.*)')
_KNOWN_TYPES = frozenset({"chapter", "section", "subsection", "image", "var"})

_EXPECTED_HEADING_LEVEL = {"chapter": 1, "section": 2, "subsection": 3}


def _extract_heading(line: str) -> tuple[str | None, int]:
    """Return (title_text, heading_level) for #/##/### lines, or (None, 0)."""
    m = _HEADING_RE.match(line.rstrip())
    if not m:
        return None, 0
    return m.group(2).strip(), len(m.group(1))


def extract_entries(
    merged_content: str,
    merged_path: Path,
    yaml_dir: Path,
) -> list[dict]:
    """Scan *merged_content* for {{#id:...}} markers and return inventory entries.

    *merged_path* and source file paths are recorded relative to *yaml_dir*.
    Current source file is tracked via <!-- source: ... --> comments that
    expand_md inserts at the top of each expanded file.

    The line immediately following each ID marker is inspected for a heading
    (#/##/###) to populate the title field.
    """
    entries: list[dict] = []
    current_source: str = "<DUMMY>"

    try:
        merged_display = merged_path.relative_to(yaml_dir).as_posix()
    except ValueError:
        merged_display = merged_path.as_posix()

    lines = merged_content.splitlines()

    for i, line in enumerate(lines):
        line_no = i + 1

        m_src = _SOURCE_COMMENT_RE.match(line.rstrip())
        if m_src:
            current_source = m_src.group(1)
            continue

        matches = list(_ID_RE.finditer(line))
        if not matches:
            continue

        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        heading_text, heading_level = _extract_heading(next_line)

        for m in matches:
            id_type, part_id, local_id = m.group(1), m.group(2), m.group(3)

            if id_type not in _KNOWN_TYPES:
                logging.warning(
                    "Unknown identifier_type %r in {{#id:%s:%s:%s}} — accepted",
                    id_type, id_type, part_id, local_id,
                )

            if heading_text is None:
                logging.warning(
                    "No heading found after {{#id:%s:%s:%s}} at line %d — using 'TITLE NOT FOUND'",
                    id_type, part_id, local_id, line_no,
                )
                title = "TITLE NOT FOUND"
            else:
                title = heading_text
                expected_level = _EXPECTED_HEADING_LEVEL.get(id_type)
                if expected_level is not None and heading_level != expected_level:
                    logging.warning(
                        "Heading level mismatch for %s {{#id:%s:%s:%s}} at line %d:"
                        " expected %s, got %s",
                        id_type, id_type, part_id, local_id, line_no,
                        "#" * expected_level, "#" * heading_level,
                    )

            entries.append({
                "full_id": f"{id_type}:{part_id}:{local_id}",
                "identifier_type": id_type,
                "part_id": part_id,
                "local_id": local_id,
                "title": title,
                "source": {
                    "pptx": "<DUMMY>",
                    "md": current_source,
                },
                "location": {
                    "file": merged_display,
                    "line": line_no,
                },
            })

    return entries


def write_inventory(
    inventory_path: Path,
    entries: list[dict],
    yaml_path: Path,
    yaml_dir: Path,
) -> None:
    try:
        config_yaml_display = yaml_path.relative_to(yaml_dir).as_posix()
    except ValueError:
        config_yaml_display = yaml_path.as_posix()

    data = {
        "schema_version": 1,
        "kind": "id_inventory",
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
        },
        "entries": entries,
    }
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
