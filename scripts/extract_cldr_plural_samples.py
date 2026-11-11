"""Extract the CLDR 49 plural rules and samples into a test fixture.

Run once by hand, never in CI or by the tests::

    .venv/Scripts/python scripts/extract_cldr_plural_samples.py

It downloads two pinned files of the ``cldr-json`` tag ``49.0.0``
(``plurals.json`` and ``parentLocales.json``) and writes
``tests/data/cldr49_plural_samples.json``. To work offline, pass local copies
of the same two files instead::

    python scripts/extract_cldr_plural_samples.py plurals.json parentLocales.json

The output is deterministic: running the script again gives the same bytes.

Sample handling:

* the ellipsis token (``…`` or ``...``) is dropped;
* tokens in compact-exponent notation (``1c6``, ``1.1c3``) are skipped and
  counted, because locjson sets the ``c`` and ``e`` operands to 0;
* ``a~b`` ranges are expanded in ascending order: integers in steps of 1,
  decimals in steps of ``10**-k`` where ``k`` is the number of fraction
  digits of ``a``, each value written with exactly ``k`` fraction digits;
  at most the first 100 values of a range are kept;
* repeated samples keep their first occurrence.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

CLDR_TAG = "49.0.0"
BASE_URL = (
    "https://raw.githubusercontent.com/unicode-org/cldr-json/"
    f"{CLDR_TAG}/cldr-json/cldr-core/supplemental"
)
PLURALS_URL = f"{BASE_URL}/plurals.json"
PARENT_LOCALES_URL = f"{BASE_URL}/parentLocales.json"

TAGS = (
    "en",
    "tr",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "pt-PT",
    "nl",
    "ru",
    "uk",
    "pl",
    "cs",
    "ar",
    "he",
    "ja",
    "zh",
    "ko",
)
"""The 18 rule tags of the built-in plural rules."""

RANGE_LIMIT = 100
"""The most values kept from one ``a~b`` range."""

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "data"
    / "cldr49_plural_samples.json"
)

_PREFIX = "pluralRule-count-"
_ELLIPSIS = frozenset({"…", "..."})


def fetch(url: str) -> Any:
    """Download and parse one JSON document.

    Args:
        url: A pinned https URL.

    Returns:
        The parsed document.
    """
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def read(path: str) -> Any:
    """Parse one local JSON document.

    Args:
        path: The path of a local copy of a pinned file.

    Returns:
        The parsed document.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expand_range(start: str, stop: str) -> list[str]:
    """Expand an ``a~b`` sample range in ascending order.

    Args:
        start: The first value, such as ``"2"`` or ``"0.0"``.
        stop: The last value, inclusive.

    Returns:
        At most :data:`RANGE_LIMIT` values, as sample strings.
    """
    if "." not in start:
        last = min(int(stop), int(start) + RANGE_LIMIT - 1)
        return [str(value) for value in range(int(start), last + 1)]
    digits = len(start.partition(".")[2])
    step = Decimal(1).scaleb(-digits)
    value, end = Decimal(start), Decimal(stop)
    values: list[str] = []
    while value <= end and len(values) < RANGE_LIMIT:
        values.append(f"{value:.{digits}f}")
        value += step
    return values


def parse_samples(text: str) -> tuple[list[str], int]:
    """Read the samples of one rule.

    Args:
        text: The rule text after its first ``@``, such as
            ``"integer 1, 21~23, … @decimal 0.0~1.5"`` with the leading ``@``
            removed.

    Returns:
        The samples in source order without repeats, and the number of
        compact-exponent tokens skipped.
    """
    samples: dict[str, None] = {}
    skipped = 0
    for section in text.split("@"):
        _, _, body = section.strip().partition(" ")
        for raw in body.split(","):
            token = raw.strip()
            if not token or token in _ELLIPSIS:
                continue
            if "c" in token or "e" in token:
                skipped += 1
                continue
            start, tilde, stop = token.partition("~")
            values = expand_range(start, stop) if tilde else [token]
            samples.update(dict.fromkeys(values))
    return list(samples), skipped


def extract(plurals: Any, parent_locales: Any) -> dict[str, Any]:
    """Build the fixture from the two CLDR documents.

    Args:
        plurals: The parsed ``plurals.json``.
        parent_locales: The parsed ``parentLocales.json``.

    Returns:
        The fixture document.
    """
    cardinal = plurals["supplemental"]["plurals-type-cardinal"]
    rules: dict[str, dict[str, str]] = {}
    samples: dict[str, dict[str, list[str]]] = {}
    skipped = 0
    for tag in TAGS:
        rules[tag] = {}
        samples[tag] = {}
        for name, text in cardinal[tag].items():
            category = name.removeprefix(_PREFIX)
            expression, _, annotations = text.partition("@")
            rules[tag][category] = expression.strip()
            values, count = parse_samples(annotations)
            samples[tag][category] = values
            skipped += count
    parents = parent_locales["supplemental"]["parentLocales"]["parentLocale"]
    children = sorted(
        child.replace("_", "-")
        for child, parent in parents.items()
        if parent == "pt-PT"
    )
    return {
        "cldr": CLDR_TAG,
        "sources": [PLURALS_URL, PARENT_LOCALES_URL],
        "skipped_compact_samples": skipped,
        "pt_pt_children": children,
        "rules": rules,
        "samples": samples,
    }


def main(argv: list[str]) -> int:
    """Download (or read) the CLDR files and write the fixture.

    Args:
        argv: The command-line arguments after the script name: nothing, or
            local copies of ``plurals.json`` and ``parentLocales.json``.

    Returns:
        The exit status.
    """
    if argv and len(argv) != 2:  # noqa: PLR2004
        print(__doc__)
        return 2
    if argv:
        plurals, parent_locales = read(argv[0]), read(argv[1])
    else:
        plurals, parent_locales = fetch(PLURALS_URL), fetch(PARENT_LOCALES_URL)
    fixture = extract(plurals, parent_locales)
    text = json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    samples: dict[str, dict[str, list[str]]] = fixture["samples"]
    total = sum(len(values) for forms in samples.values() for values in forms.values())
    skipped = fixture["skipped_compact_samples"]
    print(f"wrote {OUTPUT.name}: {total} samples, {skipped} compact samples skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
