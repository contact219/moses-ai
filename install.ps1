# ============================================================
#  Moses AI Assistant - Windows Installer
#  Run with install.bat (double-click), or from PowerShell:
#    powershell -ExecutionPolicy Bypass -File install.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Step($n, $msg) { Write-Host "[$n/7] $msg" -ForegroundColor Yellow }
function Ok($msg)       { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg)     { Write-Host "  !!  $msg" -ForegroundColor Red }
function Fail($msg)     { Warn $msg; Write-Host ""; Read-Host "Press Enter to close"; exit 1 }

Write-Host ""
Write-Host "  M.O.S.E.S  AI Assistant - Windows Installer"
Write-Host "  ============================================"
Write-Host ""

# -- 1. Python ---------------------------------------------------
# 3.12 / 3.13 have prebuilt wheels for every dependency; 3.14 works too.
Step 1 "Finding Python..."
function Find-Python {
    foreach ($v in "3.13", "3.12", "3.14") {
        try {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch {}
    }
    try {
        $out = & python -c "import sys; print(sys.version_info >= (3, 12), sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -like "True *") { return $out.Substring(5).Trim() }
    } catch {}
    return $null
}
$Python = Find-Python
if (-not $Python) {
    Warn "Python 3.12 or newer was not found."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $ans = Read-Host "  Install Python 3.13 now with winget? [Y/n]"
        if ($ans -eq "" -or $ans -match "^[Yy]") {
            winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            $Python = Find-Python
        }
    }
    if (-not $Python) {
        Fail "Install Python 3.13 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this installer again."
    }
}
Ok "Using $Python"

# -- 2. Virtual environment --------------------------------------
Step 2 "Creating Python virtual environment..."
$VenvPy = Join-Path $Root "env\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    & $Python -m venv env
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}
& $VenvPy -m pip install --upgrade pip --quiet
Ok "Virtual environment ready (env\)"

# -- 3. Python packages ------------------------------------------
Step 3 "Installing Python packages (this may take a few minutes)..."
& $VenvPy -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Fail "Package install failed - see the messages above." }
Ok "Python packages installed"

# -- 4. Playwright browser ---------------------------------------
Step 4 "Installing Playwright browser (Chromium)..."
& $VenvPy -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Warn "Playwright browser install failed - browser automation won't work until you rerun this." }
else { Ok "Playwright ready" }

# -- 5. Config + memory ------------------------------------------
Step 5 "Setting up configuration..."
$Cfg = Join-Path $Root "config\api_keys.json"
if (-not (Test-Path $Cfg)) {
    Copy-Item (Join-Path $Root "config\api_keys.template.json") $Cfg
}
$conf = Get-Content $Cfg -Raw -Encoding UTF8 | ConvertFrom-Json
$conf.os_system = "windows"
if ($conf.gemini_api_key -eq "YOUR_GEMINI_API_KEY_HERE" -or -not $conf.gemini_api_key) {
    Write-Host "  Paste your Gemini API key (free at https://aistudio.google.com/app/apikey)"
    $key = Read-Host "  or press Enter to add it later"
    if ($key.Trim()) { $conf.gemini_api_key = $key.Trim() }
}
# UTF-8 without BOM: Python's json module rejects a BOM.
[IO.File]::WriteAllText($Cfg, ($conf | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
Ok "config\api_keys.json ready (os_system = windows)"

$Mem = Join-Path $Root "memory\long_term.json"
if (-not (Test-Path $Mem)) {
    $empty = '{ "identity": {}, "preferences": {}, "projects": {}, "relationships": {}, "wishes": {}, "notes": {} }'
    [IO.File]::WriteAllText($Mem, $empty, (New-Object Text.UTF8Encoding $false))
    Ok "Memory store initialized"
}

# -- 6. Icon -----------------------------------------------------
Step 6 "Making the app icon..."
$Ico = Join-Path $Root "assets\moses.ico"
& $VenvPy -c "from PIL import Image; im = Image.open(r'assets\moses-face.jpg'); s = min(im.size); im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2)); im.save(r'assets\moses.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])"
if (Test-Path $Ico) { Ok "assets\moses.ico" } else { Warn "Icon not created - the shortcut will use a default icon." }

# -- 7. Shortcuts ------------------------------------------------
Step 7 "Creating Desktop and Start Menu shortcuts..."
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Moses.lnk"))
    $lnk.TargetPath       = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $lnk.Arguments        = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Root\start_moses.ps1`""
    $lnk.WorkingDirectory = $Root
    $lnk.WindowStyle      = 7   # minimized: no console flash
    $lnk.Description      = "Moses AI Assistant"
    if (Test-Path $Ico) { $lnk.IconLocation = $Ico }
    $lnk.Save()
}
Ok "Shortcuts created"

# -- Done --------------------------------------------------------
Write-Host ""
Write-Host "  Moses is installed!" -ForegroundColor Green
Write-Host ""
$conf = Get-Content $Cfg -Raw -Encoding UTF8 | ConvertFrom-Json
if ($conf.gemini_api_key -eq "YOUR_GEMINI_API_KEY_HERE") {
    Write-Host "  NEXT STEP: add your Gemini API key to config\api_keys.json" -ForegroundColor Yellow
    Write-Host "  (or just start Moses - the setup screen will ask for it)."
    Write-Host ""
}
Write-Host "  Start Moses from the Desktop icon or the Start Menu."
Write-Host "  If something goes wrong, run start_moses.bat to see the log in a window,"
Write-Host "  or open logs\moses.log."
Write-Host ""
Read-Host "Press Enter to close"
