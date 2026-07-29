# editor_core.py — AI Video Editor core processing
# ffmpeg-only pipeline. No moviepy / librosa / numpy / scikit-learn.
# Detects silence via ffmpeg's own silencedetect filter, derives padded
# speech segments, then cuts/exports with real ffmpeg progress + cancel support.

import os
import re
import math
import shutil
import subprocess
import threading
import queue

from . import editor_config as config
from . import game_vision


class OperationCancelled(Exception):
    """Raised when a cancel_event fires mid-analysis or mid-export."""
    pass


def check_dependencies(vad_backend=None, vad_device=None):
    """Return (ok: bool, error_msg: str | None). ffmpeg/ffprobe on PATH is
    always required; if vad_backend="silero" this also checks onnxruntime
    (+ a GPU execution provider, if vad_device="gpu")."""
    missing = [b for b in ("ffmpeg", "ffprobe") if shutil.which(b) is None]
    if missing:
        return False, (
            f"Missing on PATH: {', '.join(missing)}.\n"
            "Install ffmpeg (https://ffmpeg.org/download.html) and make sure "
            "ffmpeg/ffprobe are on your system PATH."
        )

    backend = vad_backend if vad_backend is not None else getattr(config, "VAD_BACKEND", "ffmpeg")
    if backend == "silero":
        from . import silero_vad
        device = vad_device if vad_device is not None else getattr(config, "SILERO_DEVICE", "cpu")
        ok, err = silero_vad.check_dependencies(device)
        if not ok:
            return False, err

    if getattr(config, "USE_GAME_VISION", False):
        ok, err = game_vision.check_dependencies()
        if not ok:
            return False, err

    return True, None


# ══════════════════════════════════════════════════════════════════════════════
# ffprobe helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_duration(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def has_audio_stream(video_path):
    """ffprobe check for at least one audio stream. Replaces moviepy's
    `video.audio is None` guard so a silent/broken file fails fast and clearly."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


# ══════════════════════════════════════════════════════════════════════════════
# Generic ffmpeg runner: real progress (via -progress pipe:1) + cancel support
# ══════════════════════════════════════════════════════════════════════════════

def _drain_lines(stream, sink):
    """Read a subprocess pipe line-by-line into `sink` (list or Queue) until EOF."""
    try:
        for line in stream:
            sink.put(line) if isinstance(sink, queue.Queue) else sink.append(line)
    except ValueError:
        pass  # stream closed underneath us during teardown
    finally:
        if isinstance(sink, queue.Queue):
            sink.put(None)  # sentinel


def _run_ffmpeg(cmd, total_seconds=None, on_pct=None, cancel_event=None, poll_s=0.2):
    """
    Runs an ffmpeg command with `-progress pipe:1 -nostats` inserted, streaming
    real progress (0-100, based on total_seconds) to on_pct(pct), and checking
    cancel_event roughly every `poll_s` seconds so it can be killed promptly.
    Returns the captured stderr text (ffmpeg's normal log) for error reporting.
    """
    # insert global -progress flag right after the binary name
    cmd = [cmd[0], "-progress", "pipe:1", "-nostats"] + cmd[1:]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    stdout_q = queue.Queue()
    stderr_buf = []
    threading.Thread(target=_drain_lines, args=(proc.stdout, stdout_q), daemon=True).start()
    threading.Thread(target=_drain_lines, args=(proc.stderr, stderr_buf), daemon=True).start()

    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise OperationCancelled("Cancelled by user.")

            try:
                line = stdout_q.get(timeout=poll_s)
            except queue.Empty:
                continue

            if line is None:
                break
            line = line.strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")

            if key == "out_time_ms" and total_seconds and on_pct:
                try:
                    secs = int(val) / 1_000_000
                    on_pct(min(99.0, max(0.0, secs / total_seconds * 100)))
                except ValueError:
                    pass
            elif key == "progress" and val == "end":
                break

        proc.wait()
    finally:
        # make sure the process is never left running if something above raised
        if proc.poll() is None:
            proc.kill()

    stderr_text = "".join(stderr_buf)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=stderr_text)
    return stderr_text


_SIL_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SIL_END_RE   = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silence(video_path, noise_db, min_silence_dur, duration=None,
                    on_pct=None, cancel_event=None):
    """One ffmpeg pass using the silencedetect filter; parses stderr for spans
    while streaming real decode progress via on_pct."""
    cmd = [
        "ffmpeg", "-nostdin", "-i", video_path,
        "-af", f"silencedetect=noise={noise_db:.2f}dB:d={min_silence_dur:.3f}",
        "-f", "null", "-",
    ]
    stderr_text = _run_ffmpeg(cmd, total_seconds=duration, on_pct=on_pct, cancel_event=cancel_event)

    silences = []
    pending_start = None
    for line in stderr_text.splitlines():
        m = _SIL_START_RE.search(line)
        if m:
            pending_start = float(m.group(1))
            continue
        m = _SIL_END_RE.search(line)
        if m and pending_start is not None:
            silences.append((pending_start, float(m.group(1))))
            pending_start = None
    return silences


# ══════════════════════════════════════════════════════════════════════════════
# Speech segments (complement of silence), padded so nothing gets cut off
# ══════════════════════════════════════════════════════════════════════════════

def _pad_and_merge_segments(duration, segments):
    """Apply SPEECH_PADDING_START/END + MIN_CLIP_LENGTH to raw (start, end)
    speech spans and merge anything that now overlaps. Shared by both VAD
    backends (ffmpeg silencedetect and Silero) since they both ultimately
    produce the same raw-span shape."""
    padded = []
    for start, end in segments:
        s = max(0.0, start - config.SPEECH_PADDING_START)
        e = min(duration, end + config.SPEECH_PADDING_END)
        if e - s >= config.MIN_CLIP_LENGTH:
            padded.append({"start": s, "end": e})
    return merge_overlapping_cuts(padded)


def compute_speech_segments(duration, silences):
    """ffmpeg-backend path: speech = the complement of the detected silences."""
    segments = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start > cursor:
            segments.append((cursor, s_start))
        cursor = max(cursor, s_end)
    if cursor < duration:
        segments.append((cursor, duration))

    return _pad_and_merge_segments(duration, segments)


def decide_cuts(segments):
    return [{"start": s["start"], "end": s["end"]} for s in segments]


# ══════════════════════════════════════════════════════════════════════════════
# Game-audio helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_cuts_from_events(events, padding=0.4):
    return [
        {"start": max(0, e["time"] - padding),
         "end":   e["time"] + padding,
         "reason": e["type"]}
        for e in events
    ]


def merge_overlapping_cuts(cuts):
    if not cuts:
        return []
    cuts   = sorted(cuts, key=lambda c: c["start"])
    merged = [dict(cuts[0])]
    for c in cuts[1:]:
        if c["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
        else:
            merged.append(dict(c))
    return merged


# ══════════════════════════════════════════════════════════════════════════════
# Shared analysis step (used by both preview_cuts and process_video)
# ══════════════════════════════════════════════════════════════════════════════

def analyze(video_path, volume_threshold=None, progress_cb=None, cancel_event=None):
    """
    Runs the audio-guard + silencedetect + speech-segment + (optional game
    audio) pipeline and returns:
        {"duration": float, "cuts": [...], "kept_seconds": float}
    Does NOT touch the filesystem for output — safe to call for a preview.
    """
    vad_backend = getattr(config, "VAD_BACKEND", "ffmpeg")
    vad_device  = getattr(config, "SILERO_DEVICE", "cpu")

    ok, err = check_dependencies(vad_backend, vad_device)
    if not ok:
        raise RuntimeError(err)

    def log(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)

    threshold = volume_threshold if volume_threshold is not None else config.VOLUME_THRESHOLD

    log(5, "Reading video info…")
    duration = get_duration(video_path)

    if not has_audio_stream(video_path):
        raise ValueError("Video has no audio track.")

    if vad_backend == "silero":
        from . import silero_vad

        log(8, f"Loading Silero VAD ({vad_device.upper()})…")

        def _vad_pct(p):
            log(10 + p * 0.30, "Scanning for speech (Silero VAD)…")  # maps 0-100 -> 10-40

        raw_spans = silero_vad.detect_speech_segments(
            video_path,
            threshold=getattr(config, "SILERO_THRESHOLD", 0.5),
            min_speech_ms=getattr(config, "SILERO_MIN_SPEECH_MS", 250),
            min_silence_ms=int(config.MIN_SILENCE_DURATION * 1000),
            device=vad_device,
            model_path=getattr(config, "SILERO_MODEL_PATH", None),
            on_pct=_vad_pct,
            cancel_event=cancel_event,
        )
        speech_segments = _pad_and_merge_segments(
            duration, [(s["start"], s["end"]) for s in raw_spans]
        )
    else:
        sil_thresh = max(threshold * config.SILENCE_THRESHOLD_MULT, 1e-4)
        noise_db   = 20 * math.log10(sil_thresh)

        def _silence_pct(p):
            log(10 + p * 0.30, "Scanning for silence…")  # maps 0-100 -> 10-40

        silences = detect_silence(
            video_path, noise_db, config.MIN_SILENCE_DURATION,
            duration=duration, on_pct=_silence_pct, cancel_event=cancel_event,
        )
        speech_segments = compute_speech_segments(duration, silences)

    log(45, "Building padded speech segments…")
    all_cuts = decide_cuts(speech_segments)
    log(50, f"Found {len(all_cuts)} speech segment(s).")

    if config.USE_GAME_VISION:
        damage_region = getattr(config, "GAME_DAMAGE_REGION", None)
        ammo_region   = getattr(config, "GAME_AMMO_REGION", None)

        if damage_region or ammo_region:
            log(55, "Scanning game HUD for damage/ammo events…")
            events = game_vision.detect_game_events(
                video_path,
                damage_region=damage_region,
                ammo_region=ammo_region,
                fps=getattr(config, "GAME_VISION_FPS", 4),
                damage_threshold=getattr(config, "GAME_DAMAGE_THRESHOLD", 0.12),
                cooldown=getattr(config, "GAME_EVENT_COOLDOWN", 0.5),
                cancel_event=cancel_event,
            )
            game_cuts = build_cuts_from_events(events, padding=getattr(config, "GAME_EVENT_PADDING", 0.4))
            all_cuts.extend(game_cuts)
            log(60, f"Found {len(events)} game HUD event(s).")
        else:
            log(60, "Game HUD detection enabled but no region is set — skipping.")

    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("Cancelled by user.")

    log(65, "Merging overlapping cuts…")
    all_cuts = merge_overlapping_cuts(all_cuts)
    kept_seconds = sum(c["end"] - c["start"] for c in all_cuts)

    return {"duration": duration, "cuts": all_cuts, "kept_seconds": kept_seconds}


def preview_cuts(video_path, volume_threshold=None, progress_cb=None, cancel_event=None):
    """
    Analysis only, no export. Returns the same dict as `analyze`, plus
    cut_count and removed_seconds, so a UI can show "12 clips kept, cutting
    video from 8:42 down to 5:10" before committing to a re-encode.
    """
    result = analyze(video_path, volume_threshold, progress_cb, cancel_event)
    result["cut_count"] = len(result["cuts"])
    result["removed_seconds"] = max(0.0, result["duration"] - result["kept_seconds"])
    if progress_cb:
        progress_cb(100, "Preview ready.")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Export — one ffmpeg pass for "single", one call per clip for "multiple"
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Export — segment-then-concat for "single", one call per clip for "multiple"
#
# NOTE: an earlier version built one giant `-filter_complex` graph (a
# trim/atrim branch per cut, joined by a single `concat` filter). That works
# for a few cuts but does NOT scale — with dozens/hundreds of segments (which
# is exactly what silence removal produces) the filtergraph has to hold
# decoded frames for every branch in memory at once, which can balloon RAM
# and appear to hang at a fixed percent, or actually stall the machine.
# Cutting each segment to its own file and joining with the concat *demuxer*
# (stream copy — no re-encode) scales linearly instead.
# ══════════════════════════════════════════════════════════════════════════════

def export_single(video_path, cuts, output_folder, progress_cb=None, cancel_event=None):
    out     = os.path.join(output_folder, "output_final.mp4")
    tmp_dir = os.path.join(output_folder, ".vellum_segments_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    total = sum(c["end"] - c["start"] for c in cuts) or 1.0
    n = len(cuts)
    seg_paths = []
    list_path = None

    try:
        elapsed_before = 0.0
        for i, c in enumerate(cuts):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelled("Cancelled by user.")

            dur = c["end"] - c["start"]
            seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
            if progress_cb:
                progress_cb(None, f"Encoding segment {i+1}/{n}…")

            def _pct(p, i=i, dur=dur, elapsed_before=elapsed_before):
                if progress_cb:
                    done = elapsed_before + (p / 100.0) * dur
                    progress_cb(min(95.0, done / total * 95.0),
                                f"Encoding segment {i+1}/{n}… {p:.0f}%")

            cmd = [
                "ffmpeg", "-y", "-nostdin",
                "-ss", f"{c['start']:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k",
                seg_path,
            ]
            _run_ffmpeg(cmd, total_seconds=dur, on_pct=_pct, cancel_event=cancel_event)
            seg_paths.append(seg_path)
            elapsed_before += dur

        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled("Cancelled by user.")

        if progress_cb:
            progress_cb(95, f"Joining {n} segment(s)…")

        list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for p in seg_paths:
                escaped = os.path.abspath(p).replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")

        cmd = ["ffmpeg", "-y", "-nostdin", "-f", "concat", "-safe", "0",
               "-i", list_path, "-c", "copy", out]

        def _final_pct(p):
            if progress_cb:
                progress_cb(95 + p * 0.05, f"Joining… {p:.0f}%")

        _run_ffmpeg(cmd, total_seconds=total, on_pct=_final_pct, cancel_event=cancel_event)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        if list_path:
            try:
                os.remove(list_path)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    if progress_cb:
        progress_cb(100, f"Saved → {out}")
    return [out]


def export_multiple(video_path, cuts, output_folder, progress_cb=None, cancel_event=None):
    paths = []
    n = len(cuts)
    for i, c in enumerate(cuts):
        out = os.path.join(output_folder, f"output_clip_{i+1:03d}.mp4")
        dur = c["end"] - c["start"]
        if progress_cb:
            progress_cb(None, f"Exporting clip {i+1}/{n}…")

        def _pct(p, i=i):
            if progress_cb:
                overall = (i + p / 100.0) / n * 100.0
                progress_cb(overall, f"Exporting clip {i+1}/{n}… {p:.0f}%")

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-ss", f"{c['start']:.3f}", "-i", video_path, "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            out,
        ]
        _run_ffmpeg(cmd, total_seconds=dur, on_pct=_pct, cancel_event=cancel_event)
        paths.append(out)
    if progress_cb:
        progress_cb(100, f"Saved {len(paths)} clips → {output_folder}")
    return paths


def export_video(cuts, video_path, mode="single", output_folder=None,
                  progress_cb=None, cancel_event=None):
    folder = output_folder or os.getcwd()
    os.makedirs(folder, exist_ok=True)
    if not cuts:
        raise ValueError("No clips to export — nothing met the threshold.")
    if mode == "single":
        return export_single(video_path, cuts, folder, progress_cb, cancel_event)
    return export_multiple(video_path, cuts, folder, progress_cb, cancel_event)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def process_video(
    video_path,
    mode             = None,
    output_folder    = None,
    volume_threshold = None,
    progress_cb      = None,
    cancel_event     = None,
):
    """
    Full pipeline: audio-guard -> silencedetect -> padded speech segments ->
    (game audio) -> merge -> export. Real progress via progress_cb(pct, msg).
    Pass a threading.Event as cancel_event to allow cancellation mid-run;
    raises OperationCancelled if it fires. Returns list of output file paths.
    """
    if mode             is not None: config.OUTPUT_MODE      = mode
    if output_folder    is not None: config.OUTPUT_FOLDER    = output_folder
    if volume_threshold is not None: config.VOLUME_THRESHOLD = volume_threshold

    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)

    if progress_cb is None:
        def progress_cb(pct, msg):
            print(f"[{int(pct or 0):3d}%] {msg}")

    def analysis_progress(pct, msg):
        progress_cb(pct * 0.65 if pct is not None else None, msg)  # analysis = first 65%

    result = analyze(
        video_path, config.VOLUME_THRESHOLD,
        progress_cb=analysis_progress, cancel_event=cancel_event,
    )
    all_cuts = result["cuts"]

    def export_progress(pct, msg):
        scaled = 65 + pct * 0.35 if pct is not None else None  # export = last 35%
        progress_cb(scaled, msg)

    progress_cb(65, f"Exporting {len(all_cuts)} cut(s)…")

    paths = export_video(
        all_cuts, video_path,
        mode          = config.OUTPUT_MODE,
        output_folder = config.OUTPUT_FOLDER,
        progress_cb   = export_progress,
        cancel_event  = cancel_event,
    )

    progress_cb(100, "Done!")
    return paths
