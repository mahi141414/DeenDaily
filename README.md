# YT Render Probe

This folder is a standalone Render test app for checking whether yt-dlp can download the YouTube URL on Render.

## Render settings

- Root directory: `HOSTEDv1/yt_render_probe`
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`

## What it does

- uses the hardcoded test URL from `app.py`
- uses `cookie.json` from this folder automatically
- converts the JSON cookie export into yt-dlp cookie format
- tries the download on boot
- shows success or failure in the browser
