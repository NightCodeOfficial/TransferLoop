#!/usr/bin/env bash
set -u

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQ_FILE="$PROJECT_DIR/requirements.txt"
REQ_MARKER="$VENV_DIR/.transferloop_requirements.txt"
APP_FILE="$PROJECT_DIR/app.py"

cd "$PROJECT_DIR" || exit 1

printf '\nTransferLoop\n------------\n'

PYTHON_EXE=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            PYTHON_EXE="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON_EXE" ]]; then
    printf '\nERROR: Python 3.10 or newer was not found.\n'
    printf 'Install Python 3.10+ and make sure python3 or python is available on PATH.\n\n'
    exit 1
fi

if [[ ! -f "$REQ_FILE" ]]; then
    printf '\nERROR: requirements.txt was not found in:\n%s\n' "$PROJECT_DIR"
    printf 'Make sure run.sh is located in the TransferLoop project folder.\n\n'
    exit 1
fi

if [[ ! -f "$APP_FILE" ]]; then
    printf '\nERROR: app.py was not found in:\n%s\n' "$PROJECT_DIR"
    printf 'Make sure run.sh is located in the TransferLoop project folder.\n\n'
    exit 1
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    printf 'Creating project virtual environment...\n'
    if ! "$PYTHON_EXE" -m venv "$VENV_DIR"; then
        printf '\nERROR: Could not create the project virtual environment.\n'
        printf 'On Debian/Ubuntu, install the Python venv package (for example: sudo apt install python3-venv).\n\n'
        exit 1
    fi
fi

INSTALL_DEPS=0
if [[ ! -f "$REQ_MARKER" ]] || ! cmp -s "$REQ_FILE" "$REQ_MARKER"; then
    INSTALL_DEPS=1
fi

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    printf 'Installing TransferLoop dependencies...\n'
    if ! "$VENV_PYTHON" -m pip install -r "$REQ_FILE"; then
        printf '\nERROR: TransferLoop dependencies could not be installed.\n'
        printf 'Check the messages above for details, then run this file again.\n\n'
        exit 1
    fi
    if ! cp "$REQ_FILE" "$REQ_MARKER"; then
        printf '\nERROR: Could not save the dependency state marker.\n\n'
        exit 1
    fi
else
    printf 'Dependencies are already installed.\n'
fi

printf 'Starting TransferLoop...\n\n'
"$VENV_PYTHON" "$APP_FILE"
APP_EXIT=$?

if [[ "$APP_EXIT" -ne 0 ]]; then
    printf '\nTransferLoop exited with error code %s.\n' "$APP_EXIT"
fi

exit "$APP_EXIT"
