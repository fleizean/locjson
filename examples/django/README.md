# Django

A single-file Django project that answers in the language of the
`Accept-Language` header. The settings, the middleware, the views and the URLs
all live in `app.py`.

```text
django/
├── locales/
│   ├── en.json
│   └── tr.json
├── app.py
├── pytest.ini
├── requirements.txt
└── test_app.py
```

## Run it

From the repository root:

```bash
pip install -e .                                # locjson is not on PyPI yet
pip install -r examples/django/requirements.txt
cd examples/django
python app.py runserver
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough. Django and
pytest are only needed by this example; locjson itself has no dependencies.

Then, in another terminal:

```console
$ curl -i -H "Accept-Language: tr-TR,tr;q=0.9,en;q=0.8" http://127.0.0.1:8000/
HTTP/1.1 200 OK
Content-Language: tr
...
{"locale": "tr", "title": "Fırınımıza hoş geldiniz", "greeting": "Merhaba, Ada!"}

$ curl "http://127.0.0.1:8000/cart?items=3"
{"summary": "3 loaves in your basket"}
```

Run the tests with `python -m pytest` in this folder.

## What it shows

- `locale_middleware` picks the locale with
  `l10n.negotiate(request.headers.get("Accept-Language"))` and wraps the rest
  of the request in `with l10n.use(locale):`. Views just call `l10n.t(...)`.
- `use()` restores the previous locale when the block ends, so nothing stays
  behind on the worker thread. `test_locale_does_not_leak_between_requests`
  checks this.
- The middleware also sets `Content-Language` on the response.
- In a regular Django project, put the middleware in a module of your app and
  add its dotted path to `MIDDLEWARE` in `settings.py`. Create the
  `Localizer` once, at import time, for example in that same module.

This example uses locjson instead of Django's gettext-based translation
system; `django.middleware.locale.LocaleMiddleware` is not needed.
