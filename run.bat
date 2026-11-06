@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title TransferLoop

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%PROJECT_DIR%requirements.txt"
set "REQ_MARKER=%VENV_DIR%\.transferloop_requirements.txt"
set "APP_FILE=%PROJECT_DIR%app.py"

echo.
echo TransferLoop
echo ------------

rem Find a usable Python installation.
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
        if not errorlevel 1 (
            set "PYTHON_EXE=python"
            set "PYTHON_ARGS="
        )
    )
)

if not defined PYTHON_EXE goto :NO_PYTHON

rem TransferLoop currently requires Python 3.10 or newer.
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :OLD_PYTHON

if not exist "%REQ_FILE%" goto :NO_REQUIREMENTS
if not exist "%APP_FILE%" goto :NO_APP

rem Create the project-local virtual environment when needed.
if not exist "%VENV_PYTHON%" (
    echo Creating project virtual environment...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :VENV_FAILED
)

rem Install dependencies only when requirements.txt is new or has changed.
set "INSTALL_DEPS=0"

if not exist "%REQ_MARKER%" (
    set "INSTALL_DEPS=1"
) else (
    fc /b "%REQ_FILE%" "%REQ_MARKER%" >nul 2>&1
    if errorlevel 1 set "INSTALL_DEPS=1"
)

if "%INSTALL_DEPS%"=="1" (
    echo Installing TransferLoop dependencies...
    "%VENV_PYTHON%" -m pip install -r "%REQ_FILE%"
    if errorlevel 1 goto :DEPENDENCY_FAILED

    copy /y "%REQ_FILE%" "%REQ_MARKER%" >nul
    if errorlevel 1 goto :DEPENDENCY_FAILED
) else (
    echo Dependencies are already installed.
)

echo Starting TransferLoop...
echo.
"%VENV_PYTHON%" "%APP_FILE%"
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo TransferLoop exited with error code %APP_EXIT%.
    pause
)

exit /b %APP_EXIT%

:NO_PYTHON
echo.
echo ERROR: Python was not found.
echo.
echo TransferLoop requires Python 3.10 or newer.
echo Install Python, make sure the Python launcher or python.exe is available
echo on PATH, then run this file again.
echo.
pause
exit /b 1

:OLD_PYTHON
echo.
echo ERROR: TransferLoop requires Python 3.10 or newer.
echo A Python installation was found, but it is too old.
echo.
pause
exit /b 1

:NO_REQUIREMENTS
echo.
echo ERROR: requirements.txt was not found in:
echo "%PROJECT_DIR%"
echo.
echo Make sure run.bat is located in the TransferLoop project folder.
echo.
pause
exit /b 1

:NO_APP
echo.
echo ERROR: app.py was not found in:
echo "%PROJECT_DIR%"
echo.
echo Make sure run.bat is located in the TransferLoop project folder.
echo.
pause
exit /b 1

:VENV_FAILED
echo.
echo ERROR: Could not create the project virtual environment.
echo.
pause
exit /b 1

:DEPENDENCY_FAILED
echo.
echo ERROR: TransferLoop dependencies could not be installed.
echo Check the messages above for details, then run this file again.
echo.
pause
exit /b 1
