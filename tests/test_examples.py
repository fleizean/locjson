"""The dependency-free examples in ``examples/`` run and print what they promise.

Each script runs in a subprocess, from its own folder, with warnings turned
into errors. Its output must equal the block marked ``<!-- expected-output -->``
in the example's README, so the documented output cannot drift. The testing
example's own pytest suite runs in a subprocess too.

The FastAPI, Flask and Django examples need third-party packages and run in the
``examples-frameworks`` CI job instead.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TIMEOUT = 120.0

_EXPECTED_BLOCK = re.compile(
    r"^<!-- expected-output -->\n```text\n(.*?)^```$", re.MULTILINE | re.DOTALL
)


def _run(example: str, *args: str) -> str:
    """Run ``python -W error <args>`` in ``examples/<example>``; return stdout."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("LOCJSON_STRICT", None)
    try:
        result = subprocess.run(
            [sys.executable, "-W", "error", *args],
            cwd=EXAMPLES / example,
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=True,
            timeout=TIMEOUT,
        )
    except subprocess.CalledProcessError as error:
        pytest.fail(
            f"{example}: exit code {error.returncode}\n"
            f"--- stdout ---\n{error.stdout}\n--- stderr ---\n{error.stderr}"
        )
    assert result.stderr == ""
    return result.stdout


def _expected_output(example: str) -> str:
    readme = (EXAMPLES / example / "README.md").read_text(encoding="utf-8")
    blocks = _EXPECTED_BLOCK.findall(readme)
    assert len(blocks) == 1, f"{example}/README.md needs one expected-output block"
    return str(blocks[0])


@pytest.mark.parametrize(
    ("example", "script"),
    [
        ("quickstart", "main.py"),
        ("namespaced", "main.py"),
        ("background-jobs", "send_digests.py"),
    ],
)
def test_example_prints_its_readme_output(example: str, script: str) -> None:
    printed = _run(example, script)
    assert printed.strip("\n") == _expected_output(example).strip("\n")


def test_testing_example_script_runs() -> None:
    printed = _run("testing", "shop.py")
    assert "Siparişiniz için teşekkürler, Ada!" in printed


def test_testing_example_suite_passes() -> None:
    printed = _run("testing", "-m", "pytest", "-p", "no:cacheprovider", "-q")
    assert re.search(r"^\d+ passed in ", printed, re.MULTILINE), printed
    assert "failed" not in printed


def test_expected_output_blocks_are_found() -> None:
    text = "Intro\n\n<!-- expected-output -->\n```text\na\nb\n```\n\n```text\nc\n```\n"
    assert _EXPECTED_BLOCK.findall(text) == ["a\nb\n"]
