# Vellum — Automatic Video Editor

Removes silence, keeps speech. Drop in a video, get a clean cut.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

Python 3.10+ recommended.

## Project structure

```
vellum_tool/
├── main.py                     ← entry point
├── requirements.txt
├── core/
│   ├── app.py                  ← app shell & top bar
│   ├── settings.py             ← config.json persistence
│   └── theme.py                ← Slate / Rose / Forest / Dark themes
├── tool/
│   └── editor_page.py          ← editor UI (file picker, settings, log)
└── video_editor/
    ├── editor_config.py        ← processing defaults
    ├── editor_core.py          ← audio analysis + export pipeline
    └── game_audio.py           ← optional game-event detection (beta)
```

## How it works

1. Extracts audio from the video via MoviePy
2. Uses librosa RMS energy to find speech segments
3. Filters out clips below the volume threshold
4. Merges overlapping segments with padding
5. Re-assembles and exports via MoviePy + libx264

## Settings

| Setting | Default | Effect |
|---|---|---|
| Voice sensitivity | 0.030 | Lower = pick up quieter speech |
| Output mode | Single file | Merge all clips or export separately |
| Game audio (beta) | Off | Flag moments matching a reference sound |

## Themes

Switch via the dropdown in the top bar. Takes effect on next launch.
Available: **Slate** (light), **Rose**, **Forest**, **Dark**.
