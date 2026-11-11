# FastAPI

A FastAPI app that answers in the language of the `Accept-Language` header.

```text
fastapi/
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
pip install -r examples/fastapi/requirements.txt
cd examples/fastapi
uvicorn app:app --reload
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough. FastAPI and
the other packages in `requirements.txt` are only needed by this example;
locjson itself has no dependencies.

Then, in another terminal:

```console
$ curl -i -H "Accept-Language: tr-TR,tr;q=0.9,en;q=0.8" http://127.0.0.1:8000/
HTTP/1.1 200 OK
content-language: tr
...
{"locale":"tr","title":"Fırınımıza hoş geldiniz","greeting":"Merhaba, Ada!"}

$ curl "http://127.0.0.1:8000/cart?items=3"
{"summary":"3 loaves in your basket"}
```

Run the tests with `python -m pytest` in this folder.

## What it shows

- An HTTP middleware picks the locale with
  `l10n.negotiate(request.headers.get("accept-language"))`. It returns the best
  locale that has a catalog, or `default_locale` for a missing, unknown or
  malformed header. It never raises on bad input.
- `with l10n.use(locale):` around `call_next(request)` makes that locale the
  current one while the endpoint runs. Endpoints just call `l10n.t(...)`.
- The current locale lives in a `ContextVar`, so concurrent requests never see
  each other's locale, and `use()` restores the previous value when the block
  ends. `test_locale_does_not_leak_between_requests` checks this.
- The middleware also sets `Content-Language` on the response.

Prefer `use()` to `set_locale()` here: a value set with `set_locale()` stays
for whatever runs later in the same context.
