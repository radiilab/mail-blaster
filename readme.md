# Mautic (updated) Docker setup

- Access Mautic at http://localhost:8080
- Uses MySQL 8.0 and latest Mautic image
- Optional Gmail SMTP via `MAUTIC_MAILER_DSN`

Quick start
- Copy `.env.example` to `.env` and fill values (DB password, Gmail DSN, etc.)
- From `mail-blaster/` run: `docker compose up -d`
- Wait for DB to become healthy, then visit http://localhost:8080

Database connection (during Mautic install)
- Host: `db`
- Port: `3306`
- Name: `mautic`
- User: `mautic`
- Password: value from `MAUTIC_DB_PASSWORD` in `.env`

Gmail SMTP (recommended)
- Create a Google App Password (required for Gmail SMTP)
- Set `MAUTIC_MAILER_DSN` in `.env`:
  - Example: `smtp://alice%40gmail.com:abcdefghijklmnop@smtp.gmail.com:587?encryption=tls`
- You can also configure mail in Mautic UI under Settings → Configuration → Email settings.

Azure MySQL → Mautic contact sync
- Script: `scripts/sync_to_mautic.py`
- Install deps: `python3 -m venv .venv && . .venv/bin/activate && pip install -r scripts/requirements.txt`
- Configure `.env` with your Azure MySQL and Mautic API credentials
- Run once: `env $(grep -v '^#' .env | xargs) python3 scripts/sync_to_mautic.py`

Schedule periodic sync (choose one)
- Cron (host):
  - `*/15 * * * * cd /path/to/mail-blaster && /usr/bin/env bash -lc 'source .venv/bin/activate && env $(grep -v "^#" .env | xargs) python3 scripts/sync_to_mautic.py >> sync.log 2>&1'`
- Windows Task Scheduler: run the same command via a scheduled task every N minutes.

Notes
- Pin the Mautic image to a specific major (e.g., `mautic/mautic:v5-apache`) for stability if desired.
- This stack enables Mautic’s cron inside the container (`MAUTIC_RUN_CRON_JOBS=true`).
