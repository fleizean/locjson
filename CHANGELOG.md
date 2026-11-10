# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Hatchling packaging with a `src/` layout, a static version and a `py.typed` marker.
- Import-boundary and encoding guards: ruff module-level import bans, an
  import-linter contract, a fresh-subprocess `sys.modules` test, encoding warnings
  as errors and LF line endings.
- CI matrix on Python 3.11–3.15 × Linux/macOS/Windows plus a non-blocking
  free-threaded 3.14t job, with combined branch coverage ≥ 90 %.
- Release workflow that publishes to TestPyPI and PyPI through trusted publishing.

[Unreleased]: https://github.com/fleizean/locjson/commits/main
