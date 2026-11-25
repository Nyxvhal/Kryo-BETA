@echo off
setlocal
rem Kryo - optional AI module (Real-ESRGAN upscaling, RIFE smooth motion).
rem Usage: setup-ai.bat [auto|cpu|cu118|cu126|cu128]   (default: auto)
cd /d "%~dp0"
title Kryo - AI setup
echo.
echo  Kryo: installing the optional AI module
echo  ------------------------------------------------
echo  Needs Python 3.10-3.12 and about 3 GB of disk space (CUDA build).
echo.
where py >nul 2>nul
if errorlevel 1 (set "PY=python") else (set "PY=py -3")
if not exist ".ai-venv\Scripts\python.exe" %PY% -m venv .ai-venv
if errorlevel 1 goto failed
.ai-venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
set "FLAVOR=%~1"
if "%FLAVOR%"=="" set "FLAVOR=auto"
if /I "%FLAVOR%"=="auto" (
  where nvidia-smi >nul 2>nul
  if errorlevel 1 (set "FLAVOR=cpu") else (set "FLAVOR=cu126")
)
echo  PyTorch build: %FLAVOR%
.ai-venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/%FLAVOR%
if errorlevel 1 goto failed
.ai-venv\Scripts\python.exe -m pip install -r requirements-ai.txt
if errorlevel 1 goto failed
.ai-venv\Scripts\python.exe -c "import torch; print(' torch', torch.__version__, '| CUDA:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
echo.
echo  AI module installed. Return to the player and press "Check again".
echo  Models (17-64 MB each) download from the player when first needed.
exit /b 0
:failed
echo.
echo  Installation failed. Install Python 3.10-3.12 from python.org
echo  (tick "Add python.exe to PATH") and run this file again.
echo  Older NVIDIA drivers: setup-ai.bat cu118   No NVIDIA GPU: setup-ai.bat cpu
exit /b 1
