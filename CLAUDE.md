# YouTube Shorts Pipeline - Claude Code Instructions

This repo contains a complete pipeline for editing videos and uploading them to YouTube Shorts.

## Overview

**Workflow:**
1. User places source videos in `content/`
2. You help edit: transcribe, cut segments, add animations, burn subtitles
3. Render to vertical 1080x1920 format in `generated/`
4. Upload to YouTube Shorts with optional scheduling

## Folder Structure

```
content/          # Source videos (user provides)
edit/             # Working directory
  edl.json        # Edit decision list (segments to extract)
  transcripts/    # Transcription JSON files
  animations/     # Overlay animations (slot_1/, slot_2/, etc.)
generated/        # Final rendered videos
lib/upload.py     # YouTube upload library
secrets/          # OAuth credentials (gitignored)
```

## Video Editing Pipeline

### 1. Transcription

Use `ffmpeg` and a transcription service/model to generate word-level timestamps.

Save transcripts as JSON in `edit/transcripts/`:
```json
{
  "words": [
    {"word": "Hello", "start": 0.0, "end": 0.5},
    {"word": "world", "start": 0.6, "end": 1.0}
  ]
}
```

### 2. Edit Decision List (EDL)

Create `edit/edl.json` to define which segments to extract:

```json
{
  "source": "content/raw_video.mp4",
  "segments": [
    {
      "name": "HOOK",
      "start": 12.5,
      "end": 18.2,
      "quote": "This changed everything"
    },
    {
      "name": "MAIN",
      "start": 45.0,
      "end": 52.3
    }
  ],
  "animations": [
    {
      "slot": 1,
      "start": 0.0,
      "duration": 2.5
    }
  ]
}
```

### 3. Vertical Rendering (1080x1920)

YouTube Shorts require 9:16 vertical format. Two approaches:

**Padding (letterbox):** Scale to fit width, pad top/bottom with black
```bash
ffmpeg -i input.mp4 -vf "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" output.mp4
```

**Cropping:** Crop center portion for vertical
```bash
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" output.mp4
```

### 4. Animation Overlays

Create animations as transparent video files (PNG sequence or ProRes 4444).

Place build scripts in `edit/animations/slot_N/build.py`:

```python
# Example: Title card animation
# Output: 1080x1920 @ 30fps, 2.5 seconds
# Creates fade-in text overlay

from PIL import Image, ImageDraw, ImageFont
import subprocess

WIDTH, HEIGHT = 1080, 1920
FPS = 30
DURATION = 2.5

frames = []
for i in range(int(FPS * DURATION)):
    t = i / FPS
    alpha = min(1.0, t / 0.5)  # Fade in over 0.5s

    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # ... draw text with alpha
    frames.append(img)

# Save as PNG sequence, then encode to video
```

Composite animations onto the main video:
```bash
ffmpeg -i main.mp4 -i animation.mov -filter_complex "[0][1]overlay=0:0" output.mp4
```

### 5. Subtitle Generation

Generate SRT from transcript + EDL timing:

```python
# Remove filler words: um, uh, like, you know, basically, so
# Group into 2-word chunks
# Output uppercase for visibility
```

Burn subtitles into video:
```bash
ffmpeg -i input.mp4 -vf "subtitles=master.srt:force_style='FontSize=24,Bold=1'" output.mp4
```

### 6. Final Render Pipeline

```python
# render_vertical.py pattern:
# 1. Extract segments from source per EDL
# 2. Scale/crop to 1080x1920
# 3. Concatenate segments
# 4. Overlay animations at specified times
# 5. Burn subtitles
# 6. Output to generated/
```

## YouTube Upload

### Authentication

First run opens browser for OAuth. Credentials saved to `secrets/token.json`.

### Single Upload

```python
from lib.upload import get_authenticated_service, upload_video

youtube = get_authenticated_service()
video_id, url = upload_video(
    youtube,
    "generated/final.mp4",
    title="My Video Title",
    is_short=True,
    privacy="public"
)
```

### Scheduled Batch Upload

```python
from datetime import datetime, timedelta
from lib.upload import get_authenticated_service, upload_video

youtube = get_authenticated_service()
schedule_time = datetime(2024, 1, 15, 14, 0, 0)  # 2pm UTC

videos = [
    ("generated/video1.mp4", "Title One"),
    ("generated/video2.mp4", "Title Two"),
]

for filepath, title in videos:
    upload_video(
        youtube, filepath, title,
        is_short=True,
        privacy="private",
        schedule=schedule_time.isoformat() + "Z"
    )
    schedule_time += timedelta(hours=24)  # Next day
```

### Presets

Available presets: `sauna`, `tesla`, `cats`, `travel`

```python
upload_video(youtube, path, title, is_short=True, preset="sauna")
```

## Common Tasks

### "Edit this video for Shorts"
1. Get source video info: `ffprobe -v quiet -print_format json -show_streams content/video.mp4`
2. Ask user what content/moments to feature
3. Create EDL with segments
4. Render vertical format
5. Add any requested overlays/text
6. Output to `generated/`

### "Upload these videos"
1. Confirm video files exist in `generated/`
2. Ask for titles, scheduling preferences
3. Use `lib/upload.py` to upload
4. Report back URLs

### "Schedule uploads for the week"
1. Get list of videos to upload
2. Calculate schedule (e.g., daily at 2pm UTC)
3. Batch upload with scheduling
4. Report schedule and URLs

## Dependencies

- Python 3.8+
- ffmpeg / ffprobe
- Pillow (for animation generation)
- google-api-python-client (for YouTube upload)
