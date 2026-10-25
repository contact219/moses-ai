@echo off
rem Double-click to install Moses on Windows. Runs install.ps1 without
rem changing the system's PowerShell script policy.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
