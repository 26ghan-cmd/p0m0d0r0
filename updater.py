"""
Pomodoro self-updater for the downloaded app (Mac .app / Windows .exe).

When the app opens it asks GitHub whether the "latest" release was built from
a different commit than this copy. If so, the setup screen offers "Update now",
which downloads the new build, swaps it in place and restarts Pomodoro.

Because the update is downloaded by Pomodoro itself (not a web browser), macOS
doesn't quarantine it, so the "Open Anyway" step is only ever needed once.

Running from source (the launcher) doesn't use this: the launcher runs
`git pull` instead.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO = "26ghan-cmd/p0m0d0r0"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/tag/latest"

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")
ASSET = "Pomodoro-mac.zip" if IS_MAC else "Pomodoro-windows.exe" if IS_WINDOWS else None

try:  # written by the GitHub build; missing when running from source
    from build_info import COMMIT as BUILD_COMMIT
except ImportError:
    BUILD_COMMIT = None


class UpdateError(Exception):
    """A problem worth showing to the user as-is."""


@dataclass
class Update:
    commit: str
    url: str
    size: int


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) and BUILD_COMMIT is not None and ASSET is not None


def current_version() -> str:
    return BUILD_COMMIT[:7] if BUILD_COMMIT else "source"


def _open(url: str, timeout: float):
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Pomodoro-updater",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def check_for_update(timeout: float = 10) -> Optional[Update]:
    """Return the newer build, or None if up to date (or not a packaged app)."""
    if not is_packaged():
        return None
    with _open(RELEASE_API, timeout) as r:
        data = json.load(r)
    commit = data.get("target_commitish") or ""
    if not commit or commit == BUILD_COMMIT:
        return None
    for asset in data.get("assets", []):
        if asset.get("name") == ASSET:
            return Update(commit, asset["browser_download_url"], int(asset.get("size") or 0))
    return None


def _download(update: Update, dest: Path, progress: Optional[Callable[[float], None]]) -> None:
    done = 0
    with _open(update.url, 60) as r, open(dest, "wb") as out:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress and update.size:
                progress(min(1.0, done / update.size))
    if update.size and dest.stat().st_size != update.size:
        raise UpdateError("The download was incomplete. Check your internet connection and try again.")


def _detached(cmd) -> None:
    """Start a process that keeps running after Pomodoro quits."""
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  close_fds=True)
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


# ------------------------------------------------------------------ macOS
def _mac_app_path() -> Path:
    app = Path(sys.executable).resolve().parents[2]  # .../Pomodoro.app/Contents/MacOS/Pomodoro
    if app.suffix != ".app":
        raise UpdateError("Couldn't find the Pomodoro app to update.")
    if "AppTranslocation" in str(app):
        raise UpdateError("macOS is running Pomodoro from a temporary location. Drag Pomodoro "
                          "into your Applications folder, open it from there, then update.")
    if not os.access(app.parent, os.W_OK):
        raise UpdateError(f"Pomodoro can't write to {app.parent}. Move it into your "
                          "Applications folder and try again.")
    return app


def _install_mac(update: Update, progress) -> None:
    app = _mac_app_path()
    tmp = Path(tempfile.mkdtemp(prefix="pomodoro-update-"))
    zip_path = tmp / ASSET
    _download(update, zip_path, progress)
    unpacked = tmp / "unpacked"
    if subprocess.run(["/usr/bin/ditto", "-x", "-k", str(zip_path), str(unpacked)]).returncode != 0:
        raise UpdateError("Couldn't unpack the update.")
    new_app = unpacked / "Pomodoro.app"
    if not (new_app / "Contents" / "MacOS").is_dir():
        raise UpdateError("The downloaded update looks broken. Try again later.")
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(new_app)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    backup = app.with_name(app.name + ".old")
    shutil.rmtree(backup, ignore_errors=True)
    os.rename(app, backup)  # the running app keeps working from its moved files
    try:
        if subprocess.run(["/usr/bin/ditto", str(new_app), str(app)]).returncode != 0:
            raise UpdateError("Couldn't put the new version in place.")
    except BaseException:
        shutil.rmtree(app, ignore_errors=True)
        os.rename(backup, app)
        raise
    q = shlex.quote
    _detached(["/bin/sh", "-c", f"sleep 2; /usr/bin/open -n {q(str(app))}; "
                                f"sleep 5; rm -rf {q(str(backup))} {q(str(tmp))}"])


# ---------------------------------------------------------------- Windows
def _install_windows(update: Update, progress) -> None:
    exe = Path(sys.executable).resolve()
    if not os.access(exe.parent, os.W_OK):
        raise UpdateError(f"Pomodoro can't write to {exe.parent}. Move Pomodoro to a folder "
                          "like Documents or Desktop and try again.")
    new = exe.with_name(exe.stem + ".new.exe")
    _download(update, new, progress)
    old = exe.with_name(f"{exe.stem}.old-{int(time.time())}.exe")
    os.rename(exe, old)  # Windows allows renaming a running program, not replacing it
    try:
        os.rename(new, exe)
    except BaseException:
        os.rename(old, exe)
        raise
    _detached([str(exe)])


def install(update: Update, progress: Optional[Callable[[float], None]] = None) -> None:
    """Download and swap in the update, then start the new version.
    The caller should quit Pomodoro right after this returns."""
    if not is_packaged():
        raise UpdateError("Updates are only for the downloaded app.")
    try:
        if IS_MAC:
            _install_mac(update, progress)
        else:
            _install_windows(update, progress)
    except UpdateError:
        raise
    except OSError as e:
        raise UpdateError(f"Couldn't install the update ({e.strerror or e}).") from e
    except Exception as e:
        raise UpdateError(f"Couldn't install the update ({e}).") from e


def cleanup_leftovers() -> None:
    """Remove old copies left behind by a previous Windows update."""
    if not (is_packaged() and IS_WINDOWS):
        return
    exe = Path(sys.executable).resolve()
    for leftover in exe.parent.glob(exe.stem + ".old-*.exe"):
        try:
            leftover.unlink()
        except OSError:
            pass  # still in use; next launch will get it
