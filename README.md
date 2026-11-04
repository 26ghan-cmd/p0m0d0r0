# Pomodoro

A desktop focus timer for college students. You set up a study session (how long, when to take breaks, and which apps and websites you're allowed to use). While you're studying, every other app is closed the moment it opens, and on a Mac, tabs on other websites are closed too. During breaks, and once the session ends, everything unlocks.

Works on **Windows** and **macOS**.

## Get it (easiest: no Python needed)

Go to the repo's **Releases** page (or the **latest** release) and download:

- **Mac (Apple Silicon: M1/M2/M3/M4):** `Pomodoro-mac.zip`. Unzip it and move **Pomodoro** into Applications.
- **Windows:** `Pomodoro-windows.exe`

### Opening it the first time

The app isn't signed by Apple or Microsoft, so your computer will ask you to confirm it once. This is expected and doesn't mean anything is wrong with the app.

**Mac.** The first time you double-click Pomodoro, macOS shows a box titled **"Pomodoro" Not Opened**, saying Apple could not verify it is free of malware.

1. Click **Done**. Don't click "Move to Trash".
2. Open **System Settings → Privacy & Security**.
3. Scroll down to the **Security** section. You'll see a line saying "Pomodoro" was blocked. Click **Open Anyway**.
4. Enter your Mac password, then click **Open** on the final prompt.

You only need to do this once. After that, Pomodoro opens normally. On older macOS versions you can instead right-click the app and choose **Open**.

If the **Open Anyway** button doesn't appear, clear the block from Terminal (this assumes you moved the app into Applications), then double-click Pomodoro again:

```bash
xattr -dr com.apple.quarantine /Applications/Pomodoro.app
```

**Windows.** If a blue SmartScreen box appears, click **More info → Run anyway**.

These downloads are rebuilt automatically every time code is pushed to `main`.

## Run from the code (double-click launcher)

Clone or download this repo, then double-click:

- **Mac:** `Start Pomodoro.command`
- **Windows:** `Start Pomodoro.bat`

The first run installs what it needs (about 30 seconds). After that it opens right away. If Python isn't installed, the launcher opens the python.org download page for you. On a Mac, if the launcher is blocked the first time, right-click it and choose **Open**.

Or run it from a terminal:

```bash
python3 -m pip install -r requirements.txt    # Windows: py -m pip install -r requirements.txt
python3 pomodoro.py                         # Windows: py pomodoro.py
```

Tkinter (the window toolkit) ships with the python.org installers for Windows and macOS. If you see `No module named tkinter` on a Mac with Homebrew Python, run `brew install python-tk`.

## How to use

1. **Session length**: total minutes, breaks included.
2. **Breaks**: e.g. a 10-minute break every 50 minutes. Set either value to 0 for no breaks. The plan line shows the exact schedule, and a session never ends on a break.
3. **Allowed apps**: pick from the apps open right now (double-click or **Allow →**), or type a name (e.g. `Notion`, `WINWORD`, `Google Chrome`). Your choices are saved for next time.
4. **Allowed websites** (Mac, optional): on the **Allowed websites** tab, turn on **Only allow these websites while studying** and add sites (see below).
5. **Strict mode** (optional): hides the "End early" option and stops the window from being closed.
6. Press **Start session**. Pomodoro lists any open apps that will be closed so you can save your work first.

During the session, the screen shows a countdown, what comes next, and a log of the apps and websites it blocked. When a break starts or ends, the window chimes and jumps to the front. When the session ends, a message on the setup screen shows how many distractions were blocked.

## Allowed websites (Mac)

When **Only allow these websites while studying** is on, Pomodoro checks your browser tabs about once a second during study blocks and closes any tab on a website that isn't on your list. Breaks unlock every site.

- **Browsers it can watch:** Safari, Google Chrome, Microsoft Edge, Brave, Arc, Chromium and Vivaldi. Your browser also has to be on the **Allowed apps** list, or it's closed like any other app.
- **Browsers it can't watch:** Firefox, Opera, Zen, DuckDuckGo, Orion and Tor Browser don't let other apps see their tabs. If one of them is an allowed app, every website in it works. Pomodoro warns you when you start a session, and the fix is to leave that browser off the allowed apps list.
- **Adding sites:** type a site like `docs.google.com` or paste a full link. A site includes its subdomains, so `instructure.com` covers `myschool.instructure.com` (Canvas). Add a path to allow only part of a site: `google.com/search` allows Google searches but not Gmail or YouTube.
- **Always allowed:** new-tab pages, browser settings, local files, and the Google, Microsoft, Apple, Okta and Duo sign-in pages, so logging in to Canvas or Google Docs keeps working. If your school's own login page gets closed, add it to your list.

### Giving permission the first time

The first time a session starts with website limits on, macOS asks once per browser: **"Pomodoro" wants access to control "Safari"** (or Chrome, etc.). Click **OK** (or **Allow**). If you started Pomodoro with the launcher, the prompt names **Terminal** instead of Pomodoro.

If you clicked **Don't Allow**, Pomodoro shows a red warning during the session. To fix it, open **System Settings → Privacy & Security → Automation**, find **Pomodoro** (or **Terminal**), and turn on the browser.

## How the blocking works

- A background thread checks running apps about once a second during study blocks and closes any that aren't allowed (a gentle close first, then a force close if needed).
- **Windows:** an "app" is any program with a visible window that lives outside `C:\Windows`. Programs in the Windows folder (Explorer, Task Manager, Settings, system services) are never touched. An app's background helper processes are closed along with it.
- **macOS:** an "app" is any `.app` you can open, wherever it lives: `/Applications`, Apple's built-in apps (Safari, Messages, Mail, Music, FaceTime, Notes…), or an app run from Downloads. Helper processes inside the app bundle count as part of the app. System services in `/System/Library`, `/Library` and `~/Library` (Dock, menu bar, Spotlight, Control Center, background helpers) are never touched.
- **Essential apps are never blocked**, even if they're not on your allowed list. On macOS: System Settings, Finder, Activity Monitor, Terminal, iTerm, Console, Disk Utility, Keychain Access, Passwords, Screenshot, Software Update, Installer, Archive Utility. On Windows: Settings, Task Manager, Explorer and everything else in `C:\Windows`, plus Windows Terminal and Windows Security.
- Only your own user's apps are affected.
- Pomodoro never closes itself, Python, or whatever launched it (your terminal or code editor).

## Known limits (good for a "future work" slide)

- The downloadable apps aren't signed, which is why first-time users see a security warning. Removing it would mean signing and notarizing the Mac app with an Apple Developer account ($99/year) and signing the Windows app with a code-signing certificate.
- It's not tamper-proof. A determined user can kill Pomodoro from Task Manager or Activity Monitor.
- Website limits work on macOS only, and only in browsers that let other apps see their tabs (see above). A browser extension would extend them to Windows and Firefox.
- A blocked website can show for up to a second before its tab closes.
- On macOS, menu-bar apps (Dropbox, Rectangle, etc.) count as apps, so allow them if you want them to keep running.
- On Windows, Store apps that run inside `ApplicationFrameHost` (Calculator, Photos) can't be told apart, so they aren't blocked.

## Files

| File | What it does |
|---|---|
| `pomodoro.py` | The app window: setup screen and live session screen |
| `engine.py` | Schedule builder, session timer, app detection, and blocking (no GUI code, easy to test) |
| `sites.py` | Website allow list: matching sites and closing browser tabs on macOS |
| `requirements.txt` | Python dependency (`psutil`) |
| `Start Pomodoro.command` / `.bat` | Double-click launchers for Mac / Windows |
| `.github/workflows/build.yml` | Builds the Mac and Windows apps and publishes the "latest" release |

Settings are saved to `~/.pomodoro.json`.

## Optional: make a double-clickable app

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name Pomodoro pomodoro.py
```

The app ends up in `dist/`.
