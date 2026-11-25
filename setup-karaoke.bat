@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PY=python") else (set "PY=py -3")
if not exist ".karaoke-venv\Scripts\python.exe" %PY% -m venv .karaoke-venv
if errorlevel 1 goto failed
.karaoke-venv\Scripts\python.exe -m pip install --upgrade pip
set "REQ=requirements-karaoke-align.txt"
if /I "%~1"=="light" set "REQ=requirements-karaoke.txt"
if /I "%~1"=="separation" set "REQ=requirements-karaoke-separation.txt"
.karaoke-venv\Scripts\python.exe -m pip install -r "%REQ%"
if errorlevel 1 goto failed
echo Karaoke worker installed. Restart the player.
echo Models download on first generation. CUDA is optional.
exit /b 0
:failed
echo Installation failed. Use Python 3.10-3.12 and see KARAOKE_RU.md.
exit /b 1
