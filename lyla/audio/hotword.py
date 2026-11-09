"""Hot‑word detection for LYLA.
Implements a lightweight listener using Picovoice Porcupine (offline).
If Picovoice is not installed, the module will raise ImportError when instantiated.
"""
import struct
import threading
import signal
import os
import sys
from pathlib import Path

try:
    import pvporcupine
    import pyaudio
except ImportError as e:
    pvporcupine = None  # type: ignore
    pyaudio = None  # type: ignore

class HotwordListener:
    """Continuously listens for the configured hot‑words and invokes callbacks.

    Parameters
    ----------
    callbacks: dict
        Mapping of hot‑word identifiers to callables, e.g. {'lyla': fn, 'laila': fn2}
    """

    def __init__(self, callbacks: dict):
        if pvporcupine is None or pyaudio is None:
            raise RuntimeError("pvporcupine and pyaudio are required for hot‑word detection")
        self.callbacks = callbacks
        self._stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        # Porcupine supports keyword names; we use the built‑in "hey google" as placeholder
        # but the user can train custom models. Here we use generic keywords list.
        porcupine = pvporcupine.create(keywords=["hey lyla", "hey laila"])
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length,
        )
        while not self._stop.is_set():
            pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)
            result = porcupine.process(pcm)
            if result >= 0:
                # result indexes the keyword list
                if result == 0:
                    self.callbacks.get("lyla", lambda: None)()
                else:
                    self.callbacks.get("laila", lambda: None)()
        audio_stream.stop_stream()
        audio_stream.close()
        pa.terminate()

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join()

