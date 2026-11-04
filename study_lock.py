"""
StudyLock — study sessions that lock distracting apps.

Pick a session length, optional breaks, and the apps you're allowed to use.
During study blocks every other app is closed the moment it opens.
During breaks (and when the session ends) everything is unlocked.

Run:   python study_lock.py
"""
import queue
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import engine
from engine import BREAK, DONE, STUDY

STUDY_COLOR = "#2563eb"
BREAK_COLOR = "#16a34a"
MUTED = "#6b7280"


def fmt(seconds: float) -> str:
    s = max(0, int(seconds + 0.999))  # round up so the clock never shows 00:00 early
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def minutes_text(seconds: int) -> str:
    m = round(seconds / 60)
    return f"{m} min"


class StudyLockApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("StudyLock")
        root.minsize(620, 560)

        self.cfg = engine.load_config()
        self.allowed = list(self.cfg.get("allowed", []))
        self.session = None
        self.loop = None
        self.closed_queue = queue.Queue()
        self.closed_counts = {}
        self.last_phase = None

        self._fonts()
        self.setup_frame = self._build_setup()
        self.session_frame = self._build_session()
        self.show_setup()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        if not engine.platform_supported():
            messagebox.showwarning(
                "StudyLock",
                "App blocking only works on Windows and macOS.\n"
                "The timer will still run, but no apps will be closed.")

    # ------------------------------------------------------------------ UI
    def _fonts(self):
        family = tkfont.nametofont("TkDefaultFont").actual()["family"]
        self.f_title = tkfont.Font(family=family, size=18, weight="bold")
        self.f_phase = tkfont.Font(family=family, size=22, weight="bold")
        self.f_clock = tkfont.Font(family=family, size=60, weight="bold")
        self.f_small = tkfont.Font(family=family, size=10)

    def _build_setup(self) -> ttk.Frame:
        f = ttk.Frame(self.root, padding=18)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)

        ttk.Label(f, text="New study session", font=self.f_title).grid(row=0, column=0, sticky="w")

        # --- timing settings
        s = ttk.Frame(f)
        s.grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.var_duration = tk.StringVar(value=str(self.cfg["duration_min"]))
        self.var_every = tk.StringVar(value=str(self.cfg["break_every_min"]))
        self.var_blen = tk.StringVar(value=str(self.cfg["break_len_min"]))
        rows = [("Session length (minutes)", self.var_duration),
                ("Take a break every (minutes)", self.var_every),
                ("Break length (minutes)", self.var_blen)]
        for r, (label, var) in enumerate(rows):
            ttk.Label(s, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
            ttk.Spinbox(s, from_=0, to=720, increment=5, textvariable=var, width=7).grid(
                row=r, column=1, sticky="w")
            var.trace_add("write", lambda *_: self.update_plan())
        ttk.Label(s, text="Set either break value to 0 for no breaks.",
                  foreground=MUTED, font=self.f_small).grid(row=3, column=0, columnspan=2, sticky="w")
        self.var_strict = tk.BooleanVar(value=bool(self.cfg.get("strict", False)))
        ttk.Checkbutton(s, text="Strict mode (no ending the session early)",
                        variable=self.var_strict).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.plan_label = ttk.Label(f, foreground=MUTED, wraplength=560)
        self.plan_label.grid(row=2, column=0, sticky="w", pady=(6, 10))

        # --- allowed apps picker
        box = ttk.LabelFrame(f, text="Allowed apps — everything else closes during study time",
                             padding=10)
        box.grid(row=3, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.columnconfigure(2, weight=1)
        box.rowconfigure(1, weight=1)

        ttk.Label(box, text="Open right now").grid(row=0, column=0, sticky="w")
        ttk.Label(box, text="Allowed").grid(row=0, column=2, sticky="w")
        self.lb_running = tk.Listbox(box, selectmode="extended", exportselection=False, height=10)
        self.lb_allowed = tk.Listbox(box, selectmode="extended", exportselection=False, height=10)
        self.lb_running.grid(row=1, column=0, sticky="nsew")
        self.lb_allowed.grid(row=1, column=2, sticky="nsew")
        self.lb_running.bind("<Double-Button-1>", lambda _e: self.add_selected())
        self.lb_allowed.bind("<Double-Button-1>", lambda _e: self.remove_selected())

        mid = ttk.Frame(box, padding=(8, 0))
        mid.grid(row=1, column=1)
        ttk.Button(mid, text="Allow →", command=self.add_selected).pack(fill="x", pady=2)
        ttk.Button(mid, text="← Remove", command=self.remove_selected).pack(fill="x", pady=2)
        ttk.Button(mid, text="Refresh", command=self.refresh_running).pack(fill="x", pady=(12, 2))

        add = ttk.Frame(box)
        add.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        add.columnconfigure(1, weight=1)
        ttk.Label(add, text="Add by name:").grid(row=0, column=0, padx=(0, 6))
        self.var_manual = tk.StringVar()
        entry = ttk.Entry(add, textvariable=self.var_manual)
        entry.grid(row=0, column=1, sticky="ew")
        entry.bind("<Return>", lambda _e: self.add_manual())
        ttk.Button(add, text="Add", command=self.add_manual).grid(row=0, column=2, padx=(6, 0))
        ttk.Label(add, text="Tip: allow the apps you study with (browser, notes, PDF reader) "
                            "before starting. Not open yet? Type its name, e.g. Notion or WINWORD.",
                  foreground=MUTED, font=self.f_small, wraplength=560).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Button(f, text="Start session", command=self.start).grid(
            row=4, column=0, sticky="e", pady=(14, 0), ipadx=12, ipady=4)
        return f

    def _build_session(self) -> ttk.Frame:
        f = ttk.Frame(self.root, padding=24)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(6, weight=1)

        self.lbl_phase = tk.Label(f, text="", font=self.f_phase)
        self.lbl_phase.grid(row=0, column=0)
        self.lbl_sub = ttk.Label(f, text="", foreground=MUTED)
        self.lbl_sub.grid(row=1, column=0, pady=(2, 0))
        self.lbl_clock = tk.Label(f, text="00:00", font=self.f_clock)
        self.lbl_clock.grid(row=2, column=0, pady=(6, 0))
        self.progress = ttk.Progressbar(f, maximum=100, mode="determinate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(8, 4))
        self.lbl_total = ttk.Label(f, text="")
        self.lbl_total.grid(row=4, column=0)
        self.lbl_allowed = ttk.Label(f, text="", foreground=MUTED, wraplength=540, justify="center")
        self.lbl_allowed.grid(row=5, column=0, pady=(10, 6))

        log = ttk.LabelFrame(f, text="Blocked this session", padding=8)
        log.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        log.columnconfigure(0, weight=1)
        log.rowconfigure(0, weight=1)
        self.lb_closed = tk.Listbox(log, height=5, activestyle="none")
        self.lb_closed.grid(row=0, column=0, sticky="nsew")

        self.btn_end = ttk.Button(f, text="End session early", command=self.end_early)
        self.btn_end.grid(row=7, column=0, pady=(14, 0))
        return f

    def show_setup(self):
        self.session_frame.pack_forget()
        self.setup_frame.pack(fill="both", expand=True)
        self.refresh_allowed()
        self.refresh_running()
        self.update_plan()

    def show_session(self):
        self.setup_frame.pack_forget()
        self.session_frame.pack(fill="both", expand=True)

    # ------------------------------------------------------- allowed list
    def _is_allowed(self, name: str) -> bool:
        return engine.normalize(name) in {engine.normalize(a) for a in self.allowed}

    def refresh_running(self):
        try:
            names = sorted(engine.list_running_apps().keys(), key=str.lower)
        except Exception:
            names = []
        self.lb_running.delete(0, "end")
        for n in names:
            if not self._is_allowed(n) and engine.normalize(n) not in engine.ALWAYS_ALLOWED:
                self.lb_running.insert("end", n)

    def refresh_allowed(self):
        self.lb_allowed.delete(0, "end")
        for n in sorted(self.allowed, key=str.lower):
            self.lb_allowed.insert("end", n)

    def _add(self, name: str):
        name = name.strip()
        if name.lower().endswith((".exe", ".app")):
            name = name[:-4]
        if name and not self._is_allowed(name):
            self.allowed.append(name)

    def add_selected(self):
        for i in self.lb_running.curselection():
            self._add(self.lb_running.get(i))
        self.refresh_allowed()
        self.refresh_running()

    def remove_selected(self):
        drop = {engine.normalize(self.lb_allowed.get(i)) for i in self.lb_allowed.curselection()}
        self.allowed = [a for a in self.allowed if engine.normalize(a) not in drop]
        self.refresh_allowed()
        self.refresh_running()

    def add_manual(self):
        self._add(self.var_manual.get())
        self.var_manual.set("")
        self.refresh_allowed()
        self.refresh_running()

    # ------------------------------------------------------------ session
    def _read_settings(self):
        try:
            duration = float(self.var_duration.get())
            every = float(self.var_every.get() or 0)
            blen = float(self.var_blen.get() or 0)
        except ValueError:
            raise ValueError("Please enter numbers for the session and break times.")
        return duration, every, blen

    def update_plan(self):
        try:
            schedule = engine.build_schedule(*self._read_settings())
            breaks = sum(1 for s in schedule if s.kind == BREAK)
            self.plan_label.config(
                text=f"Plan: {engine.describe_schedule(schedule)}   "
                     f"({breaks} break{'s' if breaks != 1 else ''})",
                foreground=MUTED)
        except ValueError as e:
            self.plan_label.config(text=str(e), foreground="#dc2626")

    def start(self):
        try:
            duration, every, blen = self._read_settings()
            schedule = engine.build_schedule(duration, every, blen)
        except ValueError as e:
            messagebox.showerror("StudyLock", str(e))
            return

        self.cfg.update(duration_min=duration, break_every_min=every, break_len_min=blen,
                        strict=self.var_strict.get(), allowed=self.allowed)
        engine.save_config(self.cfg)

        enforcer = engine.Enforcer(self.allowed)
        try:
            open_now = sorted(enforcer.blocked_now().keys(), key=str.lower)
        except Exception:
            open_now = []

        msg = f"Start a {minutes_text(int(duration * 60))} session?\n\n"
        if open_now:
            msg += ("These open apps are not allowed and will close right away:\n  • "
                    + "\n  • ".join(open_now) + "\n\nSave your work in them first.\n\n")
        if self.var_strict.get():
            msg += "Strict mode is on: you won't be able to end the session early."
        if not messagebox.askokcancel("Start session", msg.strip()):
            return

        self.session = engine.Session(schedule)
        self.closed_counts = {}
        self.lb_closed.delete(0, "end")
        self.last_phase = None
        self.loop = engine.EnforcementLoop(
            enforcer,
            should_enforce=lambda: self.session is not None and self.session.status().phase == STUDY,
            on_closed=self.closed_queue.put)
        self.loop.start()

        allowed_txt = ", ".join(sorted(self.allowed, key=str.lower)) or "none"
        self.lbl_allowed.config(text=f"Allowed during study: {allowed_txt}")
        if self.var_strict.get():
            self.btn_end.config(text="Strict mode — can't end early", state="disabled")
        else:
            self.btn_end.config(text="End session early", state="normal")

        self.show_session()
        self.tick()

    def tick(self):
        if self.session is None:
            return
        self._drain_closed()
        st = self.session.status()
        if st.phase == DONE:
            self.finish()
            return
        if st.phase != self.last_phase:
            self._phase_changed(st.phase, first=self.last_phase is None)
            self.last_phase = st.phase

        self.lbl_clock.config(text=fmt(st.phase_left))
        total = self.session.total_seconds
        self.progress["value"] = 100 * (total - st.total_left) / total
        if st.next_phase == BREAK:
            nxt = f"then a {minutes_text(st.next_seconds)} break"
        elif st.next_phase == STUDY:
            nxt = "then back to studying"
        else:
            nxt = "then you're done"
        self.lbl_total.config(text=f"Session ends in {fmt(st.total_left)}  ·  {nxt}")
        self.root.after(250, self.tick)

    def _phase_changed(self, phase: str, first: bool):
        if phase == STUDY:
            self.lbl_phase.config(text="Focus time", fg=STUDY_COLOR)
            self.lbl_clock.config(fg=STUDY_COLOR)
            self.lbl_sub.config(text="Only your allowed apps can run.")
        else:
            self.lbl_phase.config(text="Break — apps unlocked", fg=BREAK_COLOR)
            self.lbl_clock.config(fg=BREAK_COLOR)
            self.lbl_sub.config(text="Stretch, grab water. Apps lock again when the timer ends.")
        if not first:
            self._get_attention()

    def _get_attention(self):
        self.root.bell()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1500, lambda: self.root.attributes("-topmost", False))

    def _drain_closed(self):
        changed = False
        while True:
            try:
                name = self.closed_queue.get_nowait()
            except queue.Empty:
                break
            self.closed_counts[name] = self.closed_counts.get(name, 0) + 1
            changed = True
        if changed:
            self.lb_closed.delete(0, "end")
            for name, n in sorted(self.closed_counts.items(), key=lambda kv: -kv[1]):
                self.lb_closed.insert("end", f"{name} — closed {n}×")

    def end_early(self):
        if self.session is None or self.var_strict.get():
            return
        if messagebox.askyesno("End session", "End this study session now? All apps will unlock."):
            self.session.end_early()

    def _stop_session(self):
        if self.loop:
            self.loop.stop()
            self.loop = None
        self.session = None
        self.last_phase = None

    def finish(self):
        early = self.session.ended_early
        self._drain_closed()
        blocked = sum(self.closed_counts.values())
        self._stop_session()
        self._get_attention()
        if early:
            messagebox.showinfo("StudyLock", "Session ended early. All apps are unlocked.")
        else:
            messagebox.showinfo(
                "StudyLock",
                f"Session complete — nice work!\n\nDistractions blocked: {blocked}\n"
                "All apps are unlocked.")
        self.show_setup()

    def on_close(self):
        if self.session is not None:
            if self.var_strict.get():
                messagebox.showwarning("StudyLock", "Strict mode is on — StudyLock stays open "
                                                    "until the session ends.")
                return
            if not messagebox.askyesno("Quit StudyLock", "A session is running. End it and quit?"):
                return
            self._stop_session()
        self.root.destroy()


def main():
    try:  # crisp text on high-DPI Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    StudyLockApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
