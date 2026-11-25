# Localization Audit

## Supported Languages (12)

`en` (base), `ru`, `es`, `pt`, `de`, `fr`, `it`, `tr`, `pl`, `uk`, `zh`, `ja`.

- **Russian (`ru`) UI localization:** Preserved in the player (`PACKS.ru`).
- **Installer & documentation:** English-only (`build/installer.iss`, `installer/wizard.html`, `installer/bootstrap.py`, `README.md`, `BUILD.md`, `docs/*.md`).

## Coverage Summary

- **Total unique translation keys:** 3,099 across all 11 non-English packs (`en` uses source strings directly).
- **Missing keys:** 0 (added 158 missing keys + `Updating in background…` in `kryonyx/web/js/i18n-v86.js`, loaded after `i18n-v73.js` in `kryonyx/web/index.html`).
- **Empty values:** 0
- **Placeholder token mismatches (`{name}`, `{n}`, `{size}`, `{done}`, `{total}`, etc.):** 0

## Verification

- Automated check: `node tests/test_i18n_coverage.cjs` → `I18N_COVERAGE_PASS languages=12 keys=3099`.
- Dynamic UI strings (recommendations status, karaoke translation, share, layout studio, AI notices) are covered by `t()` / `tf()` and verified in live browser checks.
