@echo off
setlocal EnableExtensions
set "SCRIPT=%LOCALAPPDATA%\TransferLoop\uninstall_windows.ps1"
if exist "%SCRIPT%" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\uninstall_windows.ps1"
)
pause
