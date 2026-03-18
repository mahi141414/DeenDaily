# Shorts Forge

Web app + background worker for turning a YouTube video into Shorts, uploading them automatically, and retrying blocked uploads after 1 hour.

## What this repo contains

- `app.py` - Flask web app for queuing jobs and viewing status
- `worker.py` - background worker that processes queued jobs
- `processor.py` - video cutting and upload pipeline
- `convex/` - Convex schema and job mutations for durable state
- `render.yaml` - Render web + worker service config

## How it works

- Paste a YouTube URL into the web UI.
- The job is stored in Convex.
- The Render worker picks it up, downloads the source, finds short segments, cuts them, and uploads them.
- If YouTube returns `uploadLimitExceeded`, the job is marked `waiting_retry` and will resume after 1 hour from the last saved segment.

## Local setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Install Convex backend dependencies:

```bash
npm install
```

3. Create a Convex project and set up the backend:

```bash
npx convex dev
```

4. Set environment variables in `.env`:

- `CONVEX_URL`
- `NVIDIA_API_KEY`
- `YOUTUBE_TOKEN_JSON`
- `FLASK_SECRET_KEY`

5. Run the web app:

```bash
python app.py
```

6. Run the worker in another terminal:

```bash
python worker.py
```

If you already have a local `token.pickle`, export it into a JSON string for Render with:

```bash
python export_youtube_token.py > youtube-token.json
```

Then copy the JSON contents into the `YOUTUBE_TOKEN_JSON` Render secret.

## Render deployment

Render should run this as two services:

- Web service: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Worker service: `python worker.py`

Use the values in `render.yaml` as a starting point.

## YouTube auth on Render

The worker is headless, so interactive Google login will not work there.

Use a reusable refresh token stored in `YOUTUBE_TOKEN_JSON` or mount a persistent `token.pickle` file. The code supports `YOUTUBE_TOKEN_JSON` directly.

## Notes

- This version is URL-based to match the current subtitle-driven pipeline.
- If you want direct file upload next, the pipeline will need transcription support instead of subtitle extraction.
