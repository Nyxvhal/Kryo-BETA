@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
if not exist .translate-venv\Scripts\python.exe %PY% -m venv .translate-venv
if errorlevel 1 goto error
.translate-venv\Scripts\python.exe -m pip install argostranslate==1.11.0 langdetect==1.0.9
if errorlevel 1 goto error
set "SRC=%~1"
set "DST=%~2"
if not defined SRC set "SRC=en"
if not defined DST set "DST=ru"
.translate-venv\Scripts\python.exe tools\setup_translate.py %SRC% %DST%
if errorlevel 1 goto error
echo Offline translator is ready. Restart Kryo.
pause
exit /b 0
:error
echo Setup failed. Check Python and internet connection.
pause
exit /b 1
