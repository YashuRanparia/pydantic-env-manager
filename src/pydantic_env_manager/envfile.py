"""Line-preserving merge of VarSpecs into an existing .env file."""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from .render import env_line
from .schema import VarSpec

EXTRAS_HEADING = "# Your additional env variables"
_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][\w.-]*)\s*=(.*)$", re.S)

# item: (key or None, lines, leading_comment_lines)
Item = Tuple[Optional[str], List[str], List[str]]


def _closes(rest: str, quote: str) -> bool:
    """True if `rest` contains the closing quote for a value that opened with `quote`."""
    i = 0
    while i < len(rest):
        if quote == '"' and rest[i] == "\\":
            i += 2
            continue
        if rest[i] == quote:
            return True
        i += 1
    return False


def _parse(text: str) -> List[Item]:
    lines = re.findall(r"[^\n]*\n|[^\n]+", text)
    items: List[Item] = []
    comments: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _KEY.match(line.rstrip("\r\n"))
        if m:
            chunk = [line]
            value = m.group(2).lstrip()
            if value[:1] in ("'", '"') and not _closes(value[1:], value[0]):
                while i + 1 < len(lines):  # multi-line quoted value
                    i += 1
                    chunk.append(lines[i])
                    if _closes(lines[i], value[0]):
                        break
            items.append((m.group(1), chunk, comments))
            comments = []
        elif line.lstrip().startswith("#"):
            comments.append(line)
        else:  # blank or unparseable: keep verbatim
            items.append((None, comments + [line], []))
            comments = []
        i += 1
    if comments:
        items.append((None, comments, []))
    return items


def _norm(key: str, case_sensitive: bool) -> str:
    return key if case_sensitive else key.upper()


def keys_in(text: str, case_sensitive: bool = False) -> Set[str]:
    return {_norm(k, case_sensitive) for k, _, _ in _parse(text) if k}


def merge(text: str, specs: List[VarSpec], case_sensitive: bool = False) -> str:
    """Append missing keys and move unknown keys under a trailing heading.

    Existing values, comments and order of known keys are untouched.
    """
    eol = "\r\n" if "\r\n" in text else "\n"
    known = {s.key for s in specs}
    kept: List[str] = []
    extras: List[str] = []
    present: Set[str] = set()
    for key, lines, comments in _parse(text):
        if key is None:
            kept += lines
        elif _norm(key, case_sensitive) in known:
            present.add(_norm(key, case_sensitive))
            kept += comments + lines
        else:
            extras += [c for c in comments if c.strip() != EXTRAS_HEADING] + lines

    def nl(lines: List[str]) -> List[str]:
        return [x if x.endswith("\n") else x + eol for x in lines]

    kept, extras = nl(kept), nl(extras)
    missing = [s for s in specs if s.key not in present]
    if not missing and not extras:
        return text
    while kept and not kept[-1].strip():  # trailing blanks are regenerated below
        kept.pop()
    out = kept
    if missing:
        block: List[str] = []
        for s in missing:
            block += ([f"# REQUIRED{eol}"] if s.required else []) + [env_line(s) + eol]
        out += ([eol] if out else []) + block
    if extras:
        out += ([eol] if out else []) + [EXTRAS_HEADING + eol] + extras
    return "".join(out)


def missing_and_extra(text: str, specs: List[VarSpec], case_sensitive: bool = False) -> Tuple[List[str], List[str]]:
    have = keys_in(text, case_sensitive)
    known = {s.key for s in specs}
    return [s.key for s in specs if s.key not in have], sorted(have - known)
