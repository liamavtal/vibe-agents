#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Vibe Agents - Windows Installation & Service Setup Script

.DESCRIPTION
    Installs Vibe Agents as a Windows service using NSSM.
    - Installs Python dependencies
    - Downloads NSSM if not present
    - Configures and installs the Windows service
    - Opens firewall port
    - Starts the service

.PARAMETER Port
    Port to run the server on (default: 8000)

.PARAMETER InstallDir
    Directory where vibe-agents is located (default: script's parent)

.PARAMETER ServiceName
    Windows service name (default: VibeAgents)

.EXAMPLE
    .\install-windows.ps1
    .\install-windows.ps1 -Port 9000
    .\install-windows.ps1 -InstallDir "C:\vibe-agents"
#>

param(
    [int]$Port = 8000,
    [string]$InstallDir = "",
    [string]$ServiceName = "VibeAgents"
)

$ErrorActionPreference = "Stop"

# ==================== Helpers ====================

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "  >> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Test-CommandExists {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

# ==================== Resolve Install Directory ====================

if (-not $InstallDir) {
    $InstallDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (-not (Test-Path (Join-Path $InstallDir "backend"))) {
        $InstallDir = Split-Path -Parent $PSScriptRoot
    }
}

if (-not (Test-Path (Join-Path $InstallDir "backend"))) {
    Write-Fail "Cannot find vibe-agents at: $InstallDir"
    Write-Host "  Use -InstallDir to specify the correct path."
    exit 1
}

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Blue
Write-Host "  Vibe Agents - Windows Installer" -ForegroundColor Blue
Write-Host "  ================================================" -ForegroundColor Blue
Write-Host ""
Write-Host "  Install dir : $InstallDir"
Write-Host "  Service name: $ServiceName"
Write-Host "  Port        : $Port"
Write-Host ""

# ==================== Step 1: Check Python ====================

Write-Step "Checking Python..."

if (Test-CommandExists "python") {
    $pyVersion = python --version 2>&1
    Write-Ok "Python found: $pyVersion"
} else {
    Write-Fail "Python not found. Install Python 3.9+ from https://python.org"
    exit 1
}

# Verify version >= 3.9
$pyVersionNum = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$major, $minor = $pyVersionNum -split '\.'
if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 9)) {
    Write-Fail "Python 3.9+ required, found $pyVersionNum"
    exit 1
}

# ==================== Step 2: Check Claude CLI ====================

Write-Step "Checking Claude CLI..."

if (Test-CommandExists "claude") {
    $claudeVersion = claude --version 2>&1
    Write-Ok "Claude CLI found: $claudeVersion"
} else {
    Write-Warn "Claude CLI not found."
    Write-Host "  Install with: npm install -g @anthropic-ai/claude-code"
    Write-Host "  The service will NOT work without Claude CLI."
    Write-Host ""
    $continue = Read-Host "  Continue anyway? (y/N)"
    if ($continue -ne "y") { exit 1 }
}

# ==================== Step 3: Check Node.js (for Claude CLI) ====================

Write-Step "Checking Node.js..."

if (Test-CommandExists "node") {
    $nodeVersion = node --version 2>&1
    Write-Ok "Node.js found: $nodeVersion"
} else {
    Write-Warn "Node.js not found. Claude CLI requires Node.js."
    Write-Host "  Install from: https://nodejs.org"
}

# ==================== Step 4: Install Python Dependencies ====================

Write-Step "Installing Python dependencies..."

$reqFile = Join-Path $InstallDir "backend\requirements.txt"
if (Test-Path $reqFile) {
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r $reqFile
    Write-Ok "Dependencies installed"
} else {
    Write-Warn "requirements.txt not found at $reqFile"
}

# Install the vibe-agents package itself (editable)
$pyprojectFile = Join-Path $InstallDir "pyproject.toml"
if (Test-Path $pyprojectFile) {
    Push-Location $InstallDir
    python -m pip install --quiet -e .
    Pop-Location
    Write-Ok "vibe-agents package installed (editable)"
} else {
    Write-Warn "pyproject.toml not found, skipping package install"
}

# ==================== Step 5: Download NSSM ====================

Write-Step "Setting up NSSM (service manager)..."

$nssmDir = Join-Path $InstallDir "deploy\nssm"
$nssmExe = Join-Path $nssmDir "nssm.exe"

if (Test-Path $nssmExe) {
    Write-Ok "NSSM already present at $nssmExe"
} else {
    if (Test-CommandExists "nssm") {
        $nssmExe = (Get-Command nssm).Source
        Write-Ok "NSSM found in PATH: $nssmExe"
    } else {
        Write-Host "  Downloading NSSM..."
        $nssmZip = Join-Path $env:TEMP "nssm-2.24.zip"
        $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"

        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
            Expand-Archive -Path $nssmZip -DestinationPath $env:TEMP -Force
            New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null
            Copy-Item (Join-Path $env:TEMP "nssm-2.24\win64\nssm.exe") $nssmExe
            Write-Ok "NSSM downloaded to $nssmExe"
        } catch {
            Write-Fail "Could not download NSSM: $_"
            Write-Host "  Download manually from https://nssm.cc/download"
            Write-Host "  Place nssm.exe at: $nssmExe"
            exit 1
        }
    }
}

# ==================== Step 6: Remove Existing Service ====================

Write-Step "Configuring Windows service..."

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "  Stopping existing service..."
    & $nssmExe stop $ServiceName 2>$null
    Start-Sleep -Seconds 2
    & $nssmExe remove $ServiceName confirm 2>$null
    Write-Ok "Removed existing $ServiceName service"
}

# ==================== Step 7: Install Service ====================

$pythonExe = (python -c "import sys; print(sys.executable)").Trim()
$backendMain = Join-Path $InstallDir "backend\main.py"

# Use uvicorn module to run the server
& $nssmExe install $ServiceName $pythonExe "-m uvicorn backend.main:app --host 0.0.0.0 --port $Port"
& $nssmExe set $ServiceName AppDirectory $InstallDir
& $nssmExe set $ServiceName DisplayName "Vibe Agents Server"
& $nssmExe set $ServiceName Description "Vibe Agents - Multi-Agent AI Coding Platform"
& $nssmExe set $ServiceName Start SERVICE_AUTO_START

# Logging
$logDir = Join-Path $InstallDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
& $nssmExe set $ServiceName AppStdout (Join-Path $logDir "vibe-agents-stdout.log")
& $nssmExe set $ServiceName AppStderr (Join-Path $logDir "vibe-agents-stderr.log")
& $nssmExe set $ServiceName AppRotateFiles 1
& $nssmExe set $ServiceName AppRotateBytes 5242880  # 5MB rotation

# Restart on failure
& $nssmExe set $ServiceName AppExit Default Restart
& $nssmExe set $ServiceName AppRestartDelay 5000  # 5 second delay before restart

Write-Ok "Service '$ServiceName' installed"

# ==================== Step 8: Firewall Rule ====================

Write-Step "Configuring firewall..."

$ruleName = "Vibe Agents (Port $Port)"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if ($existingRule) {
    Remove-NetFirewallRule -DisplayName $ruleName
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Port `
    -Action Allow `
    -Profile Private | Out-Null

Write-Ok "Firewall rule added for port $Port (Private network)"

# ==================== Step 9: Start Service ====================

Write-Step "Starting service..."

& $nssmExe start $ServiceName
Start-Sleep -Seconds 3

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Ok "Service is running!"
} else {
    Write-Warn "Service may not have started. Check logs at:"
    Write-Host "    $logDir\vibe-agents-stderr.log"
}

# ==================== Step 10: Display Info ====================

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""

# Get local IP addresses
$localIPs = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.IPAddress -ne "127.0.0.1" } |
    Select-Object -ExpandProperty IPAddress

Write-Host "  Access Vibe Agents at:"
Write-Host "    Local:   http://localhost:$Port" -ForegroundColor Yellow
foreach ($ip in $localIPs) {
    Write-Host "    Network: http://${ip}:$Port" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Service management:"
Write-Host "    Start:   nssm start $ServiceName"
Write-Host "    Stop:    nssm stop $ServiceName"
Write-Host "    Restart: nssm restart $ServiceName"
Write-Host "    Status:  nssm status $ServiceName"
Write-Host "    Logs:    Get-Content $logDir\vibe-agents-stderr.log -Tail 50"
Write-Host ""
Write-Host "  Health check:"
Write-Host "    curl http://localhost:$Port/api/health"
Write-Host "    curl http://localhost:$Port/api/health/detailed"
Write-Host ""
Write-Host "  The service will auto-start on boot and restart on crash."
Write-Host ""
