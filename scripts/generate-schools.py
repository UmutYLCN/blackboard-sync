#!/usr/bin/env python3
"""Write the iPad app's school list from ``src/blackboard_sync/schools.py``.

    python3 scripts/generate-schools.py          # rewrite Schools.swift
    python3 scripts/generate-schools.py --check  # exit 1 when Schools.swift is out of date

Only the part between the BEGIN GENERATED and END GENERATED lines changes. It needs nothing
but the standard library.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "blackboard_sync" / "schools.py"
SWIFT = ROOT / "ios" / "BlackboardSync" / "BlackboardSync" / "Core" / "Schools.swift"
BEGIN = "    // BEGIN GENERATED"
END = "    // END GENERATED"


def load_schools():
    spec = importlib.util.spec_from_file_location("blackboard_sync_schools", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def literal(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def array(items) -> str:
    return "[" + ", ".join(literal(item) for item in items) + "]"


def generated(schools) -> str:
    """The Swift lines between the markers."""
    lines = ["    static let all: [KnownSchool] = ["]
    for school in schools.SCHOOLS:
        lines.append(
            f"        KnownSchool(name: {literal(school.name)}, url: {literal(school.url)}, "
            f"domain: {literal(school.domain)},\n"
            f"                    localNames: {array(school.local_names)}, aliases: {array(school.aliases)}),")
    lines.append("    ]")
    return "\n".join(lines)


def render(text: str, schools) -> str:
    """``text`` with the generated part replaced."""
    start = text.index(BEGIN)
    after_begin = text.index("\n", start) + 1
    end = text.index(END)
    return text[:after_begin] + generated(schools) + "\n" + text[end:]


def main(argv: list[str]) -> int:
    current = SWIFT.read_text(encoding="utf-8")
    updated = render(current, load_schools())
    if "--check" in argv:
        if updated != current:
            print(f"{SWIFT.relative_to(ROOT)} is out of date; run scripts/generate-schools.py", file=sys.stderr)
            return 1
        return 0
    if updated != current:
        SWIFT.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Wrote {SWIFT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
