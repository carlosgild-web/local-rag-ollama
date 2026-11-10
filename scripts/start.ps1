# One-command start for Windows (decision 0013). Run it through start.cmd:
#
#   .\start.cmd             start (asks a few questions the first time)
#   .\start.cmd stop        stop the app (your documents and models are kept)
#   .\start.cmd status      show what's running
#
# Options: --yes (accept every suggestion), --check (look and explain, change
# nothing), --reconfigure (ask again instead of using the saved answers).
# Test-only: --no-host-ollama, --no-docker (pretend they're missing).
#
# It never installs anything without asking, only from official sources
# (winget, ollama.com, this repo's GitHub Release with a checksum), and the app
# listens on 127.0.0.1 only. Works in Windows PowerShell 5.1 and PowerShell 7.

# "Continue": in Windows PowerShell 5.1, "Stop" turns any stderr line from docker
# or curl into an exception. Failures are checked by exit code instead.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $Root ".env"
$DataDir = Join-Path $Root "data"
$Repo = "carlosgild-web/local-rag-ollama"
$OllamaUrl = "http://127.0.0.1:11434"
$EmbeddingModel = "bge-m3"
$ModelSizes = @{ "bge-m3" = "1.2 GB"; "qwen2.5:3b" = "1.9 GB"; "llama3.1" = "4.9 GB" }

# --- Arguments ---------------------------------------------------------------

$Command = "start"
$Yes = $false; $CheckOnly = $false; $Reconfigure = $false
$NoHostOllama = $false; $NoDocker = $false
foreach ($a in $args) {
    switch -Regex ($a) {
        '^(start|stop|status)$' { $Command = $a }
        '^-{1,2}yes$' { $Yes = $true }
        '^-{1,2}check$' { $CheckOnly = $true }
        '^-{1,2}reconfigure$' { $Reconfigure = $true }
        '^-{1,2}no-host-ollama$' { $NoHostOllama = $true }
        '^-{1,2}no-docker$' { $NoDocker = $true }
        '^-{1,2}(h|help)$' { Get-Content $PSCommandPath -TotalCount 12 | ForEach-Object { $_ -replace '^# ?', '' }; exit 0 }
        default { Write-Host "Unknown option: $a (try --help)"; exit 2 }
    }
}

# --- Output helpers ------------------------------------------------------------

function Say([string]$Text) { Write-Host $Text }
function Step([string]$Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "  [ok] $Text" -ForegroundColor Green }
function Info([string]$Text) { Write-Host "  - $Text" }
function Warn([string]$Text) { Write-Host "  [!] $Text" -ForegroundColor Yellow }
function Fail([string]$Text) { Write-Host ""; Write-Host "[x] $Text" -ForegroundColor Red; exit 1 }

function Ask([string]$Question, [bool]$Default = $true) {
    if ($Yes) { return $Default }
    $hint = if ($Default) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "  $Question $hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer.Trim().ToLower().StartsWith("y")
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

function Compose-Args([string]$Route) {
    if ($Route -eq "B") { return @("compose", "-f", "compose.yaml", "-f", "compose.host-ollama.yaml") }
    return @("compose")
}

function Invoke-Docker([string[]]$DockerArgs) {
    Push-Location $Root
    try { & docker @DockerArgs; if ($LASTEXITCODE -ne 0) { throw "docker $($DockerArgs -join ' ') failed" } }
    finally { Pop-Location }
}

# --- Ollama on this computer ---------------------------------------------------

function Ollama-Running { return [bool](HttpJson "$OllamaUrl/api/version") }

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
    Info "Ollama is installed but not running; starting it..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        if (Ollama-Running) { Ok "Ollama started"; return $true }
        Start-Sleep -Seconds 1
    }
    Warn "Ollama didn't answer after 30 seconds."
    return $false
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
    if (-not (Ollama-Running)) { return (Start-HostOllama) }
    return $true
}

# --- Docker ----------------------------------------------------------------------

function Docker-Running {
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerDesktop {
    $docker = (Get-Command docker).Source
    $candidates = @(
        (Join-Path (Split-Path (Split-Path (Split-Path $docker))) "Docker Desktop.exe"),
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    )
    $exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { Warn "Couldn't find Docker Desktop. Start it yourself, then run this again."; return $false }
    Start-Process -FilePath $exe | Out-Null
    Info "Waiting for Docker Desktop (up to 2 minutes)..."
    for ($i = 0; $i -lt 60; $i++) {
        if (Docker-Running) { Ok "Docker is running"; return $true }
        Start-Sleep -Seconds 2
    }
    Warn "Docker didn't start in time."
    return $false
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
    $proc = Start-Process -FilePath $VenvPy `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $s.APP_PORT, "--workers", "1" `
        -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError (Join-Path $DataDir "server.err.log")
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

function Do-Stop {
    $s = Read-Settings
    $route = $s.START_ROUTE
    if (-not $route) { Say "Nothing to stop: start.cmd hasn't been run here."; return }
    if ($route -eq "C") {
        $pidFile = Join-Path $DataDir "app.pid"
        if (Test-Path $pidFile) {
            $p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
            if ($p) { Stop-Process -Id $p.Id -Force; Ok "App stopped" } else { Info "The app wasn't running" }
            Remove-Item $pidFile -ErrorAction SilentlyContinue
        }
    } else {
        Invoke-Docker ((Compose-Args $route) + @("down"))
        Ok "App stopped. Your documents and models are kept (docker compose down -v would delete them)."
    }
}

function Do-Status {
    $s = Read-Settings
    if (-not $s.START_ROUTE) { Say "Not set up yet: run .\start.cmd"; return }
    $port = if ($s.APP_PORT) { $s.APP_PORT } else { "8000" }
    Say "Route $($s.START_ROUTE), chat model $($s.CHAT_MODEL), http://localhost:$port"
    $h = HttpJson "http://127.0.0.1:$port/health"
    if (-not $h) { Say "The app isn't running."; return }
    foreach ($k in "ollama", "sqlite", "vector_store", "job_worker") {
        $state = if ($h.$k.ok) { "ok" } else { "PROBLEM" }
        Say ("  {0,-13} {1,-8} {2}" -f $k, $state, $h.$k.detail)
    }
}

function Choose-ChatModel([string]$Suggested, [string[]]$HostModels) {
    if (-not $HostModels -or $HostModels.Count -eq 0) {
        if ($Yes) { return $Suggested }
        $answer = Read-Host "  Chat model to use [$Suggested$(Size $Suggested)]"
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Suggested }
        return $answer.Trim()
    }
    $chat = @($HostModels | Where-Object { Is-ChatModel $_ })
    if ($chat.Count -eq 0) { return $Suggested }
    $default = $chat | Where-Object { ($_ -replace ':latest$', '') -eq $Suggested } | Select-Object -First 1
    if (-not $default) { $default = $chat[0] }
    Say "  Ollama already has these chat models: $($chat -join ', ')"
    if ($Yes) { return $default }
    $answer = Read-Host "  Use $default? Press Enter, or type another name (it's downloaded if missing)"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}

function Do-Start {
    Say ""
    Say "Local RAG with Ollama: one-command start"
    Say "Everything runs on this computer; your documents never leave it."

    $s = Read-Settings
    $port = if ($s.APP_PORT) { [int]$s.APP_PORT } else { 8000 }

    # Already running? Just open it.
    if ($s.START_ROUTE -and -not $CheckOnly -and -not $Reconfigure) {
        $h = HttpJson "http://127.0.0.1:$port/health"
        if ($h -and $h.status) {
            Ok "The app is already running at http://localhost:$port"
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
    $hostOllama = $false
    if (-not $NoHostOllama) {
        if (Ollama-Running) { $hostOllama = $true; Ok "Ollama is running on this computer" }
        elseif (Has "ollama") {
            if ($CheckOnly) { Info "Ollama is installed but not running (it would be started)"; $hostOllama = $true }
            else { $hostOllama = Start-HostOllama }
        } else { Info "Ollama isn't installed on this computer" }
    }
    $docker = $false
    if (-not $NoDocker -and (Has "docker")) {
        if (Docker-Running) { $docker = $true; Ok "Docker is running" }
        elseif ($CheckOnly) { Info "Docker is installed but not running (it would offer to start it)"; $docker = $true }
        elseif (Ask "Docker Desktop is installed but not running. Start it now?") { $docker = Start-DockerDesktop }
    } elseif (-not $NoDocker) {
        Info "Docker isn't installed (optional: https://www.docker.com/products/docker-desktop/)"
    }

    Step "3. How to run it"
    if ($s.START_ROUTE -and -not $Reconfigure) {
        $route = $s.START_ROUTE
        Info "Using your saved choice (route $route). Run with --reconfigure to choose again."
    } elseif ($docker -and $hostOllama) {
        $route = "B"; Info "Route B: the app in Docker, using the Ollama and models already on this computer."
    } elseif ($docker) {
        $route = "A"; Info "Route A: the app and Ollama both in Docker; nothing else is installed."
    } else {
        $route = "C"; Info "Route C: no Docker, so the app runs with Python, next to Ollama on this computer."
    }

    if ($CheckOnly) {
        Info "Chat model: $(if ($s.CHAT_MODEL) { $s.CHAT_MODEL } else { $suggested }); embedding model: $EmbeddingModel"
        Say ""; Say "--check: nothing was changed."
        return
    }

    $python = $null
    if ($route -eq "C") {
        if (-not $hostOllama) {
            Info "Route C needs Ollama on this computer."
            if (-not (Install-Ollama)) { Fail "Ollama is needed. Install it from https://ollama.com/download, or install Docker Desktop, then run this again." }
            $hostOllama = $true
        }
        $python = Find-Python
        if (-not $python) {
            Info "Route C needs Python 3.11 or newer."
            if (-not (Install-Python)) { Fail "Python 3.11+ is needed (https://www.python.org/downloads/), or install Docker Desktop." }
            $python = Find-Python
        }
        Ok "Python: $($python -join ' ')"
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
        & docker @((Compose-Args $route) + @("pull", "--quiet", "app")) 2>$null
        if ($LASTEXITCODE -ne 0) { Warn "Couldn't check for a newer app image; using the one already downloaded." }
        Pop-Location
        Invoke-Docker ((Compose-Args $route) + @("up", "-d"))
        if ($route -eq "A") {
            foreach ($m in @($EmbeddingModel, $s.CHAT_MODEL)) {
                Info "Making sure $m is in Docker's Ollama$(Size $m)..."
                Invoke-Docker @("compose", "exec", "ollama", "ollama", "pull", $m)
            }
        }
    }
    if (-not (Wait-Healthy $port)) {
        Warn "The app isn't fully healthy yet. Open http://localhost:$port and click Troubleshoot."
    }

    Step "6. The demo company"
    Load-Demo $port

    Step "Ready"
    Say "  Company website:  http://localhost:$port/site"
    Say "  Employee portal:  http://localhost:$port/intranet"
    Say "  Admin console:    http://localhost:$port"
    Say ""
    Say "  Stop:    .\start.cmd stop      Status: .\start.cmd status"
    Say "  Your answers are saved in .env; the next start skips the questions."
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
    switch ($Command) {
        "stop" { Do-Stop }
        "status" { Do-Status }
        default { Do-Start }
    }
} finally {
    # Keep a double-clicked window open so the messages stay readable.
    if (Started-FromExplorer) { Write-Host ""; Read-Host "Press Enter to close" | Out-Null }
}
