# Examples

Small, runnable projects that use locjson. Each folder is self-contained, with
its own `locales/`, code and README.

| Example | What it shows | How to run |
|---|---|---|
| [quickstart](quickstart/) | `t()` with variables, plurals (`zero`/`one`/`other`), fallback to English, `use()`, `for_locale()`, the module-level `locjson.setup()` / `locjson.t()` | `python examples/quickstart/main.py` |
| [namespaced](namespaced/) | The `locales/<locale>/<namespace>.json` layout, `scope()`, `$meta` and `direction()` with an Arabic (right-to-left) locale | `python examples/namespaced/main.py` |
| [background-jobs](background-jobs/) | E-mails rendered in each user's language with `for_locale()`, safely on a `ThreadPoolExecutor` | `python examples/background-jobs/send_digests.py` |
| [testing](testing/) | Testing translations with pytest: `DictLoader` fixtures, `strict=True` and `LOCJSON_STRICT=1`, checks on the real catalog files | `cd examples/testing && python -m pytest` |
| [fastapi](fastapi/) | A middleware that negotiates `Accept-Language` and wraps the request in `l10n.use()`; tests with `TestClient` | `cd examples/fastapi && uvicorn app:app --reload` |
| [flask](flask/) | The same with `before_request` / `teardown_request`; tests with Flask's test client | `cd examples/flask && flask --app app run` |
| [django](django/) | A single-file Django project with a locale middleware; tests with Django's test client | `cd examples/django && python app.py runserver` |

## Installing locjson

locjson is not on PyPI yet. Install it from the repository root:

```bash
pip install -e .
```

or straight from GitHub:

```bash
pip install "locjson @ git+https://github.com/fleizean/locjson"
```

Once it is published, `pip install locjson` will be enough.

The framework examples list their own dependencies in `requirements.txt`
(`pip install -r examples/fastapi/requirements.txt`). They are only needed by
the examples: locjson itself has no runtime dependencies.

## How the examples are tested

- The quickstart, namespaced, background-jobs and testing examples need nothing
  but locjson. `tests/test_examples.py` runs them as part of locjson's own test
  suite on every supported Python and operating system. It compares each
  script's output with the "Output" block of its README, and runs the testing
  example's pytest suite.
- The FastAPI, Flask and Django examples run their `test_app.py` in the
  `examples-frameworks` CI job, with the packages from their
  `requirements.txt`.
