# One-command start for Windows (decision 0013). Run it through start.cmd:
#
#   .\start.cmd             start (asks a few questions the first time)
#   .\start.cmd stop        stop the app (your documents and models are kept)
#   .\start.cmd status      show how it's running and whether it's healthy
#
# Options: --yes (accept every suggestion), --check (look and explain, change
# nothing), --reconfigure (ask again instead of using the saved answers).
# Test-only: --no-host-ollama, --no-docker (pretend they're missing),
# --ollama-start-fails (pretend Ollama won't start).
#
# It never installs anything or falls back to another way without asking, only
# installs from official sources (winget, ollama.com, this repo's GitHub
# Release with a checksum), and the app listens on 127.0.0.1 only. Each run is
# logged to data\start.log. Works in Windows PowerShell 5.1 and PowerShell 7.

# "Continue": in Windows PowerShell 5.1, "Stop" turns any stderr line from docker
# or curl into an exception. Failures are checked by exit code instead.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $Root ".env"
$DataDir = Join-Path $Root "data"
$LogFile = Join-Path $DataDir "start.log"
$Repo = "carlosgild-web/local-rag-ollama"
$OllamaUrl = "http://127.0.0.1:11434"
$EmbeddingModel = "bge-m3"
$ModelSizes = @{ "bge-m3" = "1.2 GB"; "qwen2.5:3b" = "1.9 GB"; "llama3.1" = "4.9 GB" }
$script:Logging = $false
$script:OllamaStartedHere = $false

# --- Arguments ---------------------------------------------------------------

$Command = "start"
$Yes = $false; $CheckOnly = $false; $Reconfigure = $false
$NoHostOllama = $false; $NoDocker = $false; $OllamaStartFails = $false
foreach ($a in $args) {
    switch -Regex ($a) {
        '^(start|stop|status)$' { $Command = $a }
        '^-{1,2}yes$' { $Yes = $true }
        '^-{1,2}check$' { $CheckOnly = $true }
        '^-{1,2}reconfigure$' { $Reconfigure = $true }
        '^-{1,2}no-host-ollama$' { $NoHostOllama = $true }
        '^-{1,2}no-docker$' { $NoDocker = $true }
        '^-{1,2}ollama-start-fails$' { $OllamaStartFails = $true }
        '^-{1,2}(h|help)$' { Get-Content $PSCommandPath -TotalCount 16 | ForEach-Object { $_ -replace '^# ?', '' }; exit 0 }
        default { Write-Host "Unknown option: $a (try --help)"; exit 2 }
    }
}

# --- Output helpers ------------------------------------------------------------

function Say([string]$Text) { Write-Host $Text }
function Step([string]$Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "  [ok] $Text" -ForegroundColor Green }
function Info([string]$Text) { Write-Host "  - $Text" }
function Warn([string]$Text) { Write-Host "  [!] $Text" -ForegroundColor Yellow }
function Fail([string]$Text) {
    Write-Host ""; Write-Host "[x] $Text" -ForegroundColor Red
    if ($script:Logging) { Write-Host "    Details of this run: data\start.log" }
    exit 1
}
function Quit([string]$Text) { Write-Host ""; Write-Host $Text; exit 0 }

# Every question goes through here: in a console Read-Host shows the prompt and the
# transcript records it; with piped answers (tests, CI) the prompt is printed by hand.
function Prompt-Line([string]$Text) {
    if ([Console]::IsInputRedirected) {
        Write-Host "$Text`: " -NoNewline
        $answer = [Console]::In.ReadLine()
        Write-Host $answer
        return $answer
    }
    return Read-Host $Text
}

function Ask([string]$Question, [bool]$Default = $true) {
    if ($Yes) { return $Default }
    $hint = if ($Default) { "[Y/n]" } else { "[y/N]" }
    $answer = Prompt-Line "  $Question $hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer.Trim().ToLower().StartsWith("y")
}

# Choose "Question" "WPQ" "W": one letter, Enter for the default.
function Choose([string]$Question, [string]$Letters, [string]$Default) {
    if ($Yes) { return $Default }
    while ($true) {
        $answer = Prompt-Line "  $Question [$Default]"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
        $c = $answer.Trim().Substring(0, 1).ToUpper()
        if ($Letters.Contains($c)) { return $c }
        Say "  Please type one of: $(($Letters.ToCharArray()) -join ', ')"
    }
}

function Size([string]$Model) {
    $base = $Model -replace ':latest$', ''
    if ($ModelSizes.ContainsKey($base)) { return " (about $($ModelSizes[$base]))" }
    return ""
}

# --- Small utilities -----------------------------------------------------------

function Has([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function HttpGet([string]$Url) {
    # curl.exe returns the body for any status (the health check sends 503 with details).
    $out = & curl.exe -s -m 5 $Url 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($out -join "`n")
}

function HttpJson([string]$Url) {
    $body = HttpGet $Url
    if (-not $body) { return $null }
    try { return $body | ConvertFrom-Json -ErrorAction Stop } catch { return $null }
}

function PortFree([int]$Port) {
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start(); $listener.Stop(); return $true
    } catch { return $false }
}

function Refresh-Path {
    # After a winget install, pick up the new PATH without reopening the window.
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Read-Settings {
    $s = @{}
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $s[$Matches[1]] = $Matches[2] }
        }
    }
    return $s
}

function Save-Settings([hashtable]$s) {
    $lines = @("# Written by start.cmd / start.sh. Docker Compose reads it too. Safe to delete.")
    foreach ($key in "START_ROUTE", "CHAT_MODEL", "EMBEDDING_MODEL", "APP_PORT") {
        if ($s.ContainsKey($key)) { $lines += "$key=$($s[$key])" }
    }
    Set-Content -Path $EnvFile -Value $lines -Encoding ASCII
}

# Callers wrap it as @(Compose-Args $r): PowerShell returns a one-item array as a
# bare string, and "compose" + @("up") would otherwise become "composeup".
function Compose-Args([string]$Route) {
    if ($Route -eq "B") { return @("compose", "-f", "compose.yaml", "-f", "compose.host-ollama.yaml") }
    return @("compose")
}

# Runs docker in the project folder; returns whether it succeeded (callers explain failures).
function Invoke-Docker([string[]]$DockerArgs) {
    Push-Location $Root
    # Out-Host: docker's output goes to the screen, not into this function's return value.
    try { & docker @DockerArgs | Out-Host; return ($LASTEXITCODE -eq 0) }
    finally { Pop-Location }
}

# Downloads a model into Docker's Ollama; on failure explains and offers Retry/Quit.
function Pull-InDocker([string]$Model) {
    $attempt = 0
    while ($true) {
        $attempt++
        Info "Making sure $Model is in Docker's Ollama$(Size $Model)..."
        if (Invoke-Docker @("compose", "exec", "ollama", "ollama", "pull", $Model)) { return }
        Warn "Couldn't download $Model into Docker's Ollama. The internet connection may have dropped, or the Ollama container stopped (check Docker Desktop)."
        if ($Yes -and $attempt -ge 2) { Fail "Couldn't download $Model. Run .\start.cmd again to retry." }
        $c = Choose "[R]etry or [Q]uit?" "RQ" "R"
        if ($c -eq "Q") { Quit "Stopped. The app is set up; run .\start.cmd again to finish downloading the models." }
        # The container may have been stopped or removed: bring it back before retrying.
        [void](Invoke-Docker @("compose", "up", "-d"))
    }
}

function Container-Names([string]$Route) {
    Push-Location $Root
    try { $names = & docker @(@(Compose-Args $Route) + @("ps", "--format", "{{.Name}}")) 2>$null }
    finally { Pop-Location }
    return @($names | Where-Object { $_ })
}

function Describe-Route([string]$Route) {
    switch ($Route) {
        "A" { return "in Docker (route A): the app and Ollama both run in containers" }
        "B" { return "in Docker (route B): the app runs in a container and uses the Ollama on this computer" }
        default { return "with Python, without Docker (route C), next to the Ollama on this computer" }
    }
}

# --- Ollama on this computer ---------------------------------------------------

function Ollama-Running { return [bool](HttpJson "$OllamaUrl/api/version") }

function Ollama-State {
    if ($NoHostOllama) { return "missing" }
    if (Ollama-Running) { return "running" }
    if (Has "ollama") { return "stopped" }
    return "missing"
}

function Ollama-Models {
    $tags = HttpJson "$OllamaUrl/api/tags"
    if (-not $tags) { return @() }
    return @($tags.models | ForEach-Object { $_.name })
}

function Is-ChatModel([string]$Name) {
    try {
        $info = Invoke-RestMethod -Method Post -Uri "$OllamaUrl/api/show" -TimeoutSec 10 `
            -ContentType "application/json" -Body (@{ model = $Name } | ConvertTo-Json -Compress) -ErrorAction Stop
        return @($info.capabilities) -contains "completion"
    } catch { return $false }
}

function Has-Model([string[]]$Installed, [string]$Name) {
    $want = if ($Name.Contains(":")) { $Name } else { "$Name`:latest" }
    return ($Installed -contains $want) -or ($Installed -contains $Name)
}

function Start-HostOllama {
    # The normal way on Windows is the Ollama app (tray icon); `ollama serve` otherwise.
    if ($OllamaStartFails) { Info "(test) pretending Ollama won't start"; Start-Sleep -Seconds 2; return $false }
    $exe = (Get-Command ollama).Source
    $app = Join-Path (Split-Path $exe) "ollama app.exe"
    if (Test-Path $app) {
        Info "Starting the Ollama app..."
        Start-Process -FilePath $app | Out-Null
    } else {
        Info "Starting ollama serve in the background..."
        Start-Process -FilePath $exe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    }
    for ($i = 0; $i -lt 60; $i++) {
        if (Ollama-Running) { $script:OllamaStartedHere = $true; Ok "Ollama started"; return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

# Ollama is installed but not running: start it, and never switch silently.
# Returns "running", or "docker" when the user picks Docker's own Ollama.
function Ensure-HostOllama([bool]$OfferDocker) {
    Info "Ollama is installed but not running."
    $attempt = 0
    while ($true) {
        $attempt++
        if (Start-HostOllama) { return "running" }
        Warn "Ollama didn't answer within 60 seconds."
        if ($Yes -and $attempt -ge 2) { Fail "Ollama didn't start. Start the Ollama app yourself, then run this again." }
        if ($OfferDocker) {
            $c = Choose "[R]etry, use Ollama inside [D]ocker instead (downloads the models again, about 3 GB), or [Q]uit?" "RDQ" "R"
        } else {
            $c = Choose "[R]etry or [Q]uit?" "RQ" "R"
        }
        if ($c -eq "Q") { Quit "Stopped; nothing was changed. Start the Ollama app yourself, then run this again." }
        if ($c -eq "D") { return "docker" }
    }
}

function Install-Ollama {
    if (-not (Has "winget")) {
        Warn "Install Ollama from https://ollama.com/download, then run this again."
        return $false
    }
    Say "  Command: winget install -e --id Ollama.Ollama"
    if (-not (Ask "Install Ollama now with winget?")) { return $false }
    & winget install -e --id Ollama.Ollama
    Refresh-Path
    if (-not (Has "ollama")) { Warn "Ollama isn't on the PATH yet. Open a new window and run this again."; return $false }
    if (Ollama-Running) { return $true }
    return ((Ensure-HostOllama $false) -eq "running")
}

# --- Docker ----------------------------------------------------------------------

# Returns @{ State = "running" | "down" | "missing"; Detail = text }.
function Docker-State {
    if ($NoDocker -or -not (Has "docker")) { return @{ State = "missing"; Detail = "" } }
    $out = & docker info --format "{{.ServerVersion}}" 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -eq 0) { return @{ State = "running"; Detail = ($out -join " ").Trim() } }
    $detail = (($out | Where-Object { $_.Trim() }) | Select-Object -Last 2) -join " "
    return @{ State = "down"; Detail = $detail.Trim() }
}

function Wait-Docker {
    if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
        $docker = (Get-Command docker).Source
        $candidates = @(
            (Join-Path (Split-Path (Split-Path (Split-Path $docker))) "Docker Desktop.exe"),
            "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
        )
        $exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($exe) { Info "Starting Docker Desktop..."; Start-Process -FilePath $exe | Out-Null }
        else { Warn "Couldn't find Docker Desktop to start it; start it yourself, and this keeps waiting." }
    }
    Info "Waiting for Docker to answer (up to 3 minutes)..."
    for ($i = 0; $i -lt 90; $i++) {
        if ((Docker-State).State -eq "running") { Ok "Docker is running"; return $true }
        Start-Sleep -Seconds 2
    }
    Warn "Docker still isn't answering."
    return $false
}

# Docker is installed but not answering: wait for it, or switch only if asked.
# Returns "running" or "python".
function Ensure-Docker([string]$Detail, [bool]$OfferPython) {
    if ($Detail) { Warn "Docker is installed but isn't answering: $Detail" }
    else { Warn "Docker is installed but isn't answering." }
    while ($true) {
        if ($OfferPython) {
            $c = Choose "[W]ait for Docker (starts Docker Desktop if it's closed), use [P]ython instead, or [Q]uit?" "WPQ" "W"
        } else {
            $c = Choose "[W]ait for Docker (starts Docker Desktop if it's closed), or [Q]uit?" "WQ" "W"
        }
        if ($c -eq "Q") { Quit "Stopped; nothing was changed. Start Docker Desktop, then run this again." }
        if ($c -eq "P") { return "python" }
        if (Wait-Docker) { return "running" }
        if ($Yes) { Fail "Docker didn't answer within 3 minutes. Start Docker Desktop, then run this again (or run with --reconfigure and choose Python)." }
    }
}

# --- Python (route C) -----------------------------------------------------------

function Find-Python {
    # The py launcher first: the "python" on a fresh Windows can be the Store stub.
    foreach ($cmd in @(@("py", "-3"), @("python"))) {
        if (-not (Has $cmd[0])) { continue }
        $exe = $cmd[0]; $pre = @($cmd | Select-Object -Skip 1)
        $v = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match '^(\d+)\.(\d+)$') {
            if ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 11) {
                $found = @($exe) + $pre
                return , $found
            }
        }
    }
    return $null
}

function Install-Python {
    if (-not (Has "winget")) { Warn "Install Python 3.12 from https://www.python.org/downloads/, then run this again."; return $false }
    Say "  Command: winget install -e --id Python.Python.3.12"
    if (-not (Ask "Install Python 3.12 now with winget?")) { return $false }
    & winget install -e --id Python.Python.3.12
    Refresh-Path
    return [bool](Find-Python)
}

function Setup-RouteC([string[]]$Python) {
    $backend = Join-Path $Root "backend"
    $venvPy = Join-Path $backend ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Info "Creating backend\.venv"
        $exe = $Python[0]; $pre = @($Python | Select-Object -Skip 1)
        & $exe @pre -m venv (Join-Path $backend ".venv")
        if ($LASTEXITCODE -ne 0) { Fail "Couldn't create the virtual environment." }
    }
    $req = Join-Path $backend "requirements.txt"
    $marker = Join-Path $backend ".venv\.requirements.sha256"
    $hash = (Get-FileHash $req -Algorithm SHA256).Hash
    if (-not (Test-Path $marker) -or (Get-Content $marker) -ne $hash) {
        Info "Installing the Python packages (a few minutes the first time)..."
        & $venvPy -m pip install --disable-pip-version-check -q -r $req
        if ($LASTEXITCODE -ne 0) { Fail "pip install failed; see the messages above." }
        Set-Content -Path $marker -Value $hash -Encoding ASCII
    }
    Ok "Python packages ready"

    $dist = Join-Path $Root "frontend\dist"
    if (-not (Test-Path (Join-Path $dist "index.html"))) {
        Get-WebApp $dist
    }
    Ok "Web app ready"
    return $venvPy
}

function Get-WebApp([string]$Dist) {
    $base = "https://github.com/$Repo/releases/latest/download"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("rag-web-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Info "Downloading the ready-built web app from this project's latest GitHub Release..."
        & curl.exe -fsSL -o "$tmp\web-dist.zip" "$base/web-dist.zip"
        if ($LASTEXITCODE -ne 0) { throw "download failed" }
        & curl.exe -fsSL -o "$tmp\web-dist.zip.sha256" "$base/web-dist.zip.sha256"
        if ($LASTEXITCODE -ne 0) { throw "checksum download failed" }
        $expected = ((Get-Content "$tmp\web-dist.zip.sha256" -Raw).Trim() -split '\s+')[0].ToUpper()
        $actual = (Get-FileHash "$tmp\web-dist.zip" -Algorithm SHA256).Hash
        if ($expected -ne $actual) { throw "checksum mismatch" }
        Expand-Archive -Path "$tmp\web-dist.zip" -DestinationPath $Dist -Force -ErrorAction Stop
        Ok "Web app downloaded and checked (SHA-256)"
    } catch {
        if (Has "npm") {
            Warn "Couldn't download it ($_). Node is installed, so building it here instead."
            Push-Location (Join-Path $Root "frontend")
            try { & npm ci --no-audit --no-fund; & npm run build } finally { Pop-Location }
            if (-not (Test-Path (Join-Path $Dist "index.html"))) { Fail "The web app build failed." }
        } else {
            Fail "Couldn't get the web app ($_). Check your internet connection, or install Node 22 and run this again."
        }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Start-RouteC([string]$VenvPy, [hashtable]$s) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $env:DATA_DIR = $DataDir
    $env:CHAT_MODEL = $s.CHAT_MODEL
    $env:EMBEDDING_MODEL = $s.EMBEDDING_MODEL
    $env:OLLAMA_BASE_URL = $OllamaUrl
    $log = Join-Path $DataDir "server.log"
    # cmd does the log redirection. Start-Process without -Redirect* launches through
    # the shell, so the server doesn't inherit this window's handles: a caller that
    # captures our output (a pipe, CI) isn't kept waiting for the server to exit.
    $serve = "`"$VenvPy`" -m uvicorn app.main:app --host 127.0.0.1 --port $($s.APP_PORT) --workers 1"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$serve > `"$log`" 2>&1`"" `
        -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $DataDir "app.pid") -Value $proc.Id -Encoding ASCII
    Info "App started in the background (logs: data\server.log)"
}

# --- The app ---------------------------------------------------------------------

function Wait-Healthy([int]$Port) {
    Info "Waiting for the app to answer..."
    for ($i = 0; $i -lt 90; $i++) {
        $h = HttpJson "http://127.0.0.1:$Port/health"
        if ($h) {
            if ($h.status -eq "ok") { Ok "All systems OK"; return $true }
            if ($i -gt 20) {
                foreach ($k in "ollama", "sqlite", "vector_store", "job_worker") {
                    if ($h.$k -and -not $h.$k.ok) { Warn "$k`: $($h.$k.detail)" }
                }
                return $false
            }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Load-Demo([int]$Port) {
    $demo = HttpJson "http://127.0.0.1:$Port/api/demo"
    if (-not $demo -or -not $demo.available) { return }
    if ($demo.documents -gt 0) { Ok "Your library already has $($demo.documents) documents"; return }
    if (-not (Ask "Load the demo company now? (11 documents, a few minutes)")) {
        Info "You can load it later from the dashboard."
        return
    }
    & curl.exe -s -m 10 -X POST "http://127.0.0.1:$Port/api/demo/seed" *> $null
    $last = -1
    while ($true) {
        Start-Sleep -Seconds 2
        $d = HttpJson "http://127.0.0.1:$Port/api/demo"
        $job = $d.job
        if (-not $job) { continue }
        $pct = [int][math]::Round($job.progress * 100)
        if ($pct -ne $last) { Write-Host "`r  Loading the demo company... $pct%   " -NoNewline; $last = $pct }
        if ($job.status -eq "completed") { Write-Host ""; Ok "Demo company loaded: $($job.result.ingested) documents"; return }
        if ($job.status -eq "failed" -or $job.status -eq "cancelled") {
            Write-Host ""; Warn "Loading stopped: $($job.error). Open the dashboard and click Troubleshoot."; return
        }
    }
}

# --- Commands --------------------------------------------------------------------

function Stop-Route([string]$Route) {
    if ($Route -eq "C") {
        $pidFile = Join-Path $DataDir "app.pid"
        if (Test-Path $pidFile) {
            $p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
            if ($p) {
                # The whole tree: cmd, the venv's python launcher and the server it starts.
                & taskkill.exe /PID $p.Id /T /F *> $null
                Ok "App stopped (it was running with Python)"
            } else { Info "The app wasn't running" }
            Remove-Item $pidFile -ErrorAction SilentlyContinue
        } else { Info "The app wasn't running" }
    } elseif ((Docker-State).State -eq "running") {
        if (Invoke-Docker (@(Compose-Args $Route) + @("down"))) { Ok "App stopped (it was running in Docker). Your documents and models are kept." }
        else { Warn "docker compose down reported a problem; see the messages above." }
    } else {
        Warn "Docker isn't answering, so the containers couldn't be stopped. Start Docker Desktop and run stop again."
    }
}

function Do-Stop {
    $s = Read-Settings
    if (-not $s.START_ROUTE) { Say "Nothing to stop: start.cmd hasn't been run here."; return }
    Stop-Route $s.START_ROUTE
}

function Do-Status {
    $s = Read-Settings
    if (-not $s.START_ROUTE) { Say "Not set up yet: run .\start.cmd"; return }
    $port = if ($s.APP_PORT) { $s.APP_PORT } else { "8000" }
    Say "Set up to run $(Describe-Route $s.START_ROUTE)."
    Say "Chat model $($s.CHAT_MODEL), at http://localhost:$port"
    if ($s.START_ROUTE -ne "C" -and (Docker-State).State -eq "running") {
        $names = Container-Names $s.START_ROUTE
        if ($names) { Say "Containers: $($names -join ', ')" }
    }
    $h = HttpJson "http://127.0.0.1:$port/health"
    if (-not $h) { Say "The app isn't running. Start it with .\start.cmd"; return }
    foreach ($k in "ollama", "sqlite", "vector_store", "job_worker") {
        $state = if ($h.$k.ok) { "ok" } else { "PROBLEM" }
        Say ("  {0,-13} {1,-8} {2}" -f $k, $state, $h.$k.detail)
    }
}

function Choose-ChatModel([string]$Suggested, [string[]]$HostModels) {
    if (-not $HostModels -or $HostModels.Count -eq 0) {
        if ($Yes) { return $Suggested }
        $answer = Prompt-Line "  Chat model to use [$Suggested$(Size $Suggested)]"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Suggested }
        return $answer.Trim()
    }
    $chat = @($HostModels | Where-Object { Is-ChatModel $_ })
    if ($chat.Count -eq 0) { return $Suggested }
    $default = $chat | Where-Object { ($_ -replace ':latest$', '') -eq $Suggested } | Select-Object -First 1
    if (-not $default) { $default = $chat[0] }
    Say "  Ollama already has these chat models: $($chat -join ', ')"
    if ($Yes) { return $default }
    $answer = Prompt-Line "  Use $($default)? Press Enter, or type another name (it's downloaded if missing)"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}

# What --check reports: the route the questions would lead to with the default answers.
function Explain-Check([string]$OllamaState, [hashtable]$Docker, [hashtable]$s, [string]$Suggested) {
    Step "3. How to run it"
    if ($s.START_ROUTE -and -not $Reconfigure) {
        Info "Saved choice: run $(Describe-Route $s.START_ROUTE). (--reconfigure asks again.)"
    } else {
        $dockerUsable = $Docker.State -ne "missing"
        if ($Docker.State -eq "down") { Info "Docker isn't answering: it would ask to wait for it, use Python instead, or quit." }
        if ($OllamaState -eq "stopped") { Info "Ollama isn't running: it would start the Ollama app." }
        if ($dockerUsable -and $OllamaState -ne "missing") {
            Info "It would ask 'Run the app in Docker?'. Yes (the default): route B; no: route C."
        } elseif ($dockerUsable) {
            Info "It would ask 'Run Ollama inside Docker?'. Yes (the default): route A; no: install Ollama, then route B."
        } else {
            Info "Without Docker: route C (Python), installing Ollama and Python first if needed, after asking."
        }
    }
    Info "Chat model: $(if ($s.CHAT_MODEL) { $s.CHAT_MODEL } else { $Suggested }); embedding model: $EmbeddingModel"
    Say ""; Say "--check: nothing was changed."
}

function Do-Start {
    Say ""
    Say "Local RAG with Ollama: one-command start"
    Say "Everything runs on this computer; your documents never leave it."

    $s = Read-Settings
    $savedRoute = $s.START_ROUTE
    $port = if ($s.APP_PORT) { [int]$s.APP_PORT } else { 8000 }

    # Already running? Just open it.
    if ($savedRoute -and -not $CheckOnly -and -not $Reconfigure) {
        $h = HttpJson "http://127.0.0.1:$port/health"
        if ($h -and $h.status) {
            Ok "The app is already running $(Describe-Route $savedRoute), at http://localhost:$port"
            Start-Process "http://localhost:$port/site" | Out-Null
            return
        }
    }

    Step "1. This computer"
    $ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $drive = (Get-Item $Root).PSDrive
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    $suggested = if ($ramGb -lt 12) { "qwen2.5:3b" } else { "llama3.1" }
    Info "Windows, $ramGb GB of RAM, $freeGb GB free on $($drive.Name):"
    if ($ramGb -lt 12) { Info "Suggested chat model: qwen2.5:3b (small enough for $ramGb GB)" } else { Info "Suggested chat model: llama3.1" }
    if ($freeGb -lt 8) { Warn "Less than 8 GB free; the models need 3-7 GB." }

    Step "2. Ollama and Docker"
    $ollamaState = Ollama-State
    switch ($ollamaState) {
        "running" { Ok "Ollama is running on this computer" }
        "stopped" { Info "Ollama is installed on this computer but not running" }
        default { Info "Ollama isn't installed on this computer" }
    }
    $docker = Docker-State
    switch ($docker.State) {
        "running" { Ok "Docker is running (engine $($docker.Detail))" }
        "down" { Info "Docker is installed but isn't answering" }
        default { Info "Docker isn't installed (optional: https://www.docker.com/products/docker-desktop/)" }
    }

    if ($CheckOnly) { Explain-Check $ollamaState $docker $s $suggested; return }

    Step "3. How to run it"
    if ($savedRoute -and -not $Reconfigure) {
        # Reuse the saved route, making sure what it needs is up. No silent switching.
        $route = $savedRoute
        Info "Using your saved choice: run $(Describe-Route $route). (--reconfigure asks again.)"
        if ($route -ne "C") {
            if ($docker.State -eq "missing") { Fail "Docker isn't available, but this was set up to run in Docker. Run .\start.cmd --reconfigure to choose again." }
            if ($docker.State -eq "down") { [void](Ensure-Docker $docker.Detail $false) }
        }
        if ($route -ne "A") {
            if ($ollamaState -eq "missing") { Fail "Ollama isn't available on this computer, but this setup uses it. Run .\start.cmd --reconfigure to choose again." }
            if ($ollamaState -eq "stopped") { [void](Ensure-HostOllama $false) }
        }
    } else {
        $dockerOk = $docker.State -eq "running"
        $whyNoDocker = "Docker isn't installed"
        if ($docker.State -eq "down") {
            if ((Ensure-Docker $docker.Detail $true) -eq "running") { $dockerOk = $true }
            else { $whyNoDocker = "you chose Python instead of waiting for Docker" }
        }
        $hostOllama = $ollamaState -eq "running"
        $ollamaInDocker = $false
        if ($ollamaState -eq "stopped") {
            if ((Ensure-HostOllama $dockerOk) -eq "running") { $hostOllama = $true } else { $ollamaInDocker = $true }
        }

        if ($dockerOk -and $hostOllama) {
            if (Ask "Run the app in Docker? (recommended; it uses the Ollama and models already on this computer)") {
                $route = "B"
            } else {
                $route = "C"; $whyNoDocker = "you chose to run without Docker"
            }
        } elseif ($dockerOk) {
            if ($ramGb -lt 12) {
                Warn "With $ramGb GB of RAM, Docker gets only part of it, so answers from Ollama inside Docker are much slower (minutes). Ollama installed on this computer is faster."
            }
            if ($ollamaInDocker -or (Ask "Ollama isn't installed on this computer. Run it inside Docker? (recommended: nothing to install; the models download into Docker, about 3 GB)")) {
                $route = "A"
            } else {
                if (-not (Install-Ollama)) { Fail "Ollama is needed. Install it from https://ollama.com/download, or run this again and choose Ollama inside Docker." }
                $route = "B"
            }
        } else {
            $route = "C"
            if (-not $hostOllama) {
                Info "Running without Docker needs Ollama on this computer."
                if (-not (Install-Ollama)) { Fail "Ollama is needed. Install it from https://ollama.com/download, or install Docker Desktop, then run this again." }
            }
        }
        if ($route -eq "C") { Ok "Will run $(Describe-Route 'C'): $whyNoDocker." }
        else { Ok "Will run $(Describe-Route $route)." }
    }

    $python = $null
    if ($route -eq "C") {
        $python = Find-Python
        if (-not $python) {
            Info "Running with Python needs Python 3.11 or newer."
            if (-not (Install-Python)) { Fail "Python 3.11+ is needed (https://www.python.org/downloads/), or install Docker Desktop." }
            $python = Find-Python
        }
        Ok "Python: $($python -join ' ')"
    }

    # Switching from another way: stop it first, so the port is free.
    if ($savedRoute -and $savedRoute -ne $route) {
        Info "Switching from route $savedRoute to route $route; stopping the old one first."
        Stop-Route $savedRoute
        Info "Each way keeps its own library (data\ for Python, a Docker volume for Docker), so the demo is loaded again here."
    }

    Step "4. Models"
    if (-not $s.CHAT_MODEL -or $Reconfigure) {
        $hostModels = if ($route -ne "A") { Ollama-Models } else { @() }
        $s.CHAT_MODEL = Choose-ChatModel $suggested $hostModels
    }
    $s.EMBEDDING_MODEL = $EmbeddingModel
    Info "Chat model: $($s.CHAT_MODEL); embedding model: $EmbeddingModel"

    if (-not (PortFree $port)) {
        $free = 8001..8010 | Where-Object { PortFree $_ } | Select-Object -First 1
        if (-not $free) { Fail "Ports 8000-8010 are all in use. Free one and run this again." }
        Warn "Port $port is in use, so the app will use $free."
        $port = $free
    }
    $s.APP_PORT = "$port"
    $s.START_ROUTE = $route
    Save-Settings $s

    if ($route -ne "A") {
        $installed = Ollama-Models
        foreach ($m in @($EmbeddingModel, $s.CHAT_MODEL)) {
            if (Has-Model $installed $m) { Ok "$m is already downloaded" }
            elseif (Ask "Download $m$(Size $m) into Ollama now?") {
                & ollama pull $m
                if ($LASTEXITCODE -ne 0) { Fail "Couldn't download $m." }
            } else { Warn "$m isn't downloaded; the app will ask for it." }
        }
    }

    Step "5. Starting the app"
    if ($route -eq "C") {
        $venvPy = Setup-RouteC $python
        Start-RouteC $venvPy $s
    } else {
        Info "Starting the containers (the first time downloads the images, which can take a while)..."
        # Refresh the app image so an earlier download isn't stale; offline, the cached one is used.
        Push-Location $Root
        & docker @(@(Compose-Args $route) + @("pull", "--quiet", "app")) 2>$null
        if ($LASTEXITCODE -ne 0) { Warn "Couldn't check for a newer app image; using the one already downloaded." }
        Pop-Location
        if (-not (Invoke-Docker (@(Compose-Args $route) + @("up", "-d")))) {
            Fail "Docker couldn't start the containers; the reason is in the messages above."
        }
        if ($route -eq "A") {
            foreach ($m in @($EmbeddingModel, $s.CHAT_MODEL)) { Pull-InDocker $m }
        }
    }
    if (-not (Wait-Healthy $port)) {
        Warn "The app isn't fully healthy yet. Open http://localhost:$port and click Troubleshoot."
    }

    Step "6. The demo company"
    Load-Demo $port

    Step "Ready"
    Say "  Running $(Describe-Route $route)."
    if ($route -ne "C") {
        $names = Container-Names $route
        if ($names) { Say "  Containers (see them in Docker Desktop): $($names -join ', ')" }
    }
    if ($script:OllamaStartedHere) { Say "  Ollama was started by this script; it keeps running after this window closes." }
    Say ""
    Say "  Company website:  http://localhost:$port/site"
    Say "  Employee portal:  http://localhost:$port/intranet"
    Say "  Admin console:    http://localhost:$port"
    Say ""
    Say "  Stop: .\start.cmd stop   Status: .\start.cmd status   Choose another way: .\start.cmd --reconfigure"
    Say "  Your answers are saved in .env. This run's log: data\start.log"
    Start-Process "http://localhost:$port/site" | Out-Null
}

function Started-FromExplorer {
    # Double-clicking start.cmd: explorer -> cmd -> this PowerShell.
    try {
        $me = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction Stop
        $cmd = Get-CimInstance Win32_Process -Filter "ProcessId=$($me.ParentProcessId)" -ErrorAction Stop
        return (Get-Process -Id $cmd.ParentProcessId -ErrorAction Stop).ProcessName -eq "explorer"
    } catch { return $false }
}

try {
    if ($Command -eq "start" -and -not $CheckOnly) {
        # A log of each start (overwritten every time) for troubleshooting.
        New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
        try { Start-Transcript -Path $LogFile -Force | Out-Null; $script:Logging = $true } catch { $script:Logging = $false }
    }
    switch ($Command) {
        "stop" { Do-Stop }
        "status" { Do-Status }
        default { Do-Start }
    }
} finally {
    if ($script:Logging) { try { Stop-Transcript | Out-Null } catch { } }
    # Keep a double-clicked window open so the messages stay readable.
    if (Started-FromExplorer) { Write-Host ""; Read-Host "Press Enter to close" | Out-Null }
}
