"""The README quick start runs and prints what its comments promise.

README.md marks its executable parts with HTML comments:

- ``<!-- file: locales/<name>.json -->`` before a JSON fence names the file the
  fence holds. The test writes it under ``tmp_path``.
- ``<!-- quickstart -->`` before the Python quick start. The test runs it in
  ``tmp_path`` and compares every printed line with the ``# -> <expected>``
  comment on the ``print`` line, in order.
- ``<!-- exec -->`` before every other runnable Python snippet. Each one runs
  in a copy of the quick start's namespace and in a copy of the current
  context, so a ``set_locale()`` in one snippet cannot leak into the next. Its
  output is checked like the quick start's, and every ``test_*`` function it
  defines is called.
- ``<!-- no-exec -->`` before a snippet that needs a third-party framework
  (FastAPI). It is only parsed with :func:`ast.parse`.

Every Python fence carries one of these markers, so a new README example
cannot go untested.
"""

from __future__ import annotations

import ast
import contextlib
import contextvars
import io
import re
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

import locjson

if TYPE_CHECKING:
    from collections.abc import Iterator

README = Path(__file__).resolve().parent.parent / "README.md"

_MARKER = re.compile(r"^<!--\s*(.*?)\s*-->$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_EXPECTED = re.compile(r"#\s*->\s?(.*)$")


class Block(NamedTuple):
    """One fenced code block and the HTML-comment marker right above it."""

    marker: str | None
    lang: str
    code: str


def _fenced_blocks(text: str) -> list[Block]:
    """Return every fenced block, with the marker on the closest line above."""
    blocks: list[Block] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        opening = _FENCE.match(lines[i])
        if opening is None or not opening.group(1):
            i += 1
            continue
        marker = None
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and (found := _MARKER.match(lines[j].strip())) is not None:
            marker = found.group(1)
        end = i + 1
        while end < len(lines) and lines[end].rstrip() != "```":
            end += 1
        code = "\n".join(lines[i + 1 : end]) + "\n"
        blocks.append(Block(marker, opening.group(1), code))
        i = end + 1
    return blocks


def _expected_lines(code: str) -> list[str]:
    """Return the ``# -> <expected>`` comments of ``code``, in order."""
    return [
        found.group(1).rstrip()
        for line in code.splitlines()
        if (found := _EXPECTED.search(line)) is not None
    ]


def _readme_blocks() -> list[Block]:
    return _fenced_blocks(README.read_text(encoding="utf-8"))


def _write_catalogs(blocks: list[Block], root: Path) -> list[str]:
    written: list[str] = []
    for block in blocks:
        if block.marker is None or not block.marker.startswith("file:"):
            continue
        assert block.lang == "json", block.marker
        relative = block.marker.removeprefix("file:").strip()
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.code, encoding="utf-8")
        written.append(relative)
    return written


def _run(code: str, namespace: dict[str, object]) -> list[str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, str(README), "exec"), namespace)  # noqa: S102
    return out.getvalue().splitlines()


@pytest.fixture(autouse=True)
def _no_default_localizer() -> Iterator[None]:
    locjson._DEFAULT.localizer = None
    yield
    locjson._DEFAULT.localizer = None


def test_fence_parser_reads_markers_and_expectations() -> None:
    text = (
        "Intro\n\n"
        "<!-- file: locales/en.json -->\n"
        '```json\n{"a": "b"}\n```\n\n'
        "```python\nprint(1)  # -> 1\nx = 2\nprint(x)  #->2\n```\n"
        "```\nplain\n```\n"
    )
    blocks = _fenced_blocks(text)
    assert blocks == [
        Block("file: locales/en.json", "json", '{"a": "b"}\n'),
        Block(None, "python", "print(1)  # -> 1\nx = 2\nprint(x)  #->2\n"),
    ]
    assert _expected_lines(blocks[1].code) == ["1", "2"]


def _run_quickstart(
    blocks: list[Block], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    written = _write_catalogs(blocks, tmp_path)
    assert written == ["locales/en.json", "locales/tr.json"]
    quickstart = [block for block in blocks if block.marker == "quickstart"]
    assert len(quickstart) == 1
    assert quickstart[0].lang == "python"
    code = quickstart[0].code
    expected = _expected_lines(code)
    assert "Hello, Enes!" in expected

    monkeypatch.delenv("LOCJSON_STRICT", raising=False)
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {"__name__": "readme_quickstart"}
    printed = _run(code, namespace)

    assert printed == expected
    return namespace


def _run_snippet(code: str, base: dict[str, object]) -> list[str]:
    namespace = dict(base)
    before = set(namespace)
    printed = _run(code, namespace)
    for name in sorted(set(namespace) - before):
        test = namespace[name]
        if name.startswith("test_") and callable(test):
            test()
    return printed


def test_readme_quickstart_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_quickstart(_readme_blocks(), tmp_path, monkeypatch)


def test_every_python_fence_is_marked() -> None:
    markers = [block.marker for block in _readme_blocks() if block.lang == "python"]
    assert markers
    assert all(m in {"quickstart", "exec", "no-exec"} for m in markers), markers


def test_readme_snippets_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocks = _readme_blocks()
    base = _run_quickstart(blocks, tmp_path, monkeypatch)
    snippets = [block.code for block in blocks if block.marker == "exec"]
    assert len(snippets) >= 5

    for code in snippets:
        locjson._DEFAULT.localizer = None
        printed = contextvars.copy_context().run(_run_snippet, code, base)
        assert printed == _expected_lines(code), code


def test_readme_snippet_tests_are_called() -> None:
    calls: list[str] = []
    code = "def test_one():\n    calls.append('one')\nprint('x')  # -> x\n"
    printed = _run_snippet(code, {"calls": calls})
    assert printed == ["x"]
    assert calls == ["one"]


def test_framework_snippets_parse() -> None:
    snippets = [block.code for block in _readme_blocks() if block.marker == "no-exec"]
    assert snippets
    for code in snippets:
        ast.parse(code)
    assert any('@app.middleware("http")' in code for code in snippets)


def test_readme_is_utf8_without_email_addresses() -> None:
    text = README.read_text(encoding="utf-8")
    assert "ı" in text
    assert "Yağız" in text
    assert re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text) is None
