# Flask

A Flask app that answers in the language of the `Accept-Language` header.

```text
flask/
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
pip install -r examples/flask/requirements.txt
cd examples/flask
flask --app app run
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough. Flask and
pytest are only needed by this example; locjson itself has no dependencies.

Then, in another terminal:

```console
$ curl -i -H "Accept-Language: tr-TR,tr;q=0.9,en;q=0.8" http://127.0.0.1:5000/
HTTP/1.1 200 OK
Content-Language: tr
...
{"greeting":"Merhaba, Ada!","locale":"tr","title":"Fırınımıza hoş geldiniz"}

$ curl "http://127.0.0.1:5000/cart?items=3"
{"summary":"3 loaves in your basket"}
```

Run the tests with `python -m pytest` in this folder.

## What it shows

- `before_request` picks the locale with
  `l10n.negotiate(request.headers.get("Accept-Language"))` and enters
  `l10n.use(locale)`. Views just call `l10n.t(...)`.
- `teardown_request` leaves the `use()` block again, so the previous locale is
  restored even when a view raises. The block is kept open across the two
  hooks with a `contextlib.ExitStack` stored on `g`.
- `after_request` sets `Content-Language` on the response.
- `test_locale_does_not_leak_between_requests` checks that nothing stays
  behind after a request. With `l10n.set_locale()` in `before_request`
  instead, the locale of one request would stay on the worker thread and
  apply to the next request served by that thread.
