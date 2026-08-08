# Background tasks

Celery, configured in `config/celery.py`, autodiscovering `tasks.py` in every
installed app.

## Eager mode in development

With no `CELERY_BROKER_URL` (or `REDIS_URL`), `CELERY_TASK_ALWAYS_EAGER` is on
and `.delay()` runs the task inline, synchronously, in the calling process.

This is not just convenience. Without a broker `.delay()` would otherwise
silently queue into nothing, and you would not discover it until production.
Running inline means task code is genuinely exercised in dev, and
`CELERY_TASK_EAGER_PROPAGATES` makes failures raise instead of being swallowed.

The trade-off is that eager mode does not exercise serialization boundaries or
real concurrency. Before shipping anything task-heavy, run a real worker once.

## Running a real worker

```
# terminal 1
redis-server

# terminal 2 — note the pool flag on Windows
uv run celery -A config worker --loglevel=info --pool=solo

# terminal 3, if you need periodic tasks
uv run celery -A config beat --loglevel=info
```

**`--pool=solo` is required on Windows.** Celery's default prefork pool relies
on `fork()` and does not work there; without it the worker starts and then fails
in confusing ways. On Linux in production, drop the flag.

Verify the wiring:

```
uv run celery -A config call core.ping
```

## Writing a task

```python
from celery import shared_task


@shared_task(name="myapp.do_thing")
def do_thing(thing_id: int) -> str: ...
```

Use `@shared_task`, not `@app.task`, so the module does not import the Celery
app and stays easy to test.

Pass **identifiers, not objects**. Arguments are JSON-serialized
(`CELERY_TASK_SERIALIZER = "json"`), and a model instance pickled into a queue is
stale by the time it runs.

## Existing tasks

| Task | Purpose |
| --- | --- |
| `core.ping` | Confirms a worker is connected. |
| `core.send_email` | Sends mail with retry and exponential backoff, up to 3 attempts. |

All allauth mail — verification, password reset — goes through `core.send_email`
via `AccountAdapter.send_mail`. Rendering happens in the request (the templates
need request context); only delivery is queued, so a slow SMTP server cannot
stall a signup response.

## Periodic tasks

`django-celery-beat` is installed, so schedules live in the database and are
editable in the admin under **Periodic Tasks**. No code deploy to change a
schedule.

## Production

Run the worker as its own process, separate from the web server:

```
celery -A config worker --loglevel=info --concurrency=4
celery -A config beat  --loglevel=info
```

Run exactly one `beat` process. Two will double-fire every scheduled task.
