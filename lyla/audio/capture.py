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
        self.current_file = self.output_dir / "user_input.wav"
        if self.current_file.exists():
            self.current_file.unlink()

        cmd = [
            "pw-record",
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            str(self.current_file)
        ]
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return self.current_file

    def stop_recording(self) -> Path:
        if self.current_process:
            self.current_process.send_signal(signal.SIGINT)
            try:
                self.current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
            self.current_process = None

        return self.current_file
