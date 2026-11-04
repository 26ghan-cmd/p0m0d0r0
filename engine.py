"""
Pomodoro engine: session schedule, app detection, and app blocking.

This file has no GUI code so it can be tested on its own.
Supported platforms for blocking: Windows and macOS.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import psutil

STUDY, BREAK, DONE = "study", "break", "done"
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# A break is only scheduled if at least this much study time comes after it;
# otherwise the leftover time is added to the last study block.
MIN_STUDY_AFTER_BREAK = 5 * 60

# Essential apps: NEVER closed, no matter what the allowed list says.
# (Core system processes like the Dock, menu bar, Spotlight and Explorer are
# also never touched, because they live in protected system folders.)
ESSENTIAL_MAC = [
    "System Settings", "System Preferences", "Finder", "Activity Monitor",
    "Terminal", "iTerm", "iTerm2", "Console", "Disk Utility", "Keychain Access",
    "Passwords", "Screenshot", "Software Update", "Installer", "Archive Utility",
    "Accessibility Inspector", "VoiceOver Utility",
]
ESSENTIAL_WIN = [
    "WindowsTerminal", "OpenConsole", "SecHealthUI",  # terminal, Windows Security
]
_ALWAYS_HIDDEN = ["python", "pythonw", "py", "python3", "Python Launcher", "IDLE", "Pomodoro"]

ESSENTIAL_APPS = ESSENTIAL_MAC if IS_MAC else ESSENTIAL_WIN if IS_WINDOWS else []
ALWAYS_ALLOWED = {n.lower() for n in ESSENTIAL_MAC + ESSENTIAL_WIN + _ALWAYS_HIDDEN}

# macOS locations that hold system services and background helpers, never apps
# the user opens. Anything here is left alone.
MAC_PROTECTED_PREFIXES = ("/System/Library/", "/Library/", "/usr/", "/bin/",
                          "/sbin/", "/opt/", "/private/var/db/")

CONFIG_PATH = Path.home() / ".pomodoro.json"
LEGACY_CONFIG_PATH = Path.home() / ".studylock.json"  # settings from before the rename
DEFAULT_CONFIG = {
    "duration_min": 120,
    "break_every_min": 50,
    "break_len_min": 10,
    "strict": False,
    "allowed": [],
}


# --------------------------------------------------------------------------
# Schedule
# --------------------------------------------------------------------------
@dataclass
class Segment:
    kind: str      # STUDY or BREAK
    seconds: int


def build_schedule(total_min: float, break_every_min: float = 0,
                   break_len_min: float = 0) -> List[Segment]:
    """Split a session into alternating study / break blocks.

    Breaks count toward the total length. A session never ends on a break.
    Set break_every_min or break_len_min to 0 for no breaks.
    """
    total = int(round(total_min * 60))
    every = int(round(break_every_min * 60))
    blen = int(round(break_len_min * 60))
    if total <= 0:
        raise ValueError("Session length must be more than 0 minutes.")
    if every < 0 or blen < 0:
        raise ValueError("Break values can't be negative.")
    if every == 0 or blen == 0 or every >= total:
        return [Segment(STUDY, total)]

    min_after = min(MIN_STUDY_AFTER_BREAK, every)
    segments: List[Segment] = []
    remaining = total
    while remaining > 0:
        study = min(every, remaining)
        segments.append(Segment(STUDY, study))
        remaining -= study
        if remaining >= blen + min_after:
            segments.append(Segment(BREAK, blen))
            remaining -= blen
        elif remaining > 0:
            segments[-1].seconds += remaining  # too short for break + study
            remaining = 0
    return segments


def describe_schedule(segments: List[Segment], max_items: int = 7) -> str:
    parts = [f"{round(s.seconds / 60)}m {'study' if s.kind == STUDY else 'break'}"
             for s in segments]
    if len(parts) > max_items:
        parts = parts[:max_items] + ["…"]
    return " → ".join(parts)


# --------------------------------------------------------------------------
# Session timer
# --------------------------------------------------------------------------
@dataclass
class Status:
    phase: str                  # STUDY, BREAK or DONE
    phase_left: float           # seconds left in the current block
    total_left: float           # seconds left in the whole session
    index: int                  # index of the current block
    next_phase: Optional[str]   # kind of the next block, or None at the end
    next_seconds: int


class Session:
    def __init__(self, schedule: List[Segment],
                 clock: Callable[[], float] = time.monotonic):
        if not schedule:
            raise ValueError("Empty schedule")
        self.schedule = schedule
        self.clock = clock
        self.started = clock()
        self.total_seconds = sum(s.seconds for s in schedule)
        self.ended_early = False

    def end_early(self) -> None:
        self.ended_early = True

    def status(self) -> Status:
        n = len(self.schedule)
        if self.ended_early:
            return Status(DONE, 0, 0, n, None, 0)
        elapsed = self.clock() - self.started
        start = 0
        for i, seg in enumerate(self.schedule):
            end = start + seg.seconds
            if elapsed < end:
                nxt = self.schedule[i + 1] if i + 1 < n else None
                return Status(seg.kind, end - elapsed, self.total_seconds - elapsed, i,
                              nxt.kind if nxt else None, nxt.seconds if nxt else 0)
            start = end
        return Status(DONE, 0, 0, n, None, 0)


# --------------------------------------------------------------------------
# App detection
# --------------------------------------------------------------------------
def normalize(name: str) -> str:
    """Compare app names loosely: 'Discord.exe' == 'discord' == 'Discord.app'."""
    n = name.strip().lower()
    for suffix in (".exe", ".app"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def mac_identity(exe: str, home: str) -> Optional[str]:
    """App name for a macOS process, or None if it isn't a user app.

    Any process inside a .app bundle counts, wherever the app lives
    (/Applications, Apple's built-in apps like Safari and Messages, apps run
    from Downloads...). The outermost bundle is used, so helper processes
    ('Google Chrome Helper') count as their parent app. System services in
    /System/Library, /Library and ~/Library are never touched.
    """
    if not exe or ".app/" not in exe:
        return None
    if exe.startswith(MAC_PROTECTED_PREFIXES):
        return None
    if exe.startswith(home.rstrip("/") + "/Library/"):
        return None
    for part in exe.split("/"):
        if part.endswith(".app"):
            return part[:-4]
    return None


def windows_identity(exe: str, windir: str) -> Optional[str]:
    """App name for a Windows process (exe name), or None for Windows' own
    programs (anything inside C:\\Windows is never touched)."""
    if not exe:
        return None
    path = exe.replace("/", "\\")
    root = windir.replace("/", "\\").rstrip("\\").lower() + "\\"
    if path.lower().startswith(root):
        return None
    base = path.rsplit("\\", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base or None


def _windows_visible_pids() -> set:
    """PIDs that own a visible, titled, normal (non-tool) window."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x00000080
    pids = set()
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if (user32.IsWindowVisible(hwnd)
                and user32.GetWindowTextLengthW(hwnd) > 0
                and not (user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return pids


def _current_user() -> Optional[str]:
    try:
        return psutil.Process().username()
    except psutil.Error:
        return None


def platform_supported() -> bool:
    return IS_WINDOWS or IS_MAC


def list_running_apps() -> Dict[str, List[psutil.Process]]:
    """Map app name -> its running processes, for the current user's apps only.

    Windows: apps that currently have a visible window (background helpers
    of those apps are included so the whole app closes).
    macOS: any app bundle outside the protected system folders.
    """
    if not platform_supported():
        return {}
    me = _current_user()
    if me is None:
        return {}
    home = str(Path.home())
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    apps: Dict[str, List[psutil.Process]] = {}
    for proc in psutil.process_iter(["username"]):
        if proc.info.get("username") != me:
            continue
        try:
            exe = proc.exe() or ""
        except psutil.Error:
            continue
        ident = mac_identity(exe, home) if IS_MAC else windows_identity(exe, windir)
        if ident:
            apps.setdefault(ident, []).append(proc)

    if IS_WINDOWS:
        try:
            visible = _windows_visible_pids()
            apps = {k: v for k, v in apps.items() if any(p.pid in visible for p in v)}
        except Exception:
            pass
    return apps


# --------------------------------------------------------------------------
# Enforcement
# --------------------------------------------------------------------------
def _protected_pids() -> set:
    """Pomodoro's own process and everything that launched it (terminal,
    code editor...). Closing those would close Pomodoro too."""
    pids = set()
    try:
        p = psutil.Process()
        while p is not None:
            pids.add(p.pid)
            p = p.parent()
    except psutil.Error:
        pass
    return pids


class Enforcer:
    def __init__(self, allowed: Iterable[str],
                 lister: Callable[[], Dict[str, List[psutil.Process]]] = list_running_apps):
        self.allowed = {normalize(a) for a in allowed} | {normalize(a) for a in ALWAYS_ALLOWED}
        self.lister = lister
        self.protected = _protected_pids()

    def blocked_now(self) -> Dict[str, List[psutil.Process]]:
        """Apps running right now that are not allowed."""
        out = {}
        for name, procs in self.lister().items():
            if normalize(name) in self.allowed:
                continue
            if any(p.pid in self.protected for p in procs):
                continue
            out[name] = procs
        return out

    def sweep(self) -> List[str]:
        """Close every app that isn't allowed. Returns names of apps closed."""
        blocked = self.blocked_now()
        if not blocked:
            return []
        owner = {}
        for name, procs in blocked.items():
            for p in procs:
                owner[p.pid] = name
                try:
                    p.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        # One shared wait for all apps, then force-close anything still open.
        everything = [p for procs in blocked.values() for p in procs]
        gone, alive = psutil.wait_procs(everything, timeout=1.0)
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        closed_pids = {p.pid for p in gone} | {p.pid for p in alive if not p.is_running()}
        return sorted({owner[pid] for pid in closed_pids})


class EnforcementLoop(threading.Thread):
    """Background thread: once a second, close non-allowed apps while
    should_enforce() is True (i.e. during study blocks)."""

    def __init__(self, enforcer: Enforcer, should_enforce: Callable[[], bool],
                 on_closed: Callable[[str], None], interval: float = 1.0):
        super().__init__(daemon=True)
        self.enforcer = enforcer
        self.should_enforce = should_enforce
        self.on_closed = on_closed
        self.interval = interval
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                if self.should_enforce():
                    for name in self.enforcer.sweep():
                        self.on_closed(name)
            except Exception:
                pass  # never let one bad sweep stop the lock
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
            break
        except (OSError, ValueError):
            continue
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass
