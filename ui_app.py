import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from datetime import datetime

import numpy as np
import pyaudiowpatch as pyaudio
from vosk import Model, KaldiRecognizer
import sys


def _resource_path(*parts: str) -> str:
    """
    Returns an absolute path to a bundled resource.
    Works both for normal python runs and PyInstaller one-file builds.
    """
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, *parts)


class TranscriptionWorker:
    """
    Background transcription worker.
    Pushes finalized transcript segments to a thread-safe queue as:
      ("text", "[HH:MM:SS] some text")
      ("status", "Recording started...")
      ("error", "...")
      ("stopped", None)
    """

    def __init__(self, model_lang: str = "en-us", model_dir: str | None = None):
        if model_dir is None:
            model_dir = _resource_path("assets", "vosk-model-small-en-us-0.15")
        self.model = Model(model_dir)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(
        self,
        out_queue: "queue.Queue[tuple[str, str | None]]",
        paused_event: threading.Event | None = None,
    ):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(out_queue, paused_event),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self, out_queue: "queue.Queue[tuple[str, str | None]]", paused_event: threading.Event | None):
        try:
            out_queue.put(("status", "Finding loopback audio device..."))

            with pyaudio.PyAudio() as p:
                default_speakers = p.get_default_output_device_info()
                loopback_devices = p.get_loopback_device_info_generator()

                target_device = next(
                    (d for d in loopback_devices if default_speakers["name"] in d["name"]),
                    None,
                )

                if not target_device:
                    out_queue.put(("error", "Could not find loopback device."))
                    out_queue.put(("stopped", None))
                    return

                actual_rate = int(target_device["defaultSampleRate"])
                rec = KaldiRecognizer(self.model, actual_rate)

                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=actual_rate,
                    input=True,
                    input_device_index=target_device["index"],
                    frames_per_buffer=4000,
                )

                out_queue.put(("status", f"Recording started (rate={actual_rate})."))

                try:
                    while not self._stop_event.is_set():
                        if paused_event is not None and paused_event.is_set():
                            # Sleep lightly while paused (keep stream open, stop processing)
                            out_queue.put(("status", "Paused"))
                            self._stop_event.wait(0.15)
                            continue

                        data = stream.read(2000, exception_on_overflow=False)

                        audio_data = np.frombuffer(data, dtype=np.int16)
                        mono_data = audio_data[::2].tobytes()

                        if rec.AcceptWaveform(mono_data):
                            res = json.loads(rec.Result())
                            text = res.get("text", "").strip()
                            if text:
                                current_time = datetime.now().strftime("%H:%M:%S")
                                entry = f"[{current_time}] {text}"
                                out_queue.put(("text", entry))

                finally:
                    stream.close()

        except Exception as e:
            out_queue.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            out_queue.put(("stopped", None))


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Live Transcript (Vosk)")
        self.geometry("900x600")

        self.queue: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
        self.worker = TranscriptionWorker(model_lang="en-us")

        self.current_file_path: str | None = None
        self.paused = threading.Event()  # set() => paused

        self._build_ui()
        self._poll_queue()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        self.btn_start = tk.Button(top, text="Start", width=10, command=self.on_start)
        self.btn_start.pack(side="left")

        self.btn_stop = tk.Button(top, text="Stop", width=10, state="disabled", command=self.on_stop)
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.btn_pause = tk.Button(top, text="Pause", width=10, state="disabled", command=self.on_pause_toggle)
        self.btn_pause.pack(side="left", padx=(8, 0))

        self.lbl_file = tk.Label(self, text="File: (will ask on Start)", anchor="w")
        self.lbl_file.pack(fill="x", padx=10)

        self.lbl_status = tk.Label(self, text="Status: Idle", anchor="w")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 6))

        self.txt = scrolledtext.ScrolledText(self, wrap="word", font=("Consolas", 11))
        self.txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt.insert("end", self._default_header())
        self.txt.see("end")

    def _default_header(self) -> str:
        return (
            "MEETING TRANSCRIPT\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            + "=" * 40
            + "\n\n"
        )

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()

                if kind == "text" and payload:
                    self._append_text(payload + "\n\n")

                elif kind == "status" and payload:
                    self._set_status(payload)

                elif kind == "error" and payload:
                    self._set_status("Error")
                    messagebox.showerror("Transcription Error", payload)

                elif kind == "stopped":
                    self._set_running(False)
                    self._set_status("Stopped")

        except queue.Empty:
            pass

        self.after(80, self._poll_queue)

    def _append_text(self, s: str):
        self.txt.insert("end", s)
        self.txt.see("end")

    def _set_status(self, s: str):
        self.lbl_status.config(text=f"Status: {s}")

    def _set_running(self, running: bool):
        self.btn_start.config(state=("disabled" if running else "normal"))
        self.btn_stop.config(state=("normal" if running else "disabled"))
        self.btn_pause.config(state=("normal" if running else "disabled"))
        if not running:
            self.btn_pause.config(text="Pause")

    def _select_new_file_path_on_start(self) -> bool:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Meeting_Notes_{timestamp_str}.txt"

        path = filedialog.asksaveasfilename(
            title="Save transcript file",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return False

        self.current_file_path = path
        self.lbl_file.config(text=f"File: {self.current_file_path}")
        return True

    def _save_current_file(self):
        if not self.current_file_path:
            return
        try:
            content = self.txt.get("1.0", "end-1c")
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._set_status("Saved")
        except Exception as e:
            messagebox.showerror("Save Error", f"{type(e).__name__}: {e}")


    def on_start(self):
        # Every Start => choose a save path and start a NEW recording file.
        if self.worker.is_running():
            return

        if not self._select_new_file_path_on_start():
            return

        # Reset UI contents for a new session
        self.txt.delete("1.0", "end")
        self.txt.insert("end", self._default_header())
        self.txt.see("end")

        # Clear pause state
        self.paused.clear()
        self.btn_pause.config(text="Pause")

        self._set_running(True)
        self._set_status("Starting...")
        self.worker.start(self.queue, self.paused)

    def on_pause_toggle(self):
        if not self.worker.is_running():
            return

        if not self.paused.is_set():
            self.paused.set()
            self.btn_pause.config(text="Resume")
            self._set_status("Paused")
        else:
            self.paused.clear()
            self.btn_pause.config(text="Pause")
            self._set_status("Recording...")

    def on_stop(self):
        if self.worker.is_running():
            self._set_status("Stopping...")
            self.worker.stop()
        self._save_current_file()

    def on_close(self):
        if self.worker.is_running():
            self.worker.stop()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
