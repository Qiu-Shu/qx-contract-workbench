param([switch]$BackendOnly)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv/Scripts/python.exe'
$buildModules = Join-Path $repo '.local/desktop-tools/python-build'
$npm = Join-Path $repo '.local/desktop-tools/npm/package/bin/npm-cli.js'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $buildModules)) {
    throw 'First provision the fixed project environment and desktop build dependencies; see desktop/README.md.'
}
$oldPythonPath = $env:PYTHONPATH
$oldPath = $env:PATH
Push-Location $repo
try {
    $shim = Join-Path $repo '.local/desktop-tools/bin'
    New-Item -ItemType Directory -Path $shim -Force | Out-Null
    # npm's upstream .cmd assumes a Node distribution layout; use a local shim.
    # Resolve the Unicode repository path at execution time, outside cmd encoding.
    Set-Content -LiteralPath (Join-Path $shim 'npm.cmd') -Encoding ASCII -Value '@node "%~dp0..\npm\package\bin\npm-cli.js" %*'
    $env:PATH = $shim + ';' + $env:PATH
    $env:PYTHONPATH = $buildModules
    & $python -m PyInstaller --noconfirm --distpath (Join-Path $repo 'dist') --workpath (Join-Path $repo 'build/desktop-python') (Join-Path $repo 'desktop/backend.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Python bundle failed.' }
    if (!$BackendOnly) {
        Push-Location (Join-Path $repo 'desktop')
        try {
            & node $npm run pack
            if ($LASTEXITCODE -ne 0) { throw 'Windows installer failed.' }
        } finally { Pop-Location }
    }
} finally { $env:PYTHONPATH = $oldPythonPath; $env:PATH = $oldPath; Pop-Location }
