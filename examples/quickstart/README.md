# Quickstart

The basics of locjson in one script: variables, plurals, the fallback chain,
the current locale, bound translators and the module-level API.

```text
quickstart/
├── locales/
│   ├── en.json
│   └── tr.json      # has no "farewell" key, on purpose
└── main.py
```

## Run it

From the repository root, install locjson, then run the script:

```bash
pip install -e .                 # locjson is not on PyPI yet
python examples/quickstart/main.py
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough.

## What it shows

- `Localizer(LOCALES)`: the catalog folder is the only required argument, and
  `default_locale` is `"en"`.
- `t("greeting", name="Ada")`: named `{name}` placeholders. `{{` and `}}` are
  literal braces (`help`).
- `t("shelf.books", count=n)`: a plural entry. The `zero` form wins for 0,
  then `one` for 1, otherwise `other`. `{count}` is filled in automatically.
- Fallback: `tr.json` has no `farewell`, so the Turkish lookup returns the
  English text. `tr-TR` has no catalog, so its chain is `tr-TR → tr → en`. A
  key that exists nowhere returns the key itself.
- `with l10n.use("tr"):` sets the current locale for a block and restores it
  afterwards.
- `l10n.for_locale("tr")` returns a translator bound to one locale. An explicit
  `locale=` argument still wins.
- `locjson.setup()` + `locjson.t()`: one default Localizer for small scripts
  and CLI tools.

## Output

<!-- expected-output -->
```text
Locales: en, tr

== Variables
Hello, Ada!
Merhaba, Ada!
Type {title} to search by title.

== Plurals
Your shelf is empty
You have 1 book on your shelf
You have 3 books on your shelf
Rafınız boş
Rafınızda 1 kitap var
Rafınızda 3 kitap var

== Fallback
See you soon, Ada.
Kitaplık
shelf.title

== use(): the current locale
Current locale: en
Current locale: tr
Kitaplık
Rafınızda 2 kitap var
Current locale: en

== for_locale(): a translator bound to one locale
Merhaba, Yağız!
Hello, Yağız!

== Module-level API, for scripts and CLIs
Hello, Enes!
Merhaba, Enes!
```
