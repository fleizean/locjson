<p align="center">
  <a href="https://github.com/fleizean/locjson">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://cdn.jsdelivr.net/gh/fleizean/locjson@main/docs/assets/logo-dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="https://cdn.jsdelivr.net/gh/fleizean/locjson@main/docs/assets/logo.svg">
      <img alt="locjson" src="https://cdn.jsdelivr.net/gh/fleizean/locjson@main/docs/assets/logo.svg" width="360">
    </picture>
  </a>
</p>

<p align="center">
  <strong>Typed, zero-dependency JSON localization for Python.</strong><br>
  Plain JSON catalogs, locale fallback chains, safe <code>{name}</code> interpolation and plurals,<br>
  with a CLI that keeps your translation files healthy.
</p>

<p align="center">
  <a href="https://github.com/fleizean/locjson/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/fleizean/locjson/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/locjson/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/locjson.svg"></a>
  <a href="https://pypi.org/project/locjson/"><img alt="Supported Python versions" src="https://img.shields.io/pypi/pyversions/locjson.svg"></a>
  <a href="https://github.com/fleizean/locjson/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://peps.python.org/pep-0561/"><img alt="Typed" src="https://img.shields.io/badge/typing-typed-blue.svg"></a>
  <a href="https://pypi.org/project/locjson/"><img alt="Zero dependencies" src="https://img.shields.io/badge/dependencies-0-brightgreen.svg"></a>
</p>

---

> **🚧 Status: 0.2.0 prepared, PyPI release pending.** The core runtime and the CLDR plural rules are complete. Neither 0.1.0 nor 0.2.0 is on PyPI yet, so `pip install locjson` will not find them; install from GitHub instead (see [Installation](#installation)). Features marked *planned* do not exist yet.

## Why locjson?

Many web teams already keep their frontend translations in JSON files (i18next, vue-i18n). On the Python side, the standard answer is gettext with Babel: mature and powerful, but built around `.po`/`.mo` files, a compile step and a separate toolchain. That means two formats and two workflows for the same strings.

locjson keeps translations in **plain JSON** on the backend too, and focuses on a few things:

- **Small, typed runtime.** Zero runtime dependencies, ships `py.typed`, checked with `mypy --strict`.
- **Fast warm path.** Catalogs are loaded lazily per locale, validated once and compiled at load. A warm `t()` call is a dict lookup plus a join, with no file I/O.
- **Safe by construction.** Only named `{name}` placeholders. No attribute or index access, no format specs, no `eval`.
- **Loud at load, quiet at render.** Broken catalogs raise at load time with the file path and a JSON pointer. Translation slips at render time are lenient by default and logged once at WARNING, or raise with `strict=True`.
- **Tooling included** *(planned)*. A `locjson` CLI to check, format, sync and measure your catalogs in CI and pre-commit.

## Features

| Feature | Status |
|---|---|
| JSON catalogs, single-file or namespaced layout (auto-detected) | 0.1 |
| Nested keys flattened to dot keys (`nav.home`) | 0.1 |
| BCP 47 locale normalization (`pt_BR` → `pt-BR`) and script-aware fallback chains | 0.1 |
| Safe `{name}` interpolation with `{{` / `}}` escapes | 0.1 |
| Plural entries keyed by CLDR category, with an explicit `zero` form | 0.1 |
| Current locale via `contextvars` (`use()` / `set_locale()`), safe across asyncio tasks and threads | 0.1 |
| Bound translators: `for_locale()` for jobs and e-mails, `scope()` for key prefixes | 0.1 |
| `missing` policy, `strict=` / `LOCJSON_STRICT`, WARNING-once slip logging | 0.1 |
| `LocJsonError` hierarchy with file path + JSON pointer | 0.1 |
| `reload()`, `negotiate()` (Accept-Language), `direction()` (LTR/RTL) | 0.1 |
| Custom loaders via a `Loader` protocol, in-memory `DictLoader` | 0.1 |
| CLDR plural rules for 17 built-in languages, `categories_for()`, optional Babel for every other language | 0.2 |
| `locjson` CLI: `init`, `check`, `stats`, `fmt` | planned 0.3 |
| `locjson` CLI: `sync`, `extract`, `import --from i18next` | planned 0.4 |
| `lazy()` strings, hot reload, FastAPI / Django / Flask recipes | planned 0.5 |

## Installation

locjson requires **Python 3.11+** and has no runtime dependencies.

```bash
pip install locjson
```

> Neither 0.1.0 nor 0.2.0 is on PyPI yet. Until they are published, install the current code from GitHub:
>
> ```bash
> pip install "git+https://github.com/fleizean/locjson.git"
> pip install "locjson[babel] @ git+https://github.com/fleizean/locjson.git"   # with the babel extra
> ```

Optional extras:

```bash
pip install "locjson[babel]"   # 0.2: full CLDR plural rules, via Babel, for languages without a built-in rule
pip install "locjson[watch]"   # planned 0.5: hot reload via watchfiles
```

## Quick start

Put one JSON file per locale in a `locales/` folder.

<!-- file: locales/en.json -->
```json
{
  "greeting": "Hello, {name}!",
  "nav": { "home": "Home", "settings": "Settings" },
  "inbox": {
    "messages": {
      "zero": "You have no messages",
      "one": "You have {count} message",
      "other": "You have {count} messages"
    }
  }
}
```

<!-- file: locales/tr.json -->
```json
{
  "greeting": "Merhaba, {name}!",
  "nav": { "home": "Ana sayfa", "settings": "Ayarlar" },
  "inbox": {
    "messages": {
      "zero": "Hiç mesajınız yok",
      "one": "{count} mesajınız var",
      "other": "{count} mesajınız var"
    }
  }
}
```

Then create a `Localizer` and translate:

<!-- quickstart -->
```python
from locjson import Localizer

l10n = Localizer("locales")  # default_locale="en"

print(l10n.t("greeting", name="Enes"))               # -> Hello, Enes!
print(l10n.t("greeting", locale="tr", name="Enes"))  # -> Merhaba, Enes!
print(l10n.t("inbox.messages", count=0))             # -> You have no messages
print(l10n.t("inbox.messages", count=1))             # -> You have 1 message
print(l10n.t("inbox.messages", count=3))             # -> You have 3 messages
print(l10n.has("nav.home", locale="tr"))             # -> True
print(sorted(l10n.locales))                          # -> ['en', 'tr']

with l10n.use("tr"):
    print(l10n.t("nav.home"))                        # -> Ana sayfa
    print(l10n.t("inbox.messages", count=3))         # -> 3 mesajınız var

# The same Localizer with its options spelled out:
l10n = Localizer(
    path="locales",
    default_locale="en",
    fallbacks={"pt-BR": ["pt"]},
    missing="key",  # "key" | "empty" | "raise" | callable(key, locale) -> str
)

print(l10n.t("nav.home", locale="pt-BR"))            # -> Home
print(l10n.t("nav.profile"))                         # -> nav.profile
```

`Localizer("locales")` is the short form: `path` is the first argument and `default_locale` is `"en"`. `pt-BR` has no catalog here, so the lookup walks `pt-BR → pt → en` and returns the English text. `nav.profile` exists nowhere, so `missing="key"` returns the key itself.

## Use cases

The examples below use the `locales/` folder and the `l10n` from the quick start.

### Web requests (FastAPI)

Pick the locale per request from the `Accept-Language` header. Each request runs in its own context, so concurrent requests never see each other's locale.

<!-- no-exec -->
```python
from fastapi import FastAPI, Request

from locjson import Localizer

app = FastAPI()
l10n = Localizer("locales")


@app.middleware("http")
async def locale_from_header(request: Request, call_next):
    with l10n.use(l10n.negotiate(request.headers.get("accept-language", ""))):
        return await call_next(request)


@app.get("/")
async def home() -> dict[str, str]:
    return {"title": l10n.t("nav.home")}  # "Ana sayfa" for Accept-Language: tr
```

Prefer `use()` to `set_locale()` here. `use()` puts the previous locale back when the block ends, while a `set_locale()` value stays for whatever runs later in the same context, for example the next job on a reused worker thread.

### E-mails and background jobs

Outside a request there is no current locale to rely on. `for_locale()` returns a translator bound to one locale. It never reads or changes the current locale, which suits Celery tasks, cron jobs and e-mails sent in a user's language.

<!-- exec -->
```python
def welcome_subject(user_name: str, user_language: str) -> str:
    t = l10n.for_locale(user_language)
    return t("greeting", name=user_name)


print(welcome_subject("Yağız", "tr"))                # -> Merhaba, Yağız!
print(welcome_subject("Ada", "de"))                  # -> Hello, Ada!
```

`de` has no catalog, so it falls back to `en`. An invalid tag binds `default_locale`, and an explicit `locale=` argument still wins over the bound locale.

### One module, one key prefix

`scope()` prepends a prefix to every key. It combines with `for_locale()` in either order.

<!-- exec -->
```python
inbox = l10n.scope("inbox")
print(inbox("messages", count=2))                    # -> You have 2 messages
print(inbox.for_locale("tr")("messages", count=0))   # -> Hiç mesajınız yok

nav_tr = l10n.for_locale("tr").scope("nav")
print(nav_tr("settings"))                            # -> Ayarlar
print(nav_tr.has("profile"))                         # -> False
```

Translators are immutable and safe to share between threads and tasks. They always use the Localizer's latest catalogs, its `missing` policy and its `strict` setting.

### Scripts and CLI tools

For a small program, install one default Localizer and use the module-level functions.

<!-- exec -->
```python
import locjson

locjson.setup("locales")

print(locjson.t("greeting", name="Enes"))            # -> Hello, Enes!
with locjson.use("tr"):
    print(locjson.t("nav.settings"))                 # -> Ayarlar
```

`locjson.has()`, `set_locale()`, `for_locale()`, `scope()` and `get_localizer()` work the same way. Calling `setup()` again replaces the default atomically.

### Tests

Build catalogs in memory with `DictLoader` and turn on `strict=True`, so a typo in a key or a missing variable fails the test instead of passing quietly.

<!-- exec -->
```python
import pytest

from locjson import DictLoader, Localizer, MissingTranslationError


def make_l10n() -> Localizer:
    return Localizer(
        loader=DictLoader({"en": {"greeting": "Hello, {name}!"}}),
        strict=True,
    )


def test_greeting() -> None:
    assert make_l10n().t("greeting", name="Enes") == "Hello, Enes!"


def test_a_typo_fails_loudly() -> None:
    with pytest.raises(MissingTranslationError):
        make_l10n().t("greting", name="Enes")
```

## JSON file format

### Layouts

Both layouts are auto-detected. Pick one per locale.

```text
locales/                     locales/
├── en.json                  ├── en/
└── tr.json                  │   ├── common.json   → keys "common.*"
                             │   └── inbox.json    → keys "inbox.*"
                             └── tr/
                                 ├── common.json
                                 └── inbox.json
```

A locale present in both layouts (`en.json` *and* `en/`) is an error that names both paths.

### Keys, values and plurals

| JSON | Meaning |
|---|---|
| `{"nav": {"home": "Home"}}` | Nested objects flatten to dot keys: `t("nav.home")` |
| `"Hello, {name}!"` | A translation. Values must be strings. |
| `""` or `null` | Untranslated: the lookup falls through to the next locale in the chain |
| `{"zero": …, "one": …, "other": …}` | A plural entry: every key is a CLDR category (`zero`, `one`, `two`, `few`, `many`, `other`), `other` is required, all values are strings |
| `{"$plural": false, "one": …, "other": …}` | Forces an object that looks like a plural entry to be read as a normal group |
| `"$meta"` (top level) | File metadata, never a translation |
| `"$comment"` and other `$` keys | Ignored, handy for notes to translators |

How a plural entry picks its form is described in [Plural rules](#plural-rules).

`$meta` describes the file:

```json
{
  "$meta": { "locale": "ar", "direction": "rtl" },
  "greeting": "مرحبًا، {name}!"
}
```

`locale` must match the file's locale, `direction` is `"ltr"` or `"rtl"`, and unknown `$meta` keys are rejected.

Numbers, booleans and arrays as values, duplicate keys, `NaN`/`Infinity` and key-path collisions are all rejected at load with an `InvalidCatalogError`. Files are read as UTF-8 (a BOM is accepted), so non-ASCII text such as Turkish `İ`/`ı` round-trips unchanged.

### Plural rules

- `count` is passed to the template automatically, so `{count}` just works.
- When the count equals 0 (`0`, `0.0`, `Decimal("0.00")`) and the entry has a `zero` form, `zero` is used in every language.
- Otherwise the language's CLDR plural rule picks a category (`zero`, `one`, `two`, `few`, `many` or `other`), and `other` is used when the entry has no form for it.

locjson ships the CLDR 49 cardinal plural rules for 17 languages as plain Python functions: `en`, `tr`, `de`, `fr`, `es`, `it`, `pt`, `nl`, `ru`, `uk`, `pl`, `cs`, `ar`, `he`, `ja`, `zh` and `ko`. `pt-PT` has its own rule, which the locales CLDR groups under it (such as `pt-AO`, `pt-MZ` and `pt-MO`) share, while `pt` and `pt-BR` use the Brazilian one. Regional tags use their language's rule (`ru-UA` uses `ru`). Other languages use a one/other rule (`one` for exactly 1, `other` for everything else) unless [Babel](#more-languages-with-babel) is installed.

The rule follows the catalog that supplied the text: if a Russian request falls back to an English message, the English rule picks its form.

<!-- exec -->
```python
from locjson import DictLoader, Localizer

catalogs = {
    "ru": {
        "files": {
            "one": "{count} файл",
            "few": "{count} файла",
            "many": "{count} файлов",
            "other": "{count} файла",
        }
    }
}
l10n_ru = Localizer(loader=DictLoader(catalogs), default_locale="ru")

print(l10n_ru.t("files", count=1))                   # -> 1 файл
print(l10n_ru.t("files", count=2))                   # -> 2 файла
print(l10n_ru.t("files", count=5))                   # -> 5 файлов
print(l10n_ru.t("files", count=21))                  # -> 21 файл
print(l10n_ru.t("files", count=1.5))                 # -> 1.5 файла
```

A count can be an `int`, a `float` or a `Decimal`, or another integer type with `__index__`, such as NumPy's `np.int64`. A float is read through its shortest `repr`, so `1.0` counts as the integer 1. Pass a `Decimal` to keep visible decimals: `Decimal("1.0")` is `other` in English ("1.0 messages") but `one` in Turkish, because the two languages' rules treat visible decimals differently.

<!-- exec -->
```python
from decimal import Decimal

print(l10n.t("inbox.messages", count=1))                 # -> You have 1 message
print(l10n.t("inbox.messages", count=Decimal("1.0")))    # -> You have 1.0 messages
```

An invalid count is a slip, like a missing variable: `True` or `False`, a string, NaN, an infinity, any other type, or a number with more than 1000 integer or fraction digits. The `other` form is used, `{count}` stays as literal text, and the slip is logged (see [Logging](#logging)). With `strict=True` or `missing="raise"`, an `InterpolationError` is raised instead.

`categories_for(locale)` returns the categories a locale's rule can produce, found the same way `t()` finds the rule. Use it to check that each locale's plural entries have the forms that locale needs. An invalid tag raises `InvalidLocaleError`.

<!-- exec -->
```python
import locjson

print(sorted(locjson.categories_for("ru")))          # -> ['few', 'many', 'one', 'other']
print(sorted(locjson.categories_for("ja")))          # -> ['other']
```

### More languages with Babel

```bash
pip install "locjson[babel]"
```

With the `babel` extra, languages without a built-in rule get Babel's CLDR rules. For example, a Welsh (`cy`) catalog then uses all six categories: `zero` for 0, `one` for 1, `two` for 2, `few` for 3, `many` for 6 and `other` for 4. The 17 built-in languages always keep their built-in rules, so installing Babel never changes their output. A locale Babel does not know falls back to the one/other rule without raising.

Babel is imported only when a catalog in such a language is first loaded (or `categories_for()` is asked about one), never by `import locjson`. The rule is resolved once per catalog at load, so a warm `t()` does no Babel work.

Latvian (`lv`) and Prussian (`prg`), which get their rules from Babel, have a CLDR `zero` category that also covers 10 to 20, 30, 40 and so on. Write their `zero` forms with `{count}` rather than as "no items".

**Security note:** Babel compiles CLDR rule text into Python code with `eval`, inside its own code and only on the CLDR data bundled with Babel; locjson passes it nothing but a locale tag. locjson's own code never uses `eval`.

### Interpolation

Placeholders are **named fields only**, compiled once when the catalog loads:

| Template | Result |
|---|---|
| `"Hello, {name}!"` | `t("greeting", name="Enes")` → `Hello, Enes!` |
| `"Use {{name}} for a placeholder"` | `Use {name} for a placeholder` (doubled braces are literal) |
| `{0}`, `{user.name}`, `{items[0]}` | Rejected at load |
| `{price:.2f}`, `{value!r}` | Rejected at load (no format specs or conversions) |

Format values in Python before passing them in, for example `t("total", price=f"{price:.2f}")`.

If a variable is not passed, the placeholder stays as literal `{name}` text and the slip is logged (see [Logging](#logging)). With `strict=True` or `missing="raise"`, an `InterpolationError` is raised instead.

## Locales and fallback

Locale tags are normalized to BCP 47, so `pt_BR`, `tr_TR.UTF-8` and `zh-hant-tw` become `pt-BR`, `tr-TR` and `zh-Hant-TW`. Legacy codes are mapped (`iw` → `he`).

For a requested locale, the lookup chain is: the locale itself → its explicit `fallbacks` → its parents → `default_locale`. Parents are script-aware, so Traditional Chinese never falls back to Simplified:

| Requested | Chain (`default_locale="en"`, `fallbacks={"pt-BR": ["pt"]}`) |
|---|---|
| `pt-BR` | `pt-BR` → `pt` → `en` |
| `tr-CY` | `tr-CY` → `tr` → `en` |
| `zh-TW` | `zh-TW` → `zh-Hant` → `en` |
| `zh-Hans-CN` | `zh-Hans-CN` → `zh-Hans` → `zh` → `en` |

Invalid tags raise `InvalidLocaleError` when passed to the constructor. At request time (`t(locale=...)`, `use(...)`), they fall back to `default_locale` instead of failing.

### Current locale

The current locale lives in a `ContextVar` per `Localizer`, so each asyncio task and thread sees its own value.

<!-- exec -->
```python
with l10n.use("tr"):                # scoped: the previous locale comes back on exit
    print(l10n.t("nav.home"))       # -> Ana sayfa

l10n.set_locale("tr")               # for the rest of the current context
print(l10n.current_locale)          # -> tr
```

### Negotiation and text direction

`negotiate()` picks the best discovered locale for an `Accept-Language` header and falls back to `default_locale`. Malformed headers never raise. `direction()` returns the first `$meta.direction` along the locale's chain, taken only from catalogs in the same language and script as the requested locale (`ar-EG` uses `ar`'s, `ar` never uses `en`'s), otherwise a built-in table decides.

<!-- exec -->
```python
print(l10n.negotiate("tr-TR,tr;q=0.9,en;q=0.8"))     # -> tr
print(l10n.direction("ar"))                          # -> rtl
```

### Missing translations

| `missing=` | When a key is missing in the whole chain |
|---|---|
| `"key"` (default) | Returns the key, e.g. `"nav.profile"` |
| `"empty"` | Returns `""` |
| `"raise"` | Raises `MissingTranslationError`, and makes missing variables and a missing or invalid `count` raise `InterpolationError` |
| `callable(key, locale)` | Returns whatever your function returns |

### Strict mode

`strict=True` makes every slip raise, whatever `missing` says: a missing key raises `MissingTranslationError`, and a missing variable, a plural message without `count` or an invalid `count` raises `InterpolationError`.

With `strict=None` (the default), the Localizer reads the `LOCJSON_STRICT` environment variable once, when it is created. `1`, `true`, `yes` and `on` turn strict mode on, and `0`, `false`, `no`, `off` and an empty value leave it off (case-insensitive). Any other value raises `ConfigurationError`. The result is available as `l10n.strict`.

The usual setup is strict in development and lenient in production, either with `Localizer("locales", strict=settings.DEBUG)` or from the environment:

```bash
LOCJSON_STRICT=1 pytest
```

### Logging

Lenient slips (a missing key, a missing variable, a plural message without `count`, an invalid `count`) are logged on the `locjson` logger. The first time a slip of a given kind happens for a locale and key, it is logged at WARNING. Repeats are logged at DEBUG, so a missing key shows up once instead of on every request. Records name the key, the locale and the placeholder, never the values you pass in.

Invalid locale tags at request time, for example from an `Accept-Language` header, are logged at DEBUG only.

### Errors

All exceptions inherit from `LocJsonError`:

| Exception | Raised when |
|---|---|
| `ConfigurationError` | The `Localizer` is misconfigured, e.g. neither `path` nor `loader` is given, or `LOCJSON_STRICT` holds an unknown value |
| `InvalidLocaleError` | A locale tag in the configuration is invalid |
| `InvalidCatalogError` | A catalog file is invalid. Exposes `.path` and `.pointer` (RFC 6901). |
| `MissingTranslationError` | A key is missing in strict mode or under `missing="raise"`. Also a `LookupError`. |
| `InterpolationError` | A variable or `count` is missing, or `count` is not a valid number, in strict mode or under `missing="raise"` |

### Custom loaders

Catalogs can come from anywhere that implements the `Loader` protocol (`discover_locales()` and `load(locale)`). An in-memory loader is included, which is handy for tests:

<!-- exec -->
```python
from locjson import DictLoader, Localizer

l10n = Localizer(
    loader=DictLoader({"en": {"greeting": "Hello, {name}!"}}),
    default_locale="en",
)
print(l10n.t("greeting", name="Enes"))               # -> Hello, Enes!
```

### Reloading

Call `l10n.reload()` to rebuild the loaded catalogs. The new set is swapped in atomically. If a file is broken, the error is raised and the old catalogs stay in place. Locales that were never loaded are read later, from the files as they are when first needed.

## CLI *(planned 0.3 / 0.4)*

The `locjson` command will keep translation files consistent locally, in pre-commit and in CI. None of these commands exist yet.

| Command | What it will do | Planned |
|---|---|---|
| `locjson init --locales en,tr` | Scaffold `locales/` and a `[tool.locjson]` config section | 0.3 |
| `locjson check` | Report invalid JSON, missing/extra keys, placeholder mismatches, incomplete plurals | 0.3 |
| `locjson stats` | Translation coverage per locale as a table | 0.3 |
| `locjson fmt [--check]` | Canonical formatting: sorted keys, 2-space indent, UTF-8, trailing newline | 0.3 |
| `locjson sync [--fill empty\|source\|todo] [--prune]` | Add keys missing from target locales, optionally remove stale ones | 0.4 |
| `locjson extract src/` | Find keys used in code but missing from JSON, and keys never used | 0.4 |
| `locjson import --from i18next` | Convert i18next JSON files to locjson catalogs | 0.4 |

Configuration will live in `pyproject.toml`:

```toml
[tool.locjson]
path = "locales"
source_locale = "en"
functions = ["t", "_"]
```

Every command will support `--format text`, `json` or `github` (inline annotations on pull requests) and exit with `0` (OK), `1` (problems found), `2` (usage or config error) or `3` (internal error).

## Roadmap

| Version | Focus | Status |
|---|---|---|
| **0.1** | Core runtime: JSON catalogs, fallback chains, safe interpolation, explicit-zero/one/other plurals, current locale, `reload()`, `negotiate()`, `direction()` | Complete, PyPI release pending |
| **0.2** | CLDR plural rules for 17 built-in languages, `categories_for()`, optional Babel for full CLDR coverage | Complete and prepared, PyPI release pending |
| **0.3** | CLI part 1: `init`, `check`, `stats`, `fmt`, output formats, pre-commit hooks | Planned |
| **0.4** | CLI part 2: `sync`, `extract`, `import --from i18next` | Planned |
| **0.5** | `lazy()` strings, hot reload, FastAPI / Django / Flask recipes | Planned |
| **1.0** | Stable public API and a documentation site | Planned |

See the [changelog](https://github.com/fleizean/locjson/blob/main/CHANGELOG.md) for what has shipped.

## Examples

The [`examples/`](https://github.com/fleizean/locjson/tree/main/examples) folder holds small, runnable projects: a quick start, the namespaced layout with a right-to-left locale, background jobs that send e-mails in each user's language, testing translations with pytest, and FastAPI, Flask and Django apps that pick the locale from `Accept-Language`. See the [examples index](https://github.com/fleizean/locjson/blob/main/examples/README.md) for how to run each one.

## Contributing

Issues and pull requests are welcome. Please open an issue first for larger changes.

```bash
git clone https://github.com/fleizean/locjson.git
cd locjson
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[babel]" --group dev   # needs pip 25.1+

ruff check . && ruff format --check .
mypy --strict
pytest
```

Installing the `babel` extra lets the Babel tests run and lets mypy see Babel's types. CI runs the same checks on Python 3.11 to 3.15 across Linux, macOS and Windows without Babel, to prove the zero-dependency path, plus one job with Babel.

## License

locjson is released under the [MIT License](https://github.com/fleizean/locjson/blob/main/LICENSE).
