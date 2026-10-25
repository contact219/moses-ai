@echo off
rem Starts Moses in a console window so you can watch the log (troubleshooting).
rem The Desktop / Start Menu shortcut starts him without a window instead.
cd /d "%~dp0"
if not exist env\Scripts\python.exe (
    echo Moses is not installed yet - run install.bat first.
    pause
    exit /b 1
)
set PYTHONUTF8=1
chcp 65001 >nul
env\Scripts\python.exe main.py
if errorlevel 1 pause
