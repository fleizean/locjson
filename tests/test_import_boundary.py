"""Import-boundary guard: ``import locjson`` must stay lightweight (PKG-03)."""

from __future__ import annotations

import json
import subprocess
import sys

import locjson
import locjson._version

FORBIDDEN = (
    "locjson.cli",
    "locjson.analysis",
    "argparse",
    "ast",
    "tomllib",
    "babel",
    "watchfiles",
    "importlib.metadata",
)
# On 3.14 `logging` pulls in `ast`; `dataclasses` and `inspect` do on every version.
EARLY_WARNING = ("logging", "dataclasses", "inspect")


def test_import_locjson_is_lightweight() -> None:
    code = "import sys, json, locjson; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    loaded = set(json.loads(out))
    leaked = {
        name
        for name in loaded
        for banned in FORBIDDEN + EARLY_WARNING
        if name == banned or name.startswith(banned + ".")
    }
    assert not leaked, f"import locjson pulled in: {sorted(leaked)}"


def test_version_is_static() -> None:
    assert isinstance(locjson.__version__, str)
    assert locjson.__version__
    assert locjson.__version__ == locjson._version.__version__
    assert "__version__" in locjson.__all__
