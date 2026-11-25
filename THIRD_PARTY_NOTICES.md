# Third-party notices


The project's MIT license does not replace component licenses. This table is a guide, not a substitute for exact-build verification or full upstream notices.

| Component | Upstream license / qualification |
| --- | --- |
| CPython | PSF License and included notices |
| aiohttp, aiohttp-socks | Apache-2.0; transitive packages have separate terms |
| ytmusicapi, pytubefix | MIT |
| pywebview | BSD-3-Clause; WebView2 Runtime is separately licensed |
| Pillow | HPND and bundled codec/library notices |
| imageio-ffmpeg | BSD-2-Clause for the Python wrapper, not a single license for the FFmpeg binary |
| FFmpeg | LGPL/GPL depending on the actual binary configuration and libraries/codecs |
| yt-dlp | Core source: Unlicense; standalone executables may include separately licensed components |
| PyInstaller | GPL-2.0 with bootloader exception; build tool |
| Inno Setup | Upstream terms/modified BSD; build tool |
| Pangolin, Caveat, Roboto | SIL OFL 1.1 according to the supplied font metadata |
| shazamio-core 1.1.x | MIT; local Rust acoustic fingerprint generation |
| Real-ESRGAN (architectures + weights, optional AI module) | BSD-3-Clause (xinntao/Real-ESRGAN); network code adapted from BasicSR, Apache-2.0 |
| RIFE (IFNet architecture + weights, optional AI module) | MIT (hzwer/Practical-RIFE / ECCV2022-RIFE) |
| PyTorch, NumPy (optional AI module, installed by `setup-ai.bat`) | BSD-3-Clause; CUDA wheels include NVIDIA components under NVIDIA terms |

Full font licenses and source URLs are under `licenses/fonts`. Supplied Roboto metadata indicates OFL; an older blanket Apache label was corrected. The recognition core license is in `licenses/shazamio-core-LICENSE.txt`. The project uses an unofficial Shazam fingerprint-discovery endpoint, not an affiliated or guaranteed service; uploaded recognition media remains temporary and local.

`tools/collect_licenses.py` runs after dependencies and yt-dlp are installed. It records real package names/versions, available LICENSE/COPYING/NOTICE/AUTHORS files, package license metadata, actual FFmpeg version/configuration/`-L` output, binary hashes and reference upstream texts. Results are included in the runtime folder/installer. Missing notices are marked `reviewRequired`; build tools listed in the environment do not necessarily ship at runtime.

This source archive does not include the inventory of your future Windows build. Reference texts fetched from upstream master must be matched to released versions. Wrapper licenses do not relicense bundled executables.

Before distributing FFmpeg, establish the exact binary source/configuration and supply required corresponding source, included-library source, build scripts/information and an applicable delivery method. A link to ffmpeg.org, `-L`, or a GPL text alone is insufficient. Review Python, WebView2, yt-dlp.exe and every other shipped component similarly.

Optional karaoke engines and weights are not considered bundled merely because requirement files exist. Check code and model licenses separately. This document grants no rights to third-party music, lyrics, artwork or trademarks.

The optional AI module (v72) is not bundled: `kryonyx/ai_arch.py` contains network definitions adapted from Real-ESRGAN/BasicSR and RIFE so that the published weights load; weights are downloaded on demand over HTTPS from the upstream GitHub/Hugging Face release URLs listed in `kryonyx/ai_models.py`, verified by size and SHA-256, and stored in the user data folder. PyTorch and NumPy are installed by the user into `.ai-venv`. Check upstream licenses again before redistributing weights or a pre-built AI environment.

## Argos Translate (optional offline lyric translation)
Argos Translate is installed separately by the user; models are not bundled in this archive. The library is available under MIT / CC0: https://github.com/argosopentech/argos-translate. Its models and dependencies may have separate terms.

## Offline language detection
`langdetect` 1.0.9 is installed separately for optional offline lyric translation: https://github.com/Mimino666/langdetect (MIT). Its distributed NOTICE also identifies language-detection by Cybozu Labs under Apache-2.0. Review the installed package LICENSE and NOTICE when distributing it.
