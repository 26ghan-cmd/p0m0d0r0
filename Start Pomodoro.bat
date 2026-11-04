@echo off
rem Double-click this file to start Pomodoro on Windows.
rem First run sets things up (about 30 seconds); after that it opens right away.
cd /d "%~dp0"

rem Get the latest version if this folder came from git clone.
if not exist .git goto afterupdate
where git >nul 2>nul || goto afterupdate
echo Checking for updates...
set "GIT_TERMINAL_PROMPT=0"
git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 pull --ff-only --quiet 2>nul || echo Couldn't check for updates. Starting the version you have.
:afterupdate

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

rem Private copy of the dependencies in a hidden .venv folder. Set up on the
rem first run, and again whenever an update changes requirements.txt.
.venv\Scripts\python.exe -c "import psutil, tkinter" >nul 2>nul
if not errorlevel 1 goto checkreqs
echo First run: setting up Pomodoro, about 30 seconds...
if exist .venv rmdir /s /q .venv
%PY% -m venv .venv || goto fail

:checkreqs
fc /b requirements.txt .venv\requirements.installed >nul 2>nul && goto run
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fail
copy /y requirements.txt .venv\requirements.installed >nul

:run
start "" .venv\Scripts\pythonw.exe pomodoro.py
exit /b 0

:nopython
echo Pomodoro needs Python 3. Opening the download page...
echo Install it, tick "Add python.exe to PATH", then double-click this file again.
start https://www.python.org/downloads/windows/
pause
exit /b 1

:fail
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
