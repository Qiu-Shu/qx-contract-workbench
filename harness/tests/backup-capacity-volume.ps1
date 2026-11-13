param(
  [Parameter(Mandatory=$true)][string]$Node,
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$Restic,
  [string]$Evidence='D:/CodexChecks/AI-Shixiong-resilience-20261113/root'
)
$ErrorActionPreference='Stop'
$base=[IO.Path]::GetFullPath($Evidence)
if (-not $base.StartsWith('D:\CodexChecks\AI-Shixiong-resilience-20261113\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Test evidence must be inside the dedicated D: directory' }
foreach ($program in @($Node,$Python,$Restic)) { if (-not [IO.Path]::IsPathFullyQualified($program) -or -not (Test-Path -LiteralPath $program -PathType Leaf)) { throw 'Missing absolute runtime path' } }
New-Item -ItemType Directory -Path $base -Force | Out-Null
$id=[Guid]::NewGuid().ToString()
$run=Join-Path $base ('capacity-'+$id)
New-Item -ItemType Directory -Path $run | Out-Null
$image=Join-Path $run 'bounded-test-volume.vhdx'
if (Test-Path -LiteralPath $image) { throw 'Never overwrite an existing image' }
$letter=@('R','S','T','U','V','W','X','Y','Z') | Where-Object { -not (Get-PSDrive -Name $_ -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath ($_+':\')) } | Select-Object -First 1
if (-not $letter) { throw 'No unused test drive letter' }
$commands=Join-Path $run 'create-image.txt'
[IO.File]::WriteAllLines($commands,@("create vdisk file=`"$image`" maximum=512 type=expandable",'exit'),[Text.Encoding]::ASCII)
$mounted=$false
$testExit=$null
try {
  & "$env:SystemRoot/System32/diskpart.exe" /s $commands *> (Join-Path $run 'create-image.log')
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $image)) { throw 'Creating the bounded test image failed' }
  Mount-DiskImage -ImagePath $image -NoDriveLetter | Out-Null
  $mounted=$true
  $diskImage=Get-DiskImage -ImagePath $image
  $disk=$diskImage | Get-Disk
  if (-not $diskImage.Attached -or [IO.Path]::GetFullPath($diskImage.ImagePath) -ne $image -or $disk.IsBoot -or $disk.IsSystem -or $disk.Size -ne 512MB -or $disk.PartitionStyle -ne 'RAW') { throw 'Refusing to initialize an unverified disk' }
  # Only the new image-derived disk object can reach destructive volume operations.
  $disk | Initialize-Disk -PartitionStyle GPT
  $partition=New-Partition -DiskNumber $disk.Number -UseMaximumSize -DriveLetter $letter
  $confirmed=Get-DiskImage -ImagePath $image | Get-Disk
  if ($confirmed.Number -ne $partition.DiskNumber -or $confirmed.IsSystem -or $confirmed.IsBoot) { throw 'Test disk identity changed' }
  $partition | Format-Volume -FileSystem NTFS -NewFileSystemLabel 'QX_Resilience_Test' -Confirm:$false | Out-Null
  $volumeRoot=$letter+':\'
  $marker=@{schema=1;syntheticOnly=$true;testId=$id;image=$image;diskNumber=$disk.Number;evidence=$run}
  [IO.File]::WriteAllText((Join-Path $volumeRoot '.qx-capacity-test.json'),($marker|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
  $env:QX_BACKUP_CAPACITY='1'
  $env:QX_BACKUP_TEST_VOLUME=$volumeRoot
  $env:QX_BACKUP_CAPACITY_EVIDENCE=$run
  $env:QX_TEST_PYTHON=$Python
  $env:QX_TEST_RESTIC=$Restic
  $env:TEMP=Join-Path $run 'temp'
  $env:TMP=$env:TEMP
  New-Item -ItemType Directory -Path $env:TEMP | Out-Null
  $env:DEEPSEEK_API_KEY=''
  $env:OPENAI_API_KEY=''
  $env:ANTHROPIC_API_KEY=''
  & $Node --test (Join-Path $PSScriptRoot '../desktop/backup-capacity.test.cjs') *> (Join-Path $run 'test.log')
  $testExit=$LASTEXITCODE
} finally {
  if ($mounted) {
    $current=Get-DiskImage -ImagePath $image
    if ($current.Attached -and [IO.Path]::GetFullPath($current.ImagePath) -eq $image) { Dismount-DiskImage -ImagePath $image | Out-Null }
  }
  $result=@{testExitCode=$testExit;image=$image;imageDetached= -not (Get-DiskImage -ImagePath $image -ErrorAction SilentlyContinue).Attached;run=$run;finishedAt=[DateTime]::UtcNow.ToString('o')}
  [IO.File]::WriteAllText((Join-Path $run 'volume-result.json'),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
  $result|ConvertTo-Json
}
if ($null -eq $testExit) { exit 1 }
exit $testExit
