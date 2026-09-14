# Contributing

Thanks for considering a contribution to this template.

## Setup

```bash
uv sync
cp .env.example .env
uv run python manage.py migrate
```

## Before opening a PR

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```

Both run in CI and gate merging. It's also worth running

```bash
uv run python manage.py check --deploy
```

against a `DEBUG=False` env before touching anything in `config/settings.py` —
CI doesn't run this one (it exits 0 on warnings, so it wouldn't gate anything
if it did), but it's the fastest way to catch a hardening regression.

## Scope

This is a template, not an application — changes should stay generically
useful to anyone cloning it, not specific to one downstream project. A
feature you need for your own project probably belongs in your clone after
you've renamed it (see [docs/NEW_PROJECT.md](docs/NEW_PROJECT.md)), not in
this repo.

Bug fixes, doc corrections, and clearly reusable additions are all welcome.
For anything larger, open an issue first so the direction can be agreed on
before you put the work in.

## Style

Keep commits focused and explain *why*, not just *what*. Small, reviewable
PRs over large ones. No comments that restate what the code already says —
see the existing modules for the level of comment this project expects.
