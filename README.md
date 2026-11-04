# StudyLock

A desktop focus timer for college students. You set up a study session (how long, when to take breaks, and which apps you're allowed to use). While you're studying, every other app is closed the moment it opens. During breaks, and once the session ends, everything unlocks.

Works on **Windows** and **macOS**.

## Get it (easiest: no Python needed)

Go to the repo's **Releases** page (or the **latest** release) and download:

- **Mac (Apple Silicon: M1/M2/M3/M4):** `StudyLock-mac.zip`. Unzip it and move **StudyLock** into Applications.
- **Windows:** `StudyLock-windows.exe`

**Opening it the first time.** The app isn't signed by Apple or Microsoft, so your computer will ask you to confirm once:

- **Mac:** double-click StudyLock. When macOS says it can't be opened, go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to StudyLock. (On older macOS versions, right-click the app and choose **Open**.)
- **Windows:** if SmartScreen appears, click **More info → Run anyway**.

These downloads are rebuilt automatically every time code is pushed to `main`.

## Run from the code (double-click launcher)

Clone or download this repo, then double-click:

- **Mac:** `Start StudyLock.command`
- **Windows:** `Start StudyLock.bat`

The first run installs what it needs (about 30 seconds). After that it opens right away. If Python isn't installed, the launcher opens the python.org download page for you. On a Mac, if the launcher is blocked the first time, right-click it and choose **Open**.

Or run it from a terminal:

```bash
python3 -m pip install -r requirements.txt    # Windows: py -m pip install -r requirements.txt
python3 study_lock.py                         # Windows: py study_lock.py
```

Tkinter (the window toolkit) ships with the python.org installers for Windows and macOS. If you see `No module named tkinter` on a Mac with Homebrew Python, run `brew install python-tk`.

## How to use

1. **Session length**: total minutes, breaks included.
2. **Breaks**: e.g. a 10-minute break every 50 minutes. Set either value to 0 for no breaks. The plan line shows the exact schedule, and a session never ends on a break.
3. **Allowed apps**: pick from the apps open right now (double-click or **Allow →**), or type a name (e.g. `Notion`, `WINWORD`, `Google Chrome`). Your choices are saved for next time.
4. **Strict mode** (optional): hides the "End early" option and stops the window from being closed.
5. Press **Start session**. StudyLock lists any open apps that will be closed so you can save your work first.

During the session, the screen shows a countdown, what comes next, and a log of the apps it blocked. When a break starts or ends, the window chimes and jumps to the front. When the session ends, a message on the setup screen shows how many distractions were blocked.

## How the blocking works

- A background thread checks running apps about once a second during study blocks and closes any that aren't allowed (a gentle close first, then a force close if needed).
- **Windows:** an "app" is any program with a visible window that lives outside `C:\Windows`. Programs in the Windows folder (Explorer, Task Manager, Settings, system services) are never touched. An app's background helper processes are closed along with it.
- **macOS:** an "app" is any `.app` you can open, wherever it lives: `/Applications`, Apple's built-in apps (Safari, Messages, Mail, Music, FaceTime, Notes…), or an app run from Downloads. Helper processes inside the app bundle count as part of the app. System services in `/System/Library`, `/Library` and `~/Library` (Dock, menu bar, Spotlight, Control Center, background helpers) are never touched.
- **Essential apps are never blocked**, even if they're not on your allowed list. On macOS: System Settings, Finder, Activity Monitor, Terminal, iTerm, Console, Disk Utility, Keychain Access, Passwords, Screenshot, Software Update, Installer, Archive Utility. On Windows: Settings, Task Manager, Explorer and everything else in `C:\Windows`, plus Windows Terminal and Windows Security.
- Only your own user's apps are affected.
- StudyLock never closes itself, Python, or whatever launched it (your terminal or code editor).

## Known limits (good for a "future work" slide)

- It's not tamper-proof. A determined user can kill StudyLock from Task Manager or Activity Monitor.
- It blocks apps, not websites. If your browser is allowed, every site in it is allowed. A browser extension or hosts-file blocking would be the next step.
- On macOS, menu-bar apps (Dropbox, Rectangle, etc.) count as apps, so allow them if you want them to keep running.
- On Windows, Store apps that run inside `ApplicationFrameHost` (Calculator, Photos) can't be told apart, so they aren't blocked.

## Files

| File | What it does |
|---|---|
| `study_lock.py` | The app window: setup screen and live session screen |
| `engine.py` | Schedule builder, session timer, app detection, and blocking (no GUI code, easy to test) |
| `requirements.txt` | Python dependency (`psutil`) |
| `Start StudyLock.command` / `.bat` | Double-click launchers for Mac / Windows |
| `.github/workflows/build.yml` | Builds the Mac and Windows apps and publishes the "latest" release |

Settings are saved to `~/.studylock.json`.

## Optional: make a double-clickable app

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name StudyLock study_lock.py
```

The app ends up in `dist/`.
