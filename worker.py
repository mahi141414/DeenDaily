import os
import time

from convex import ConvexClient, ConvexError
from dotenv import load_dotenv

from processor import process_job

load_dotenv()

CONVEX_URL = os.getenv("CONVEX_URL")
POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "30"))


def get_client() -> ConvexClient:
    if not CONVEX_URL:
        raise RuntimeError("CONVEX_URL is not set")
    return ConvexClient(CONVEX_URL)


def run_worker():
    client = get_client()
    print("Worker started. Polling for jobs...")

    while True:
        try:
            job = client.mutation("jobs:claimNextJob", {})
            if not job:
                time.sleep(POLL_SECONDS)
                continue

            print(f"Picked up job {job['_id']} from {job.get('sourceUrl')}")
            process_job(job, client)
        except ConvexError as exc:
            print(f"Convex error: {exc}")
            time.sleep(POLL_SECONDS)
        except Exception as exc:
            print(f"Worker error: {exc}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_worker()
