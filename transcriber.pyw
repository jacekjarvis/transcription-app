#!/usr/bin/env python3
"""
Whisper Transcriber — a simple double-click GUI for OpenAI Whisper on Windows.

Pick one or more audio/video files, choose language + model + output format,
press Transcribe, and watch a real progress bar (driven by the file's duration
from ffprobe vs. Whisper's live timestamp output). No terminal, no flags.

Depends on tools already installed on this machine:
  - whisper  (openai-whisper CLI)
  - ffprobe  (from ffmpeg) — used to read each file's duration for the progress bar
"""

import ctypes
from ctypes import wintypes
import glob
import os
import re
import shutil
import subprocess
import threading
import time
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUDIO_EXTS = ["mp3", "wav", "m4a", "aac", "flac", "ogg", "oga", "wma", "opus"]
VIDEO_EXTS = ["mp4", "mov", "mkv", "avi", "webm", "m4v", "flv", "wmv", "mpg", "mpeg"]

# Display name -> value passed to `whisper --language`. Empty = auto-detect.
LANGUAGES = [
    ("Auto-detect", ""),
    ("English", "English"),
    ("Spanish", "Spanish"),
    ("French", "French"),
    ("German", "German"),
    ("Italian", "Italian"),
    ("Portuguese", "Portuguese"),
    ("Dutch", "Dutch"),
    ("Polish", "Polish"),
    ("Russian", "Russian"),
    ("Ukrainian", "Ukrainian"),
    ("Japanese", "Japanese"),
    ("Chinese", "Chinese"),
    ("Korean", "Korean"),
    ("Arabic", "Arabic"),
    ("Hindi", "Hindi"),
    ("Turkish", "Turkish"),
    ("Greek", "Greek"),
    ("Czech", "Czech"),
    ("Swedish", "Swedish"),
    ("Norwegian", "Norwegian"),
    ("Danish", "Danish"),
    ("Finnish", "Finnish"),
    ("Romanian", "Romanian"),
    ("Hungarian", "Hungarian"),
    ("Welsh", "Welsh"),
]

MODELS = ["tiny", "base", "small", "medium", "large"]
FORMATS = ["All", "txt", "srt", "vtt", "json"]

# Matches Whisper's verbose lines, e.g. "[00:00.000 --> 00:12.480]  some text"
TIMESTAMP_RE = re.compile(
    r"\[\s*(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*-->\s*"
    r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*\]\s*(.*)"
)

# Matches Whisper's one-time model-download progress bar (tqdm), e.g.
# "43%|████▎     | 615M/1.42G [00:30<00:40, 19.8MiB/s]"
DOWNLOAD_RE = re.compile(r"^\s*(\d{1,3})%\|[^|]*\|\s*([\d.]+\w*)/([\d.]+\w*)\s*\[")

# Windows-only: hide the console window that subprocesses would otherwise flash.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# ---------------------------------------------------------------------------
# Process-cleanup helpers.
#
# `whisper.exe` is a launcher stub that spawns a *separate* python.exe child
# to do the actual work, so terminating just the stub leaves the real worker
# running invisibly in the background. Two layers of defense:
#   1. A Windows Job Object with KILL_ON_JOB_CLOSE, so the OS itself kills
#      every process we spawned (and their children) the instant this app's
#      own process ends, for ANY reason -- clean quit, crash, or being force-
#      killed via Task Manager.
#   2. `taskkill /T /F` on Cancel / normal window close, for an immediate,
#      complete kill of the whole process tree rather than waiting on OS
#      cleanup semantics.
# ---------------------------------------------------------------------------

def _create_kill_on_close_job():
    """Returns (job_handle, assign_fn) or (None, None) if unavailable."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount",
                "WriteTransferCount", "OtherTransferCount")]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9
        PROCESS_TERMINATE = 0x0001
        PROCESS_SET_QUOTA = 0x0100

        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None, None

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(info))

        def assign(pid):
            hproc = kernel32.OpenProcess(
                PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, pid)
            if not hproc:
                return False
            ok = kernel32.AssignProcessToJobObject(job, hproc)
            kernel32.CloseHandle(hproc)
            return bool(ok)

        return job, assign
    except Exception:
        return None, None


def kill_process_tree(pid):
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def _hms_to_seconds(h, m, s):
    return (int(h) if h else 0) * 3600 + int(m) * 60 + float(s)


def find_tool(exe_name, extra_globs):
    """Locate a command-line tool, falling back to known winget install
    locations. Needed because a tool installed moments ago via winget (e.g.
    by Setup.bat) may not be on PATH yet in the current process/session —
    Windows only refreshes PATH for new processes after a fresh logon.
    """
    found = shutil.which(exe_name)
    if found:
        return found
    for pattern in extra_globs:
        matches = sorted(glob.glob(os.path.expandvars(pattern)), reverse=True)
        if matches:
            return matches[0]
    return None


def find_whisper():
    return find_tool("whisper", [
        r"%LocalAppData%\Programs\Python\Python3*\Scripts\whisper.exe",
    ])


def find_ffprobe():
    return find_tool("ffprobe", [
        r"%LocalAppData%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffprobe.exe",
    ])


class TranscriberApp:
    def __init__(self, root):
        self.root = root
        root.title("Whisper Transcriber")
        root.geometry("760x620")
        root.minsize(680, 540)

        self.files = []                 # queued file paths
        self.worker = None              # background thread
        self.proc = None                # current subprocess.Popen
        self.cancel_flag = threading.Event()
        self.ui_queue = queue.Queue()   # thread -> UI messages

        # Job Object safety net: ensures whisper subprocesses are killed by
        # Windows itself if this app dies unexpectedly (crash, Task Manager).
        self.job_handle, self._assign_to_job = _create_kill_on_close_job()

        # Tracks what the current file is doing, for the "still working"
        # status ticker (see _tick_phase): preparing -> [downloading] ->
        # transcribing -> idle.
        self.phase = "idle"
        self.phase_started_at = None
        self.phase_ctx = (0, 0, "")

        self.whisper_path = find_whisper()
        self.ffprobe_path = find_ffprobe()
        # Whisper shells out to `ffmpeg` internally by name (not full path),
        # so make sure ffmpeg's folder is on PATH for the subprocess even if
        # it isn't yet on PATH for this app's own process (e.g. right after
        # Setup.bat installed it, before Windows has refreshed PATH).
        self.subprocess_env = os.environ.copy()
        if self.ffprobe_path:
            ffmpeg_dir = os.path.dirname(self.ffprobe_path)
            if ffmpeg_dir not in self.subprocess_env.get("PATH", ""):
                self.subprocess_env["PATH"] = (
                    ffmpeg_dir + os.pathsep + self.subprocess_env.get("PATH", ""))

        self._build_ui()
        self._poll_ui_queue()
        self._tick_phase()

        if not self.whisper_path:
            messagebox.showerror(
                "Whisper not found",
                "Could not find the 'whisper' command on your PATH.\n\n"
                "Install it with:\n    pip install openai-whisper\n\n"
                "Then reopen this app.",
            )

    # ---------------------------------------------------------------- UI build
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- File list ---
        files_frame = ttk.LabelFrame(self.root, text="Files to transcribe")
        files_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        list_wrap = ttk.Frame(files_frame)
        list_wrap.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self.listbox = tk.Listbox(list_wrap, selectmode=tk.EXTENDED, height=6,
                                  activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_wrap, orient="vertical",
                           command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        btn_row = ttk.Frame(files_frame)
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_row, text="Add files…",
                   command=self.add_files).pack(side="left")
        ttk.Button(btn_row, text="Add folder…",
                   command=self.add_folder).pack(side="left", padx=(6, 0))
        ttk.Button(btn_row, text="Remove selected",
                   command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(btn_row, text="Clear all",
                   command=self.clear_all).pack(side="left", padx=(6, 0))

        # --- Options ---
        opts = ttk.LabelFrame(self.root, text="Options")
        opts.pack(fill="x", padx=10, pady=4)

        row1 = ttk.Frame(opts)
        row1.pack(fill="x", **pad)

        ttk.Label(row1, text="Language:").pack(side="left")
        self.language_var = tk.StringVar(value="English")
        self.language_cb = ttk.Combobox(
            row1, textvariable=self.language_var, state="readonly", width=14,
            values=[name for name, _ in LANGUAGES])
        self.language_cb.pack(side="left", padx=(4, 16))

        ttk.Label(row1, text="Model:").pack(side="left")
        self.model_var = tk.StringVar(value="medium")
        self.model_cb = ttk.Combobox(
            row1, textvariable=self.model_var, state="readonly", width=9,
            values=MODELS)
        self.model_cb.pack(side="left", padx=(4, 16))

        ttk.Label(row1, text="Output:").pack(side="left")
        self.format_var = tk.StringVar(value="srt")
        self.format_cb = ttk.Combobox(
            row1, textvariable=self.format_var, state="readonly", width=7,
            values=FORMATS)
        self.format_cb.pack(side="left", padx=(4, 0))

        ttk.Label(opts, text="Tip: 'large' is the most accurate but noticeably "
                             "slower on a CPU. 'medium' is a good balance.",
                  foreground="#666").pack(anchor="w", padx=10, pady=(0, 4))

        # --- Output folder ---
        outf = ttk.Frame(opts)
        outf.pack(fill="x", **pad)
        self.same_folder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(outf, text="Save next to each source file",
                        variable=self.same_folder_var,
                        command=self._toggle_outdir).pack(side="left")
        self.outdir_var = tk.StringVar(value="")
        self.outdir_entry = ttk.Entry(outf, textvariable=self.outdir_var,
                                      state="disabled")
        self.outdir_entry.pack(side="left", fill="x", expand=True, padx=(10, 6))
        self.outdir_btn = ttk.Button(outf, text="Browse…",
                                     command=self.choose_outdir,
                                     state="disabled")
        self.outdir_btn.pack(side="left")

        # --- Action buttons ---
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", padx=10, pady=(6, 2))
        self.transcribe_btn = ttk.Button(actions, text="Transcribe",
                                         command=self.start)
        self.transcribe_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Cancel",
                                     command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))

        # --- Progress ---
        prog = ttk.Frame(self.root)
        prog.pack(fill="x", padx=10, pady=(4, 2))
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(prog, textvariable=self.status_var).pack(anchor="w",
                                                           pady=(2, 0))

        # --- Log / preview ---
        logf = ttk.LabelFrame(self.root, text="Log / live transcript")
        logf.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.log = scrolledtext.ScrolledText(logf, height=8, wrap="word",
                                             state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ------------------------------------------------------------ file actions
    def _filetypes(self):
        audio = " ".join(f"*.{e}" for e in AUDIO_EXTS)
        video = " ".join(f"*.{e}" for e in VIDEO_EXTS)
        return [
            ("Audio & video", f"{audio} {video}"),
            ("Audio files", audio),
            ("Video files", video),
            ("All files", "*.*"),
        ]

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select audio/video files",
                                            filetypes=self._filetypes())
        for p in paths:
            self._add_one(p)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder of media files")
        if not folder:
            return
        exts = set(AUDIO_EXTS + VIDEO_EXTS)
        added = 0
        for name in sorted(os.listdir(folder)):
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            full = os.path.join(folder, name)
            if ext in exts and os.path.isfile(full):
                if self._add_one(full):
                    added += 1
        self._log(f"Added {added} file(s) from {folder}")

    def _add_one(self, path):
        path = os.path.normpath(path)
        if path in self.files:
            return False
        self.files.append(path)
        self.listbox.insert(tk.END, path)
        return True

    def remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.files[idx]

    def clear_all(self):
        self.listbox.delete(0, tk.END)
        self.files.clear()

    def _toggle_outdir(self):
        if self.same_folder_var.get():
            self.outdir_entry.config(state="disabled")
            self.outdir_btn.config(state="disabled")
        else:
            self.outdir_entry.config(state="normal")
            self.outdir_btn.config(state="normal")

    def choose_outdir(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.outdir_var.set(os.path.normpath(folder))

    # ------------------------------------------------------------- run control
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("No files", "Add at least one file first.")
            return
        if not self.whisper_path:
            messagebox.showerror("Whisper not found",
                                 "The 'whisper' command is not available.")
            return
        if not self.same_folder_var.get():
            od = self.outdir_var.get().strip()
            if not od or not os.path.isdir(od):
                messagebox.showerror("Output folder",
                                     "Choose a valid output folder, or tick "
                                     "'Save next to each source file'.")
                return

        # Snapshot options for the worker thread.
        lang_value = dict(LANGUAGES)[self.language_var.get()]
        opts = {
            "files": list(self.files),
            "model": self.model_var.get(),
            "language": lang_value,
            "format": self.format_var.get(),
            "same_folder": self.same_folder_var.get(),
            "outdir": self.outdir_var.get().strip(),
        }

        self.cancel_flag.clear()
        self._set_running(True)
        self._clear_log()
        self.worker = threading.Thread(target=self._run_batch, args=(opts,),
                                       daemon=True)
        self.worker.start()

    def cancel(self):
        self.cancel_flag.set()
        self._post(("status", "Cancelling…"))
        if self.proc and self.proc.poll() is None:
            kill_process_tree(self.proc.pid)
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _set_running(self, running):
        self.transcribe_btn.config(state="disabled" if running else "normal")
        self.cancel_btn.config(state="normal" if running else "disabled")
        state = "disabled" if running else "readonly"
        for cb in (self.language_cb, self.model_cb, self.format_cb):
            cb.config(state=state)

    # ---------------------------------------------------- worker (bg thread)
    def _run_batch(self, opts):
        total = len(opts["files"])
        try:
            for i, path in enumerate(opts["files"]):
                if self.cancel_flag.is_set():
                    break
                self._transcribe_one(path, i, total, opts)
            if self.cancel_flag.is_set():
                self._post(("status", "Cancelled."))
                self._post(("progress_overall", 0.0))
            else:
                self._post(("status", f"Done — {total} file(s) transcribed."))
                self._post(("progress_overall", 1.0))
        finally:
            self._post(("finished", None))

    def _transcribe_one(self, path, index, total, opts):
        name = os.path.basename(path)
        self._post(("log", f"\n=== [{index + 1}/{total}] {name} ==="))

        if not os.path.isfile(path):
            self._post(("log", f"  ! File not found, skipping: {path}"))
            return

        duration = self._probe_duration(path)
        if duration:
            self._post(("log", f"  Duration: {duration:.1f}s"))
        else:
            self._post(("log", "  Duration unknown."))

        outdir = (os.path.dirname(path) if opts["same_folder"]
                  else opts["outdir"])

        cmd = [
            self.whisper_path, path,
            "--model", opts["model"],
            "--output_dir", outdir,
            "--output_format", ("all" if opts["format"] == "All"
                                else opts["format"]),
            "--device", "cpu",
            "--fp16", "False",
            "--verbose", "True",
        ]
        if opts["language"]:
            cmd += ["--language", opts["language"]]
            self._post(("log", f"  Language: {opts['language']}"))
        else:
            self._post(("log", "  Language: auto-detect"))

        # "preparing" covers model loading (and, the very first time a given
        # model size is used, downloading it) plus decoding the first audio
        # chunk -- there's no progress info from Whisper yet during this
        # window, so show a moving/indeterminate bar + elapsed-time status
        # instead of leaving the bar looking dead.
        self._post(("phase", ("preparing", index, total, name)))

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW,
                env=self.subprocess_env,
            )
        except Exception as e:
            self._post(("log", f"  ! Failed to start whisper: {e}"))
            return

        if self._assign_to_job:
            try:
                self._assign_to_job(self.proc.pid)
            except Exception:
                pass

        first_progress_seen = False
        for line in self.proc.stdout:
            if self.cancel_flag.is_set():
                break
            line = line.rstrip("\n")
            if not line:
                continue

            dl = DOWNLOAD_RE.search(line)
            if dl:
                percent = int(dl.group(1))
                self._post(("phase", ("downloading", index, total, name)))
                self._post(("download_progress",
                           (percent, opts["model"])))
                continue

            m = TIMESTAMP_RE.search(line)
            if m:
                if not first_progress_seen:
                    first_progress_seen = True
                    self._post(("phase", ("transcribing", index, total, name)))
                end_sec = _hms_to_seconds(m.group(4), m.group(5), m.group(6))
                text = m.group(7)
                self._post(("log", f"  {text}"))
                if duration and duration > 0:
                    frac = max(0.0, min(1.0, end_sec / duration))
                    self._post(("progress_file", (index, total, frac)))
                    self._post(("status",
                                f"File {index + 1}/{total} — "
                                f"{int(frac * 100)}% — {name}"))
                else:
                    self._post(("status",
                                f"File {index + 1}/{total} — "
                                f"transcribing… — {name}"))
            elif ("Detected language" in line or "Detecting language" in line
                  or "warn" in line.lower() or "error" in line.lower()):
                self._post(("log", f"  {line}"))

        self.proc.wait()
        rc = self.proc.returncode
        self.proc = None

        if self.cancel_flag.is_set():
            return
        self._post(("phase", ("idle", index, total, name)))
        if rc == 0:
            self._post(("progress_file", (index, total, 1.0)))
            written = self._list_outputs(path, outdir, opts["format"])
            self._post(("log", "  ✔ Done. Wrote: " + ", ".join(written)))
        else:
            self._post(("log", f"  ! whisper exited with code {rc}"))

    def _probe_duration(self, path):
        if not self.ffprobe_path:
            return None
        try:
            out = subprocess.run(
                [self.ffprobe_path, "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
            return float(out.stdout.strip())
        except Exception:
            return None

    def _list_outputs(self, src, outdir, fmt):
        stem = os.path.splitext(os.path.basename(src))[0]
        exts = (["txt", "srt", "vtt", "tsv", "json"] if fmt == "All"
                else [fmt])
        found = []
        for e in exts:
            candidate = os.path.join(outdir, f"{stem}.{e}")
            if os.path.exists(candidate):
                found.append(f"{stem}.{e}")
        return found or ["(no output files found)"]

    # ------------------------------------------------- thread-safe UI plumbing
    def _post(self, msg):
        self.ui_queue.put(msg)

    def _poll_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                self._handle_ui(kind, payload)
        except queue.Empty:
            pass
        self.root.after(60, self._poll_ui_queue)

    def _handle_ui(self, kind, payload):
        if kind == "log":
            self._log(payload)
        elif kind == "status":
            self.status_var.set(payload)
        elif kind == "progress_file":
            index, total, frac = payload
            overall = (index + frac) / total * 100
            self._enter_determinate()
            self.progress["value"] = overall
        elif kind == "progress_overall":
            self._enter_determinate()
            self.progress["value"] = payload * 100
        elif kind == "download_progress":
            percent, model_name = payload
            self._enter_determinate()
            self.progress["value"] = percent
            idx, total, _name = self.phase_ctx
            self.status_var.set(
                f"File {idx + 1}/{total} — downloading '{model_name}' "
                f"model (one-time download) — {percent}%")
        elif kind == "phase":
            phase, index, total, name = payload
            self.phase = phase
            self.phase_started_at = time.time()
            self.phase_ctx = (index, total, name)
            if phase == "preparing":
                if self.progress["mode"] != "indeterminate":
                    self.progress.config(mode="indeterminate")
                    self.progress.start(12)
                self.status_var.set(
                    f"File {index + 1}/{total} — preparing… (0s)")
            elif phase == "idle":
                if self.progress["mode"] == "indeterminate":
                    self.progress.stop()
                    self.progress.config(mode="determinate")
            # "downloading" / "transcribing": bar + status are driven by the
            # download_progress / progress_file / status messages that
            # accompany them. If duration is unknown, the bar simply stays
            # in whatever mode it was already in (indeterminate marquee),
            # which correctly shows "still working, no ETA available".
        elif kind == "finished":
            self._set_running(False)
            self.proc = None
            self.phase = "idle"

    def _enter_determinate(self):
        if self.progress["mode"] == "indeterminate":
            self.progress.stop()
        if self.progress["mode"] != "determinate":
            self.progress.config(mode="determinate")

    def _tick_phase(self):
        if self.phase == "preparing" and self.phase_started_at:
            elapsed = int(time.time() - self.phase_started_at)
            index, total, _name = self.phase_ctx
            self.status_var.set(
                f"File {index + 1}/{total} — preparing… ({elapsed}s elapsed — "
                "loading the model / processing the first chunk; this can "
                "take a while on a CPU, longer if the model still needs "
                "to download)")
        self.root.after(1000, self._tick_phase)

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.config(state="disabled")


def main():
    root = tk.Tk()
    try:
        # Slightly nicer default theme on Windows.
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    app = TranscriberApp(root)

    def on_close():
        if app.worker and app.worker.is_alive():
            if not messagebox.askokcancel(
                    "Quit", "A transcription is running. Quit anyway?"):
                return
            app.cancel_flag.set()
            if app.proc and app.proc.poll() is None:
                kill_process_tree(app.proc.pid)
                try:
                    app.proc.terminate()
                except Exception:
                    pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
