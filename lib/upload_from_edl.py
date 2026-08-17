#!/usr/bin/env python3
"""Upload Shorts from edl.json.

Reads `edit/edl.json` and uploads every short that has a `schedule` set but no
`uploaded_url` yet. Writes the URL back to edl.json after each successful upload
so the process is resumable.

Uses the sauna preset's tags. Description is the per-short `description` field
in the EDL, plus standard hashtags appended.
"""
import json
import sys
from pathlib import Path

from upload import get_authenticated_service, upload_video, PRESETS

REPO = Path(__file__).resolve().parent.parent
EDL_PATH = REPO / "edit" / "edl.json"
GEN = REPO / "generated"

HASHTAG_TAILS = {
    "sauna": "#Shorts #DIY #SaunaBuild #ASMR #Satisfying",
    "roofing": "#Shorts #DIY #Roofing #ASMR #Satisfying",
}
DEFAULT_PRESET = "sauna"


def main():
    edl = json.loads(EDL_PATH.read_text())
    shorts = edl["shorts"]

    pending = [s for s in shorts if s.get("schedule") and not s.get("uploaded_url")]
    if not pending:
        print("Nothing to upload (all scheduled shorts already have uploaded_url).")
        return 0

    print(f"Will upload {len(pending)} shorts:")
    for s in pending:
        print(f"  {s['schedule']}  {s['name']}  -> {s['title']}")
    print()

    yt = get_authenticated_service()

    for s in pending:
        path = GEN / f"{s['name']}.mp4"
        if not path.exists():
            print(f"SKIP: {path} not found", file=sys.stderr)
            continue

        preset_name = s.get("preset", DEFAULT_PRESET)
        tail = HASHTAG_TAILS[preset_name]
        tags = list(PRESETS[preset_name]["tags"])
        body_desc = s.get("description", "").strip()
        description = f"{body_desc}\n\n{tail}" if body_desc else tail

        vid, url = upload_video(
            yt, path, s["title"],
            description=description,
            tags=tags,
            is_short=True,
            privacy="private",
            schedule=s["schedule"],
        )

        if url:
            s["uploaded_url"] = url
            EDL_PATH.write_text(json.dumps(edl, indent=2) + "\n")
            print(f"  saved url to edl.json\n")

    print("\n=== Done ===")
    for s in pending:
        if s.get("uploaded_url"):
            print(f"{s['schedule']}  {s['uploaded_url']}  {s['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
