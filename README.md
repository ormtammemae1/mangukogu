# Mängukogu

A small home-screen web app for a kindergarten special-needs teacher: learning games sorted into
categories (Peenmotoorika, Töömälu, …), each with a photo, age range and notes. The UI is in Estonian.

FastAPI + SQLite + plain HTML/JS.

## Run locally

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/uvicorn app.main:app --reload --port 8020

The database (`data/mangukogu.db`) and photos (`data/images/`) are created on first start; the
default categories are added when the database is new.

## Tests

    .venv/bin/python -m pytest

## Deploy to a Raspberry Pi

Replace `user@pi-host` with your Pi's login and hostname.

    rsync -av --exclude .venv --exclude data --exclude .git --exclude __pycache__ --exclude .pytest_cache \
        ./ user@pi-host:mangukogu/
    ssh user@pi-host 'cd mangukogu && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart mangukogu'

First time only: create the venv on the Pi, then `sudo sh ~/mangukogu/deploy/setup.sh`.

## Backup

Everything lives in `data/` on the Pi: copy `mangukogu.db` and the `images/` folder.
