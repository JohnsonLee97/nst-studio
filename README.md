# NST Studio

A Flask web application for neural style transfer using TensorFlow and VGG19.

## Features

- Upload content and style images with browser previews.
- Choose style influence and iteration count.
- Generate and download stylised images.
- Record generation settings and processing time.
- Browse previous results through a history page.

## Run locally

Use Python 3.12.

```bash
python3.12 -m venv .venv-nst
source .venv-nst/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

The first generation downloads pretrained VGG19 weights and requires
an internet connection. CPU generation can take time.

Uploaded files and generated results are stored locally in uploads/.
History is stored in MySQL. Uploaded images and generated results remain
in local run folders under uploads/. JSON metadata is retained per run.

Completion timestamps are stored in UTC and displayed using the
DISPLAY_TIMEZONE setting.

This version is intended for local development.

## Database setup

Install and start MySQL Server, then create the database structure:

```bash
sudo mysql < schema.sql
```

Create a local MySQL account named `nst_app` with a private password.
Grant it SELECT, INSERT and DELETE permissions on `nst_studio.generations`.

Copy the configuration template:

```bash
cp .env.example .env
```

Fill in your local database password in `.env`. Never commit `.env`.

Test the connection:

```bash
python db.py
```

## Import existing local history

To import existing uploads/\*/metadata.json records into MySQL:

```bash
python import_history.py
```

Existing run IDs are skipped. Image files must remain in their run folders.

## Image privacy and retention

Generation history, result pages and downloads are restricted to the
browser session that created them. Clearing session cookies or using
another browser session removes access to previous results.

Configure retention in `.env`:

```dotenv
IMAGE_RETENTION_HOURS=24
```

Results become inaccessible after the configured period. The cleanup
script removes expired upload folders and database records.

Preview cleanup without deleting anything:

```bash
python cleanup_history.py
```

Permanently delete expired runs:

```bash
python cleanup_history.py --delete
```

The configured database account needs SELECT, INSERT and DELETE
permissions on `nst_studio.generations`.

### Automatic cleanup

For local WSL development, cron runs cleanup hourly using the project's
virtual-environment Python. The latest output is written to
`logs/cleanup.log`. The `logs/` directory must exist and is excluded
from Git.

The crontab is configured separately from this repository. Use
`crontab -e` to add the following entry, replacing `/absolute/path/nst-web`
with the actual project path:

```cron
0 * * * * /usr/bin/flock -n /absolute/path/nst-web/logs/cleanup.lock /absolute/path/nst-web/.venv-nst/bin/python /absolute/path/nst-web/cleanup_history.py --delete > /absolute/path/nst-web/logs/cleanup.log 2>&1
```

Cleanup requires WSL, cron, MySQL and Redis to be running. Expired files remain
stored until a successful cleanup run. Folders without a usable
completion timestamp are skipped for review.

## Background generation

Image generation runs in a separate RQ worker using Redis.

Install and start Redis in WSL:

```bash
sudo apt install redis-server
sudo systemctl enable --now redis-server
```

Configure these settings in `.env`:

```dotenv
REDIS_URL=redis://127.0.0.1:6379/0
RQ_QUEUE_NAME=nst
GENERATION_TIMEOUT_SECONDS=900
MAX_QUEUED_JOBS=3
QUEUE_WAIT_TIMEOUT_SECONDS=600
JOB_POLL_INTERVAL_SECONDS=2
```

After completing database and environment setup, start Flask:

```bash
source .venv-nst/bin/activate
python app.py
```

In a second terminal, start one generation worker:

```bash
source .venv-nst/bin/activate
python worker.py
```

Keep both processes running. The worker processes one job at a time.
Each browser session can have one active generation. Additional visitors
can queue jobs until the configured waiting capacity is reached.

The page checks job status and opens the result when ready. Jobs that
exceed the waiting limit expire without running.

Cleanup preserves active jobs and removes eligible expired completed
or unfinished runs. Redis must be available for cleanup to check job
status safely.
