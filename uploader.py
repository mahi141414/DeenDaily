import os
import json
import pickle
import re
import sys
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

load_dotenv()

# YouTube Config
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_service():
    """Handles YouTube OAuth2 authentication."""
    creds = None
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")

    if token_json:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        except Exception as e:
            print(f"Error loading YOUTUBE_TOKEN_JSON: {e}")
            return None
    elif os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists("client_secrets.json"):
                    print("Error: client_secrets.json not found. Please download it from Google Cloud Console.")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
                creds = flow.run_local_server(port=0)
        except RefreshError:
            print("YouTube token is expired or revoked. Re-authenticating...")
            creds = None
            if os.path.exists("token.pickle"):
                try:
                    os.remove("token.pickle")
                except OSError:
                    pass

            if not os.path.exists("client_secrets.json"):
                print("Error: client_secrets.json not found. Please download it from Google Cloud Console.")
                return None

            flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
            try:
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"Error during YouTube re-authentication: {e}")
                return None
        except Exception as e:
            print(f"Error during YouTube authentication: {e}")
            return None

        try:
            with open("token.pickle", "wb") as token:
                pickle.dump(creds, token)
        except Exception as e:
            print(f"Warning: could not save YouTube token: {e}")
            
    return build("youtube", "v3", credentials=creds)

def upload_to_youtube_short(video_path, title, video_title_context="", service=None):
    """Uploads a video as a YouTube Short with dynamic description based on speaker."""
    service = service or get_youtube_service()
    if not service:
        return {"success": False, "blocked": False, "error": "YouTube auth unavailable"}

    print(f"Uploading to YouTube Shorts: {title}...")

    # Load base description from description.txt
    base_desc = ""
    if os.path.exists("description.txt"):
        with open("description.txt", "r", encoding="utf-8") as f:
            base_desc = f.read()

    # Load info for speakers
    speaker_info = ""
    if os.path.exists("info.txt"):
        with open("info.txt", "r", encoding="utf-8") as f:
            info_content = f.read()
            
            # Simple check for speaker in the ORIGINAL video title or the new short title
            search_context = (video_title_context + " " + title).lower()
            
            if "azhari" in search_context or "আজহারী" in search_context:
                # Extract Azhari info (text between "Azhari"{ and })
                match = re.search(r'"Azhari"\{(.*?)\}', info_content, re.DOTALL)
                if match: speaker_info = "\n\n" + match.group(1).strip()
            
            elif "ahmadullah" in search_context or "আহমাদুল্লাহ" in search_context:
                # Extract Ahmadullah info
                match = re.search(r'"Ahmadullah"\{(.*?)\}', info_content, re.DOTALL)
                if match: speaker_info = "\n\n" + match.group(1).strip()

    full_description = f"{title}\n\n{base_desc}{speaker_info}"

    body = {
        "snippet": {
            "title": title[:100],
            "description": full_description[:5000], # YouTube limit
            "tags": ["shorts", "waz", "bangla", "islamic"],
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    
    try:
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        
        print(f"Successfully uploaded to YouTube! Video ID: {response['id']}")
        return {"success": True, "blocked": False, "video_id": response.get("id")}
    except HttpError as e:
        message = str(e)
        blocked = "uploadLimitExceeded" in message
        print(f"Error during YouTube upload: {e}")
        return {"success": False, "blocked": blocked, "error": message}
    except Exception as e:
        print(f"Error during YouTube upload: {e}")
        return {"success": False, "blocked": False, "error": str(e)}
