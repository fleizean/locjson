"""The CI workflow bounds every job's run time (WR-03).

A job without ``timeout-minutes`` holds a runner for GitHub's 6-hour default
when it hangs, and blocks every job that ``needs`` it. ``.github`` is not in
the sdist, so the test is skipped there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CI = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
_JOB = re.compile(r"  (?P<name>[A-Za-z0-9_-]+):\s*")
_TIMEOUT = re.compile(r"    timeout-minutes: (?P<minutes>[0-9]+)\s*")


def _job_timeouts(text: str) -> dict[str, int | None]:
    jobs: dict[str, int | None] = {}
    current: str | None = None
    in_jobs = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_jobs = line.rstrip() == "jobs:"
            current = None
            continue
        if not in_jobs:
            continue
        if job := _JOB.fullmatch(line):
            current = job["name"]
            jobs[current] = None
        elif current is not None and (timeout := _TIMEOUT.fullmatch(line)):
            jobs[current] = int(timeout["minutes"])
    return jobs


def test_every_ci_job_has_a_timeout() -> None:
    if not CI.is_file():
        pytest.skip(".github is not shipped in the sdist")
    timeouts = _job_timeouts(CI.read_text(encoding="utf-8"))
    assert {"lint", "test", "test-babel", "coverage", "build"} <= timeouts.keys()
    missing = sorted(name for name, minutes in timeouts.items() if minutes is None)
    assert not missing, f"jobs without timeout-minutes: {missing}"
    for name, minutes in timeouts.items():
        assert minutes is not None
        assert 5 <= minutes <= 30, f"{name}: timeout-minutes {minutes}"


def test_the_parser_finds_jobs_and_their_timeouts() -> None:
    text = (
        "on:\n  push:\n\njobs:\n"
        "  a:\n    runs-on: x\n    timeout-minutes: 15\n"
        "    steps:\n      - run: echo\n"
        "  # a comment\n"
        "  b:\n    runs-on: x\n"
        "env:\n  c: d\n"
    )
    assert _job_timeouts(text) == {"a": 15, "b": None}
