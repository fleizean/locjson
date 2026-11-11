# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-11

First release: the core runtime.

### Added

- `Localizer(path, *, loader, default_locale, fallbacks, missing, preload)` with
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

[Unreleased]: https://github.com/fleizean/locjson/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fleizean/locjson/releases/tag/v0.1.0
