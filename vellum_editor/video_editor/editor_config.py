# editor_config.py — settings for the AI Video Editor

OUTPUT_MODE   = "single"   # "single" or "multiple"
OUTPUT_FOLDER = "videos"

VOLUME_THRESHOLD      = 0.03
MIN_CLIP_LENGTH       = 1.0

SPEECH_PADDING_START  = 0.25   # seconds before speech onset
SPEECH_PADDING_END    = 0.35   # seconds after speech ends

SILENCE_THRESHOLD_MULT = 0.5
MIN_SILENCE_DURATION   = 0.3   # seconds of silence to split a sentence

# ── Game HUD detection (beta) ─────────────────────────────────────────────────
# Visual, not audio: samples two small screen regions you drag out in the UI —
# one over the damage indicator (hit flash/vignette), one over the ammo
# counter — and flags moments where the HUD shows damage taken or a shot fired.
# See game_vision.py for how each region is analyzed.
USE_GAME_VISION       = False
GAME_VISION_FPS       = 4       # HUD samples/sec — higher = more precise timing, slower to run
GAME_DAMAGE_REGION    = None    # (x1,y1,x2,y2) as fractions 0-1 of the frame; set via the UI's region picker
GAME_DAMAGE_THRESHOLD = 0.12    # how much redder/brighter the region must get, above its own baseline, to flag "damage"
GAME_AMMO_REGION      = None    # (x1,y1,x2,y2) as fractions 0-1 of the frame, tightly cropped to the ammo digits
GAME_EVENT_COOLDOWN   = 0.5     # min seconds between two events of the same type (debounce)
GAME_EVENT_PADDING    = 0.4     # seconds of context kept before/after each detected event

# ── Voice-activity-detection backend ─────────────────────────────────────────
# "ffmpeg" — fast, zero extra deps, plain amplitude threshold (silencedetect).
# "silero" — neural VAD via onnxruntime (beta). More accurate with music/game
#            audio or noisy mics in the background, at the cost of one extra
#            dependency. See silero_vad.py for install instructions.
VAD_BACKEND = "ffmpeg"

SILERO_DEVICE         = "cpu"   # "cpu" or "gpu" — GPU needs onnxruntime-gpu/-directml + drivers
SILERO_THRESHOLD      = 0.5     # speech-probability threshold, 0.0-1.0 (higher = stricter)
SILERO_MIN_SPEECH_MS  = 250     # discard speech blips shorter than this
SILERO_MODEL_PATH     = None    # override to use a local .onnx file instead of the cached download
