# silero_vad.py — Silero VAD (ONNX) speech-detection backend (beta)
#
# Alternative to the ffmpeg silencedetect approach in editor_core.py. Runs a
# small neural VAD model (~1-2MB) via onnxruntime instead of a plain
# amplitude threshold. Meaningfully better with music/game audio in the
# background or noisy mics — it can tell "loud game sound, nobody talking"
# from actual speech, which pure amplitude thresholding (and WebRTC VAD)
# can still get wrong.
#
# Dependencies are OPTIONAL and imported lazily, so importing this module
# (or editor_core, which imports it) never fails just because onnxruntime
# or numpy aren't installed — you only pay for it if VAD_BACKEND="silero"
# is actually selected.
#
#   pip install silero-vad         # RECOMMENDED — ships the ONNX model file
#                                   # locally, so no network download is needed
#                                   # at runtime and it can't 404 if the repo
#                                   # reorganizes its files again
#   pip install onnxruntime        # CPU only
#   pip install onnxruntime-gpu    # + CUDA GPU (Linux/Windows, NVIDIA)
#   pip install onnxruntime-directml  # + GPU on Windows via DirectML
#   pip install numpy
#
# Without the silero-vad package installed, the model is downloaded once on
# first use and cached under ~/.cache/vellum/silero_vad/ (or wherever
# VAD_MODEL_DIR points) — see _ensure_model() for the full resolution order.

import os
import shutil
import subprocess
import tempfile
import urllib.request
import wave

# The ONNX model file itself is resolved in this order:
#   1. VAD_MODEL_PATH override, if you've set one
#   2. a copy already cached locally from a previous run
#   3. the `silero-vad` pip package's own bundled copy, if installed
#      (pip install silero-vad — ships the .onnx file locally, so it can
#      never go stale/404 the way a hardcoded GitHub URL can)
#   4. download it now, trying each URL in MODEL_URLS in turn
#
# The upstream repo has moved this file's location before (files/ ->
# src/silero_vad/data/), so #3 is the most future-proof option if you hit
# download issues.

MODEL_URLS = [
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
    "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx",  # older layout, kept as a fallback
]
CACHE_DIR   = os.path.join(os.path.expanduser("~"), ".cache", "vellum", "silero_vad")
MODEL_PATH  = os.path.join(CACHE_DIR, "silero_vad.onnx")

SAMPLE_RATE = 16000   # Silero VAD is trained on 16kHz mono audio
_WINDOW     = 512     # samples per inference step at 16kHz (Silero's expected chunk size)

GPU_PROVIDERS = ("CUDAExecutionProvider", "DmlExecutionProvider", "ROCMExecutionProvider")

# Sessions are cached per (device, model_path) so switching CPU <-> GPU in the
# UI doesn't reload the model from disk on every run.
_session_cache = {}


class SileroVADError(RuntimeError):
    """Raised for anything that should surface as a clear message in the UI —
    missing dependency, no GPU provider available, model download failure."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# Dependency / capability checks (call these before use so the UI can warn early)
# ══════════════════════════════════════════════════════════════════════════════

def onnxruntime_installed():
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def numpy_installed():
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def available_providers():
    """onnxruntime execution providers actually available on this machine.
    Empty list if onnxruntime isn't installed."""
    if not onnxruntime_installed():
        return []
    import onnxruntime as ort
    return ort.get_available_providers()


def gpu_available():
    """True if at least one GPU execution provider (CUDA / DirectML / ROCm)
    is available — i.e. onnxruntime-gpu (or -directml) is installed *and*
    the matching driver/runtime is present."""
    providers = available_providers()
    return any(p in providers for p in GPU_PROVIDERS)


def check_dependencies(device="cpu"):
    """Return (ok, error_msg). Mirrors editor_core.check_dependencies() so the
    UI/debug tool can surface a clear reason before attempting a run."""
    if not numpy_installed():
        return False, "Silero VAD requires numpy. Install with: pip install numpy"
    if not onnxruntime_installed():
        return False, (
            "Silero VAD requires onnxruntime. Install with:\n"
            "  pip install onnxruntime          (CPU)\n"
            "  pip install onnxruntime-gpu      (NVIDIA GPU)\n"
            "  pip install onnxruntime-directml (Windows GPU)"
        )
    if device == "gpu" and not gpu_available():
        return False, (
            "No GPU execution provider available for onnxruntime. Install "
            "onnxruntime-gpu (NVIDIA/CUDA) or onnxruntime-directml (Windows), "
            "make sure drivers are installed, or switch back to CPU."
        )
    return True, None


# ══════════════════════════════════════════════════════════════════════════════
# Model download / session management
# ══════════════════════════════════════════════════════════════════════════════

def _find_bundled_model():
    """If the `silero-vad` pip package is installed, use its own bundled
    ONNX file directly — no network download needed, and it can't go stale
    the way a hardcoded GitHub URL can. Returns None if not installed or the
    expected file isn't where recent versions put it."""
    try:
        import silero_vad as _sv_pkg
    except ImportError:
        return None

    pkg_dir = os.path.dirname(_sv_pkg.__file__)
    for candidate in (
        os.path.join(pkg_dir, "data", "silero_vad.onnx"),
        os.path.join(pkg_dir, "files", "silero_vad.onnx"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _ensure_model(model_path=None):
    if model_path:
        if os.path.exists(model_path):
            return model_path
        raise SileroVADError(f"SILERO_MODEL_PATH is set but the file doesn't exist: {model_path}")

    if os.path.exists(MODEL_PATH):
        return MODEL_PATH

    bundled = _find_bundled_model()
    if bundled:
        return bundled

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    last_err = None
    for url in MODEL_URLS:
        tmp = MODEL_PATH + ".part"
        try:
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, MODEL_PATH)
            return MODEL_PATH
        except Exception as e:
            last_err = e
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    raise SileroVADError(
        f"Could not download the Silero VAD model (tried {len(MODEL_URLS)} URL(s); "
        f"last error: {last_err}).\n"
        "Easiest fix: pip install silero-vad  (ships the model file locally — "
        "no download needed, and it won't break again if the repo reorganizes).\n"
        "Or download it manually from "
        "https://github.com/snakers4/silero-vad/tree/master/src/silero_vad/data "
        f"and place it at:\n  {MODEL_PATH}"
    )


def _providers_for(device):
    if device == "gpu":
        providers = available_providers()
        ordered = [p for p in GPU_PROVIDERS if p in providers]
        if not ordered:
            raise SileroVADError(
                "No GPU execution provider available. Install onnxruntime-gpu "
                "(or onnxruntime-directml on Windows) with matching drivers, "
                "or switch this run back to CPU."
            )
        ordered.append("CPUExecutionProvider")  # fallback for any op the GPU EP doesn't cover
        return ordered
    return ["CPUExecutionProvider"]


def _get_session(device="cpu", model_path=None):
    ok, err = check_dependencies(device)
    if not ok:
        raise SileroVADError(err)

    key = (device, model_path)
    if key in _session_cache:
        return _session_cache[key]

    import onnxruntime as ort

    path = _ensure_model(model_path)
    so = ort.SessionOptions()
    so.log_severity_level = 3  # quiet — we surface our own errors/messages
    session = ort.InferenceSession(path, sess_options=so, providers=_providers_for(device))
    _session_cache[key] = session
    return session


def warm_up(device="cpu", model_path=None):
    """Load the model / init the ORT session ahead of time (e.g. from a
    'Preload Silero VAD' debug action) so the first real run isn't slower
    than the rest just because of a one-time download + session init."""
    _get_session(device, model_path)


# ══════════════════════════════════════════════════════════════════════════════
# Audio decode (reuses the same ffmpeg-decode trick as game_audio.py)
# ══════════════════════════════════════════════════════════════════════════════

def _decode_to_float32(video_path, sr=SAMPLE_RATE):
    import numpy as np

    if shutil.which("ffmpeg") is None:
        raise SileroVADError("ffmpeg not found on PATH.")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = ["ffmpeg", "-y", "-nostdin", "-i", video_path, "-ac", "1", "-ar", str(sr), tmp.name]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        with wave.open(tmp.name, "rb") as w:
            raw = w.readframes(w.getnframes())
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

    audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    return audio


# ══════════════════════════════════════════════════════════════════════════════
# Inference
# ══════════════════════════════════════════════════════════════════════════════

def _init_state(input_names, dtype):
    """Silero's public ONNX export has shipped with two state layouts over
    time: a single combined `state` tensor (recent exports) or separate
    `h`/`c` LSTM states (older exports). Support both."""
    if "state" in input_names:
        return {"state": dtype((2, 1, 128))}
    return {"h": dtype((2, 1, 64)), "c": dtype((2, 1, 64))}


def _run_frame(session, input_names, chunk, sr, state):
    import numpy as np

    feeds = {"input": chunk[None, :], "sr": np.array(sr, dtype="int64")}
    feeds.update(state)
    outputs = session.run(None, feeds)

    prob = float(outputs[0].squeeze())
    if "state" in input_names:
        new_state = {"state": outputs[1]}
    else:
        new_state = {"h": outputs[1], "c": outputs[2]}
    return prob, new_state


def detect_speech_segments(
    video_path,
    threshold=0.5,
    min_speech_ms=250,
    min_silence_ms=300,
    device="cpu",
    model_path=None,
    on_pct=None,
    cancel_event=None,
):
    """
    Runs Silero VAD over the whole audio track and returns raw speech spans
    (no start/end padding applied — same shape as editor_core's silence
    detection output, so the caller pads/merges them the same way):

        [{"start": float, "end": float}, ...]

    Raises SileroVADError for missing deps / no GPU / model download issues,
    and editor_core.OperationCancelled if cancel_event fires mid-run.
    """
    import numpy as np

    session = _get_session(device, model_path)
    input_names = {i.name for i in session.get_inputs()}

    audio = _decode_to_float32(video_path)
    n_chunks = len(audio) // _WINDOW
    if n_chunks == 0:
        return []

    state = _init_state(input_names, lambda shape: np.zeros(shape, dtype="float32"))

    probs = []
    for i in range(n_chunks):
        if cancel_event is not None and cancel_event.is_set():
            from .editor_core import OperationCancelled
            raise OperationCancelled("Cancelled by user.")

        chunk = audio[i * _WINDOW:(i + 1) * _WINDOW]
        prob, state = _run_frame(session, input_names, chunk, SAMPLE_RATE, state)
        probs.append(prob)

        if on_pct:
            on_pct(min(99.0, (i + 1) / n_chunks * 100))

    hop_s = _WINDOW / SAMPLE_RATE
    is_speech = [p >= threshold for p in probs]

    # collapse the per-frame flags into raw (start, end) spans
    raw_spans = []
    start = None
    for i, speaking in enumerate(is_speech):
        t = i * hop_s
        if speaking and start is None:
            start = t
        elif not speaking and start is not None:
            raw_spans.append((start, t))
            start = None
    if start is not None:
        raw_spans.append((start, n_chunks * hop_s))

    # drop speech blips shorter than min_speech_ms
    min_speech_s = min_speech_ms / 1000.0
    spans = [s for s in raw_spans if s[1] - s[0] >= min_speech_s]

    # bridge silence gaps shorter than min_silence_ms (keeps mid-sentence
    # pauses from getting chopped into lots of tiny separate segments)
    min_silence_s = min_silence_ms / 1000.0
    merged = []
    for s in spans:
        if merged and s[0] - merged[-1][1] < min_silence_s:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(s)

    return [{"start": s, "end": e} for s, e in merged]
