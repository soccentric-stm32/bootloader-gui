# build-windows.ps1 - PyInstaller one-folder package for Windows
#
#   $env:PYTHON = "C:\path\to\python.exe"; packaging\build-windows.ps1
#
# Writes dist\BOOT Flasher\ (windowed, no console) and zips it to
# dist\BOOT-Flasher-windows.zip.  There is no installer: copy the folder
# where you want it and run BOOT Flasher.exe.  Signing is left to the
# release owner.
#
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Python = $env:PYTHON
if (-not $Python) {
    if (Test-Path ".venv\Scripts\python.exe") {
        $Python = ".venv\Scripts\python.exe"
    } else {
        $Python = "python"
    }
}

& $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing; install it with: $Python -m pip install pyinstaller"
}

& $Python packaging/make_icons.py
if ($LASTEXITCODE -ne 0) { throw "packaging/make_icons.py failed" }
& $Python -m PyInstaller packaging/boot-flasher.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$App = "dist\BOOT Flasher"
if (-not (Test-Path "$App\BOOT Flasher.exe")) {
    throw "PyInstaller did not produce $App\BOOT Flasher.exe"
}

Compress-Archive -Path $App -DestinationPath "dist\BOOT-Flasher-windows.zip" -Force
Write-Host "Windows package: dist\BOOT Flasher and dist\BOOT-Flasher-windows.zip"
