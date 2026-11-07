#!/usr/bin/env python3
"""Check that every school in ``src/blackboard_sync/schools.py`` still answers as Blackboard Learn.

    python3 scripts/verify-schools.py [--timeout SECONDS]

Each address gets one request to Blackboard's public, sign-in-free
``/learn/api/public/v1/system/version``. A Blackboard Learn host answers with JSON that has a
``learn`` entry. Exit status 1 when any address does not, so a scheduled run can report it.
Run it by hand after adding a school; it is not part of the tests, which never use the network.
Needs ``requests`` (already a dependency of the app).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blackboard_sync.schools import SCHOOLS  # noqa: E402

VERSION_PATH = "/learn/api/public/v1/system/version"


def check(url: str, timeout: float) -> str:
    """"" when ``url`` is a Blackboard Learn host, else why it is not."""
    try:
        response = requests.get(url + VERSION_PATH, timeout=timeout,
                                headers={"User-Agent": "blackboard-sync-verify"})
        if response.status_code != 200:
            return f"HTTP {response.status_code}"
        return "" if "learn" in response.json() else "no Blackboard Learn version in the answer"
    except (requests.RequestException, ValueError) as exc:
        return type(exc).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    failed = 0
    for school in SCHOOLS:
        problem = check(school.url, args.timeout)
        failed += bool(problem)
        print(f"{'FAIL' if problem else 'ok  '} {school.url}  {school.name}" + (f"  ({problem})" if problem else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
