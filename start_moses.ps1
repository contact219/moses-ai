# Starts Moses with no console window; output goes to logs\moses.log.
# For a visible console (troubleshooting), run start_moses.bat instead.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
$env:PYTHONUTF8 = "1"        # prompts, memory and log lines are UTF-8 (emoji included)
$env:PYTHONUNBUFFERED = "1"  # log lines appear as they happen
Start-Process -FilePath (Join-Path $Root "env\Scripts\python.exe") `
    -ArgumentList "main.py" -WorkingDirectory $Root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "logs\moses.log") `
    -RedirectStandardError  (Join-Path $Root "logs\moses.err.log")
