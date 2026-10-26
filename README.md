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
Grant it SELECT and INSERT permissions on `nst_studio.generations`.

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
