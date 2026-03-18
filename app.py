import os
from datetime import datetime

from convex import ConvexClient
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, flash, url_for

load_dotenv()

CONVEX_URL = os.getenv("CONVEX_URL")
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "codec-secret-key")

app = Flask(__name__)
app.secret_key = SECRET_KEY


def get_convex_client() -> ConvexClient:
    if not CONVEX_URL:
        raise RuntimeError("CONVEX_URL is not set")
    return ConvexClient(CONVEX_URL)


def format_timestamp(value):
    if not value:
        return "-"
    return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M")


def normalize_job(job):
    return {
        "id": job["_id"],
        "sourceUrl": job.get("sourceUrl", ""),
        "status": job.get("status", "queued"),
        "createdAt": format_timestamp(job.get("createdAt")),
        "updatedAt": format_timestamp(job.get("updatedAt")),
        "retryAt": format_timestamp(job.get("retryAt")),
        "nextSegmentIndex": job.get("nextSegmentIndex", 0),
        "uploadedCount": job.get("uploadedCount", 0),
        "totalSegments": job.get("totalSegments", 0),
        "videoTitle": job.get("videoTitle", ""),
        "lastError": job.get("lastError", ""),
        "lastAttemptAt": format_timestamp(job.get("lastAttemptAt")),
    }


def fetch_jobs():
    client = get_convex_client()
    jobs = client.query("jobs:listJobs", {})
    return [normalize_job(job) for job in jobs]


@app.route("/")
def index():
    try:
        jobs = fetch_jobs()
        config_error = None
    except Exception as exc:
        jobs = []
        config_error = str(exc)
    return render_template("index.html", jobs=jobs, config_error=config_error)


@app.route("/jobs", methods=["POST"])
def create_job():
    source_url = request.form.get("source_url", "").strip()
    if not source_url:
        flash("Paste a YouTube URL first.", "error")
        return redirect(url_for("index"))

    try:
        client = get_convex_client()
        client.mutation("jobs:createJob", {"sourceUrl": source_url})
        flash("Job queued. The worker will pick it up automatically.", "success")
    except Exception as exc:
        flash(f"Could not queue job: {exc}", "error")

    return redirect(url_for("index"))


@app.route("/api/jobs")
def api_jobs():
    try:
        return jsonify({"jobs": fetch_jobs()})
    except Exception as exc:
        return jsonify({"error": str(exc), "jobs": []}), 500


@app.route("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
