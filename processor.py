import glob
import os
import subprocess
import time

from main import download_video, get_ffmpeg_path, get_shorts_timestamps, parse_subtitles
from uploader import upload_to_youtube_short


def clear_short_directory(output_dir: str):
    if os.path.exists(output_dir):
        for path in glob.glob(os.path.join(output_dir, "*.mp4")):
            try:
                os.remove(path)
            except OSError:
                pass
    else:
        os.makedirs(output_dir)


def cut_single_segment(video_path, segment, ffmpeg_path, output_filename):
    start = segment["start"]
    end = segment["end"]

    logo_path = "logo.png"
    if os.path.exists(logo_path):
        filter_complex = (
            f"[0:v]crop=ih*9/16:ih,scale=1080:1920[bg]; "
            f"[1:v]scale=300:-1[logo]; "
            f"[bg][logo]overlay=(W-w)/2:(H-h)/2+500[v]"
        )
        cmd = [
            ffmpeg_path, "-y", "-ss", start, "-to", end, "-i", video_path, "-i", logo_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_filename,
        ]
    else:
        cmd = [
            ffmpeg_path, "-y", "-ss", start, "-to", end, "-i", video_path,
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_filename,
        ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_filename


def save_job_state(client, job_id, mutation_name, payload):
    payload = {"id": job_id, **payload}
    client.mutation(mutation_name, payload)


def process_job(job, client):
    job_id = job["_id"]
    source_url = job["sourceUrl"]
    retry_index = int(job.get("nextSegmentIndex", 0) or 0)
    uploaded_count = int(job.get("uploadedCount", 0) or 0)

    ffmpeg_path = get_ffmpeg_path()
    output_dir = "shorts"
    clear_short_directory(output_dir)

    save_job_state(client, job_id, "jobs:markProcessing", {})

    try:
        video_path, sub_path, video_title = download_video(source_url, ffmpeg_path)
        if not sub_path:
            raise RuntimeError("No subtitles found for this video.")

        segments = job.get("segments")
        if not segments:
            sub_text = parse_subtitles(sub_path)
            segments = get_shorts_timestamps(sub_text, video_title)
            save_job_state(
                client,
                job_id,
                "jobs:setAnalysis",
                {
                    "videoId": os.path.splitext(os.path.basename(video_path))[0],
                    "videoTitle": video_title,
                    "segments": segments,
                    "totalSegments": len(segments),
                },
            )

        total_segments = len(segments)
        if retry_index >= total_segments:
            save_job_state(client, job_id, "jobs:markComplete", {})
            return

        save_job_state(
            client,
            job_id,
            "jobs:setProgress",
            {
                "nextSegmentIndex": retry_index,
                "uploadedCount": uploaded_count,
            },
        )

        for index in range(retry_index, total_segments):
            segment = segments[index]
            output_filename = os.path.join(output_dir, f"{job_id[:8]}_{index + 1}.mp4")

            print(f"[{index + 1}/{total_segments}] Cutting: {segment['title']}")
            cut_single_segment(video_path, segment, ffmpeg_path, output_filename)

            print(f"[{index + 1}/{total_segments}] Uploading: {segment['title']}")
            result = upload_to_youtube_short(output_filename, segment["title"], video_title)

            try:
                os.remove(output_filename)
            except OSError:
                pass

            if result.get("success"):
                uploaded_count = index + 1
                save_job_state(
                    client,
                    job_id,
                    "jobs:setProgress",
                    {
                        "nextSegmentIndex": index + 1,
                        "uploadedCount": uploaded_count,
                        "lastError": "",
                    },
                )
                continue

            error_message = result.get("error", "Unknown upload error")
            if result.get("blocked"):
                retry_at = int(time.time() * 1000) + 60 * 60 * 1000
                save_job_state(
                    client,
                    job_id,
                    "jobs:markRetry",
                    {
                        "nextSegmentIndex": index,
                        "retryAt": retry_at,
                        "lastError": error_message,
                    },
                )
                return

            save_job_state(
                client,
                job_id,
                "jobs:markFailure",
                {
                    "lastError": error_message,
                },
            )
            return

        save_job_state(client, job_id, "jobs:markComplete", {})
    except Exception as exc:
        save_job_state(
            client,
            job_id,
            "jobs:markFailure",
            {
                "lastError": str(exc),
            },
        )
        raise
