# YouTube Shorts Pipeline

A video editing and upload pipeline for YouTube Shorts, designed to work with Claude Code.

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd youtube-shorts-pipeline
pip install -r requirements.txt
```

### 2. Set up YouTube API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** > **Create Credentials** > **OAuth 2.0 Client ID**
5. Choose **Desktop App** as application type
6. Download the JSON file
7. Save it as `secrets/client_secrets.json`

### 3. Add your content

Place your source video files in the `content/` folder.

### 4. First-time authentication

Run any upload command - it will open a browser for Google OAuth:

```bash
python lib/upload.py --help
```

After authenticating, `secrets/token.json` will be created for future use.

## Usage

### With Claude Code

Start a Claude Code session from this folder. Claude will read `CLAUDE.md` for pipeline instructions and can:

1. Edit videos (cut, transcribe, add animations, burn subtitles)
2. Render to vertical 1080x1920 format for Shorts
3. Upload to YouTube with scheduling

### Manual upload

```bash
# Single video
python lib/upload.py video.mp4 --title "My Video" --short

# With scheduling
python lib/upload.py video.mp4 --title "My Video" --short --schedule "2024-01-15T14:00:00Z"

# Batch upload with daily scheduling
python lib/upload.py content/ --batch --short --schedule "2024-01-15T14:00:00Z" --schedule-interval 24
```

## Folder Structure

```
youtube-shorts-pipeline/
├── lib/upload.py        # YouTube upload library
├── secrets/             # OAuth credentials (gitignored)
├── content/             # Source videos (gitignored)
├── edit/                # Working directory for edits
│   ├── edl.json         # Edit decision list
│   ├── transcripts/     # Video transcriptions
│   └── animations/      # Overlay animations
└── generated/           # Final rendered videos (gitignored)
```

## Presets

Built-in presets for common content types:

- `sauna` - DIY/construction content
- `tesla` - EV/self-driving content
- `cats` - Pet content
- `travel` - Travel/adventure content

Use with `--preset sauna` flag.
