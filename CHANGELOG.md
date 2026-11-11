# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-11

CLDR plural rules.

### Added

- CLDR 49 cardinal plural rules for 17 built-in languages (`en`, `tr`, `de`,
  `fr`, `es`, `it`, `pt`, `nl`, `ru`, `uk`, `pl`, `cs`, `ar`, `he`, `ja`, `zh`,
  `ko`), plus the separate `pt-PT` rule shared by the locales CLDR groups under
  it, written as plain Python functions with no rule-string parsing or `eval`.
  A rule is looked up by exact tag, then by script-aware parents, then by
  language, and is resolved once per catalog at load.
- Plural operands per Unicode TR35 (`n`, `i`, `v`, `w`, `f`, `t`) for `int`,
  `float` and `Decimal` counts. A `Decimal` keeps its visible fraction digits
  (`Decimal("1.0")` is `other` in English and `one` in Turkish), and a float is
  read through its shortest `repr`.
- `categories_for(locale)`, also available as `locjson.plural.categories_for`,
  returns the plural categories a locale's rule can produce. An invalid tag
  raises `InvalidLocaleError`.
- The optional `locjson[babel]` extra gives every other CLDR language Babel's
  plural rules. Babel is imported lazily, only when a catalog in such a
  language is loaded, never by `import locjson`. A locale Babel does not know
  falls back to the one/other rule. Babel compiles CLDR rule text with `eval`
  on its own bundled data; locjson's code never does.
- Tests against the pinned CLDR 49 plural samples and against Babel's rules,
  and a CI job that runs the suite with Babel installed.

### Changed

- Plural forms follow each language's CLDR rule instead of the 0.1 one/other
  rule. For example, French and Brazilian Portuguese use `one` for 0 and 1.5
  when the entry has no `zero` form, and Russian picks `few` or `many`. The
  explicit `zero` form still wins for a count of 0 in every language.
- Invalid counts (`True`/`False`, strings, NaN, infinities, other types, more
  than 1000 digits) are now slips: 0.1 treated `True` as 1. The `other` form is
  used with `{count}` left as literal text, the slip is logged, and strict mode
  or `missing="raise"` raises `InterpolationError`.

## [0.1.0] - 2026-11-11

First release: the core runtime.

### Added

- `Localizer(path, *, loader, default_locale, fallbacks, missing, preload, strict)`
  (or just `Localizer("locales")`) with
  `t(key, /, *, locale, count, context, **vars)`, `has()`, `locales`,
  `default_locale` and `current_locale`. A warm `t()` is a dictionary lookup
  plus a join of precompiled segments, with no file I/O.
- JSON catalog format: one `<locale>.json` file per locale or a
  `<locale>/<namespace>.json` directory, auto-detected. Nested objects flatten to
  dot keys, `""` and `null` mean untranslated, `$meta` holds `locale` and
  `direction`, and other `$` keys are ignored. Broken catalogs (invalid JSON,
  duplicate keys, `NaN`, non-string values, key-path collisions) raise
  `InvalidCatalogError` at load with the file path and a JSON pointer.
- UTF-8 catalogs with an optional BOM, so non-ASCII text such as Turkish
  `İ`/`ı` round-trips unchanged.
- BCP 47 locale normalization (`pt_BR` → `pt-BR`, `iw` → `he`) and a
  script-aware fallback chain: the locale, its explicit `fallbacks`, its parents,
  then `default_locale` (`zh-TW` → `zh-Hant` → `en`, never `zh`).
- Safe interpolation: named `{name}` fields only, `{{` and `}}` for literal
  braces. Positional fields, attribute and index access, format specs and
  conversions are rejected at load. No `eval`.
- Plural entries keyed by CLDR category with a required `other`, an explicit
  `zero` form that wins for a count of 0 in every language, a one/other rule
  and `"$plural": false` to opt out.
- The `missing` policy (`"key"`, `"empty"`, `"raise"` or a callable).
- `strict=` on `Localizer` and `setup()`: `True` makes every slip raise, and
  `None` (the default) reads the `LOCJSON_STRICT` environment variable once, at
  construction. The result is exposed as `Localizer.strict`.
- Slip logging on the `locjson` logger: WARNING the first time per kind, locale
  and key, DEBUG afterwards, never with variable values.
- Bound translators: `Localizer.for_locale()` and `Localizer.scope()` (and
  `locjson.for_locale()` / `locjson.scope()`) return an immutable, composable
  `Translator` with a bound locale, a key prefix or both.
- A current locale per Localizer in a `ContextVar`, set with `use()` (a context
  manager) or `set_locale()`, and isolated across asyncio tasks and threads.
- `reload()`, which rebuilds the loaded catalogs and swaps them in atomically,
  keeping the old ones when a file is broken.
- `negotiate()` for `Accept-Language` headers and `direction()` (`"ltr"` or
  `"rtl"`, from `$meta` or a built-in table).
- A module-level API: `setup()`, `get_localizer()`, `t()`, `has()`, `use()`,
  `set_locale()`, `negotiate()` and `direction()`.
- Custom loaders through the `Loader` protocol, with `FilesystemLoader`,
  `DictLoader` and `RawSource`.
- An exception hierarchy under `LocJsonError`: `ConfigurationError`,
  `InvalidLocaleError`, `InvalidCatalogError`, `MissingTranslationError` and
  `InterpolationError`.
- Zero runtime dependencies, a lightweight `import locjson`, inline types with a
  `py.typed` marker, checked with `mypy --strict`.
- Hatchling packaging with a `src/` layout, a static version and a `py.typed` marker.
- Import-boundary and encoding guards: ruff module-level import bans, an
  import-linter contract, a fresh-subprocess `sys.modules` test, encoding warnings
  as errors and LF line endings.
- CI matrix on Python 3.11–3.15 × Linux/macOS/Windows plus a non-blocking
  free-threaded 3.14t job, with combined branch coverage ≥ 90 %.
- Release workflow that publishes to TestPyPI and PyPI through trusted publishing.

[Unreleased]: https://github.com/fleizean/locjson/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/fleizean/locjson/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/fleizean/locjson/releases/tag/v0.1.0
