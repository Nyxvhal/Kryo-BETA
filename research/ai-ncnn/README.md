# NCNN + Vulkan research (v73)

Prototypes behind `docs/AI_NCNN_MIGRATION_PLAN.md`. **Not used by the player** — nothing here is
imported by `kryonyx/`. Standard library only (Python 3.10+), plus `ffmpeg`/`ffprobe` on PATH for
`pipeline_demo.py`.

| File | What it does |
|---|---|
| `vulkan_probe.py` | Vulkan loader + GPU list through ctypes, one JSON line with a verdict (`ok`, `software`, `no-device`, `no-vulkan`). |
| `zip_range.py` | Lists a remote ZIP and fetches single members with HTTP Range (CRC-32, size, SHA-256 checked). |
| `pipeline_demo.py` | 64×64 self-test of both engines; clip: frames → Real-ESRGAN ×2 → RIFE ×2 fps → H.264 + original audio. |
| `manifest.draft.json` | Measured sizes and SHA-256 of every file the plan would download (Windows/Linux; macOS sizes only). |

## Phase 1: measuring on a Windows PC (PowerShell, in this folder)

```powershell
py vulkan_probe.py
$E = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
$R = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip"
$P = "rife-ncnn-vulkan-20221029-windows"
py zip_range.py get $E esr realesrgan-ncnn-vulkan.exe vcomp140.dll models/realesr-animevideov3-x2.param models/realesr-animevideov3-x2.bin
py zip_range.py get $R rife "$P/rife-ncnn-vulkan.exe" "$P/vcomp140.dll" "$P/rife-v4.6/flownet.param" "$P/rife-v4.6/flownet.bin"
py pipeline_demo.py selftest --esr esr --rife rife
py pipeline_demo.py clip --esr esr --rife rife --src some-720p-clip.mp4 --out result.mp4
```

The `clip` output reports frames per second for each step; those numbers decide the defaults
(scale, tile size, source height) in phase 3.

Tests: `python -m unittest tests.test_ai_ncnn_research_v73` (from the repository root).
