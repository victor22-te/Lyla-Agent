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
        # Último fondo aplicado (-1 = ninguno todavía). cycle_wallpaper lo usa
        # cuando el llamador no pasa un índice, para que el ciclo avance.
        self._wallpaper_index = -1

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

    # -------------------------------------------------------------------------
    # Gestor Híbrido de Fondos de Pantalla (Hanabi Live Videos + GNOME Imágenes)
    # -------------------------------------------------------------------------
    def get_available_wallpapers(self) -> List[Dict[str, str]]:
        """
        Escanea y lista todos los fondos animados (vídeos mp4, webm, mkv) y estáticos (jpg, png, webp)
        disponibles en ~/Pictures, ~/Imágenes, ~/Videos y ~/Vídeos sin duplicados.
        """
        search_dirs = [
            Path("/home/spider-man/Pictures"),
            Path("/home/spider-man/Imágenes"),
            Path("/home/spider-man/Videos"),
            Path("/home/spider-man/Vídeos"),
        ]
        videos: List[Dict[str, str]] = []
        images: List[Dict[str, str]] = []
        seen_names = set()

        for sdir in search_dirs:
            if not sdir.exists():
                continue
            for p in sorted(sdir.glob("*.*")):
                if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".bak"):
                    ext = p.suffix.lower()
                    name_low = p.name.lower()
                    if name_low in seen_names:
                        continue
                    if ext in [".mp4", ".webm", ".mkv", ".mov"]:
                        seen_names.add(name_low)
                        videos.append({"type": "video", "path": str(p.resolve()), "name": p.name})
                    elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        if not any(ign in name_low for ign in ["avatar", "icon", "captura", "screenshot"]):
                            seen_names.add(name_low)
                            images.append({"type": "image", "path": str(p.resolve()), "name": p.name})

        return videos + images

    def cycle_wallpaper(self, current_index: Optional[int] = None) -> Dict[str, str]:
        """
        Cambia el fondo de pantalla de forma inteligente:
        - Si el objetivo es un vídeo (.mp4/.webm): configura la extensión Hanabi y la activa.
        - Si el objetivo es una imagen (.jpg/.png): desactiva Hanabi y aplica el fondo nativo de GNOME Shell.

        Si no se pasa current_index, se usa el último fondo aplicado por esta
        instancia (para que el ciclo avance). Antes el valor por defecto era 0,
        así que cada llamada sin argumento ponía siempre el mismo fondo (#1)
        y parecía que la tecla W no hacía nada (bug del HUD táctico).
        """
        wallpapers = self.get_available_wallpapers()
        if not wallpapers:
            return {
                "success": False,
                "message": "  No se encontraron fondos en ~/Pictures o ~/Videos",
                "index": 0,
            }

        if current_index is None:
            current_index = self._wallpaper_index
        next_idx = (current_index + 1) % len(wallpapers)
        target = wallpapers[next_idx]
        self._wallpaper_index = next_idx

        has_gsettings = bool(shutil.which("gsettings"))
        has_gnome_ext = bool(shutil.which("gnome-extensions"))

        if target["type"] == "video":
            # 1. Fondo Animado vía Hanabi Extension
            if has_gsettings:
                try:
                    subprocess.Popen([
                        "gsettings", "set", "io.github.jeffshee.hanabi-extension", "video-path", target["path"]
                    ])
                except Exception:
                    pass
            if has_gnome_ext:
                try:
                    subprocess.Popen([
                        "gnome-extensions", "enable", "hanabi-extension@jeffshee.github.io"
                    ])
                except Exception:
                    pass
            desc = f"󰕧  Fondo animado (Hanabi): {target['name']}"
        else:
            # 2. Fondo Estático vía GNOME Background
            if has_gnome_ext:
                try:
                    # Desactivar temporalmente Hanabi para que no tape la imagen estática
                    subprocess.Popen([
                        "gnome-extensions", "disable", "hanabi-extension@jeffshee.github.io"
                    ])
                except Exception:
                    pass
            if has_gsettings:
                uri = f"file://{target['path']}"
                try:
                    subprocess.Popen(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
                    subprocess.Popen(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])
                except Exception:
                    pass
            desc = f"󰋩  Fondo estático: {target['name']}"

        return {
            "success": True,
            "message": desc,
            "index": next_idx,
            "item": target,
            "total": len(wallpapers),
        }

