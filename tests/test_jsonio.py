"""JSON-level catalog faults, reported with the file and a JSON pointer (CAT-06).

Every byte-level fixture is written with ``Path.write_bytes`` under
``tmp_path``. Committed fixtures would be rewritten by ``.gitattributes``
(``eol=lf``), which would hide CRLF and BOM handling (RESEARCH Pitfall 10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from locjson import InvalidCatalogError, Localizer, LocJsonError, RawSource
from locjson._jsonio import JsonObject, NonFinite, read_json
from locjson.catalog import MAX_DEPTH, build_catalog

if TYPE_CHECKING:
    from pathlib import Path

BOM = b"\xef\xbb\xbf"


def _locales(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "locales"
    root.mkdir()
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    return root


def _issues(raw: bytes, origin: str = "en.json") -> list[tuple[str, str, str]]:
    data = read_json(raw, origin=origin)
    result = build_catalog("en", [RawSource(data, origin)])
    assert (result.catalog is None) == bool(result.issues)
    return [(i.path, i.pointer, i.problem) for i in result.issues]


def _nested(levels: int) -> bytes:
    """Return ``levels`` nested objects whose innermost value is a string."""
    return b'{"k":' * (levels - 1) + b'{"k":"x"}' + b"}" * (levels - 1)


# --- end to end through Localizer -------------------------------------------


def test_duplicate_key_fails_at_first_lookup(tmp_path: Path) -> None:
    root = _locales(tmp_path, {"en.json": b'{"nav": {"home": "A", "home": "B"}}'})
    l10n = Localizer(root)
    with pytest.raises(InvalidCatalogError) as info:
        l10n.t("nav.home")
    error = info.value
    assert isinstance(error, LocJsonError)
    assert (error.path, error.pointer, error.locale) == ("en.json", "/nav/home", "en")
    assert error.problem == "duplicate key 'home'"
    assert str(error) == "en.json: /nav/home: duplicate key 'home'"


def test_turkish_text_round_trips_unescaped(tmp_path: Path) -> None:
    city = "İstanbul'da ılık bir akşam"
    raw = ('{"city": "' + city + '", "dotted": "İı / Iı"}').encode()
    root = _locales(tmp_path, {"en.json": b'{"city": "x"}', "tr.json": raw})
    l10n = Localizer(root)
    assert l10n.t("city", locale="tr") == city
    assert l10n.t("dotted", locale="tr") == "İı / Iı"


def test_one_bom_and_crlf_load(tmp_path: Path) -> None:
    raw = BOM + b'{\r\n  "nav": {\r\n    "home": "Home"\r\n  }\r\n}\r\n'
    root = _locales(tmp_path, {"en.json": raw})
    assert Localizer(root).t("nav.home") == "Home"


def test_two_boms_fail_at_first_lookup(tmp_path: Path) -> None:
    root = _locales(tmp_path, {"en.json": BOM + BOM + b'{"a": "b"}'})
    with pytest.raises(InvalidCatalogError) as info:
        Localizer(root).t("a")
    assert (info.value.path, info.value.pointer) == ("en.json", "")
    assert "BOM" in info.value.problem
    assert str(info.value).startswith("en.json: line 1, column 1: ")


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        pytest.param(
            b'{"a": "\xfd"}', "file is not valid UTF-8", id="cp1254-dotless-i"
        ),
        pytest.param(b"", "line 1, column 1: Expecting value", id="zero-bytes"),
        pytest.param(b"\xff\xfe{\x00}\x00", "file is not valid UTF-8", id="utf-16"),
    ],
)
def test_undecodable_files_point_at_the_document(
    tmp_path: Path, raw: bytes, problem: str
) -> None:
    root = _locales(tmp_path, {"en.json": raw})
    with pytest.raises(InvalidCatalogError) as info:
        Localizer(root).t("a")
    assert (info.value.path, info.value.pointer) == ("en.json", "")
    assert info.value.problem == problem
    assert str(info.value) == f"en.json: {problem}"


def test_cp1254_bytes_fail_regardless_of_code_page() -> None:
    raw = "İstanbul ılık".encode("cp1254")
    with pytest.raises(InvalidCatalogError, match="not valid UTF-8"):
        read_json(b'{"a": "' + raw + b'"}', origin="tr.json")


# --- markers ----------------------------------------------------------------


def test_objects_record_each_repetition() -> None:
    data = read_json(b'{"a": 1, "b": 2, "a": 3, "a": 4}', origin="en.json")
    assert isinstance(data, JsonObject)
    assert data == {"a": 4, "b": 2}
    assert data.duplicates == ("a", "a")
    inner = read_json(b'{"x": {"y": 1}}', origin="en.json")
    assert isinstance(inner, JsonObject)
    assert inner.duplicates == ()
    assert isinstance(inner["x"], JsonObject)


def test_non_finite_constants_become_markers() -> None:
    data = read_json(b'{"n": NaN, "i": Infinity, "m": -Infinity}', origin="en.json")
    assert isinstance(data, dict)
    names = {key: value.name for key, value in data.items()}
    assert names == {"n": "NaN", "i": "Infinity", "m": "-Infinity"}
    assert all(isinstance(value, NonFinite) for value in data.values())
    assert repr(data["n"]) == "NonFinite('NaN')"


# --- pointers from build_catalog ----------------------------------------------


def test_repeated_duplicate_is_reported_once_per_key() -> None:
    raw = b'{"a": "1", "a": "2", "a": "3", "g": {"b": "1", "b": "2"}}'
    assert _issues(raw) == [
        ("en.json", "/a", "duplicate key 'a'"),
        ("en.json", "/g/b", "duplicate key 'b'"),
    ]


def test_duplicate_key_pointer_is_escaped() -> None:
    assert _issues(b'{"a/b": "1", "a/b": "2"}') == [
        ("en.json", "/a~1b", "duplicate key 'a/b'"),
    ]


def test_non_finite_numbers_are_reported_at_their_pointer() -> None:
    raw = b'{"n": NaN, "i": Infinity, "m": -Infinity, "f": 1e400, "ok": "x"}'
    assert _issues(raw) == [
        ("en.json", "/f", "expected a string or object, got float"),
        ("en.json", "/i", "Infinity is not valid JSON"),
        ("en.json", "/m", "-Infinity is not valid JSON"),
        ("en.json", "/n", "NaN is not valid JSON"),
    ]


def test_lone_surrogates_are_reported_at_their_pointer() -> None:
    raw = b'{"v": "a\\ud800b", "\\udfff": "x", "ok": "\\ud83d\\ude00"}'
    issues = _issues(raw)
    assert issues == [
        ("en.json", "/\\udfff", "lone surrogate in key"),
        ("en.json", "/v", "lone surrogate in value"),
    ]
    for path, pointer, problem in issues:
        # Diagnostics must stay encodable even though the key was not.
        f"{path}: {pointer}: {problem}".encode()


def test_surrogate_pair_is_a_real_character(tmp_path: Path) -> None:
    root = _locales(tmp_path, {"en.json": b'{"smile": "\\ud83d\\ude00"}'})
    assert Localizer(root).t("smile") == "\U0001f600"


def test_duplicate_key_with_surrogate_is_reported_encodably() -> None:
    issues = _issues(b'{"g": {"\\ud800": "1", "\\ud800": "2"}}')
    assert ("en.json", "/g/\\ud800", "duplicate key '\\ud800'") in issues
    for path, pointer, problem in issues:
        f"{path}: {pointer}: {problem}".encode()


# --- depth --------------------------------------------------------------------


def test_max_depth_is_32() -> None:
    assert MAX_DEPTH == 32


def test_32_levels_load(tmp_path: Path) -> None:
    root = _locales(tmp_path, {"en.json": _nested(32)})
    assert Localizer(root).t(".".join(["k"] * 32)) == "x"


def test_33_levels_are_reported_at_the_deepest_object() -> None:
    assert _issues(_nested(33)) == [
        ("en.json", "/k" * 32, "nesting deeper than 32 levels"),
    ]


def test_parser_recursion_is_an_invalid_catalog(tmp_path: Path) -> None:
    root = _locales(tmp_path, {"en.json": _nested(100_000)})
    with pytest.raises(InvalidCatalogError) as info:
        Localizer(root).t("k")
    assert info.value.path == "en.json"
    assert info.value.pointer in {"", "/k" * 32}


def test_read_json_turns_recursion_error_into_invalid_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise RecursionError

    monkeypatch.setattr("locjson._jsonio.json.loads", explode)
    with pytest.raises(InvalidCatalogError) as info:
        read_json(b"{}", origin="en.json")
    assert (info.value.path, info.value.pointer) == ("en.json", "")
    assert info.value.problem == "JSON nesting is too deep"
