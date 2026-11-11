"""The built-in CLDR 49 plural rules (PLUR-01) against CLDR's own samples (PLUR-06)."""

from __future__ import annotations

import ast
import importlib
import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import locjson
from locjson import DictLoader, Localizer
from locjson.plural.operands import plural_operands
from locjson.plural.resolver import _lookup, rule_for
from locjson.plural.rules import BUILTIN_RULES, CLDR_VERSION, FALLBACK_RULE

if TYPE_CHECKING:
    from collections.abc import Mapping

    from locjson.plural.rules import RuleSpec

resolver_module = importlib.import_module("locjson.plural.resolver")

FIXTURE_PATH = Path(__file__).parent / "data" / "cldr49_plural_samples.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SAMPLES: dict[str, dict[str, list[str]]] = FIXTURE["samples"]
PT_PT_CHILDREN: list[str] = FIXTURE["pt_pt_children"]
RULE_TAGS = (
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


def _number(sample: str) -> int | Decimal:
    return Decimal(sample) if "." in sample else int(sample)


def _category(tag: str, count: float | Decimal) -> str:
    return rule_for(tag)(plural_operands(count))


def _l10n(catalogs: Mapping[str, Mapping[str, object]], default: str) -> Localizer:
    return Localizer(loader=DictLoader(catalogs), default_locale=default)


# --- every CLDR 49 sample ---------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "category"),
    [(tag, category) for tag in sorted(SAMPLES) for category in sorted(SAMPLES[tag])],
)
def test_every_cldr_sample_maps_to_its_category(tag: str, category: str) -> None:
    samples = SAMPLES[tag][category]
    mismatches = [
        (sample, got)
        for sample in samples
        if (got := _category(tag, _number(sample))) != category
    ]
    assert not mismatches, f"{tag} {category}: {mismatches}"


def test_fixture_is_cldr_49_and_covers_the_built_in_tags() -> None:
    assert CLDR_VERSION == "49"
    assert FIXTURE["cldr"].startswith("49")
    assert sorted(SAMPLES) == sorted(RULE_TAGS)
    assert sorted(FIXTURE["rules"]) == sorted(RULE_TAGS)
    assert set(BUILTIN_RULES) == set(RULE_TAGS) | set(PT_PT_CHILDREN)
    assert sum(len(v) for forms in SAMPLES.values() for v in forms.values()) > 900


@pytest.mark.parametrize("tag", RULE_TAGS)
def test_rule_categories_match_cldr(tag: str) -> None:
    assert BUILTIN_RULES[tag][1] == frozenset(SAMPLES[tag])
    assert BUILTIN_RULES[tag][1] == frozenset(FIXTURE["rules"][tag])


@pytest.mark.parametrize("tag", PT_PT_CHILDREN)
def test_pt_pt_children_use_the_pt_pt_rule(tag: str) -> None:
    assert BUILTIN_RULES[tag] is BUILTIN_RULES["pt-PT"]
    assert rule_for(tag) is rule_for("pt-PT")
    assert rule_for(tag) is not rule_for("pt")


def test_hebrew_has_no_many() -> None:
    assert "many" not in BUILTIN_RULES["he"][1]
    for n in (20, 30, 40, 100):
        assert _category("he", n) == "other"


# --- ROADMAP SC1 through the Localizer --------------------------------------

_RU = {"one": "one", "few": "few", "many": "many", "other": "other"}
_AR = {name: name for name in ("zero", "one", "two", "few", "many", "other")}


def test_russian_one_few_many_one() -> None:
    l10n = _l10n({"ru": {"x": _RU}}, "ru")
    assert [l10n.t("x", count=n) for n in (1, 2, 5, 21)] == [
        "one",
        "few",
        "many",
        "one",
    ]


def test_arabic_six_forms() -> None:
    l10n = _l10n({"ar": {"x": _AR}}, "ar")
    assert [l10n.t("x", count=n) for n in (0, 1, 2, 3, 11, 100)] == [
        "zero",
        "one",
        "two",
        "few",
        "many",
        "other",
    ]


def test_portuguese_and_european_portuguese_differ() -> None:
    forms = {"one": "one", "other": "other"}
    l10n = _l10n({"pt": {"x": forms}, "pt-PT": {"x": forms}}, "pt")
    assert l10n.t("x", count=0) == "one"
    assert l10n.t("x", count=1.5) == "one"
    assert l10n.t("x", locale="pt-PT", count=0) == "other"
    assert l10n.t("x", locale="pt-PT", count=1.5) == "other"
    assert l10n.t("x", locale="pt-PT", count=1) == "one"


def test_unknown_language_gets_one_other() -> None:
    l10n = _l10n({"xx": {"x": {"one": "one", "few": "few", "other": "other"}}}, "xx")
    assert [l10n.t("x", count=n) for n in (0, 1, 2, 3)] == [
        "other",
        "one",
        "other",
        "other",
    ]
    assert l10n.t("x", count=Decimal("1.0")) == "other"
    assert rule_for("xx") is FALLBACK_RULE[0]


@pytest.mark.parametrize("count", [0, 0.0, -0.0, Decimal("0.00"), Decimal("-0.00")])
@pytest.mark.parametrize("tag", ["ru", "ar", "en", "ja", "fr"])
def test_explicit_zero_wins_in_every_language(tag: str, count: float | Decimal) -> None:
    forms = {**_AR, "zero": "explicit zero"}
    l10n = _l10n({tag: {"x": forms}}, tag)
    assert l10n.t("x", count=count) == "explicit zero"


def test_zero_without_a_zero_form_follows_the_rule() -> None:
    assert _l10n({"ru": {"x": _RU}}, "ru").t("x", count=0) == "many"
    assert _l10n({"ru": {"x": _RU}}, "ru").t("x", count=Decimal("0.0")) == "other"


# --- the lookup chain ---------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "rule_tag"),
    [
        ("pt-BR", "pt"),
        ("pt-PT", "pt-PT"),
        ("pt-AO", "pt-PT"),
        ("pt-MZ", "pt-PT"),
        ("zh-Hant-TW", "zh"),
        ("zh-Hant", "zh"),
        ("zh-Hans", "zh"),
        ("en-IN", "en"),
        ("en-001", "en"),
        ("tr-CY", "tr"),
        # The likely (or only) script spelled out (WR-02).
        ("pt-Latn-PT", "pt-PT"),
        ("pt-Latn-AO", "pt-PT"),
        ("pt-Latn-PT-1990", "pt-PT"),
        ("pt-Latn-BR", "pt"),
        ("pt-Latn", "pt"),
        ("zh-Hans-CN", "zh"),
        # A language neither the built-in table nor Babel knows (sr would get
        # Babel's rule where the extra is installed).
        ("xx-Latn", "xx"),
    ],
)
def test_lookup_chain(tag: str, rule_tag: str) -> None:
    assert rule_for(tag) is rule_for(rule_tag)


@pytest.mark.parametrize("tag", ["pt-Latn-PT", "pt-Latn-AO"])
def test_pt_pt_with_the_latin_script_spelled_out(tag: str) -> None:
    forms = {"one": "one", "many": "many", "other": "other"}
    l10n = _l10n({"pt": {"x": forms}, tag: {"x": forms}}, "pt")
    assert l10n.t("x", locale=tag, count=0) == "other"
    assert l10n.t("x", locale=tag, count=1.5) == "other"
    assert l10n.t("x", locale=tag, count=1) == "one"
    assert locjson.categories_for(tag) == locjson.categories_for("pt-PT")


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        # The tag without its likely script comes right after each tag.
        ("sr-Cyrl-RS", ["sr-Cyrl-RS", "sr-RS", "sr-Cyrl", "sr"]),
        # cy has a single script, so any script subtag may be dropped.
        (
            "cy-Latn-GB-1990",
            ["cy-Latn-GB-1990", "cy-GB-1990", "cy-Latn-GB", "cy-GB", "cy-Latn", "cy"],
        ),
        # Another script is never dropped: sr-RS is written in Cyrillic.
        ("sr-Latn-RS", ["sr-Latn-RS", "sr-Latn", "sr"]),
        ("yue-Hans-CN", ["yue-Hans-CN", "yue-Hans", "yue"]),
        ("cy-GB", ["cy-GB", "cy"]),
    ],
)
def test_lookup_candidates_in_order(
    monkeypatch: pytest.MonkeyPatch, tag: str, expected: list[str]
) -> None:
    calls: list[str] = []

    def recording(candidate: str) -> RuleSpec | None:
        calls.append(candidate)
        return None

    monkeypatch.setattr(resolver_module, "babel_rule", recording)
    _lookup.cache_clear()
    try:
        rule_for(tag)
    finally:
        _lookup.cache_clear()
    assert calls == expected


# --- PLUR-01 edges ------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "count", "category"),
    [
        ("ru", 4, "few"),
        ("ru", 5, "many"),
        ("ru", 11, "many"),
        ("ru", 12, "many"),
        ("ru", 14, "many"),
        ("ru", 21, "one"),
        ("ru", 22, "few"),
        ("ru", 111, "many"),
        ("uk", 111, "many"),
        ("pl", 1, "one"),
        ("pl", 2, "few"),
        ("pl", 5, "many"),
        ("pl", 12, "many"),
        ("pl", 21, "many"),
        ("pl", 22, "few"),
        ("ar", 2, "two"),
        ("ar", 3, "few"),
        ("ar", 10, "few"),
        ("ar", 11, "many"),
        ("ar", 99, "many"),
        ("ar", 100, "other"),
        ("ar", 102, "other"),
        ("ar", 103, "few"),
        ("cs", 1.5, "many"),
        ("cs", 3, "few"),
        ("cs", 5, "other"),
    ],
)
def test_boundaries(tag: str, count: float, category: str) -> None:
    assert _category(tag, count) == category


@pytest.mark.parametrize("tag", ["fr", "es", "it", "pt", "pt-PT"])
def test_millions_are_many(tag: str) -> None:
    assert _category(tag, 999_999) == "other"
    assert _category(tag, 1_000_000) == "many"
    assert _category(tag, 1_000_001) == "other"
    assert _category(tag, 2_000_000) == "many"
    assert _category(tag, Decimal("1000000.0")) == "other"


@pytest.mark.parametrize(
    ("tag", "count", "category"),
    [
        ("fr", Decimal("1.9"), "one"),  # i truncates, never rounds
        ("fr", 2.0, "other"),
        ("fr", 1.9, "one"),
        ("ar", Decimal("3.0"), "few"),  # n % 100 = 3..10 holds for integral n
        ("ar", Decimal("3.5"), "other"),
        ("ar", Decimal("0.0"), "zero"),
        ("ar", Decimal("0.5"), "other"),
        ("tr", Decimal("1.0"), "one"),
        ("tr", Decimal("1.5"), "other"),
        ("es", Decimal("1.00"), "one"),
        ("en", Decimal("1.0"), "other"),
        ("he", Decimal("0.5"), "one"),
        ("he", Decimal("1.5"), "other"),
        ("he", Decimal("2.0"), "other"),
    ],
)
def test_precision(tag: str, count: float | Decimal, category: str) -> None:
    assert _category(tag, count) == category


# --- no dynamic code ------------------------------------------------------------

SOURCE_ROOT = Path(locjson.__file__).parent


def test_no_eval_exec_or_compile_in_locjson() -> None:
    calls: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls.extend(
            f"{path.name}:{node.lineno} {node.func.id}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"eval", "exec", "compile"}
        )
    assert not calls


@pytest.mark.parametrize("name", ["rules.py", "operands.py", "resolver.py"])
def test_plural_modules_do_not_import_re(name: str) -> None:
    path = SOURCE_ROOT / "plural" / name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert "re" not in imported
