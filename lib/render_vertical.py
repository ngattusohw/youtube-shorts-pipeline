#!/usr/bin/env python3
"""Render vertical 1080x1920 Shorts from edit/edl.json using ffmpeg.

- Center-crops 1920x1080 -> 1080x1920 (9:16) by default, with optional per-segment x_offset.
- HDR (BT.2020/HLG) -> SDR (BT.709) via the colorspace filter.
- Pure ASMR: keeps original audio, no captions, no music.
- Encodes H.264 yuv420p @ 60fps + AAC stereo to generated/<name>.mp4.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDL_PATH = REPO / "edit" / "edl.json"
OUT_DIR = REPO / "generated"
TMP_DIR = REPO / "edit" / "_tmp_segments"

DST_W, DST_H = 1080, 1920  # 9:16 vertical output


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def probe_dims(src: Path) -> tuple[int, int]:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(src),
    ]).decode().strip()
    parts = [p for p in out.split("x") if p]
    return int(parts[0]), int(parts[1])


def build_vf(src_w: int, src_h: int, x_offset: int) -> str:
    # 9:16 crop width: even number nearest to src_h * 9/16
    crop_w = int(round(src_h * 9 / 16))
    if crop_w % 2:
        crop_w -= 1
    crop_x_center = (src_w - crop_w) // 2
    crop_x = max(0, min(src_w - crop_w, crop_x_center + x_offset))
    # HDR (HLG, BT.2020) -> linear light -> Hable tone-map -> SDR (BT.709), then crop 9:16, scale to 1080x1920.
    return (
        "zscale=t=linear:npl=100,"
        "format=gbrpf32le,"
        "zscale=p=bt709,"
        "tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,"
        "format=yuv420p,"
        f"crop={crop_w}:{src_h}:{crop_x}:0,"
        f"scale={DST_W}:{DST_H}:flags=lanczos,"
        "format=yuv420p"
    )


def render_segment(src: Path, start: float, end: float, x_offset: int, out_path: Path) -> None:
    duration = end - start
    src_w, src_h = probe_dims(src)
    vf = build_vf(src_w, src_h, x_offset)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-r", "60",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    run(cmd)


def concat_segments(segment_paths: list[Path], out_path: Path) -> None:
    list_file = TMP_DIR / f"concat_{out_path.stem}.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in segment_paths) + "\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    run(cmd)


def render_short(short: dict, default_src: Path) -> Path:
    name = short["name"]
    print(f"\n=== Rendering {name} ===")
    seg_dir = TMP_DIR / name
    seg_dir.mkdir(parents=True, exist_ok=True)

    # Allow per-short source override, with per-segment override on top of that.
    short_src = REPO / short["source"] if "source" in short else default_src

    seg_paths: list[Path] = []
    for i, seg in enumerate(short["segments"]):
        out = seg_dir / f"seg_{i:02d}.mp4"
        x_off = int(seg.get("x_offset", 0))
        seg_src = REPO / seg["source"] if "source" in seg else short_src
        render_segment(seg_src, float(seg["start"]), float(seg["end"]), x_off, out)
        seg_paths.append(out)

    final = OUT_DIR / f"{name}.mp4"
    concat_segments(seg_paths, final)
    print(f"--> {final}")
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", help="Render only the named short(s)")
    parser.add_argument("--keep-tmp", action="store_true", help="Keep intermediate segment files")
    args = parser.parse_args()

    edl = json.loads(EDL_PATH.read_text())
    src = REPO / edl["source"]
    # Default source must exist only if any Short relies on it (no override).
    needs_default = any("source" not in s for s in edl["shorts"])
    if needs_default and not src.exists():
        print(f"Default source not found: {src}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    shorts = edl["shorts"]
    if args.only:
        wanted = set(args.only)
        shorts = [s for s in shorts if s["name"] in wanted]
        missing = wanted - {s["name"] for s in shorts}
        if missing:
            print(f"No short named: {', '.join(sorted(missing))}", file=sys.stderr)
            return 1

    outs = [render_short(s, src) for s in shorts]

    if not args.keep_tmp:
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    print("\nDone:")
    for o in outs:
        print(f"  {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
