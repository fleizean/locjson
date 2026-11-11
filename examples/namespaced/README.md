# Namespaced catalogs and text direction

One JSON file per feature instead of one big file per locale, plus an Arabic
locale that is written right to left.

```text
namespaced/
├── locales/
│   ├── ar/
│   │   ├── auth.json     # no "attempts_left" yet: falls back to English
│   │   └── common.json   # "$meta": {"direction": "rtl"}
│   ├── en/
│   │   ├── auth.json
│   │   └── common.json
│   └── tr/
│       ├── auth.json
│       └── common.json
└── main.py
```

## Run it

From the repository root, install locjson, then run the script:

```bash
pip install -e .                 # locjson is not on PyPI yet
python examples/namespaced/main.py
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough.

## What it shows

- The namespaced layout: `locales/<locale>/<namespace>.json`. The file name
  becomes the first part of every key, so `login.title` in `en/auth.json` is
  looked up as `auth.login.title`. locjson detects the layout by itself.
- `l10n.scope("auth")` returns a translator that prepends `auth.` to every key.
  It combines with `for_locale()`: `l10n.scope("auth").for_locale("tr")`.
- Fallback works per key: `ar/auth.json` has no `attempts_left`, so that one
  message comes from English while the rest stays Arabic.
- `$meta` holds file metadata, never translations. `"direction": "rtl"` in
  `ar/common.json` makes `l10n.direction("ar")` return `rtl`. Locales without
  a declared direction use a built-in table, so `he` is `rtl` even without a
  catalog.
- A typical use: `<html lang="..." dir="...">` in a page template.

## Output

<!-- expected-output -->
```text
Locales: ar, en, tr

== Namespaced keys
Welcome back, Ada!
Gezilerim
تسجيل الدخول

== scope('auth'): no need to repeat the namespace
en: Sign in | Sign out
tr: Giriş yap | Çıkış yap
ar: تسجيل الدخول | تسجيل الخروج
ada için şifre yanlış.
2 deneme hakkınız kaldı
2 attempts left

== direction(): from $meta, or a built-in table
en: ltr
tr: ltr
ar: rtl
he: rtl

== Putting it together
<html lang="en" dir="ltr"><h1>Travel Notes</h1>
<html lang="ar" dir="rtl"><h1>ملاحظات السفر</h1>
```

`direction()` takes the first `$meta.direction` found along the locale's
fallback chain, but only from catalogs in the same language and script as the
requested locale: `ar-EG` uses the direction declared in `ar`, while a
`"direction": "ltr"` in `en` never applies to `ar` or `he`, even though they
fall back to `en` for missing keys. A script counts too: `sr-Latn` never uses
the direction declared in `sr`, which is written in Cyrillic.
