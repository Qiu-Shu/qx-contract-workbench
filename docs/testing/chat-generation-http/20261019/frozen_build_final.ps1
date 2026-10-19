$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $repo '.venv/Scripts/python.exe'
$oldBuildPythonPath = $env:PYTHONPATH
Push-Location $repo
try {
    $env:PYTHONPATH = Join-Path $repo '.local/desktop-tools/python-build'
    & $python (Join-Path $PSScriptRoot 'frozen_source_snapshot.py') 'frozen-final-source-before.json'
    if ($LASTEXITCODE -ne 0) { throw 'Source snapshot failed' }
    & $python -m PyInstaller --noconfirm --distpath (Join-Path $PSScriptRoot 'frozen-backend-boundary-fixed') --workpath (Join-Path $PSScriptRoot 'build-backend-boundary-fixed') (Join-Path $repo 'desktop/backend.spec') *> (Join-Path $PSScriptRoot 'frozen-backend-boundary-fixed-build.log')
    $backendExit = $LASTEXITCODE
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'frozen-backend-boundary-fixed-build.exit') -Value $backendExit
    if ($backendExit -ne 0) { throw 'Backend build failed' }
    & $python -m PyInstaller --noconfirm --distpath (Join-Path $PSScriptRoot 'frozen-http-helper-boundary-fixed') --workpath (Join-Path $PSScriptRoot 'build-http-helper-boundary-fixed') (Join-Path $PSScriptRoot 'native_http_probe.spec') *> (Join-Path $PSScriptRoot 'frozen-http-helper-boundary-fixed-build.log')
    $helperExit = $LASTEXITCODE
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'frozen-http-helper-boundary-fixed-build.exit') -Value $helperExit
    if ($helperExit -ne 0) { throw 'Model helper build failed' }
    & $python (Join-Path $PSScriptRoot 'frozen_source_snapshot.py') 'frozen-final-source-after.json'
    if ($LASTEXITCODE -ne 0) { throw 'Source snapshot failed' }
} finally {
    $env:PYTHONPATH = $oldBuildPythonPath
    Pop-Location
}
