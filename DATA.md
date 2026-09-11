# Data and media not in this repository

Files over 4 MB, images over 1.5 MB, media, model weights, CAD and environment folders are excluded to keep the repository small. This lists them by directory so nothing is silently missing.

## Sources

- **NYC building footprints and heights along the High Line corridor** — NYC Open Data via the Socrata API; deterministic, seeded at 42
  Re-fetched 2026-08-15 after a silent partial API response had dropped 1,907 buildings. The SVF comparison read 0.808 before that repair and 0.978 after — quote only the post-repair figure.

## Excluded, by directory

| Directory | Files | Size | Why |
|---|---|---|---|
| `exports/blender` | 5 | 406.3 MB | over 4 MB |
| `exports/blender` | 7 | 104.7 MB | image over 1.5 MB |
| `ComputerVision` | 11 | 72.0 MB | image over 1.5 MB |
| `exports` | 13 | 63.4 MB | image over 1.5 MB |
| `ComputerVision` | 1 | 26.5 MB | over 4 MB |
| `ComputerVision` | 1 | 12.2 MB | binary, media or heavy data type |
| `exports/plates` | 3 | 8.3 MB | image over 1.5 MB |
| `blender` | 4 | 5.8 MB | binary, media or heavy data type |
| `ComputerVision/outputs` | 1 | 4.2 MB | image over 1.5 MB |
| `boards` | 2 | 3.3 MB | image over 1.5 MB |
| `(root)` | 1 | 2.0 MB | image over 1.5 MB |
| `boards/captures/browser` | 1 | 1.7 MB | image over 1.5 MB |
| `exports` | 1 | 0.6 MB | binary, media or heavy data type |
| `scripts/__pycache__` | 10 | 0.2 MB | environment or cache |
| `blender/__pycache__` | 2 | 0.1 MB | environment or cache |
| `houdini/__pycache__` | 2 | 0.1 MB | environment or cache |
| `(root)` | 2 | 0.1 MB | internal notes or environment file |
| `.claude` | 1 | 0.0 MB | environment or cache |
| `data/weather` | 2 | 0.0 MB | binary, media or heavy data type |

The portfolio site serves the plates and video for this project: https://sriyathotakura.com/#streetscape-biophilia
