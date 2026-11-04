@echo off
rem Double-click this file to start StudyLock on Windows.
rem First run sets things up (about 30 seconds); after that it opens right away.
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

.venv\Scripts\python.exe -c "import psutil, tkinter" >nul 2>nul
if errorlevel 1 (
  echo First run: setting up StudyLock ^(about 30 seconds^)...
  if exist .venv rmdir /s /q .venv
  %PY% -m venv .venv || goto fail
  .venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fail
)

start "" .venv\Scripts\pythonw.exe study_lock.py
exit /b 0

:nopython
echo StudyLock needs Python 3. Opening the download page...
echo Install it (tick "Add python.exe to PATH"), then double-click this file again.
start https://www.python.org/downloads/windows/
pause
exit /b 1

:fail
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
