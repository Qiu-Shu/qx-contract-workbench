$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$python=Join-Path $repo '.venv/Scripts/python.exe'
$priorPythonPath=$env:PYTHONPATH
$startedAt=(Get-Date).ToString('o')
Push-Location $repo
try {
  $env:PYTHONPATH=Join-Path $repo '.local/desktop-tools/python-build'
  & $python (Join-Path $PSScriptRoot 'frozen_source_snapshot.py') 'frozen-verified-source-before.json'
  if($LASTEXITCODE -ne 0){throw 'Source snapshot failed'}
  $arguments=@('-m','PyInstaller','--noconfirm','--distpath',(Join-Path $PSScriptRoot 'frozen-backend-verified'),
    '--workpath',(Join-Path $PSScriptRoot 'build-backend-verified'),(Join-Path $repo 'desktop/backend.spec'))
  & $python @arguments *> (Join-Path $PSScriptRoot 'frozen-build-verified.log')
  $buildExit=$LASTEXITCODE
  [pscustomobject]@{started_at=$startedAt;finished_at=(Get-Date).ToString('o');executable=$python;arguments=$arguments;
    exit_code=$buildExit;pythonpath=$env:PYTHONPATH;log='frozen-build-verified.log'} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'frozen-build-verified-command.json') -Encoding utf8
  if($buildExit -ne 0){throw 'Backend build failed'}
  & $python (Join-Path $PSScriptRoot 'frozen_source_snapshot.py') 'frozen-verified-source-after.json'
  if($LASTEXITCODE -ne 0){throw 'Source snapshot failed'}
  $before=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'frozen-verified-source-before.json') -Raw | ConvertFrom-Json
  $after=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'frozen-verified-source-after.json') -Raw | ConvertFrom-Json
  if($before.source_sha256 -ne $after.source_sha256){throw 'Build inputs changed'}
} finally {
  $env:PYTHONPATH=$priorPythonPath
  Pop-Location
}
