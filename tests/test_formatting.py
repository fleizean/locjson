"""Template grammar and render semantics (INT-01/02, RESEARCH Pattern 3).

Every row of the Pattern 3 table is a case here. Unsafe placeholders are
rejected by ``compile_template`` at load time, so they can never reach render,
and rendering never goes through ``str.format``.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import pytest

from locjson import DictLoader, InvalidCatalogError, Localizer, RawSource
from locjson._compat import override
from locjson.catalog import build_catalog
from locjson.formatting import Template, TemplateError, compile_template

if TYPE_CHECKING:
    from collections.abc import Iterator

BRACES = "invalid brace syntax"
CONVERSION = "conversion"
SPEC = "format spec"
POSITIONAL = "positional or empty placeholder"
NAME = "must be a plain ASCII name"

# --- accepted ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "segments", "fields"),
    [
        ("Hello, {name}!", ("Hello, ", "name", "!"), {"name"}),
        ("{{", ("{",), set()),
        ("}}", ("}",), set()),
        ("{{literal}} {n}", ("{literal} ", "n", ""), {"n"}),
        ("a {{ b }} c", ("a { b } c",), set()),
        ("{a:}", ("", "a", ""), {"a"}),
        ("{__class__}", ("", "__class__", ""), {"__class__"}),
        ("{a}{a}{b}", ("", "a", "", "a", "", "b", ""), {"a", "b"}),
        ("", ("",), set()),
        (
            "Merhaba, {name}! İyi akşamlar",
            ("Merhaba, ", "name", "! İyi akşamlar"),
            {"name"},
        ),
        ("{_x9}", ("", "_x9", ""), {"_x9"}),
    ],
)
def test_accept(text: str, segments: tuple[str, ...], fields: set[str]) -> None:
    template = compile_template(text)
    assert template.source == text
    assert template.segments == segments
    assert template.fields == frozenset(fields)
    assert len(template.segments) % 2 == 1


def test_empty_spec_is_the_same_as_no_spec() -> None:
    assert compile_template("{a:}").segments == compile_template("{a}").segments


# --- rejected ------------------------------------------------------------------

REJECTED = [
    pytest.param("{}", POSITIONAL, id="empty"),
    pytest.param("{0}", POSITIONAL, id="positional"),
    pytest.param("{12}", POSITIONAL, id="positional-multi-digit"),
    pytest.param("{ name }", NAME, id="padded"),
    pytest.param("{a.b}", NAME, id="attribute"),
    pytest.param("{a[0]}", NAME, id="index"),
    pytest.param("{[0]}", NAME, id="bare-index"),
    pytest.param("{.a}", NAME, id="bare-attribute"),
    pytest.param("{a]}", NAME, id="stray-bracket"),
    pytest.param("{x!r}", CONVERSION, id="conversion-r"),
    pytest.param("{x!s}", CONVERSION, id="conversion-s"),
    pytest.param("{x!a}", CONVERSION, id="conversion-a"),
    pytest.param("{x:>100000000}", SPEC, id="spec-width"),
    pytest.param("{x:{w}}", SPEC, id="spec-nested"),
    pytest.param("{x:{w}.{p}}", SPEC, id="spec-nested-two"),
    pytest.param("{", BRACES, id="lone-open"),
    pytest.param("}", BRACES, id="lone-close"),
    pytest.param("a}b", BRACES, id="close-in-text"),
    pytest.param("{x}}", BRACES, id="extra-close"),
    pytest.param("{{x}", BRACES, id="escaped-open-then-close"),
    pytest.param("{a", BRACES, id="unterminated"),
    pytest.param("{a[}", BRACES, id="unterminated-index"),
    pytest.param("{x!}", BRACES, id="empty-conversion"),
    pytest.param("{kullanıcı}", NAME, id="turkish-dotless-i"),
    pytest.param("{İsim}", NAME, id="turkish-dotted-capital-i"),
    pytest.param("{ﬁle}", NAME, id="nfkc-ligature"),
]


@pytest.mark.parametrize(("text", "kind"), REJECTED)
def test_reject(text: str, kind: str) -> None:
    with pytest.raises(TemplateError) as info:
        compile_template(text)
    assert kind in str(info.value)
    assert isinstance(info.value, ValueError)


@pytest.mark.parametrize(("text", "kind"), REJECTED)
def test_reject_in_catalog_names_the_pointer(text: str, kind: str) -> None:
    result = build_catalog("en", [RawSource({"g": {"k": text}, "ok": "x"}, "en.json")])
    (issue,) = result.issues
    assert (issue.path, issue.pointer) == ("en.json", "/g/k")
    assert kind in issue.problem


def test_reject_messages_hint_at_doubled_braces() -> None:
    with pytest.raises(
        TemplateError, match=r"use '\{\{' and '\}\}' for literal braces"
    ):
        compile_template("Use { to open")


def test_reject_messages_never_contain_the_surrounding_text() -> None:
    with pytest.raises(TemplateError) as info:
        compile_template("secret-value {0}")
    assert "secret-value" not in str(info.value)


def test_reject_in_catalog_at_load_time() -> None:
    data = {"x": "{0}", "y": {"z": "{p:.2f}"}, "fine": "{p}"}
    result = build_catalog("en", [RawSource(data, "en.json")])
    assert result.catalog is None
    assert [
        (i.pointer, POSITIONAL in i.problem, SPEC in i.problem) for i in result.issues
    ] == [
        ("/x", True, False),
        ("/y/z", False, True),
    ]


def test_reject_through_localizer_on_first_lookup() -> None:
    l10n = Localizer(
        loader=DictLoader({"en": {"ok": "fine", "bad": "{user.__class__}"}})
    )
    with pytest.raises(InvalidCatalogError) as info:
        l10n.t("ok")
    assert (info.value.path, info.value.pointer) == ("<dict>/en", "/bad")


# --- render ----------------------------------------------------------------------


def test_missing_value_stays_literal() -> None:
    assert compile_template("{a} and {b}").render({"a": 1}) == "1 and {b}"


def test_values_are_inserted_verbatim_and_never_reinterpolated() -> None:
    template = compile_template("{a}{a}{b}")
    assert template.render({"a": "{name}"}) == "{name}{name}{b}"
    assert compile_template("{a}").render({"a": "{{x}}", "x": 1}) == "{{x}}"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1.5, "1.5"), (3, "3"), (None, "None"), (True, "True"), (["x"], "['x']")],
)
def test_values_go_through_str(value: object, expected: str) -> None:
    assert compile_template("{v}").render({"v": value}) == expected


def test_literal_braces_render() -> None:
    template = compile_template("Use {{name}} to write {name}")
    assert template.render({"name": "Ada"}) == "Use {name} to write Ada"


def test_turkish_text_around_placeholders_renders_unchanged() -> None:
    template = compile_template("Merhaba, {name}! İyi akşamlar")
    assert template.render({"name": "Işık"}) == "Merhaba, Işık! İyi akşamlar"


class _Untouchable(Mapping[str, object]):
    """A mapping that fails the test if it is read at all."""

    @override
    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    @override
    def __iter__(self) -> Iterator[str]:
        raise AssertionError

    @override
    def __len__(self) -> int:
        raise AssertionError


def test_template_without_placeholders_does_not_consult_values() -> None:
    assert compile_template("Ana Sayfa").render(_Untouchable()) == "Ana Sayfa"
    assert compile_template("").render(_Untouchable()) == ""


def test_empty_template_is_untranslated_and_falls_through() -> None:
    l10n = Localizer(loader=DictLoader({"en": {"k": "English"}, "tr": {"k": ""}}))
    assert l10n.t("k", locale="tr") == "English"


def test_template_renders_without_str_format(monkeypatch: pytest.MonkeyPatch) -> None:
    template = compile_template("{a} {b}")

    def forbidden(*args: object, **kwargs: object) -> str:
        raise AssertionError

    monkeypatch.setattr("string.Formatter.format", forbidden)
    monkeypatch.setattr("string.Formatter.vformat", forbidden)
    assert template.render({"a": "x", "b": "y"}) == "x y"


def test_one_template_renders_concurrently() -> None:
    template = compile_template("Merhaba, {name}! ({n})")
    barrier = threading.Barrier(8)
    results: dict[int, list[str]] = {}

    def render(index: int) -> None:
        barrier.wait()
        results[index] = [
            template.render({"name": f"user{index}", "n": step}) for step in range(200)
        ]

    threads = [threading.Thread(target=render, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == list(range(8))
    for index, rendered in results.items():
        assert rendered == [f"Merhaba, user{index}! ({step})" for step in range(200)]


def test_template_is_immutable() -> None:
    template: Any = compile_template("{a}")
    with pytest.raises(AttributeError):
        template.extra = 1
    with pytest.raises(AttributeError):
        template._segments = ("x",)
    assert isinstance(template, Template)
    assert template.segments == ("", "a", "")
