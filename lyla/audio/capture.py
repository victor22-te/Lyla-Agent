import os
import subprocess
import signal
import time
from pathlib import Path

class AudioCapture:
    """
    Capturador de audio nativo mediante PipeWire (pw-record).
    Graba directamente a un archivo WAV sin sobrecargar la CPU.
    """
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.current_process = None
        self.current_file = None

    def start_recording(self) -> Path:
        self.stop_recording()
        self.current_file = self.output_dir / "user_input.wav"
        if self.current_file.exists():
            try:
                self.current_file.unlink()
            except Exception:
                pass

        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        cmd = [
            "pw-record",
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            str(self.current_file)
        ]
        self.current_process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        return self.current_file

    def stop_recording(self) -> Path:
        if self.current_process:
            try:
                self.current_process.send_signal(signal.SIGINT)
                self.current_process.wait(timeout=2)
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
            self.current_process = None
            time.sleep(0.08)

        return self.current_file
