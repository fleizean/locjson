"""The optional Babel extra (PLUR-05): coverage, fallbacks and lazy import."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import pytest

from locjson import DictLoader, Localizer
from locjson.plural.operands import plural_operands
from locjson.plural.resolver import _lookup, rule_for
from locjson.plural.rules import BUILTIN_RULES

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from locjson.plural.rules import RuleSpec
    from tests.conftest import IoAudit

resolver_module = importlib.import_module("locjson.plural.resolver")

CATEGORIES = ("zero", "one", "two", "few", "many", "other")
WELSH = {"x": {c: f"{c} {{count}}" for c in CATEGORIES}}
ONE_OTHER = {"x": {"one": "one {count}", "other": "other {count}"}}


@pytest.fixture(autouse=True)
def _fresh_rule_cache() -> Iterator[None]:
    """Every test resolves rules from scratch, and leaves no Babel rule behind."""
    _lookup.cache_clear()
    yield
    _lookup.cache_clear()


@pytest.fixture
def hidden_babel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``import babel`` fail, as if the extra were not installed."""
    monkeypatch.setitem(sys.modules, "babel", None)


def _l10n(catalogs: Mapping[str, Mapping[str, object]]) -> Localizer:
    return Localizer(loader=DictLoader({"en": {}, **catalogs}))


def _forms(l10n: Localizer, locale: str, counts: tuple[int, ...]) -> list[str]:
    return [l10n.t("x", locale=locale, count=n) for n in counts]


def _break_babel(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    babel = pytest.importorskip("babel")

    def parse(*args: object, **kwargs: object) -> NoReturn:
        raise error

    monkeypatch.setattr(babel.Locale, "parse", parse)


# --- the Babel path -----------------------------------------------------------


def test_welsh_gets_all_six_forms_through_babel() -> None:
    pytest.importorskip("babel")
    l10n = _l10n({"cy": WELSH})
    assert _forms(l10n, "cy", (0, 1, 2, 3, 6, 4)) == [
        "zero 0",
        "one 1",
        "two 2",
        "few 3",
        "many 6",
        "other 4",
    ]


def test_welsh_zero_is_a_cldr_category_not_only_the_explicit_zero() -> None:
    pytest.importorskip("babel")
    assert rule_for("cy")(plural_operands(0)) == "zero"
    without_zero = {"x": {c: f"{c} {{count}}" for c in CATEGORIES if c != "zero"}}
    # The zero category falls back to other when the entry has no zero form.
    assert _l10n({"cy": without_zero}).t("x", locale="cy", count=0) == "other 0"


def test_babel_tries_parents_then_language() -> None:
    pytest.importorskip("babel")
    # Babel does not know cy-XX itself; its language cy wins.
    assert rule_for("cy-XX")(plural_operands(2)) == "two"


def test_latvian_zero_covers_ten_through_babel() -> None:
    # CLDR: lv zero is n % 10 = 0 or n % 100 = 11..19, so 10 is "zero".
    pytest.importorskip("babel")
    assert rule_for("lv")(plural_operands(10)) == "zero"
    assert rule_for("lv")(plural_operands(1)) == "one"


def test_locale_babel_does_not_know_uses_one_other() -> None:
    pytest.importorskip("babel")
    l10n = _l10n({"xx": ONE_OTHER})
    assert _forms(l10n, "xx", (1, 2, 0)) == ["one 1", "other 2", "other 0"]


# --- fallbacks that never raise -------------------------------------------------


@pytest.mark.usefixtures("hidden_babel")
def test_without_babel_welsh_falls_back_to_one_other() -> None:
    l10n = _l10n({"cy": ONE_OTHER})
    assert _forms(l10n, "cy", (1, 2, 3)) == ["one 1", "other 2", "other 3"]


@pytest.mark.parametrize("kind", ["unknown", "value", "type"])
def test_babel_errors_fall_back_to_one_other(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    babel = pytest.importorskip("babel")
    errors: dict[str, Exception] = {
        "unknown": babel.UnknownLocaleError("cy"),
        "value": ValueError("bad tag"),
        "type": TypeError("bad type"),
    }
    _break_babel(monkeypatch, errors[kind])
    l10n = _l10n({"cy": ONE_OTHER})
    assert _forms(l10n, "cy", (1, 2, 0)) == ["one 1", "other 2", "other 0"]


# --- built-in languages never reach Babel ---------------------------------------


@pytest.mark.parametrize(
    ("tag", "rule_tag"),
    [
        *((tag, tag) for tag in sorted(BUILTIN_RULES)),
        ("en-GB", "en"),
        ("pt-BR", "pt"),
        ("pt-AO", "pt-PT"),
        ("zh-Hant-TW", "zh"),
    ],
)
def test_builtin_languages_always_use_builtin_rules(
    monkeypatch: pytest.MonkeyPatch, tag: str, rule_tag: str
) -> None:
    def never(candidate: str) -> RuleSpec | None:
        pytest.fail(f"Babel consulted for built-in tag {candidate!r}")

    monkeypatch.setattr(resolver_module, "babel_rule", never)
    assert rule_for(tag) is BUILTIN_RULES[rule_tag][0]


def test_babel_is_consulted_only_for_discovered_catalogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real = resolver_module.babel_rule

    def counting(candidate: str) -> RuleSpec | None:
        calls.append(candidate)
        result: RuleSpec | None = real(candidate)
        return result

    monkeypatch.setattr(resolver_module, "babel_rule", counting)
    l10n = _l10n({"cy": ONE_OTHER})
    requests = ["zz-ZZ", "cy-GB", "../x", "a" * 200, "xx-YY"]
    for n in range(50):
        l10n.t("x", locale=requests[n % len(requests)], count=n)
    assert calls == ["cy"]


def test_warm_lookups_do_no_babel_work(
    monkeypatch: pytest.MonkeyPatch, io_audit: IoAudit
) -> None:
    babel = pytest.importorskip("babel")
    l10n = _l10n({"cy": WELSH})
    assert l10n.t("x", locale="cy", count=2) == "two 2"
    with io_audit.watching():
        forms = [l10n.t("x", locale="cy", count=n) for n in range(1000)]
    assert io_audit.events == []
    _break_babel(monkeypatch, babel.UnknownLocaleError("cy"))
    assert [l10n.t("x", locale="cy", count=n) for n in range(1000)] == forms
    head = ["zero 0", "one 1", "two 2", "few 3", "other 4", "other 5", "many 6"]
    assert forms[:7] == head


# --- parity with Babel (ROADMAP SC5) --------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "data" / "cldr49_plural_samples.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SAMPLES: dict[str, dict[str, list[str]]] = FIXTURE["samples"]
PT_PT_CHILDREN: frozenset[str] = frozenset(FIXTURE["pt_pt_children"])
PARITY_DECIMALS: tuple[Decimal | float, ...] = (
    *(
        Decimal(text)
        for text in (
            "0.0",
            "0.5",
            "1.0",
            "1.00",
            "1.5",
            "2.0",
            "2.5",
            "3.0",
            "10.0",
            "11.0",
            "100.0",
            "1000000.0",
        )
    ),
    0.5,
    1.0,
    1.5,
    2.5,
)

# Babel 2.18 bundles CLDR 47; locjson pins CLDR 49. Each entry maps
# (tag, str(value)) to Babel's answer where the built-in rule follows a CLDR
# change after 47, with a comment naming that change. None found so far.
KNOWN_CLDR_DIFFERENCES: dict[tuple[str, str], str] = {}

# Built-in tags that Babel's CLDR has no locale for, mapped to the CLDR 49
# parent whose Babel rule they are compared with.
BABEL_UNKNOWN_TAGS: dict[str, str] = {
    # CLDR 49 parentLocales lists pt-FR under pt-PT; Babel 2.18 (CLDR 47) has
    # no pt_FR locale data.
    "pt-FR": "pt-PT",
}


def _number(sample: str) -> int | Decimal:
    return Decimal(sample) if "." in sample else int(sample)


def _parity_values(tag: str) -> list[int | Decimal | float]:
    samples = SAMPLES["pt-PT" if tag in PT_PT_CHILDREN else tag]
    values: list[int | Decimal | float] = [
        _number(sample) for group in samples.values() for sample in group
    ]
    values.extend(range(201))
    values.extend(PARITY_DECIMALS)
    return values


@pytest.mark.parametrize("tag", sorted(BUILTIN_RULES))
def test_builtin_rules_match_babel(tag: str) -> None:
    babel = pytest.importorskip("babel")
    try:
        babel_locale = babel.Locale.parse(tag, sep="-")
    except babel.UnknownLocaleError:
        assert tag in BABEL_UNKNOWN_TAGS, f"Babel does not know {tag!r}"
        babel_locale = babel.Locale.parse(BABEL_UNKNOWN_TAGS[tag], sep="-")
    babel_form = babel_locale.plural_form
    rule = rule_for(tag)
    mismatches = []
    for value in _parity_values(tag):
        ours = rule(plural_operands(value))
        theirs = babel_form(value)
        allowed = KNOWN_CLDR_DIFFERENCES.get((tag, str(value)))
        if theirs not in {ours, allowed}:
            mismatches.append(f"{value!r}: locjson {ours}, Babel {theirs}")
    assert not mismatches, f"{tag}: " + "; ".join(mismatches)


# --- the zero-dependency path ---------------------------------------------------


def _babel_loaded_after(code: str) -> bool:
    script = f"import sys, locjson\n{code}\nprint('babel' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return bool(json.loads(out.strip().lower()))


_BUILTIN_USE = """
from decimal import Decimal
from locjson import DictLoader, Localizer
files = {"one": "{count} one", "few": "{count} few", "many": "{count} many",
         "other": "{count} other"}
l10n = Localizer(
    loader=DictLoader({"en": {"f": files}, "ru": {"f": files}, "pt-PT": {"f": files}}),
    preload=True,
)
for tag in ("en", "ru", "pt-PT", "pt-BR", "xx-invalid-!"):
    for n in (0, 1, 2, 5, 21, 1.5, Decimal("1.0"), 1000000):
        l10n.t("f", locale=tag, count=n)
"""


def test_builtin_languages_never_import_babel() -> None:
    assert _babel_loaded_after(_BUILTIN_USE) is False


def test_loading_a_welsh_catalog_imports_babel() -> None:
    pytest.importorskip("babel")
    code = (
        "from locjson import DictLoader, Localizer\n"
        "l10n = Localizer(loader=DictLoader({'en': {}, 'cy': {}}))\n"
        "l10n.t('x', locale='cy')"
    )
    assert _babel_loaded_after(code) is True
