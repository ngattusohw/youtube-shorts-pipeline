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

## Editing Style Defaults

Defaults for this user's Shorts (don't ask, just apply unless they say otherwise):

- **Pure ASMR.** Keep original audio. No music, no voice-over, no burned captions, no on-screen text.
- **Smart center-crop** 16:9 → 9:16 (not letterbox). Use a per-segment `x_offset` (in `edl.json`) only when the subject is clearly off-center.
- **Skip out-of-sequence B-roll.** If a clip's lighting/foliage/season doesn't match the rest of the day, drop it unless it's an intentional flashback.
- **Let segments breathe.** Default per-segment length **8–12s** (was 5–8s, too short). Aim for total Short length **45–55s** — closer to the 60s cap, not 20–30s. Don't cut mid-action just because the next thumbnail looks similar; the audio is the point.
- **Title format (sauna series, from #34 onward):** `DIY backyard sauna build — <single word>`. The "DIY" prefix helps discovery; the one-word subtitle is punchier than a phrase. Examples: "drilling", "cedar", "rain", "shadow". Never two words after the em-dash. (Earlier shorts #1-33 used the older `Backyard sauna build — <phrase>` format; don't retitle them.)
- **Schedule cadence:** daily at **17:00 UTC** (noon ET), 24h apart. Continue from the next open slot — don't restart at "tomorrow."
- **Preset:** use `preset="sauna"` for sauna content — it adds the right description + tags.

### Picking cut points

For each source, run `python lib/analyze_source.py content/<file>.mov` first. Output goes to `edit/analysis/<stem>/`:

- `report.md` — sustained loud sections (active ASMR moments), quiet sections (atmospheric beats), scene-cut timestamps, full 1-Hz RMS trace.
- `thumbnails/frame_NNNNs.jpg` — HDR-tonemapped at 10s intervals (override with `--interval`).

Use these to pick cuts: **start** segments at scene cuts or the leading edge of a loud run; **end** at the trailing edge of the loud run, not the next visual change. A drill that runs 12 seconds gets a 12-second cut.

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

- Python 3.8+ (use the `.venv/` in this repo — `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`)
- **ffmpeg built with zimg** — required for proper HDR (HLG / Dolby Vision) → SDR tone mapping via `zscale` + `tonemap=hable`. The stock `brew install ffmpeg` does **not** include zimg. Install via the `homebrew-ffmpeg` tap:
  ```bash
  brew uninstall --ignore-dependencies ffmpeg
  brew tap homebrew-ffmpeg/ffmpeg
  brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg
  ```
  Verify: `ffmpeg -filters | grep zscale`. Without it, `render_vertical.py` will error and SDR output looks washed/low-contrast.
- Pillow (for animation generation)
- google-api-python-client (for YouTube upload)
