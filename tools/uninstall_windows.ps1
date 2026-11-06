$ErrorActionPreference = "SilentlyContinue"
$base = Join-Path $env:LOCALAPPDATA "TransferLoop"
$appDir = Join-Path $base "App"
$startMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TransferLoop.lnk"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\TransferLoop"

if (Get-Process -Name "TransferLoop" -ErrorAction SilentlyContinue) {
    Write-Host "TransferLoop is running. Close it and run the uninstaller again."
    exit 1
}

Remove-Item -Recurse -Force $appDir
Remove-Item -Force $startMenuShortcut
Remove-Item -Recurse -Force $uninstallKey

Write-Host "TransferLoop was uninstalled."
Write-Host "Your settings, project history, and backups remain in: $(Join-Path $base 'Data')"

$scriptPath = $MyInvocation.MyCommand.Path
Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c", "timeout /t 1 /nobreak >nul & del /q `"$scriptPath`""
