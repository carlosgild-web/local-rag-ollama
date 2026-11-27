# Pass 2 of the README video (decision 0043): fresh demo data, then the app replaying pass 1.
#
#   powershell -File video\replay.ps1            pass 1's answers (video\out\pass1)
#   powershell -File video\replay.ps1 -Dry       the storyboard's scripted answers (dry takes)
#   powershell -File video\replay.ps1 -Stop      stop the replay server
#
# Steps: `start.cmd video` (empties data-video\, loads the demo company and its golden set),
# stop that server, unload qwen2.5:3b from Ollama (pass 2 never calls it; the browser and the
# recorder get the memory), then start replay_server.py on the same data-video\ and port 8010
# with the settings start.cmd video uses. bge-m3 stays: retrieval and indexing are live.
param([switch]$Dry, [switch]$Stop, [string]$Pass1 = "video\out\pass1")

$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent
$DataDir = Join-Path $Root "data-video"
$PidFile = Join-Path $DataDir "replay.pid"
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$Port = 8010

function Stop-Replay {
    if (Test-Path $PidFile) {
        & taskkill.exe /PID (Get-Content $PidFile) /T /F *> $null
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Host "  [ok] replay server stopped"
    }
}

Stop-Replay
if ($Stop) { exit 0 }

& (Join-Path $Root "start.cmd") video
if ($LASTEXITCODE -ne 0) { Write-Host "[x] start.cmd video failed"; exit 1 }
& (Join-Path $Root "start.cmd") video stop | Out-Null
& ollama stop qwen2.5:3b 2>$null | Out-Null

$env:DATA_DIR = $DataDir
$env:CHAT_MODEL = "qwen2.5:3b"
$env:EMBEDDING_MODEL = "bge-m3"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$mode = if ($Dry) { "--dry" } else { "--pass1 `"$(Join-Path $Root $Pass1)`"" }
$log = Join-Path $DataDir "replay.log"
$serve = "`"$Python`" `"$(Join-Path $PSScriptRoot 'replay_server.py')`" $mode --port $Port"
$proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$serve > `"$log`" 2>&1`"" `
    -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden -PassThru
Set-Content -Path $PidFile -Value $proc.Id -Encoding ASCII
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { $h = $null }
    if ($h) {
        Write-Host "  [ok] replay server on port $Port ($(if ($Dry) { 'dry: scripted answers' } else { "pass 1: $Pass1" })); log: data-video\replay.log"
        exit 0
    }
}
Write-Host "[x] the replay server didn't answer; see data-video\replay.log"
Get-Content $log -Tail 20
exit 1
