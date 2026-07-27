WHISPER TRANSCRIBER
===================

A simple double-click app for transcribing audio/video files locally with
OpenAI Whisper. No login, no internet needed (after the model is downloaded),
no command line.


SETTING THIS UP ON A NEW / DIFFERENT PC
----------------------------------------
Copying just this folder to another PC is NOT enough by itself -- that PC
also needs Python, ffmpeg, and the Whisper engine installed. To do that
automatically:

1. Copy this whole folder to the other PC (e.g. via Dropbox, USB, etc.).
2. Double-click  Setup.bat  ONCE.
   It silently installs Python, ffmpeg, and Whisper (all free), and creates
   a "Transcriber" shortcut on that PC's Desktop. No PowerShell or command-
   line knowledge needed -- just double-click and wait. This can take a
   few minutes and downloads a few hundred MB.
3. After that, use the app exactly as described below.

Setup.bat is safe to re-run any time -- it skips anything already installed.


HOW TO START IT (day to day)
-----------------------------
- Double-click  Transcriber.bat  in this folder, OR
- Use the "Transcriber" shortcut on your Desktop (created by Setup.bat).


HOW TO USE IT
-------------
1. Click "Add files..." and pick one or more audio/video files
   (or "Add folder..." to add every media file in a folder).
2. Choose your options:
     - Language: defaults to "English". Switch to "Auto-detect" for
       non-English audio, or pick another language to force it.
       ^ Forcing the language fixes the occasional wrong auto-detection
         (e.g. a short English clip detected as "Hawaiian").
     - Model:   "medium" is the default (good accuracy/speed balance on CPU).
                "large" is more accurate but noticeably slower.
     - Output:  defaults to "srt" (subtitle file). "All" writes
                txt + srt + vtt + tsv + json instead, or pick another single one.
3. Output location: by default files are saved next to each source file.
   Untick that box to choose a single output folder.
4. Click "Transcribe". The progress bar fills as it works, and the live
   transcript scrolls in the log at the bottom.
5. Files transcribe one after another. Click "Cancel" to stop.


NOTES
-----
- This is CPU-only. A few-minute clip on "medium" takes a few minutes.
  The progress bar shows how far along it is.
- Before any transcript text appears, you'll see a "preparing..." message with
  an elapsed-time counter and a moving (marquee-style) progress bar. This
  covers model loading and the first audio chunk, which can take anywhere
  from several seconds to a couple of minutes on a CPU -- it's normal, not
  stuck. If a model size hasn't been used before, Whisper downloads it once
  (the "medium" model is ~1.4 GB) and the bar/status show real download
  percentage while that happens.
- Requires: Python (with Whisper installed) and ffmpeg. Run Setup.bat once on
  any new PC to install these automatically.
- Closing the app (or it crashing) while a file is transcribing will not
  leave an orphaned background process running -- it's cleaned up
  automatically.


TROUBLESHOOTING
---------------
- "Whisper not found" when the app opens: run  Setup.bat  (installs everything
  automatically), or manually open a terminal and run  pip install openai-whisper
- Nothing happens on double-click: run  Transcriber.bat  from a terminal to
  see any error message.
