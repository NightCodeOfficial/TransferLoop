@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title TransferLoop Setup

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "BUILD_DIR=%PROJECT_DIR%\build\windows"
set "DIST_DIR=%BUILD_DIR%\dist\TransferLoop"

set "PYTHON_EXE="
set "PYTHON_ARGS="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
    )
)
if not defined PYTHON_EXE (
    where python >nul 2>&1
    if not errorlevel 1 (
        python --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)
if not defined PYTHON_EXE goto :NO_PYTHON

"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :OLD_PYTHON

if not exist "%VENV_PYTHON%" (
    echo Creating build environment...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :FAILED
)

echo Installing build dependencies...
"%VENV_PYTHON%" -m pip install -r "%PROJECT_DIR%\requirements.txt" -r "%PROJECT_DIR%\requirements-build.txt"
if errorlevel 1 goto :FAILED

echo Preparing Windows application resources...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
"%VENV_PYTHON%" "%PROJECT_DIR%\tools\build_windows_assets.py" > "%BUILD_DIR%\version.txt"
if errorlevel 1 goto :FAILED
set /p APP_VERSION=<"%BUILD_DIR%\version.txt"

echo Building TransferLoop.exe...
if exist "%BUILD_DIR%\dist" rmdir /s /q "%BUILD_DIR%\dist"
if exist "%BUILD_DIR%\work" rmdir /s /q "%BUILD_DIR%\work"
"%VENV_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name TransferLoop ^
  --icon "%BUILD_DIR%\transferloop.ico" ^
  --version-file "%BUILD_DIR%\version_info.txt" ^
  --distpath "%BUILD_DIR%\dist" ^
  --workpath "%BUILD_DIR%\work" ^
  --specpath "%BUILD_DIR%" ^
  "%PROJECT_DIR%\app.py"
if errorlevel 1 goto :FAILED
if not exist "%DIST_DIR%\TransferLoop.exe" goto :FAILED

echo Installing TransferLoop...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\tools\install_windows.ps1" -SourceDir "%DIST_DIR%" -Version "%APP_VERSION%" -ProjectRoot "%PROJECT_DIR%"
if errorlevel 1 goto :FAILED

echo.
echo Setup complete. TransferLoop is available from the Start Menu.
echo run.bat remains available for source/debug use.
echo.
pause
exit /b 0

:NO_PYTHON
echo ERROR: Python 3.10 or newer was not found.
echo Install Python, then run setup.bat again.
pause
exit /b 1

:OLD_PYTHON
echo ERROR: TransferLoop requires Python 3.10 or newer.
pause
exit /b 1

:FAILED
echo.
echo ERROR: TransferLoop setup did not complete.
echo Review the messages above, close TransferLoop if it is running, and try again.
pause
exit /b 1
