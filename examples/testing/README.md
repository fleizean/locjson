# Testing translations

How to test code that renders translated text, and how to make a typo in a
key or a forgotten variable fail the test suite instead of reaching users.

```text
testing/
├── locales/
│   ├── en.json
│   └── tr.json
├── conftest.py      # fixtures: in-memory catalogs, strict mode
├── pytest.ini
├── shop.py          # the code under test
└── test_shop.py
```

## Run it

From the repository root, install locjson and pytest, then run the tests:

```bash
pip install -e . pytest          # locjson is not on PyPI yet
cd examples/testing
python -m pytest
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough.
`python shop.py` prints the rendered messages.

## What it shows

- **Pass the Localizer in.** `shop.order_confirmation()` takes the Localizer as
  an argument, so a test can hand it one built from in-memory catalogs.
- **`DictLoader` fixtures.** `Localizer(loader=DictLoader({...}))` takes the
  same documents as the JSON files. The expected strings sit right next to the
  assertions.
- **`strict=True`.** A missing key raises `MissingTranslationError`, and a
  missing variable or a plural message without `count` raises
  `InterpolationError`. Without strict mode, the same slips render the key or
  a literal `{name}` and are logged once at WARNING on the `locjson` logger
  (`test_lenient_mode_logs_the_slip_once`).
- **`LOCJSON_STRICT=1`.** With `strict=None` (the default), the Localizer reads
  this environment variable when it is created, so `LOCJSON_STRICT=1 pytest`
  makes the application's own Localizer strict for a whole test run, without
  changing any code.
- **Checks on the real files.** `preload=True` loads and validates every
  catalog up front. To check that each locale translates every key the code
  uses, build a Localizer with that locale as `default_locale`: its fallback
  chain then has no English step that could hide a gap.
- **Plural forms per language.** `locjson.categories_for(locale)` returns the
  plural forms a language's rule can pick (`one`/`other` for English and
  Turkish, `one`/`few`/`many`/`other` for Russian). The test checks that each
  plural entry in the JSON files has all of them.
- Assertions compare complete rendered strings, including Turkish text such as
  `ı` and `ş`.

Expected result:

```text
19 passed
```
