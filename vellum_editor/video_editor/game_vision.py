# game_vision.py — visual game-HUD event detection (beta)
#
# Replaces the audio-matching approach (game_audio.py) with something that
# actually looks at the screen: a small region over the damage indicator
# (hit flash / vignette) and a small region over the ammo counter. No audio
# involved at all.
#
# ffmpeg does all the decoding/cropping; numpy does the pixel math. OCR
# (pytesseract + the tesseract binary) is optional — if it's present, ammo
# detection reads the actual digits and reports exact shot counts; if not,
# it falls back to flagging "the counter's pixels changed" without a count.
#
#   pip install numpy
#   pip install pytesseract pillow   # optional, for exact ammo counts
#   # + the tesseract-ocr binary on PATH (apt/brew/choco install tesseract)

import math
import os
import shutil
import subprocess
import tempfile


class GameVisionError(RuntimeError):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# Dependency checks
# ══════════════════════════════════════════════════════════════════════════════

def numpy_installed():
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def check_dependencies():
    """Return (ok, error_msg). ffmpeg + numpy are required; OCR is optional
    (see ocr_available/ocr_status) and only affects ammo-count precision."""
    if shutil.which("ffmpeg") is None:
        return False, "game_vision requires ffmpeg on PATH."
    if not numpy_installed():
        return False, "game_vision requires numpy. Install with: pip install numpy"
    return True, None


def ocr_available():
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def ocr_status():
    if ocr_available():
        return "OCR available — ammo detection will report exact shot counts."
    return (
        "OCR not installed — ammo detection will fall back to change-detection "
        "(flags when the counter changes, without an exact count). For exact "
        "counts: pip install pytesseract pillow, then install the tesseract-ocr "
        "binary and make sure it's on PATH."
    )


# ══════════════════════════════════════════════════════════════════════════════
# Frame grabbing (used by the UI's click-and-drag region picker)
# ══════════════════════════════════════════════════════════════════════════════

def grab_frame(video_path, at_seconds, out_path):
    """Extract a single frame as a PNG, for the region-picker UI to display."""
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-ss", f"{max(0.0, at_seconds):.2f}", "-i", video_path,
        "-frames:v", "1", out_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path


def _get_resolution(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_path],
        capture_output=True, text=True, check=True,
    )
    w_str, h_str = out.stdout.strip().split("x")
    return int(w_str), int(h_str)


def _region_to_crop(region, width, height):
    """region is (x1, y1, x2, y2) as fractions 0-1 of the frame — resolution
    independent, so a region picked on a 1080p preview still lines up if the
    actual source is 1440p/4K/etc."""
    x1, y1, x2, y2 = region
    cx = int(x1 * width)
    cy = int(y1 * height)
    cw = max(2, int((x2 - x1) * width))
    ch = max(2, int((y2 - y1) * height))
    cw -= cw % 2  # even dims play nicer with some ffmpeg filters
    ch -= ch % 2
    return cx, cy, max(2, cw), max(2, ch)


# ══════════════════════════════════════════════════════════════════════════════
# Region sampling — crop a HUD region out of every frame at a fixed fps
# ══════════════════════════════════════════════════════════════════════════════

def _sample_region(video_path, region, fps, scale_to=None, cancel_event=None):
    """
    Yields (time, frame) for a cropped region sampled at `fps` frames/sec,
    where frame is an (h, w, 3) uint8 numpy array.

    scale_to=(w, h) resizes the crop down to a fixed small size — used for
    the damage region, where only average color matters. Leave it None (as
    for the ammo region) to keep native crop resolution, since OCR needs the
    actual detail to read digits reliably.
    """
    import numpy as np

    width, height = _get_resolution(video_path)
    cx, cy, cw, ch = _region_to_crop(region, width, height)

    vf = f"crop={cw}:{ch}:{cx}:{cy},fps={fps}"
    out_w, out_h = cw, ch
    if scale_to:
        out_w, out_h = scale_to
        vf += f",scale={out_w}:{out_h}"

    cmd = ["ffmpeg", "-y", "-nostdin", "-i", video_path, "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = out_w * out_h * 3
    i = 0
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                from .editor_core import OperationCancelled
                raise OperationCancelled("Cancelled by user.")

            chunk = proc.stdout.read(frame_bytes)
            if len(chunk) < frame_bytes:
                break
            frame = np.frombuffer(chunk, dtype=np.uint8).reshape(out_h, out_w, 3)
            yield i / fps, frame
            i += 1
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()


# ══════════════════════════════════════════════════════════════════════════════
# Damage detection — flags a sudden red/bright flash over the HUD region
# ══════════════════════════════════════════════════════════════════════════════

def detect_damage_events(video_path, region, threshold=0.12, cooldown=0.5, fps=4, cancel_event=None):
    """
    Tracks a slow-moving color baseline for `region` and flags moments it
    spikes redder/brighter than that baseline — the red vignette/flash most
    shooters use for "you just took damage."
    Returns [{"time": float, "type": "damage", "confidence": float}, ...].
    """
    events = []
    baseline = None
    last_event_t = -math.inf

    for t, frame in _sample_region(video_path, region, fps, scale_to=(32, 32), cancel_event=cancel_event):
        r = float(frame[..., 0].mean())
        g = float(frame[..., 1].mean())
        b = float(frame[..., 2].mean())
        score = max(0.0, (r - (g + b) / 2.0) / 255.0)  # 0-1 "how red" this frame is

        if baseline is None:
            baseline = score
            continue

        delta = score - baseline
        if delta >= threshold and (t - last_event_t) >= cooldown:
            events.append({"time": t, "type": "damage", "confidence": min(1.0, delta / threshold)})
            last_event_t = t

        # slow-decaying baseline: a sustained flash doesn't get treated as
        # "normal" within a frame or two, but slow lighting/HUD drift is
        # tracked out over a few seconds
        baseline = baseline * 0.9 + score * 0.1

    return events


# ══════════════════════════════════════════════════════════════════════════════
# Ammo-counter detection — OCR the digits when possible, else change-detect
# ══════════════════════════════════════════════════════════════════════════════

def _ocr_digits(frame):
    """Best-effort OCR of a small cropped frame to an integer. None if OCR
    isn't available or nothing digit-like was read."""
    import pytesseract
    from PIL import Image

    img = Image.fromarray(frame)
    text = pytesseract.image_to_string(
        img, config="--psm 7 -c tessedit_char_whitelist=0123456789"
    ).strip()
    return int(text) if text.isdigit() else None


def detect_ammo_events(video_path, region, fps=4, cooldown=0.12, max_shots_per_sample=5, cancel_event=None):
    """
    Reads the ammo-counter region on every sampled frame.

    With OCR available: reads the actual digits and flags one "shot" event
    per drop in the count (a small decrease). A big upward jump, or a drop
    bigger than `max_shots_per_sample`, is treated as a reload/UI change and
    ignored rather than counted as shots.

    Without OCR: falls back to flagging a generic "ammo_change" whenever the
    region's pixels change enough to suggest the digits changed — same idea,
    just without an exact count.

    Returns [{"time": float, "type": "shot"|"ammo_change", "count": int|None}, ...]
    """
    import numpy as np

    use_ocr = ocr_available()
    events = []
    last_value = None
    last_frame = None
    last_event_t = -math.inf

    for t, frame in _sample_region(video_path, region, fps, scale_to=None, cancel_event=cancel_event):
        if use_ocr:
            value = _ocr_digits(frame)
            if value is not None and last_value is not None:
                drop = last_value - value
                if 0 < drop <= max_shots_per_sample:
                    events.append({"time": t, "type": "shot", "count": drop})
            if value is not None:
                last_value = value
        else:
            if last_frame is not None:
                diff = float(np.abs(frame.astype("int16") - last_frame.astype("int16")).mean())
                if diff >= 8.0 and (t - last_event_t) >= cooldown:
                    events.append({"time": t, "type": "ammo_change", "count": None})
                    last_event_t = t
            last_frame = frame

    return events


# ══════════════════════════════════════════════════════════════════════════════
# Combined entry point
# ══════════════════════════════════════════════════════════════════════════════

def detect_game_events(
    video_path,
    damage_region=None,
    ammo_region=None,
    fps=4,
    damage_threshold=0.12,
    cooldown=0.5,
    cancel_event=None,
):
    """Runs whichever HUD detectors have a region configured and returns a
    single time-sorted event list (shape matches editor_core.build_cuts_from_events)."""
    events = []

    if damage_region:
        events += detect_damage_events(
            video_path, damage_region, threshold=damage_threshold,
            cooldown=cooldown, fps=fps, cancel_event=cancel_event,
        )

    if ammo_region:
        events += detect_ammo_events(
            video_path, ammo_region, fps=fps,
            cooldown=min(cooldown, 0.15), cancel_event=cancel_event,
        )

    events.sort(key=lambda e: e["time"])
    return events
