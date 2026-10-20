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

## Deploy to Vercel

Vercel's disk is read-only and temporary, so there the games live in Postgres and the photos in
Vercel Blob. Both connect from the project's **Storage** tab in the Vercel dashboard:

1. **Postgres:** add a Neon database (Marketplace) and connect it to the project. This sets `DATABASE_URL`.
2. **Photos:** create a Blob store with **public** access and connect it. This sets `BLOB_STORE_ID`
   (older stores set `BLOB_READ_WRITE_TOKEN` instead; either works).
3. Redeploy. The tables and default categories are created on first start.

Without both, the app refuses to start on Vercel and says what to connect. Photo URLs in Blob are
public but random and unguessable.

## Deploy to a Raspberry Pi

Replace `user@pi-host` with your Pi's login and hostname.

    rsync -av --exclude .venv --exclude data --exclude .git --exclude __pycache__ --exclude .pytest_cache \
        ./ user@pi-host:mangukogu/
    ssh user@pi-host 'cd mangukogu && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart mangukogu'

First time only: create the venv on the Pi, then `sudo sh ~/mangukogu/deploy/setup.sh`.

## Backup

Everything lives in `data/` on the Pi: copy `mangukogu.db` and the `images/` folder.
