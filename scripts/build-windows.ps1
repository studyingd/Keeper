# Build a portable Windows distribution of Keeper.
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# keeper-askpass.exe is handed the SSH password by OpenSSH, so refuse to ship a
# binary that is not the recorded build of scripts/keeper_askpass.cs. Rebuild it
# on Windows with the .NET Framework compiler and refresh the recorded digest:
#   csc /nologo /optimize /target:exe /out:keeper-askpass.exe keeper_askpass.cs
#   certutil -hashfile keeper-askpass.exe SHA256
$helper = "src\password_manager\assets\keeper-askpass.exe"
$recorded = (Get-Content "scripts\keeper-askpass.sha256" -Raw).Trim() -split "\s+" | Select-Object -First 1
$actual = (Get-FileHash $helper -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $recorded.ToLower()) {
    Write-Error "keeper-askpass.exe does not match scripts\keeper-askpass.sha256 (expected $recorded, got $actual)."
    exit 1
}

# PyInstaller usually lives in the project venv rather than in whatever python
# happens to be first on PATH.
$python = "python"
if (Test-Path "$projectRoot\.venv\Scripts\python.exe") {
    $python = "$projectRoot\.venv\Scripts\python.exe"
}

# The Windows package is described entirely by these flags, but PyInstaller
# still writes a spec file next to them by default - straight over the
# hand-maintained Keeper.spec that the macOS bundle depends on. Redirect it
# into the (already ignored) build directory instead.
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --name Keeper `
    --specpath build\windows `
    --windowed `
    --onedir `
    --icon "$projectRoot\src\password_manager\assets\keeper.ico" `
    --add-data "$projectRoot\src\password_manager\assets;password_manager\assets" `
    --add-data "$projectRoot\src\password_manager\ui\fonts;password_manager\ui\fonts" `
    --add-data "$projectRoot\src\password_manager\qml;password_manager\qml" `
    --paths "$projectRoot\src" `
    --collect-all sqlcipher3 `
    main.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host "Build complete: $projectRoot\dist\Keeper\Keeper.exe"
