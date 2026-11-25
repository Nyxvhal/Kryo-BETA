@echo off
rem Starts Kryo from source on Windows.
rem Dependencies are installed into the user folder: no admin rights needed.
setlocal
cd /d "%~dp0"

set PY=
for %%C in (py python) do (
  if not defined PY (
    %%C -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set PY=%%C
  )
)

if not defined PY (
  echo Python 3.10 or newer is required: https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% run.py %*
if errorlevel 1 pause
