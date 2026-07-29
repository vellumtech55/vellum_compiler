# debug_tool.py — fast, no-export diagnostic for the video editor pipeline.
#
# Runs the same analysis process_video() does (dependency check, duration
# probe, audio-track guard, silencedetect, padded segment build) but never
# touches ffmpeg's encoder — so it's fast and safe to run against anything.
# Drop this file next to editor_core.py.
#
# Usage:
#   python debug_tool.py path/to/video.mp4
#   python debug_tool.py path/to/video.mp4 --threshold 0.02

import argparse
import os
import sys
import time

try:
    from . import editor_core as ec
    from . import editor_config as config
except ImportError:
    # Running as a bare script (not `python -m package.debug_tool`) —
    # import the sibling modules directly, same trick main.py uses.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import editor_core as ec
    import editor_config as config


def _timed(label, fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    dt = time.perf_counter() - t0
    print(f"[{dt:6.2f}s] {label}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Fast dry-run debug for the video editor.")
    parser.add_argument("video", help="Path to a video file")
    parser.add_argument("--threshold", type=float, default=None,
                         help="Override VOLUME_THRESHOLD (default: editor_config value, ffmpeg backend only)")
    parser.add_argument("--backend", choices=["ffmpeg", "silero"], default=None,
                         help="Override VAD_BACKEND (default: editor_config value)")
    parser.add_argument("--device", choices=["cpu", "gpu"], default=None,
                         help="Override SILERO_DEVICE — only matters with --backend silero")
    args = parser.parse_args()

    if args.backend is not None:
        config.VAD_BACKEND = args.backend
    if args.device is not None:
        config.SILERO_DEVICE = args.device

    print(f"── Dependency check (backend={config.VAD_BACKEND}, device={config.SILERO_DEVICE}) ──")
    ok, err = ec.check_dependencies(config.VAD_BACKEND, config.SILERO_DEVICE)
    print("dependencies:", "OK" if ok else f"MISSING — {err}")
    if not ok:
        sys.exit(1)

    print("\n── Stage timings ──")
    duration = _timed("get_duration", ec.get_duration, args.video)
    print(f"    duration  = {duration:.2f}s")

    has_audio = _timed("has_audio_stream", ec.has_audio_stream, args.video)
    print(f"    has_audio = {has_audio}")
    if not has_audio:
        print("\nVideo has no audio track — stopping here.")
        sys.exit(1)

    threshold = args.threshold if args.threshold is not None else config.VOLUME_THRESHOLD
    label = "silencedetect" if config.VAD_BACKEND == "ffmpeg" else f"Silero VAD ({config.SILERO_DEVICE.upper()})"
    result = _timed(
        f"preview_cuts ({label} + segment build, no export)",
        ec.preview_cuts, args.video, threshold,
    )

    print("\n── Result ──")
    print(f"threshold used : {threshold}")
    print(f"duration       : {result['duration']:.2f}s")
    print(f"cuts found     : {result['cut_count']}")
    print(f"kept           : {result['kept_seconds']:.2f}s")
    print(f"removed        : {result['removed_seconds']:.2f}s")
    for i, c in enumerate(result["cuts"]):
        print(f"  [{i+1:03d}] {c['start']:8.2f} -> {c['end']:8.2f}  ({c['end']-c['start']:.2f}s)")


if __name__ == "__main__":
    main()
