# Background jobs and e-mails

A daily digest e-mail, rendered for each user in the language stored in their
profile. The jobs run on a thread pool, the way they would on a Celery, RQ or
cron worker. Nothing is sent: the e-mails are printed.

```text
background-jobs/
├── locales/
│   ├── en.json
│   ├── pt.json
│   └── tr.json
└── send_digests.py
```

## Run it

From the repository root, install locjson, then run the script:

```bash
pip install -e .                 # locjson is not on PyPI yet
python examples/background-jobs/send_digests.py
```

`pip install "locjson @ git+https://github.com/fleizean/locjson"` works too.
Once locjson is published, `pip install locjson` will be enough.

## What it shows

- Outside a web request there is no current locale to rely on. Each job calls
  `l10n.for_locale(user.language)` and gets a translator bound to that
  language. Chained with `.scope("digest")`, the job writes `t("subject")`
  instead of `t("digest.subject")`.
- A bound translator never reads or changes the Localizer's current locale, so
  many jobs can share one Localizer on a thread pool. The script checks that
  the parallel run gives the same e-mails as a sequential one, and that the
  current locale is still `en` afterwards.
- Profile values are normalized and fall back sensibly: `tr-TR` uses `tr`,
  `pt_BR` becomes `pt-BR` and uses `pt`, `de` has no catalog and gets English,
  and an invalid tag binds the default locale instead of raising.

Avoid `l10n.set_locale()` in jobs on a reused worker thread: the value stays in
that thread's context and leaks into the next job. Use `for_locale()`, or
`with l10n.use(...)` when code deeper down calls `l10n.t()` without a
translator.

## Output

<!-- expected-output -->
```text
To: Ada [en]
Subject: Your daily digest, Ada
Hi Ada,
You are all caught up.

The Acme team
----------------------------------------
To: Yağız [tr-TR]
Subject: Günlük özetiniz, Yağız
Merhaba Yağız,
3 okunmamış bildiriminiz var.

Acme ekibi
----------------------------------------
To: João [pt-BR]
Subject: Seu resumo diário, João
Olá, João,
Você tem 1 notificação não lida.

Equipe Acme
----------------------------------------
To: Hans [de]
Subject: Your daily digest, Hans
Hi Hans,
You have 2 unread notifications.

The Acme team
----------------------------------------
To: Elif [tr]
Subject: Günlük özetiniz, Elif
Merhaba Elif,
1 okunmamış bildiriminiz var.

Acme ekibi
----------------------------------------
To: Sam [en]
Subject: Your daily digest, Sam
Hi Sam,
You have 5 unread notifications.

The Acme team
----------------------------------------
Current locale after the jobs: en
Same as a sequential run: True
```
