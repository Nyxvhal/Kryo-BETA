@echo off
setlocal
cd /d "%~dp0"
echo Building Kryo and Windows installer...
echo Internet access is required. This can take several minutes.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build\build_windows.ps1"
if errorlevel 1 (
  echo.
  echo Build failed. See the error above. No success is assumed.
  pause
  exit /b 1
)
echo.
echo Build complete. Opening dist.
start "" "%~dp0dist"
pause
