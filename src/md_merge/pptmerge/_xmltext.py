"""Helpers that make text safe to write into PPTX XML via lxml.

lxml refuses strings containing NULL bytes or control characters
("All strings must be XML compatible ..."). PowerPoint exposes a soft line
break (Shift+Enter, ``<a:br>``) as a vertical tab (``\\x0b``) in python-pptx's
``.text``, so a slide title with a soft break would crash when written back
through ``<a:t>.text`` or substituted into notes via ``<__TITLE__>``.
"""
from __future__ import annotations

import re

# Characters XML 1.0 forbids (tab, LF and CR are allowed and handled separately).
INVALID_XML_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
# Soft / hard line breaks (with surrounding spaces) collapsed to one space
# when the text must stay on a single line, e.g. a slide title.
_LINE_BREAK_RE = re.compile(r'[ \t]*[\x0B\r\n]+[ \t]*')


def single_line_text(text: str) -> str:
    """Return *text* as one XML-safe line: line breaks -> one space, control chars removed."""
    return INVALID_XML_RE.sub('', _LINE_BREAK_RE.sub(' ', text)).strip()


def multiline_text(text: str) -> str:
    """Return *text* XML-safe keeping lines: soft returns -> ``\\n``, other control chars removed."""
    return INVALID_XML_RE.sub('', text.replace('\x0B', '\n'))
