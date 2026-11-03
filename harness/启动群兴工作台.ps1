$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$electronPath = 'D:/qx-contract-workbench-20261102/desktop/node_modules/electron/dist/electron.exe'
$runtimePath = Join-Path $projectRoot '.local/runtime.json'
$localPath = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Path $localPath -Force | Out-Null

function Test-WorkbenchReady {
    if (-not (Test-Path -LiteralPath $runtimePath)) { return $false }
    try {
        $runtimeState = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
        $runningHost = Get-Process -Id $runtimeState.hostPid -ErrorAction Stop
        if ($runningHost.ProcessName -ne 'node') { return $false }
        $health = Invoke-WebRequest -Uri 'http://127.0.0.1:3080/qx-wechat/state' -TimeoutSec 2 -UseBasicParsing
        return $health.StatusCode -eq 200
    } catch { return $false }
}

if (-not (Test-WorkbenchReady)) {
    Start-Process -FilePath $electronPath -ArgumentList (Join-Path $projectRoot 'scripts/start-host.cjs') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $localPath 'launcher.log') -RedirectStandardError (Join-Path $localPath 'launcher-error.log')
    $readyDeadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not (Test-WorkbenchReady)) {
        if ([DateTime]::UtcNow -gt $readyDeadline) { throw '工作台启动未完成，请查看 .local/host.log。原有工作台和材料未改动。' }
        Start-Sleep -Milliseconds 500
    }
}
Start-Process -FilePath $electronPath -ArgumentList (Join-Path $projectRoot 'desktop/main.cjs') -WorkingDirectory $projectRoot
