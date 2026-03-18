import os
import sys
import json
import requests
import subprocess
import glob
import re
import imageio_ffmpeg
import threading
from queue import Queue
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from uploader import get_youtube_service, upload_to_youtube_short

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_KEY = os.environ.get("NVIDIA_API_KEY") 
BASE_URL = "https://integrate.api.nvidia.com/v1"

# Terminal Colors for Reasoning
_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_REASONING_COLOR = "\033[90m" if _USE_COLOR else ""
_RESET_COLOR = "\033[0m" if _USE_COLOR else ""

def get_ffmpeg_path():
    """Returns the path to the ffmpeg executable."""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(f"Error finding ffmpeg: {e}")
        sys.exit(1)

def download_video(url, ffmpeg_path):
    """Downloads video, subs, and metadata with high quality and compatible audio."""
    print(f"Processing URL: {url}")
    
    video_dir = "video"
    if not os.path.exists(video_dir):
        os.makedirs(video_dir)

    # 1. Get Metadata via JSON
    print("Extracting video info...")
    info_cmd = ["yt-dlp", "--skip-download", "--dump-json", url]
    try:
        result = subprocess.run(info_cmd, capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
        video_id = metadata.get('id', 'unknown_id')
        video_title = metadata.get('title', 'YouTube Video')
        video_title = re.sub(r'\s+', ' ', video_title).strip()
        print(f"Video ID: {video_id} | Title: {video_title[:50]}...")
    except Exception as e:
        print(f"Metadata extraction failed: {e}")
        match = re.search(r"[v=|\/]([a-zA-Z0-9_-]{11})", url)
        video_id = match.group(1) if match else "unknown_id"
        video_title = "YouTube Video"

    video_path = os.path.join(video_dir, f"{video_id}.mp4")
    sub_path_base = os.path.join(video_dir, f"{video_id}")

    # 2. Check and Download with High Quality
    if os.path.exists(video_path):
        print(f"Found existing video: {video_path}. Skipping download.")
    else:
        print("Downloading High Quality 1080p + Compatible Audio...")
        command = [
            "yt-dlp",
            "--ffmpeg-location", ffmpeg_path,
            "-f", "bestvideo[height=1080]+bestaudio[ext=m4a]/bestvideo[height=1080]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--write-auto-sub", "--write-sub", "--sub-lang", "bn.*,en.*",
            "--extractor-args", "youtube:player-client=ios,android,web",
            "--impersonate", "chrome",
            "--no-check-certificate",
            "-o", f"{video_dir}/%(id)s.%(ext)s", url
        ]
        
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print("1080p failed. Falling back to best available...")
            fallback_video_cmd = [
                "yt-dlp", "--ffmpeg-location", ffmpeg_path,
                "-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4",
                "-o", f"{video_dir}/%(id)s.%(ext)s", url
            ]
            subprocess.run(fallback_video_cmd)
        
        if not os.path.exists(video_path):
            print("Fatal Error: Could not download video.")
            sys.exit(1)
            
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        print(f"Download complete! File size: {size_mb:.2f} MB")

    # 3. Find Subtitles
    sub_files = glob.glob(f"{sub_path_base}*.srt") + glob.glob(f"{sub_path_base}*.vtt")
    
    if not sub_files:
        print("Subtitles missing. Attempting fallback transcript pull...")
        fallback_cmd = [
            "yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "bn.*,en.*",
            "--extractor-args", "youtube:player-client=android,ios",
            "--impersonate", "chrome", "-o", f"{video_dir}/%(id)s.%(ext)s", url
        ]
        subprocess.run(fallback_cmd)
        sub_files = glob.glob(f"{sub_path_base}*.srt") + glob.glob(f"{sub_path_base}*.vtt")

    final_sub_path = None
    if sub_files:
        srt_files = [f for f in sub_files if f.endswith('.srt')]
        final_sub_path = srt_files[0] if srt_files else sub_files[0]
        print(f"Using subtitles: {final_sub_path}")

    return video_path, final_sub_path, video_title

def parse_subtitles(subtitle_path):
    """Parses SRT or VTT subtitles into clean text."""
    if not subtitle_path:
        return ""
        
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(r'WEBVTT|Kind:.*|Language:.*', '', content)
        content = re.sub(r'<\d{2}:\d{2}:\d{2}.\d{3}>', '', content)
        return content
    except Exception as e:
        print(f"Error reading subtitle file: {e}")
        return ""

def get_shorts_timestamps(subtitle_text, video_title):
    """Sends subtitles to NVIDIA API with strict JSON enforcement."""
    if not API_KEY:
        print("Error: NVIDIA_API_KEY not found.")
        sys.exit(1)

    print(f"Analyzing content with Qwen 3.5 (122B): {video_title[:50]}...")

    prompt = f"""
    Video Title: {video_title}
    
    Task: Identify EXACTLY 10 engaging segments for shorts (60-120s each).
    
    CRITICAL INSTRUCTION:
    You MUST return a JSON array of OBJECTS. 
    Each object MUST have "start", "end", and "title" keys.
    The "title" MUST be in Bangla and follow this format: '[Bangla Hook] ? [Speaker Name] | #waz #shorts #viral'

    Example JSON structure:
    [
      {{"start": "00:01:20", "end": "00:02:40", "title": "তারাবির নামাজ ৮ রাকাত নাকি ২০ রাকাত? মিজানুর রহমান আজহারী | Mizanur Rahman Azhari new waz | #waz #shorts #viral"}}
    ]

    Transcript:
    {subtitle_text[:60000]} 
    """

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen/qwen3.5-122b-a10b",
        "messages": [
            {"role": "system", "content": "You are a specialized video editor bot. You ONLY output valid JSON arrays of objects with start, end, and title keys. You never include any other text, reasoning, or explanation."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False} 
    }

    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, stream=True, timeout=120)
        response.raise_for_status()

        full_content = ""
        for line in response.iter_lines():
            if not line: continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]": break
                try:
                    data = json.loads(data_str)
                    delta = data['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        full_content += content
                        print(content, end="", flush=True)
                except: continue

        print("\nAnalysis complete. Extracting JSON...")
        
        # Robust extraction
        start_idx = full_content.find('[')
        end_idx = full_content.rfind(']')
        
        if start_idx == -1 or end_idx == -1:
            print(f"Error: No JSON array found. Raw: {full_content[:200]}...")
            sys.exit(1)
            
        json_str = full_content[start_idx:end_idx+1]
        segments = json.loads(json_str)
        
        # Final Validation
        valid_segments = []
        for s in segments:
            if isinstance(s, dict) and 'start' in s and 'end' in s and 'title' in s:
                valid_segments.append(s)
        
        if not valid_segments:
            print("Error: AI returned invalid data structure.")
            sys.exit(1)
            
        return valid_segments[:10]
    except Exception as e:
        print(f"\nError during API call: {e}")
        sys.exit(1)

def cut_video(video_path, segments, ffmpeg_path, upload_queue=None, video_title_context=""):
    """Cuts the video into compatible 1080x1920 vertical segments."""
    output_dir = "shorts"
    logo_path = "logo.png"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    else:
        for f in glob.glob(f"{output_dir}/*.mp4"):
            try: os.remove(f)
            except: pass
        
    print(f"Found {len(segments)} segments. Cutting to Vertical 1080x1920 with centered logo...")

    processed_shorts = []

    for i, seg in enumerate(segments):
        start = seg['start']
        end = seg['end']
        title = seg['title']
        
        output_filename = os.path.join(output_dir, f"short_{i+1}.mp4")
        
        print(f"[{i+1}/10] Processing: {title}")
        
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
                output_filename
            ]
        else:
            cmd = [
                ffmpeg_path, "-y", "-ss", start, "-to", end, "-i", video_path,
                "-vf", "crop=ih*9/16:ih,scale=1080:1920",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                output_filename
            ]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processed_short = {"path": output_filename, "title": title}
            processed_shorts.append(processed_short)
            if upload_queue:
                upload_queue.put({
                    "path": output_filename,
                    "title": title,
                    "video_title_context": video_title_context,
                })
            print(f"  Finished segment {i+1}")
        except subprocess.CalledProcessError:
            print(f"  Error cutting segment {i+1}")

    print(f"\nSuccess! {len(processed_shorts)} Vertical shorts saved to '{output_dir}'.")
    return processed_shorts

def upload_worker(upload_queue):
    """Uploads finished shorts in the background while processing continues."""
    service = None
    service_failed = False

    while True:
        item = upload_queue.get()
        try:
            if item is None:
                return

            if service is None and not service_failed:
                try:
                    service = get_youtube_service()
                except Exception as e:
                    service = None
                    service_failed = True
                    print(f"YouTube auth failed. Skipping remaining uploads. Details: {e}")
                    continue

                if not service:
                    service_failed = True
                    print("YouTube auth failed. Skipping remaining uploads.")
                    continue

            print(f"Queued upload: {item['path']}")
            try:
                upload_to_youtube_short(item['path'], item['title'], item.get('video_title_context', ""), service=service)
            except Exception as e:
                print(f"Error during YouTube upload for {item['path']}: {e}")
        finally:
            upload_queue.task_done()

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <video_url>")
        return

    url = sys.argv[1]
    ffmpeg_path = get_ffmpeg_path()

    video_path, sub_path, video_title = download_video(url, ffmpeg_path)
    
    if not sub_path:
        print("Fatal Error: No subtitles found.")
        return

    sub_text = parse_subtitles(sub_path)
    segments = get_shorts_timestamps(sub_text, video_title)
    
    if not segments:
        print("Error: No segments.")
        return
    
    upload_queue = Queue()
    upload_thread = threading.Thread(target=upload_worker, args=(upload_queue,), daemon=True)
    upload_thread.start()
    print("Auto-upload enabled: each short will upload as soon as it finishes processing.")

    shorts_list = cut_video(video_path, segments, ffmpeg_path, upload_queue=upload_queue, video_title_context=video_title)

    upload_queue.put(None)
    upload_queue.join()
    upload_thread.join()

if __name__ == "__main__":
    main()
