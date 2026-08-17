#!/usr/bin/env python3
"""
YouTube video uploader with OAuth2 authentication.
First run opens browser for auth, subsequent runs reuse saved credentials.

Usage:
    # Single upload
    python upload.py video.mp4 --title "My Video Title" --short

    # Batch upload all mp4s in a folder
    python upload.py /path/to/folder --batch --short

    # Schedule upload (will be private until publish time)
    python upload.py video.mp4 --title "My Video" --schedule "2024-01-15T14:00:00Z"

    # Batch with daily scheduling
    python upload.py folder/ --batch --short --schedule "2024-01-15T14:00:00Z" --schedule-interval 24
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# Paths relative to repo root
REPO_ROOT = Path(__file__).parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"
TOKEN_FILE = SECRETS_DIR / "token.json"
CREDENTIALS_FILE = SECRETS_DIR / "client_secrets.json"

# Content presets with SEO-optimized defaults
PRESETS = {
    "sauna": {
        "description": "Building a backyard sauna from scratch. Follow along for the full build series.\n\n#Shorts #DIY #SaunaBuild #ASMR #Satisfying",
        "tags": ["sauna", "diy", "construction", "woodworking", "backyard project", "asmr", "satisfying", "build"],
    },
    "tesla": {
        "description": "Tesla Full Self-Driving in action.\n\n#Shorts #Tesla #FSD #SelfDriving #ElectricVehicle",
        "tags": ["tesla", "fsd", "full self driving", "autopilot", "electric vehicle", "ev", "autonomous"],
    },
    "cats": {
        "description": "#Shorts #Cats #CatsOfYouTube #Cute #Pets",
        "tags": ["cats", "cute cats", "pets", "funny cats", "cat video"],
    },
    "travel": {
        "description": "#Shorts #Travel #Adventure #Wanderlust",
        "tags": ["travel", "adventure", "vacation", "wanderlust", "explore"],
    },
    "roofing": {
        "description": "Re-roofing a house — GAF StormGuard leak barrier and asphalt shingles.\n\n#Shorts #DIY #Roofing #ASMR #Satisfying",
        "tags": ["roofing", "diy", "construction", "shingles", "home improvement", "asmr", "satisfying", "build"],
    },
}


def get_authenticated_service():
    """Get authenticated YouTube service, prompting for auth if needed."""
    creds = None

    # Ensure secrets directory exists
    SECRETS_DIR.mkdir(exist_ok=True)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: {CREDENTIALS_FILE} not found.")
                print("\nTo set up YouTube API credentials:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create/select a project and enable YouTube Data API v3")
                print("3. Create OAuth 2.0 credentials (Desktop App)")
                print(f"4. Download and save as: {CREDENTIALS_FILE}")
                sys.exit(1)

            print("Opening browser for authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"Credentials saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, filepath, title, description="", privacy="unlisted",
                 tags=None, is_short=False, schedule=None, preset=None):
    """Upload a video to YouTube.

    Args:
        youtube: Authenticated YouTube service
        filepath: Path to video file
        title: Video title
        description: Video description
        privacy: "public", "unlisted", or "private"
        tags: List of tags
        is_short: If True, formats for YouTube Shorts
        schedule: ISO format datetime string for scheduled publish
        preset: Name of preset to use for description/tags

    Returns:
        Tuple of (video_id, video_url) or (None, None) on failure
    """
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return None, None

    # Apply preset defaults
    if preset and preset in PRESETS:
        p = PRESETS[preset]
        if not description:
            description = p["description"]
        if not tags:
            tags = p["tags"].copy()

    # For Shorts: add hashtags to description
    if is_short:
        if "#Shorts" not in (description or ""):
            if description:
                description = f"{description}\n\n#Shorts"
            else:
                description = "#Shorts"
        tags = (tags or []) + ["Shorts"]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Handle scheduling
    if schedule:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = schedule
        print(f"Scheduled for: {schedule}")

    media = MediaFileUpload(
        str(filepath),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )

    print(f"Uploading: {filepath.name}")
    print(f"Title: {title}")
    print(f"Privacy: {privacy}" + (" (scheduled)" if schedule else ""))
    if preset:
        print(f"Preset: {preset}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}" if is_short else f"https://youtube.com/watch?v={video_id}"

    print(f"Upload complete! {video_url}\n")
    return video_id, video_url


def batch_upload(youtube, folder_path, is_short=False, privacy="unlisted",
                 schedule_interval_hours=None, start_schedule=None,
                 preset=None, description=None, tags=None):
    """Upload all mp4 files in a folder.

    Args:
        youtube: Authenticated YouTube service
        folder_path: Path to folder containing videos
        is_short: If True, formats for YouTube Shorts
        privacy: Privacy setting
        schedule_interval_hours: Hours between scheduled uploads
        start_schedule: ISO datetime for first upload
        preset: Preset name for description/tags
        description: Override description
        tags: Override tags

    Returns:
        List of dicts with upload results
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f"Error: Not a directory: {folder}")
        sys.exit(1)

    videos = sorted(folder.glob("*.mp4")) + sorted(folder.glob("*.MP4"))
    if not videos:
        print(f"No MP4 files found in {folder}")
        return []

    print(f"Found {len(videos)} videos to upload\n")

    results = []
    current_schedule = None

    if start_schedule and schedule_interval_hours:
        current_schedule = datetime.fromisoformat(start_schedule.replace('Z', '+00:00'))

    for video in videos:
        # Use filename (without extension) as title, clean it up
        title = video.stem.replace("_", " ").replace("-", " ").title()

        schedule_str = None
        if current_schedule:
            schedule_str = current_schedule.isoformat().replace('+00:00', 'Z')
            current_schedule += timedelta(hours=schedule_interval_hours)

        video_id, video_url = upload_video(
            youtube, video, title,
            description=description,
            privacy=privacy,
            tags=tags,
            is_short=is_short,
            schedule=schedule_str,
            preset=preset,
        )
        if video_id:
            results.append({"file": str(video), "id": video_id, "url": video_url})

    print(f"\n{'='*50}")
    print(f"Uploaded {len(results)}/{len(videos)} videos")
    for r in results:
        print(f"  {r['url']}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Upload video(s) to YouTube")
    parser.add_argument("path", help="Video file or folder (with --batch)")
    parser.add_argument("-t", "--title", help="Video title (default: filename)")
    parser.add_argument("-d", "--description", default="", help="Video description")
    parser.add_argument("-p", "--privacy", default="unlisted",
                        choices=["public", "unlisted", "private"],
                        help="Privacy setting (default: unlisted)")
    parser.add_argument("--tags", nargs="+", help="Tags for the video")
    parser.add_argument("--short", action="store_true",
                        help="Mark as YouTube Short (adds #Shorts)")
    parser.add_argument("--batch", action="store_true",
                        help="Upload all MP4s in the given folder")
    parser.add_argument("--schedule",
                        help="Schedule publish time (ISO format: 2024-01-15T14:00:00Z)")
    parser.add_argument("--schedule-interval", type=int,
                        help="Hours between scheduled uploads (use with --batch)")
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        help=f"Use preset: {', '.join(PRESETS.keys())}")

    args = parser.parse_args()
    youtube = get_authenticated_service()

    if args.batch:
        batch_upload(
            youtube,
            args.path,
            is_short=args.short,
            privacy=args.privacy,
            schedule_interval_hours=args.schedule_interval,
            start_schedule=args.schedule,
            preset=args.preset,
            description=args.description,
            tags=args.tags,
        )
    else:
        title = args.title or Path(args.path).stem.replace("_", " ").title()
        upload_video(
            youtube,
            args.path,
            title,
            args.description,
            args.privacy,
            args.tags,
            args.short,
            args.schedule,
            args.preset,
        )


if __name__ == "__main__":
    main()
