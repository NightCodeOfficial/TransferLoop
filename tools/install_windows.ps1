param(
    [Parameter(Mandatory=$true)][string]$SourceDir,
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot.TrimEnd([char[]]"\/"))
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir.TrimEnd([char[]]"\/"))
$base = Join-Path $env:LOCALAPPDATA "TransferLoop"
$appDir = Join-Path $base "App"
$dataDir = Join-Path $base "Data"
$exe = Join-Path $appDir "TransferLoop.exe"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcut = Join-Path $startMenu "TransferLoop.lnk"
$uninstallScript = Join-Path $base "uninstall_windows.ps1"
$installedIcon = Join-Path $appDir "transferloop.ico"

if (Get-Process -Name "TransferLoop" -ErrorAction SilentlyContinue) {
    throw "TransferLoop is running. Close it before installing or updating."
}

New-Item -ItemType Directory -Force -Path $base | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
if (Test-Path $appDir) {
    Remove-Item -Recurse -Force $appDir
}
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $SourceDir "*") $appDir
Copy-Item -Force (Join-Path $ProjectRoot "tools\uninstall_windows.ps1") $uninstallScript
Copy-Item -Force (Join-Path $ProjectRoot "build\windows\transferloop.ico") $installedIcon

if (Test-Path $shortcut) {
    Remove-Item -Force $shortcut
}

$wsh = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($shortcut)
$link.TargetPath = $exe
$link.WorkingDirectory = $appDir
$link.IconLocation = $installedIcon
$link.Description = "TransferLoop"
$link.Save()

$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\TransferLoop"
New-Item -Force -Path $uninstallKey | Out-Null
Set-ItemProperty -Path $uninstallKey -Name "DisplayName" -Value "TransferLoop"
Set-ItemProperty -Path $uninstallKey -Name "DisplayVersion" -Value $Version
Set-ItemProperty -Path $uninstallKey -Name "Publisher" -Value "TransferLoop"
Set-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $appDir
Set-ItemProperty -Path $uninstallKey -Name "DisplayIcon" -Value $installedIcon
Set-ItemProperty -Path $uninstallKey -Name "UninstallString" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`""
Set-ItemProperty -Path $uninstallKey -Name "NoModify" -Type DWord -Value 1
Set-ItemProperty -Path $uninstallKey -Name "NoRepair" -Type DWord -Value 1


Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ShellRefresh {
    [DllImport("shell32.dll")]
    public static extern void SHChangeNotify(uint wEventId, uint uFlags, IntPtr dwItem1, IntPtr dwItem2);
}
"@
[ShellRefresh]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
$ie4uinit = Join-Path $env:SystemRoot "System32\ie4uinit.exe"
if (Test-Path $ie4uinit) {
    Start-Process -FilePath $ie4uinit -ArgumentList "-show" -WindowStyle Hidden -Wait
}

Write-Host ""
Write-Host "TransferLoop $Version installed."
Write-Host "Start Menu shortcut: $shortcut"
Write-Host "Application: $appDir"
Write-Host "User data: $dataDir"
