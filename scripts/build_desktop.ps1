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
        # Build from a clean Electron copy so the packager never needs bulk deletion
        # merely to remove unwanted locales. The fixed npm distribution stays intact.
        $electronSource = Join-Path $repo 'desktop/node_modules/electron/dist'
        $electronDist = Join-Path $repo 'build/electron-44.8.0-ui'
        New-Item -ItemType Directory -Path (Join-Path $electronDist 'locales') -Force | Out-Null
        robocopy $electronSource $electronDist /E /XD (Join-Path $electronSource 'locales') /NFL /NDL /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw 'Electron runtime copy failed.' }
        foreach ($locale in @('zh-CN.pak', 'zh-TW.pak', 'en-US.pak')) {
            Copy-Item -LiteralPath (Join-Path $electronSource "locales/$locale") -Destination (Join-Path $electronDist "locales/$locale") -Force
        }
        Push-Location (Join-Path $repo 'desktop')
        try {
            & node $npm run pack
            if ($LASTEXITCODE -ne 0) { throw 'Windows installer failed.' }
        } finally { Pop-Location }
    }
} finally { $env:PYTHONPATH = $oldPythonPath; $env:PATH = $oldPath; Pop-Location }
