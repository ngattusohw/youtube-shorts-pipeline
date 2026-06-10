#!/usr/bin/env python3
"""Analyze a source video to help pick Short cut points.

Outputs into edit/analysis/<stem>/:
- thumbnails/frame_NNNNs.jpg   (HDR-tonemapped, every --interval seconds)
- audio_rms.json               (RMS in dBFS, one sample per second)
- scenes.json                  (timestamps of detected scene cuts)
- report.md                    (human-readable summary highlighting interesting ranges)

Usage:
    python lib/analyze_source.py content/copy_<uuid>.mov
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TONEMAP_VF = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)


def fmt_t(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def probe_duration(src: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(src),
    ]).decode().strip()
    return float(out)


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


def extract_thumbnails(src: Path, out_dir: Path, duration: float, interval: int) -> list[int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    times = list(range(0, int(duration), interval))
    for t in times:
        out = out_dir / f"frame_{t:04d}s.jpg"
        if out.exists():
            continue
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(t),
            "-i", str(src),
            "-frames:v", "1", "-update", "1",
            "-vf", f"{TONEMAP_VF},scale=640:-1",
            "-q:v", "3", str(out),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return times


def audio_rms_per_second(src: Path) -> list[float]:
    """Decode audio as mono 22050 Hz s16le and compute per-second RMS in dBFS."""
    sr = 22050
    proc = subprocess.run([
        "ffmpeg", "-v", "error",
        "-i", str(src),
        "-ac", "1", "-ar", str(sr),
        "-f", "s16le", "pipe:",
    ], check=True, capture_output=True)
    raw = proc.stdout
    n_samples = len(raw) // 2
    samples_per_sec = sr
    out: list[float] = []
    for i in range(0, n_samples, samples_per_sec):
        chunk = raw[i * 2: (i + samples_per_sec) * 2]
        n = len(chunk) // 2
        if n == 0:
            break
        vals = struct.unpack(f"<{n}h", chunk)
        sumsq = sum(v * v for v in vals)
        rms = math.sqrt(sumsq / n)
        if rms == 0:
            out.append(-100.0)
        else:
            out.append(20 * math.log10(rms / 32768.0))
    return out


def detect_scenes(src: Path, threshold: float = 0.3) -> list[float]:
    proc = subprocess.run([
        "ffmpeg", "-i", str(src),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-an", "-f", "null", "-",
    ], capture_output=True)
    text = proc.stderr.decode(errors="ignore")
    times: list[float] = []
    for m in re.finditer(r"showinfo.*?pts_time:(\d+\.?\d*)", text):
        t = float(m.group(1))
        if not times or t - times[-1] > 0.3:
            times.append(t)
    return times


def find_loud_runs(rms: list[float], threshold_db: float = -28.0, min_len: int = 6) -> list[tuple[int, int, float]]:
    runs: list[tuple[int, int, float]] = []
    start = None
    for i, db in enumerate(rms):
        if db >= threshold_db:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_len:
                seg = rms[start:i]
                runs.append((start, i, sum(seg) / len(seg)))
            start = None
    if start is not None and len(rms) - start >= min_len:
        seg = rms[start:]
        runs.append((start, len(rms), sum(seg) / len(seg)))
    return runs


def find_silent_runs(rms: list[float], threshold_db: float = -55.0, min_len: int = 8) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for i, db in enumerate(rms):
        if db <= threshold_db:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(rms) - start >= min_len:
        runs.append((start, len(rms)))
    return runs


def write_report(out_dir: Path, src: Path, duration: float, dims: tuple[int, int],
                 rms: list[float], scenes: list[float], interval: int) -> None:
    loud = find_loud_runs(rms)
    quiet = find_silent_runs(rms)

    lines: list[str] = []
    lines.append(f"# Analysis: {src.name}")
    lines.append("")
    lines.append(f"- Duration: **{fmt_t(duration)}** ({duration:.1f}s)")
    lines.append(f"- Source dims: {dims[0]}x{dims[1]}")
    lines.append(f"- Thumbnails: every {interval}s under `thumbnails/`")
    lines.append(f"- Scene cuts detected: {len(scenes)}")
    lines.append("")

    lines.append("## Sustained loud sections (likely active ASMR moments)")
    lines.append("")
    lines.append("Loud = audio RMS >= -28 dBFS for >= 6s. Prefer segment **ends** at the trailing edge of these runs.")
    lines.append("")
    if loud:
        lines.append("| Range | Length | Avg RMS |")
        lines.append("|---|---|---|")
        for a, b, avg in loud:
            lines.append(f"| {fmt_t(a)} – {fmt_t(b)} | {b - a}s | {avg:.1f} dB |")
    else:
        lines.append("_(none detected with current thresholds)_")
    lines.append("")

    lines.append("## Quiet/idle sections (likely transitions or moments-of-rest)")
    lines.append("")
    lines.append("Quiet = RMS <= -55 dBFS for >= 8s. Good for atmospheric establishing shots.")
    lines.append("")
    if quiet:
        lines.append("| Range | Length |")
        lines.append("|---|---|")
        for a, b in quiet:
            lines.append(f"| {fmt_t(a)} – {fmt_t(b)} | {b - a}s |")
    else:
        lines.append("_(none detected with current thresholds)_")
    lines.append("")

    lines.append("## Scene cuts")
    lines.append("")
    if scenes:
        lines.append("| Time |")
        lines.append("|---|")
        for t in scenes:
            lines.append(f"| {fmt_t(t)} ({t:.1f}s) |")
    else:
        lines.append("_(none detected)_")
    lines.append("")

    lines.append("## RMS samples (1 Hz, dBFS)")
    lines.append("")
    lines.append("```")
    for i in range(0, len(rms), 10):
        chunk = rms[i:i+10]
        lines.append(f"{fmt_t(i):>6}  " + " ".join(f"{v:6.1f}" for v in chunk))
    lines.append("```")

    (out_dir / "report.md").write_text("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="Path to source video (relative to repo or absolute)")
    p.add_argument("--interval", type=int, default=10, help="Thumbnail interval in seconds (default 10)")
    args = p.parse_args()

    src = Path(args.source)
    if not src.is_absolute():
        src = REPO / src
    if not src.exists():
        print(f"Source not found: {src}", file=sys.stderr)
        return 1

    out_dir = REPO / "edit" / "analysis" / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Probing {src.name}")
    duration = probe_duration(src)
    dims = probe_dims(src)
    print(f"      duration={duration:.1f}s  dims={dims[0]}x{dims[1]}")

    print(f"[2/4] Thumbnails @ {args.interval}s")
    extract_thumbnails(src, out_dir / "thumbnails", duration, args.interval)

    print(f"[3/4] Audio RMS per second")
    rms = audio_rms_per_second(src)
    (out_dir / "audio_rms.json").write_text(json.dumps(rms, indent=0))

    print(f"[4/4] Scene detection")
    scenes = detect_scenes(src)
    (out_dir / "scenes.json").write_text(json.dumps(scenes, indent=0))

    write_report(out_dir, src, duration, dims, rms, scenes, args.interval)
    print(f"\nDone. See {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
