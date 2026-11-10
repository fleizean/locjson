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

> **🚧 Status: early development, not yet released.** locjson is not on PyPI yet. The core runtime (0.1.0) is being built right now, so the API below is the planned 0.1 surface and may still change before the first release. Features marked *planned* do not exist yet.

## Why locjson?

Many web teams already keep their frontend translations in JSON files (i18next, vue-i18n). On the Python side, the standard answer is gettext with Babel: mature and powerful, but built around `.po`/`.mo` files, a compile step and a separate toolchain. That means two formats and two workflows for the same strings.

locjson keeps translations in **plain JSON** on the backend too, and focuses on a few things:

- **Small, typed runtime.** Zero runtime dependencies, ships `py.typed`, checked with `mypy --strict`.
- **Fast warm path.** Catalogs are loaded lazily per locale, validated once and compiled at load. A warm `t()` call is a dict lookup plus a join, with no file I/O.
- **Safe by construction.** Only named `{name}` placeholders. No attribute or index access, no format specs, no `eval`.
- **Loud at load, quiet at render.** Broken catalogs raise at load time with the file path and a JSON pointer. Translation slips at render time are lenient by default, or strict with `missing="raise"`.
- **Tooling included** *(planned)*. A `locjson` CLI to check, format, sync and measure your catalogs in CI and pre-commit.

## Features

| Feature | Status |
|---|---|
| JSON catalogs, single-file or namespaced layout (auto-detected) | 0.1, in progress |
| Nested keys flattened to dot keys (`nav.home`) | 0.1, in progress |
| BCP 47 locale normalization (`pt_BR` → `pt-BR`) and script-aware fallback chains | 0.1, in progress |
| Safe `{name}` interpolation with `{{` / `}}` escapes | 0.1, in progress |
| Plural entries with explicit `zero` and a one/other rule | 0.1, in progress |
| Current locale via `contextvars` (`use()` / `set_locale()`), safe across asyncio tasks and threads | 0.1, in progress |
| `missing` policy, `LocJsonError` hierarchy with file path + JSON pointer | 0.1, in progress |
| `reload()`, `negotiate()` (Accept-Language), `direction()` (LTR/RTL) | 0.1, in progress |
| Custom loaders via a `Loader` protocol, in-memory `DictLoader` | 0.1, in progress |
| CLDR plural rules for 17 built-in languages, optional Babel for the rest | planned 0.2 |
| `locjson` CLI: `init`, `check`, `stats`, `fmt` | planned 0.3 |
| `locjson` CLI: `sync`, `extract`, `import --from i18next` | planned 0.4 |
| `lazy()` strings, hot reload, FastAPI / Django / Flask recipes | planned 0.5 |

## Installation

locjson requires **Python 3.11+** and has no runtime dependencies.

```bash
pip install locjson
```

> The first release (0.1.0) is not published yet, so this command will not work until then.

Optional extras, for features that are still planned:

```bash
pip install "locjson[babel]"   # planned 0.2: full CLDR plural rules via Babel
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

l10n = Localizer(
    path="locales",
    default_locale="en",
    fallbacks={"pt-BR": ["pt"]},
    missing="key",  # "key" | "raise" | "empty" | callable(key, locale) -> str
)

print(l10n.t("greeting", name="Enes"))               # -> Hello, Enes!
print(l10n.t("greeting", locale="tr", name="Enes"))  # -> Merhaba, Enes!
print(l10n.t("inbox.messages", count=0))             # -> You have no messages
print(l10n.t("inbox.messages", count=1))             # -> You have 1 message
print(l10n.t("inbox.messages", count=3))             # -> You have 3 messages
print(l10n.t("nav.home", locale="pt-BR"))            # -> Home
print(l10n.t("nav.profile"))                         # -> nav.profile
print(l10n.has("nav.home", locale="tr"))             # -> True
print(sorted(l10n.locales))                          # -> ['en', 'tr']

with l10n.use("tr"):
    print(l10n.t("nav.home"))                        # -> Ana sayfa
    print(l10n.t("inbox.messages", count=3))         # -> 3 mesajınız var

# Or use the module-level default localizer:
import locjson

locjson.setup(path="locales", default_locale="en")
print(locjson.t("greeting", name="Enes"))            # -> Hello, Enes!
```

`pt-BR` has no catalog here, so the lookup walks `pt-BR → pt → en` and returns the English text. `nav.profile` exists nowhere, so `missing="key"` returns the key itself.

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

Plural rules:

- `count` is passed to the template automatically, so `{count}` just works.
- When `count == 0` and the entry has a `zero` form, `zero` is used in every language.
- Otherwise the language's plural category is used, falling back to `other`. In 0.1 this is a simple one/other rule. CLDR rules for 17 built-in languages arrive in 0.2 *(planned)*.

`$meta` describes the file:

```json
{
  "$meta": { "locale": "ar", "direction": "rtl" },
  "greeting": "مرحبًا، {name}!"
}
```

`locale` must match the file's locale, `direction` is `"ltr"` or `"rtl"`, and unknown `$meta` keys are rejected.

Numbers, booleans and arrays as values, duplicate keys, `NaN`/`Infinity` and key-path collisions are all rejected at load with an `InvalidCatalogError`. Files are read as UTF-8 (a BOM is accepted), so non-ASCII text such as Turkish `İ`/`ı` round-trips unchanged.

### Interpolation

Placeholders are **named fields only**, compiled once when the catalog loads:

| Template | Result |
|---|---|
| `"Hello, {name}!"` | `t("greeting", name="Enes")` → `Hello, Enes!` |
| `"Use {{name}} for a placeholder"` | `Use {name} for a placeholder` (doubled braces are literal) |
| `{0}`, `{user.name}`, `{items[0]}` | Rejected at load |
| `{price:.2f}`, `{value!r}` | Rejected at load (no format specs or conversions) |

Format values in Python before passing them in, for example `t("total", price=f"{price:.2f}")`.

If a variable is not passed, the placeholder stays as literal `{name}` text and a debug record is logged on the `locjson` logger. With `missing="raise"`, an `InterpolationError` is raised instead.

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

```python
with l10n.use("tr"):        # scoped: the previous locale is restored on exit
    l10n.t("nav.home")      # "Ana sayfa"

l10n.set_locale("tr")       # for the current context, e.g. one request
l10n.current_locale         # "tr"
```

### Negotiation and text direction

```python
l10n.negotiate("tr-TR,tr;q=0.9,en;q=0.8")  # "tr" (best match from Accept-Language)
l10n.direction("ar")                       # "rtl"
```

### Missing translations

| `missing=` | When a key is missing in the whole chain |
|---|---|
| `"key"` (default) | Returns the key, e.g. `"nav.profile"` |
| `"empty"` | Returns `""` |
| `"raise"` | Raises `MissingTranslationError`, and makes missing variables and a missing `count` raise too |
| `callable(key, locale)` | Returns whatever your function returns |

Every slip is logged at DEBUG level on the `locjson` logger, so you can surface them in development without noise in production.

### Errors

All exceptions inherit from `LocJsonError`:

| Exception | Raised when |
|---|---|
| `ConfigurationError` | The `Localizer` is misconfigured, e.g. neither `path` nor `loader` is given |
| `InvalidLocaleError` | A locale tag in the configuration is invalid |
| `InvalidCatalogError` | A catalog file is invalid. Exposes `.path` and `.pointer` (RFC 6901). |
| `MissingTranslationError` | A key is missing under `missing="raise"`. Also a `LookupError`. |
| `InterpolationError` | A variable or `count` is missing under `missing="raise"` |

### Custom loaders

Catalogs can come from anywhere that implements the `Loader` protocol (`discover_locales()` and `load(locale)`). An in-memory loader is included, which is handy for tests:

```python
from locjson import DictLoader, Localizer

l10n = Localizer(
    loader=DictLoader({"en": {"greeting": "Hello, {name}!"}}),
    default_locale="en",
)
```

Call `l10n.reload()` to rebuild all catalogs. The new set is swapped in atomically, and if a file is broken the old catalogs stay in place.

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
| **0.1** | Core runtime: JSON catalogs, fallback chains, safe interpolation, explicit-zero/one/other plurals, current locale, `reload()`, `negotiate()`, `direction()` | In progress |
| **0.2** | CLDR plural rules for 17 built-in languages, optional Babel for full CLDR coverage | Planned |
| **0.3** | CLI part 1: `init`, `check`, `stats`, `fmt`, output formats, pre-commit hooks | Planned |
| **0.4** | CLI part 2: `sync`, `extract`, `import --from i18next` | Planned |
| **0.5** | `lazy()` strings, hot reload, FastAPI / Django / Flask recipes | Planned |
| **1.0** | Stable public API and a documentation site | Planned |

See the [changelog](https://github.com/fleizean/locjson/blob/main/CHANGELOG.md) for what has shipped.

## Contributing

Issues and pull requests are welcome. Please open an issue first for larger changes.

```bash
git clone https://github.com/fleizean/locjson.git
cd locjson
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e . --group dev     # needs pip 25.1+

ruff check . && ruff format --check .
mypy --strict
pytest
```

CI runs the same checks on Python 3.11 to 3.15 across Linux, macOS and Windows.

## License

locjson is released under the [MIT License](https://github.com/fleizean/locjson/blob/main/LICENSE).
