import json
import os
import subprocess
import threading
import time
from pathlib import Path

import imageio_ffmpeg
from flask import Flask

TEST_URL = os.getenv("TEST_URL", "https://www.youtube.com/watch?v=BCl3wPhVin8")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/yt_render_probe"))
PORT = int(os.getenv("PORT", "5000"))

app = Flask(__name__)
state = {
    "running": False,
    "ok": False,
    "done": False,
    "message": "Starting...",
    "output_file": "",
    "started_at": None,
    "finished_at": None,
}
state_lock = threading.Lock()


def set_state(**updates):
    with state_lock:
        state.update(updates)


def get_state():
    with state_lock:
        return dict(state)


def build_command():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    cookies_arg = normalize_cookies_file()
    command = [
        "yt-dlp",
        "--ffmpeg-location", ffmpeg_path,
        "--no-check-certificate",
        "--extractor-args", "youtube:player_client=android",
        "-f", "bestvideo*+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        TEST_URL,
    ]

    if cookies_arg:
        command[1:1] = ["--cookies", str(cookies_arg)]

    return command


def normalize_cookies_file():
    source = os.getenv("YTDLP_COOKIES_FILE")
    if not source:
        local_cookie_txt = Path(__file__).with_name("cookies-www-youtube-com.txt")
        if local_cookie_txt.exists():
            source = str(local_cookie_txt)
        else:
            local_cookie_json = Path(__file__).with_name("cookie.json")
            if local_cookie_json.exists():
                source = str(local_cookie_json)
    if not source:
        return None

    source_path = Path(source)
    if not source_path.exists():
        return None

    if source_path.suffix.lower() != ".json":
        return source_path

    target_path = DOWNLOAD_DIR / "cookies.txt"
    try:
        with source_path.open("r", encoding="utf-8") as input_file:
            cookies = json.load(input_file)

        lines = ["# Netscape HTTP Cookie File"]
        for cookie in cookies:
            domain = str(cookie.get("domain", ""))
            host_only = bool(cookie.get("hostOnly", False))
            include_subdomains = "FALSE" if host_only else "TRUE"
            path = str(cookie.get("path", "/"))
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            expiration = cookie.get("expirationDate")
            if expiration is None:
                expiration = 0
            else:
                expiration = int(float(expiration))
            name = str(cookie.get("name", ""))
            value = str(cookie.get("value", ""))
            lines.append("\t".join([domain, include_subdomains, path, secure, str(expiration), name, value]))

        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path
    except Exception as exc:
        set_state(message=f"Cookie conversion failed: {exc}")
        return None


def run_probe():
    set_state(running=True, ok=False, done=False, started_at=time.time(), message="Running yt-dlp probe...")
    command = build_command()

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        output_file = ""
        if result.returncode == 0:
            candidates = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
            output_file = str(candidates[0]) if candidates else ""
            set_state(
                running=False,
                ok=True,
                done=True,
                finished_at=time.time(),
                message="yt-dlp download succeeded on Render.",
                output_file=output_file,
            )
        else:
            combined = "\n".join(part for part in [stdout, stderr] if part)
            set_state(
                running=False,
                ok=False,
                done=True,
                finished_at=time.time(),
                message=combined[-6000:] if combined else f"yt-dlp failed with exit code {result.returncode}",
                output_file=output_file,
            )
    except Exception as exc:
        set_state(
            running=False,
            ok=False,
            done=True,
            finished_at=time.time(),
            message=str(exc),
            output_file="",
        )


@app.route("/")
def index():
    current = get_state()
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>YT Render Probe</title>
  <style>
    body {{ font-family: Arial, sans-serif; background:#0b1020; color:#f5f7ff; margin:0; padding:32px; }}
    .card {{ max-width:980px; margin:0 auto; background:#121a33; border:1px solid #27314f; border-radius:18px; padding:24px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background:#0a0f1d; padding:16px; border-radius:12px; border:1px solid #24304a; }}
    .ok {{ color:#7af0a3; }}
    .bad {{ color:#ff8f9d; }}
    code {{ background:#0a0f1d; padding:2px 6px; border-radius:6px; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>YT Render Probe</h1>
    <p><strong>Test URL:</strong> <code>{TEST_URL}</code></p>
    <p><strong>Status:</strong> <span class={'ok' if current['ok'] else 'bad'}>{'success' if current['ok'] else current['message']}</span></p>
    <p><strong>Running:</strong> {current['running']}</p>
    <p><strong>Done:</strong> {current['done']}</p>
    <p><strong>Output:</strong> <code>{current['output_file']}</code></p>
    <p><strong>Started:</strong> {current['started_at']}</p>
    <p><strong>Finished:</strong> {current['finished_at']}</p>
    <h2>Raw Message</h2>
    <pre>{current['message']}</pre>
  </div>
</body>
</html>"""


@app.route("/health")
def health():
    return {"ok": True, "state": get_state()}


@app.route("/probe")
def probe():
    current = get_state()
    if not current["running"]:
        thread = threading.Thread(target=run_probe, daemon=True)
        thread.start()
    return {"queued": True, "state": get_state()}


if __name__ == "__main__":
    thread = threading.Thread(target=run_probe, daemon=True)
    thread.start()
    app.run(host="0.0.0.0", port=PORT)
