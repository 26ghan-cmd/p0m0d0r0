#!/bin/bash
# Double-click this file in Finder to start Pomodoro on macOS.
# First run sets things up (about 30 seconds); after that it opens right away.

cd "$(dirname "$0")" || exit 1

pause_and_exit() {
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
}

# Find a Python 3 that has the window toolkit (tkinter).
# python.org's Python is tried first because its toolkit works best on macOS.
PY=""
for candidate in \
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
  /opt/homebrew/bin/python3 \
  /usr/local/bin/python3 \
  python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Pomodoro needs Python 3."
  echo "Opening the download page: install Python for macOS, then double-click this file again."
  open "https://www.python.org/downloads/macos/"
  pause_and_exit
fi

# Private copy of the one dependency (psutil), kept in a hidden .venv folder.
if ! .venv/bin/python -c "import psutil, tkinter" >/dev/null 2>&1; then
  echo "First run: setting up Pomodoro (about 30 seconds)..."
  rm -rf .venv
  "$PY" -m venv .venv \
    && .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
    || { echo "Setup failed. Check your internet connection and try again."; pause_and_exit; }
fi

echo "Starting Pomodoro. You can minimize this window, but keep it open while you study."
exec .venv/bin/python pomodoro.py
