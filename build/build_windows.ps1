# build_windows.ps1 — builds the .exe and the installer in one go.
#   powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Native programs do not throw on nonzero exit codes in Windows PowerShell.
function Invoke-Checked {
  param([string]$Command, [string[]]$Arguments)
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE). Build stopped." }
}
if ($env:OS -ne 'Windows_NT') { throw 'Run this script on Windows 10/11 x64.' }
# One version for the app, the engine and the setup: kryonyx\__init__.py.
$versionMatch = Select-String -Path (Join-Path $root 'kryonyx\__init__.py') -Pattern '__version__\s*=\s*"([0-9][0-9.]*)"' | Select-Object -First 1
if (-not $versionMatch) { throw 'kryonyx\__init__.py has no numeric __version__.' }
$appVersion = $versionMatch.Matches[0].Groups[1].Value
Write-Host "==> Kryo $appVersion" -ForegroundColor Cyan
$probe = "import sys,struct; assert (3,11)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8; print(sys.executable)"
function Find-Python {
  $candidates = @()
  if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    foreach ($version in @('-3.12','-3.13','-3.11')) {
      try { $found = & py.exe $version -c $probe 2>$null; if ($LASTEXITCODE -eq 0) { return [string]($found | Select-Object -Last 1) } } catch {}
    }
  }
  foreach ($v in @('312','313','311')) { $candidates += "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe"; $candidates += "$env:ProgramFiles\Python$v\python.exe" }
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { $candidates += $cmd.Source }
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      try { $found = & $candidate -c $probe 2>$null; if ($LASTEXITCODE -eq 0) { return [string]($found | Select-Object -Last 1) } } catch {}
    }
  }
  return $null
}
$python = Find-Python
if (-not $python -and (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
  Write-Host '==> Installing Python 3.12 x64' -ForegroundColor Cyan
  Invoke-Checked -Command 'winget.exe' -Arguments @('install','--id','Python.Python.3.12','--exact','--scope','user','--architecture','x64','--silent','--accept-package-agreements','--accept-source-agreements')
  $python = Find-Python
}
if (-not $python) { throw 'Install Python 3.12 x64 from python.org (or winget install Python.Python.3.12), reopen PowerShell and retry.' }
Write-Host "==> Python: $python" -ForegroundColor Cyan
if (-not (Test-Path '.venv\Scripts\python.exe')) { Invoke-Checked -Command $python -Arguments @('-m','venv','.venv') }
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
Invoke-Checked -Command $venvPython -Arguments @('-c',$probe)
Invoke-Checked -Command $venvPython -Arguments @('-m','pip','install','--no-cache-dir','--upgrade','pip')
Invoke-Checked -Command $venvPython -Arguments @('-m','pip','install','--no-cache-dir','-r','requirements-build.txt')
Invoke-Checked -Command $venvPython -Arguments @('-m','unittest','discover','-s','tests','-p','test_custom_avatars_v13.py')

Write-Host '==> Fresh yt-dlp for the offline install' -ForegroundColor Cyan
$vendorDir = Join-Path $root 'build\vendor'
$ytDlp = Join-Path $vendorDir 'yt-dlp.exe'
$ytDlpTmp = Join-Path $vendorDir 'yt-dlp.download.exe'
New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
$downloaded = $false
foreach ($url in @(
    'https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe',
    'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe')) {
  try {
    Remove-Item -Force $ytDlpTmp -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $ytDlpTmp
    & $ytDlpTmp --version | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "yt-dlp exited with code $LASTEXITCODE" }
    Move-Item -Force $ytDlpTmp $ytDlp
    $downloaded = $true
    break
  } catch {
    Write-Warning "Could not download yt-dlp from $url`: $($_.Exception.Message)"
  }
}
if (-not $downloaded -and -not (Test-Path $ytDlp)) {
  throw 'Could not get yt-dlp.exe. Check DNS / access to github.com and run the build again.'
}
Write-Host "    Bundled into the installer: $ytDlp" -ForegroundColor DarkGray

Write-Host '==> Licences of the actual build dependencies' -ForegroundColor Cyan
Invoke-Checked -Command $venvPython -Arguments @('tools\collect_licenses.py')

Write-Host '==> PyInstaller' -ForegroundColor Cyan
Remove-Item -Recurse -Force dist, build\work -ErrorAction SilentlyContinue
Invoke-Checked -Command $venvPython -Arguments @('-m','PyInstaller','--noconfirm','--clean','--distpath','dist','--workpath','build\work','build\KryonyxMusic.spec')

Write-Host '==> Installer (Inno Setup)' -ForegroundColor Cyan
# Inno Setup may be installed in Program Files or in the user profile
# (winget --scope user), so look in all usual places, the registry and PATH.
$isccCandidates = @(
  $env:ISCC,
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "$env:APPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($key in @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1')) {
  $loc = (Get-ItemProperty -Path $key -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
  if ($loc) { $isccCandidates += (Join-Path $loc 'ISCC.exe') }
}
$fromPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if ($fromPath) { $isccCandidates += $fromPath }

$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $iscc -and (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
  Write-Host '==> Installing Inno Setup 6' -ForegroundColor Cyan
  & winget.exe install --id JRSoftware.InnoSetup --exact --silent `
      --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -eq 0) {
    $iscc = @(
      "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
      "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
      "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  }
}
if (-not $iscc) {
  Write-Warning 'Inno Setup 6 was not found and could not be installed automatically.'
  Write-Warning 'Install it with: winget install JRSoftware.InnoSetup'
  Write-Warning 'Or set the path: $env:ISCC="C:\path\to\ISCC.exe"'
  if ($env:ISCC -and (Test-Path $env:ISCC)) { $iscc = $env:ISCC } else { exit 1 }
}
Write-Host "    ISCC: $iscc" -ForegroundColor DarkGray

$exe = Join-Path $root 'dist\Kryo\Kryo.exe'
if (-not (Test-Path $exe)) {
  Write-Warning "PyInstaller did not create $exe, so there is nothing to package."
  exit 1
}

& $iscc "/DAppVersion=$appVersion" (Join-Path $root 'build\installer.iss')
if ($LASTEXITCODE -ne 0) { Write-Warning "ISCC exited with code $LASTEXITCODE"; exit $LASTEXITCODE }
$engine = "dist\Kryo-$appVersion-engine.exe"
if (-not (Test-Path $engine)) { throw "ISCC did not create $engine." }

# Payload manifest for the wizard: real progress (file count) and the
# free-space check (bytes). Mirrors the [Files] section of installer.iss.
Write-Host '==> Payload manifest' -ForegroundColor Cyan
$payloadFiles = @(Get-ChildItem -Path 'dist\Kryo' -Recurse -File) +
  @(Get-ChildItem -Path 'licenses' -Recurse -File) +
  @(Get-Item -Path 'build\icon.ico', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'PRIVACY.md', 'TERMS.md', 'ARTWORK_RIGHTS.md')
$payloadBytes = [int64](($payloadFiles | Measure-Object -Property Length -Sum).Sum)
$payload = [ordered]@{ version = $appVersion; files = $payloadFiles.Count; bytes = $payloadBytes }
$payload | ConvertTo-Json | Set-Content -Encoding UTF8 -Path 'build\payload.json'
Write-Host "    $($payloadFiles.Count) files, $([math]::Round($payloadBytes / 1MB)) MB" -ForegroundColor DarkGray

# Package the custom Plum Wizard around the Inno native installation engine.
$setupName = "Kryo-$appVersion-setup"
& $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --name $setupName --icon build\icon.ico --add-data "installer\wizard.html;installer" --add-data "build\payload.json;installer" --add-data "LICENSE;." --add-data "TERMS.md;." --add-data "PRIVACY.md;." --add-data "THIRD_PARTY_NOTICES.md;." --add-data "$engine;dist" installer\bootstrap.py
if ($LASTEXITCODE -ne 0) { throw 'Custom installer build failed.' }
if (-not (Test-Path "dist\$setupName.exe")) { throw 'Installer output is missing.' }
Write-Host "==> Done: dist\Kryo\Kryo.exe + dist\$setupName.exe" -ForegroundColor Green

# Explorer caches icons: if the exe still shows an old logo, reset the cache
if (Get-Command ie4uinit.exe -ErrorAction SilentlyContinue) { & ie4uinit.exe -show 2>$null }
Write-Host '   (icon cache refreshed; if needed: ie4uinit.exe -ClearIconCache)' -ForegroundColor DarkGray
