#!/usr/bin/env python3
"""Retitle uploaded YouTube Shorts to match current titles in edit/edl.json.

For every short with an `uploaded_url`, fetches the current YouTube title and
updates it if it differs from `title` in the EDL. Requires
`youtube.force-ssl` scope (see lib/upload.py SCOPES).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

from upload import get_authenticated_service


def _normalize(s: str) -> str:
    """Collapse Unicode + whitespace so em-dash normalization drift doesn't trigger a rename."""
    return unicodedata.normalize("NFKC", s).strip()

REPO = Path(__file__).resolve().parent.parent
EDL_PATH = REPO / "edit" / "edl.json"


def extract_video_id(url: str) -> str:
    m = re.search(r"/shorts/([A-Za-z0-9_-]{11})", url)
    if not m:
        raise ValueError(f"Cannot parse video id from {url!r}")
    return m.group(1)


def main():
    edl = json.loads(EDL_PATH.read_text())
    shorts = [s for s in edl["shorts"] if s.get("uploaded_url") and s.get("title")]
    if not shorts:
        print("No uploaded shorts to check.")
        return 0

    yt = get_authenticated_service()

    id_to_short = {extract_video_id(s["uploaded_url"]): s for s in shorts}
    ids = list(id_to_short.keys())

    # Fetch current snippets in batches of 50
    to_update = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        resp = yt.videos().list(id=",".join(batch), part="snippet").execute()
        for item in resp.get("items", []):
            vid = item["id"]
            snip = item["snippet"]
            want = id_to_short[vid]["title"]
            if _normalize(snip["title"]) != _normalize(want):
                to_update.append((vid, snip, want))

    if not to_update:
        print("All titles already match. Nothing to do.")
        return 0

    print(f"Will retitle {len(to_update)} videos:")
    for vid, snip, want in to_update:
        print(f"  {vid}  {snip['title']!r} -> {want!r}")
    print()

    for vid, snip, want in to_update:
        body = {
            "id": vid,
            "snippet": {
                "title": want,
                "categoryId": snip.get("categoryId", "22"),
            },
        }
        for k in ("description", "tags", "defaultLanguage", "defaultAudioLanguage"):
            if k in snip:
                body["snippet"][k] = snip[k]
        yt.videos().update(part="snippet", body=body).execute()
        print(f"  updated {vid} -> {want!r}")

    print(f"\nDone. Retitled {len(to_update)} videos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
