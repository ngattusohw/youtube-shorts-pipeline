# YouTube Shorts Pipeline

End-to-end pipeline for turning long iPhone HDR clips into vertical YouTube Shorts. Designed to be driven from Claude Code, but the scripts work standalone.

`edit/edl.json` is the canonical record of every Short (title, description, schedule, segments, uploaded URL). Render and upload both read from it.

## Pipeline at a glance

```
content/<source>.mov                # raw HEVC/HLG iPhone clip
  │
  ▼
lib/analyze_source.py               # 1Hz audio RMS + scene cuts + 10s thumbnails
  │   edit/analysis/<stem>/{report.md, thumbnails/, audio_rms.json, scenes.json}
  ▼
edit/edl.json                       # add entries: name, source, title, description, schedule, segments
  │
  ▼
lib/render_vertical.py              # HDR→SDR tone-map, 9:16 crop, 1080x1920 H.264
  │   generated/<name>.mp4
  ▼
lib/upload_from_edl.py              # OAuth2, scheduled private uploads, writes uploaded_url back to EDL
```

## Setup

### 1. ffmpeg with `zimg` (required)

The stock `brew install ffmpeg` does **not** include `zimg`, so the `zscale` filter is missing and HDR→SDR tone mapping won't work. Install from the tap:

```bash
brew uninstall --ignore-dependencies ffmpeg     # if installed
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg
```

Verify: `ffmpeg -filters | grep zscale` should show `zscale`.

### 2. Python venv + deps

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. YouTube API credentials

1. Google Cloud Console → enable **YouTube Data API v3**
2. Credentials → OAuth 2.0 Client ID → **Desktop App**
3. Download JSON, save as `secrets/client_secrets.json`
4. On first upload, a browser opens for OAuth; `secrets/token.json` is saved for reuse.

### 4. Source videos

Drop `.mov`/`.mp4` files into `content/`. If they live in an iCloud Photos album, see `CLAUDE.md` for the AppleScript export pattern (use a long `with timeout of 1800 seconds` block — iCloud downloads can be slow).

## Workflow

### Analyze a source

```bash
python lib/analyze_source.py content/copy_<uuid>.mov
```

Outputs to `edit/analysis/<stem>/`:

- `report.md` — sustained loud sections (active ASMR moments), quiet/idle sections, scene-cut timestamps, full 1-Hz RMS trace.
- `thumbnails/frame_NNNNs.jpg` — HDR-tonemapped at 10s intervals (override with `--interval`).

Use these to pick cuts: start segments at scene cuts or the leading edge of a loud run; **end** at the trailing edge of the loud run, not the next visual change. Let segments breathe — 10–15s per segment, ~45–60s totals.

### Add Shorts to the EDL

Edit `edit/edl.json`. Each entry:

```json
{
  "name": "short_NN_one_word",
  "source": "content/copy_<uuid>.mov",
  "title": "DIY backyard sauna build — <word>",
  "schedule": "2026-MM-DDT17:00:00Z",
  "description": "One or two atmospheric sentences.",
  "segments": [
    {"start": 80.0,  "end": 95.0,  "note": "what's happening"},
    {"start": 100.0, "end": 115.0, "note": "..."}
  ]
}
```

Optional per-segment `x_offset` shifts the 9:16 crop window left/right.

### Render

```bash
# all entries
python lib/render_vertical.py

# subset
python lib/render_vertical.py --only short_34_studs short_35_ladder
```

Output: `generated/<name>.mp4` (1080×1920, 60 fps, H.264, AAC).

### Upload (scheduled)

```bash
.venv/bin/python -u lib/upload_from_edl.py
```

Picks up any Short with `schedule` set but no `uploaded_url`. Uploads private with `publishAt` so YouTube flips them public automatically. Writes the URL back to `edit/edl.json` after each success — the script is **resumable** if the connection drops.

## Folder structure

```
youtube-shorts-pipeline/
├── CLAUDE.md                       # Claude Code workflow + style defaults
├── README.md                       # this file
├── requirements.txt
├── lib/
│   ├── analyze_source.py           # audio + scene + thumbnail analyzer
│   ├── render_vertical.py          # HDR→SDR, 9:16 crop, concat segments
│   ├── upload.py                   # base YouTube upload library
│   └── upload_from_edl.py          # reads edl.json, uploads pending
├── content/                        # source .mov files (gitignored)
├── edit/
│   ├── edl.json                    # canonical state — committed
│   ├── analysis/<stem>/            # analyzer output (gitignored)
│   ├── animations/slot_N/          # animation build scripts (planned, optional)
│   └── transcripts/                # transcripts (optional)
├── generated/                      # final mp4s (gitignored)
└── secrets/                        # OAuth (gitignored)
    ├── client_secrets.json
    └── token.json
```

## Editing defaults

See `CLAUDE.md` for the live style guide. The short version:

- **Pure ASMR** — original audio, no captions, no music
- **Smart center-crop** (not letterbox)
- **Skip out-of-sequence B-roll**
- **Segments 10–15s, totals 45–60s** — let the action breathe
- **Title format:** `DIY backyard sauna build — <single word>`
- **Schedule:** daily at 17:00 UTC, 24h apart
