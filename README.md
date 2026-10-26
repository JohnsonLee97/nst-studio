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
History currently uses JSON metadata files; MySQL is not implemented yet.

This version is intended for local development.
