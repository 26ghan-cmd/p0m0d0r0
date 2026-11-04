"""
Pomodoro website allow-list (macOS).

During study blocks, Pomodoro reads the open tabs of supported browsers
through AppleScript and closes any tab whose website isn't on the allowed
list. The first time, macOS asks once per browser for permission to let
Pomodoro (or Terminal, when started from the launcher) control it.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

IS_MAC = sys.platform == "darwin"

# Browsers whose tabs can be read and closed with AppleScript.
SUPPORTED_BROWSERS = [
    "Safari", "Google Chrome", "Microsoft Edge", "Brave Browser", "Arc",
    "Chromium", "Vivaldi",
]
# Browsers with no AppleScript tab control: sites in them can't be limited.
UNSUPPORTED_BROWSERS = [
    "Firefox", "Firefox Developer Edition", "Firefox Nightly", "Opera", "Opera GX",
    "Zen", "Zen Browser", "DuckDuckGo", "Orion", "Tor Browser", "LibreWolf", "Waterfox",
]

# Sign-in pages that study sites redirect to. Always allowed so logging in
# to Canvas, Google Docs, Outlook etc. keeps working.
ALWAYS_ALLOWED_SITES = [
    "accounts.google.com", "login.microsoftonline.com", "login.live.com",
    "login.microsoft.com", "appleid.apple.com", "okta.com", "duosecurity.com",
    "duo.com",
]

Site = Tuple[str, str]  # (host, path prefix or "")


def website_limits_supported() -> bool:
    return IS_MAC


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------
def parse_site(text: str) -> Optional[Site]:
    """Turn what the user typed into (host, path).

    'https://www.YouTube.com/' -> ('youtube.com', '')
    'google.com/search'        -> ('google.com', '/search')
    """
    t = text.strip()
    if not t:
        return None
    if "://" not in t:
        t = "http://" + t
    try:
        parts = urlsplit(t)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host and host != "localhost":
        return None
    path = parts.path.rstrip("/")
    return host, path


def site_label(site: Site) -> str:
    return site[0] + site[1]


def url_allowed(url: str, allowed: Iterable[Site]) -> bool:
    """True if this tab's URL may stay open.

    Only http(s) pages are checked; new-tab pages, settings pages, local
    files etc. are always fine. A site also allows its subdomains
    ('instructure.com' allows 'myschool.instructure.com').
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return True
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or "/"
    for a_host, a_path in allowed:
        if host == a_host or host.endswith("." + a_host):
            if not a_path or path == a_path or path.startswith(a_path + "/"):
                return True
    return False


def host_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or url).lower()
    except ValueError:
        return url
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------
# Talking to browsers
# --------------------------------------------------------------------------
def _as_string(s: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def list_tabs_script(browser: str) -> str:
    # Separators are made outside the 'tell' block: inside it, words like
    # 'tab' and 'character' would mean the browser's own objects.
    return f'''set sep to character id 9
set nl to character id 10
set out to ""
tell application {_as_string(browser)}
    set wc to count of windows
    repeat with w from 1 to wc
        try
            set tc to count of tabs of window w
            repeat with t from 1 to tc
                set u to URL of tab t of window w
                if u is missing value then set u to ""
                set out to out & w & sep & t & sep & u & nl
            end repeat
        end try
    end repeat
end tell
return out'''


def close_tabs_script(browser: str, tabs: List[Tuple[int, int, str]]) -> str:
    """Close tabs (window, tab, url). Highest indices go first so earlier
    closes don't shift later ones; each tab is re-checked by URL first."""
    lines = [f"tell application {_as_string(browser)}"]
    for w, t, url in sorted(tabs, reverse=True):
        lines += ["    try",
                  f"        if URL of tab {t} of window {w} is {_as_string(url)} then "
                  f"close tab {t} of window {w}",
                  "    end try"]
    lines.append("end tell")
    return "\n".join(lines)


def run_osascript(script: str) -> Tuple[int, str, str]:
    try:
        # Long timeout: the very first call may wait on macOS's permission prompt.
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=90)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timed out"
    except OSError as e:
        return 1, "", str(e)


def parse_tab_list(out: str) -> List[Tuple[int, int, str]]:
    tabs = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        try:
            tabs.append((int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            continue
    return tabs


def permission_message(browser: str) -> str:
    return (f"Pomodoro isn't allowed to see {browser}'s tabs, so websites there aren't "
            f"limited. Fix: System Settings → Privacy & Security → Automation → turn on "
            f"{browser} under Pomodoro (or under Terminal if you used the launcher).")


class SiteGuard:
    def __init__(self, allowed_sites: Iterable[str],
                 runner: Callable[[str], Tuple[int, str, str]] = run_osascript):
        parsed = [parse_site(s) for s in list(allowed_sites) + ALWAYS_ALLOWED_SITES]
        self.allowed: List[Site] = [p for p in parsed if p]
        self.runner = runner
        self.reported: set = set()

    def sweep(self, running_apps: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Close disallowed tabs in every running supported browser.

        Returns (hosts of closed tabs, new problem messages)."""
        closed, problems = [], []
        running = set(running_apps)
        for browser in SUPPORTED_BROWSERS:
            if browser not in running:
                continue  # never talk to a browser that isn't open (it would launch)
            code, out, err = self.runner(list_tabs_script(browser))
            if code != 0:
                if ("-1743" in err or "Not authorized" in err) and browser not in self.reported:
                    self.reported.add(browser)
                    problems.append(permission_message(browser))
                continue
            bad = [tab for tab in parse_tab_list(out) if not url_allowed(tab[2], self.allowed)]
            if not bad:
                continue
            code, _, _ = self.runner(close_tabs_script(browser, bad))
            if code == 0:
                closed += [host_of(url) for _, _, url in bad]
        return closed, problems


class SiteLoop(threading.Thread):
    """Background thread: about once a second during study blocks, close tabs
    on websites that aren't allowed. Separate from the app blocker so a
    slow browser (or a permission prompt) never delays app blocking."""

    def __init__(self, guard: SiteGuard, running_apps: Callable[[], List[str]],
                 should_enforce: Callable[[], bool], on_closed: Callable[[str], None],
                 on_problem: Callable[[str], None], interval: float = 1.0):
        super().__init__(daemon=True)
        self.guard = guard
        self.running_apps = running_apps
        self.should_enforce = should_enforce
        self.on_closed = on_closed
        self.on_problem = on_problem
        self.interval = interval
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                if self.should_enforce():
                    closed, problems = self.guard.sweep(self.running_apps())
                    for host in closed:
                        self.on_closed(host)
                    for msg in problems:
                        self.on_problem(msg)
            except Exception:
                pass
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()
