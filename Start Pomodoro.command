#!/bin/bash
# Double-click this file in Finder to start Pomodoro on macOS.
# First run sets things up (about 30 seconds); after that it opens right away.

cd "$(dirname "$0")" || exit 1

pause_and_exit() {
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
}

# Get the latest version if this folder came from `git clone`.
# (xcode-select check: on a Mac without developer tools, running git would pop up an installer.)
if [ -d .git ] && xcode-select -p >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  echo "Checking for updates..."
  GIT_TERMINAL_PROMPT=0 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 \
    pull --ff-only --quiet 2>/dev/null \
    || echo "(Couldn't check for updates. Starting the version you have.)"
fi

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

# Private copy of the dependencies, kept in a hidden .venv folder. Set up on the
# first run, and again whenever an update changes requirements.txt.
if ! .venv/bin/python -c "import psutil, tkinter" >/dev/null 2>&1; then
  echo "First run: setting up Pomodoro (about 30 seconds)..."
  rm -rf .venv
  "$PY" -m venv .venv || { echo "Setup failed."; pause_and_exit; }
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
    && cp requirements.txt .venv/requirements.installed \
    || { echo "Setup failed. Check your internet connection and try again."; pause_and_exit; }
fi

echo "Starting Pomodoro. You can minimize this window, but keep it open while you study."
exec .venv/bin/python pomodoro.py
