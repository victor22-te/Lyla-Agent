import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional


class SystemTools:
    """
    Fase 5: Herramientas del Sistema Linux, Alarmas y Conectividad Móvil (KDE Connect / SSH).
    Zero Hardware Impact: Lectura directa de /proc y /sys e hilos ligeros para alarmas.
    """

    def __init__(self, on_alarm_trigger: Optional[Callable[[str], None]] = None):
        self.on_alarm_trigger = on_alarm_trigger
        self.alarms: List[Dict[str, str]] = []
        self._alarm_counter = 0

    # -------------------------------------------------------------------------
    # Telemetría de Sistema (Arch Linux)
    # -------------------------------------------------------------------------
    def get_system_status(self) -> Dict[str, str]:
        # CPU load average
        try:
            load1, load5, load15 = os.getloadavg()
            cores = os.cpu_count() or 1
            cpu_pct = min(100.0, (load1 / cores) * 100.0)
            cpu_str = f"{cpu_pct:.1f}% (Load: {load1:.2f}, {cores} hilos)"
        except Exception:
            cpu_str = "N/D"

        # RAM
        try:
            mem = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        mem[k.strip()] = int(v.strip().split()[0])
            tot = mem.get("MemTotal", 1)
            avail = mem.get("MemAvailable", tot)
            used = tot - avail
            ram_pct = (used * 100.0) / tot
            ram_str = f"{used / 1048576:.2f} / {tot / 1048576:.2f} GiB ({ram_pct:.1f}%)"
        except Exception:
            ram_str = "N/D"

        # Disco /
        try:
            du = shutil.disk_usage("/")
            used_gb = du.used / (1024**3)
            tot_gb = du.total / (1024**3)
            disk_pct = (du.used * 100.0) / du.total
            disk_str = f"{used_gb:.1f} / {tot_gb:.1f} GiB ({disk_pct:.1f}%)"
        except Exception:
            disk_str = "N/D"

        # Batería
        bat_str = "AC / Sin batería detectada"
        try:
            ps_dir = Path("/sys/class/power_supply")
            if ps_dir.exists():
                for item in ps_dir.iterdir():
                    if item.name.startswith("BAT"):
                        cap = (item / "capacity").read_text().strip()
                        stat = (item / "status").read_text().strip()
                        bat_str = f"{cap}% ({stat})"
                        break
        except Exception:
            pass

        # Uptime
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                up_sec = float(f.readline().split()[0])
            hrs = int(up_sec // 3600)
            mins = int((up_sec % 3600) // 60)
            up_str = f"{hrs}h {mins}m"
        except Exception:
            up_str = "N/D"

        return {
            "cpu": cpu_str,
            "ram": ram_str,
            "disk": disk_str,
            "battery": bat_str,
            "uptime": up_str,
        }

    # -------------------------------------------------------------------------
    # Sistema de Alarmas y Recordatorios con Notificación GNOME + Voz
    # -------------------------------------------------------------------------
    def add_alarm(self, time_spec: str, message: str) -> Dict[str, str]:
        """
        Programa una alarma.
        `time_spec` soporta:
          - Duración relativa: '30s', '5m', '10min', '1h'
          - Hora reloj: '18:30', '07:00'
        """
        time_spec = time_spec.strip().lower()
        message = message.strip() or "Recordatorio de LYLA 2099"
        now = datetime.now()
        delay_seconds = 0.0
        target_dt = now

        # 1. Formato relativo: e.g. 10s, 5m, 2h
        m_rel = re.match(r"^(\d+)\s*(s|seg|m|min|h|hr|hrs)?$", time_spec)
        if m_rel:
            val = int(m_rel.group(1))
            unit = m_rel.group(2) or "m"
            if unit.startswith("s"):
                delay_seconds = float(val)
            elif unit.startswith("h"):
                delay_seconds = float(val * 3600)
            else:
                delay_seconds = float(val * 60)
            target_dt = now + timedelta(seconds=delay_seconds)
        else:
            # 2. Formato HH:MM
            m_clk = re.match(r"^(\d{1,2}):(\d{2})$", time_spec)
            if m_clk:
                hh, mm = int(m_clk.group(1)), int(m_clk.group(2))
                target_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if target_dt <= now:
                    target_dt += timedelta(days=1)
                delay_seconds = (target_dt - now).total_seconds()
            else:
                raise ValueError(f"Formato de tiempo '{time_spec}' no válido. Usa por ejemplo '5m', '30s' o '18:30'.")

        self._alarm_counter += 1
        alarm_id = str(self._alarm_counter)
        alarm_info = {
            "id": alarm_id,
            "target_time": target_dt.strftime("%H:%M:%S"),
            "message": message,
            "status": "ACTIVA",
        }
        self.alarms.append(alarm_info)

        def _timer_worker():
            time.sleep(max(0.5, delay_seconds))
            if alarm_info["status"] != "ACTIVA":
                return
            alarm_info["status"] = "DISPARADA"
            # Notificación nativa de escritorio GNOME
            if shutil.which("notify-send"):
                try:
                    subprocess.Popen([
                        "notify-send",
                        "-u", "critical",
                        "-a", "LYLA 2099",
                        f"  ALARMA LYLA // {alarm_info['target_time']}",
                        message,
                    ])
                except Exception:
                    pass
            print(f"\n\033[38;2;255;0;0m\033[1m  [ALARMA LYLA {alarm_info['target_time']}]: {message}\033[0m")
            if self.on_alarm_trigger:
                try:
                    self.on_alarm_trigger(f"Oye Víctor, alarma activa: {message}")
                except Exception:
                    pass

        t = threading.Thread(target=_timer_worker, daemon=True)
        t.start()
        return alarm_info

    def list_active_alarms(self) -> List[Dict[str, str]]:
        return [a for a in self.alarms if a["status"] == "ACTIVA"]

    # -------------------------------------------------------------------------
    # Conectividad Móvil (KDE Connect / Red)
    # -------------------------------------------------------------------------
    def ping_mobile(self, text: str = "Alerta desde LYLA 2099 HUD") -> str:
        """Envía un ping/mensaje al móvil si KDE Connect está disponible."""
        if not shutil.which("kdeconnect-cli"):
            return "kdeconnect-cli no está instalado. Puedes instalarlo con 'sudo pacman -S kdeconnect' para enlazar tu móvil."
        try:
            res = subprocess.run(
                ["kdeconnect-cli", "-a", "--id-only"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            dev_ids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            if not dev_ids:
                return "No se detectaron dispositivos móviles conectados en KDE Connect actualmente."
            dev_id = dev_ids[0]
            subprocess.run(
                ["kdeconnect-cli", "-d", dev_id, "--ping-msg", text],
                check=True,
                timeout=5,
            )
            return f"Ping enviado exitosamente al dispositivo móvil ({dev_id}): '{text}'"
        except Exception as e:
            return f"Error comunicando con el dispositivo móvil: {e}"

