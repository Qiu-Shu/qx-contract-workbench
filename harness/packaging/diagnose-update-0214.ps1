param([switch]$SkipNetwork, [string]$CacheRoot, [string]$ReportPath)
# Read-only diagnostics for official 0.2.14 -> 0.2.15; no installation or cache changes.
$ErrorActionPreference = 'Stop'
if (-not $CacheRoot) { $CacheRoot = Join-Path $env:LOCALAPPDATA 'qunxing-harness-desktop-updater' }
if (-not $ReportPath) { $ReportPath = Join-Path $PSScriptRoot 'update-check-report.json' }
$report = [ordered]@{
    timeUtc = [DateTime]::UtcNow.ToString('o')
    scope = 'Official 0.2.14 to 0.2.15; read-only cache and one public HTTP range'
    cacheExists = $false
    cacheBytes = $null
    cacheMatchesOfficial0214 = $null
    cacheReadSeconds = $null
    freeBytes = $null
    reconstructionBytes = 590664446
    enoughForOneNewInstaller = $null
    cacheError = $null
    network = [ordered]@{ skipped = [bool]$SkipNetwork; status = $null; rangeCorrect = $false; bytes = 0; matchesPublishedSegment = $false; seconds = $null; error = $null }
}
try {
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($CacheRoot)))
    $report.freeBytes = $drive.AvailableFreeSpace
    $report.enoughForOneNewInstaller = $drive.AvailableFreeSpace -ge $report.reconstructionBytes
    $cache = Join-Path $CacheRoot 'installer.exe'
    $report.cacheExists = Test-Path -LiteralPath $cache -PathType Leaf
    if ($report.cacheExists) {
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $report.cacheBytes = (Get-Item -LiteralPath $cache).Length
        $digest = (Get-FileHash -LiteralPath $cache -Algorithm SHA256).Hash
        $report.cacheReadSeconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
        $report.cacheMatchesOfficial0214 = $digest -eq 'f0c4b26ce66720a5da5ea2b89a33e960febfff0a4de31a503974dd2ac1d4d363'
    }
} catch { $report.cacheError = $_.Exception.GetType().Name }
if (-not $SkipNetwork) {
    $response = $null; $stream = $null; $memory = $null; $hasher = $null
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $request = [Net.HttpWebRequest]::Create('https://github.com/Qiu-Shu/qx-contract-workbench/releases/download/v0.2.15/Qunxing-Workbench-0.2.15-Setup.exe')
        $request.Timeout = 20000; $request.ReadWriteTimeout = 15000
        $request.MaximumAutomaticRedirections = 10
        $request.AddRange(589639652, 590187894)
        $response = $request.GetResponse()
        $report.network.status = [int]$response.StatusCode
        $report.network.rangeCorrect = $response.Headers['Content-Range'] -eq 'bytes 589639652-590187894/590664446'
        if ($report.network.status -eq 206 -and $report.network.rangeCorrect) {
            $stream = $response.GetResponseStream(); $memory = [IO.MemoryStream]::new()
            $buffer = New-Object byte[] 32768
            while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                if ($memory.Length + $count -gt 548243) { throw [IO.InvalidDataException]::new('Unexpected range size') }
                $memory.Write($buffer, 0, $count)
            }
            $report.network.bytes = $memory.Length
            $hasher = [Security.Cryptography.SHA256]::Create()
            $digest = [BitConverter]::ToString($hasher.ComputeHash($memory.ToArray())).Replace('-', '').ToLowerInvariant()
            $report.network.matchesPublishedSegment = $digest -eq '7ff9cf1b9f905c08c1a093a18c449d0260fe85b9700b5218382dad4fab3127f9'
        }
    } catch {
        $failure = $_.Exception.GetBaseException()
        $report.network.error = $failure.GetType().Name
        if ($failure -is [Net.WebException]) {
            $report.network.error = $failure.Status.ToString()
            if ($failure.Response) { $report.network.status = [int]$failure.Response.StatusCode; $failure.Response.Close() }
        }
    } finally {
        if ($hasher) { $hasher.Dispose() }; if ($memory) { $memory.Dispose() }
        if ($stream) { $stream.Dispose() }; if ($response) { $response.Close() }
        $report.network.seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
    }
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Output ('Report saved: ' + $ReportPath)
Write-Output 'No application, cache, account or case files were changed. This network test uses Windows proxy settings, not the Electron network engine.'
