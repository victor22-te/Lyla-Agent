import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


class TerminalTools:
    """
    Control de Terminal, Sistema de Archivos y Lanzamiento de Aplicaciones para LYLA 2099.
    Permite al agente ejecutar comandos en Arch Linux, gestionar carpetas/archivos y abrir apps.
    """

    def __init__(self, default_cwd: Optional[str] = None):
        self.default_cwd = Path(default_cwd or os.path.expanduser("~")).resolve()

    def run_command(self, cmd: str, timeout: int = 20, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Ejecuta un comando de shell en Linux con timeout y protección de comandos destructivos."""
        cmd_clean = cmd.strip()
        if not cmd_clean:
            return {"success": False, "output": "Comando vacío", "returncode": -1}

        # Protección básica contra comandos catastróficos en el sistema
        dangerous_patterns = [
            r"\brm\s+-[rfR]*\s+/\s*$",
            r"\brm\s+-[rfR]*\s+/\*",
            r"\bmkfs\b",
            r":\(\)\s*\{\s*:\|:&\s*\};:",
            r"\bdd\s+if=.*of=/dev/sd",
        ]
        for pat in dangerous_patterns:
            if re.search(pat, cmd_clean):
                return {
                    "success": False,
                    "output": f"Comando bloqueado por el protocolo de seguridad de LYLA: '{cmd_clean}'",
                    "returncode": 1,
                }

        target_cwd = Path(cwd).expanduser().resolve() if cwd else self.default_cwd
        if not target_cwd.exists():
            target_cwd = Path(os.path.expanduser("~"))

        try:
            res = subprocess.run(
                cmd_clean,
                shell=True,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                executable="/bin/bash",
            )
            out = res.stdout.strip()
            err = res.stderr.strip()
            combined = out if not err else (f"{out}\n{err}".strip() if out else err)
            return {
                "success": res.returncode == 0,
                "stdout": out,
                "stderr": err,
                "output": combined or "(Comando ejecutado sin salida)",
                "returncode": res.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": f"Tiempo de espera agotado ({timeout}s) ejecutando: {cmd_clean}",
                "returncode": 124,
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Error ejecutando comando: {e}",
                "returncode": 1,
            }

    def create_directory(self, path_str: str) -> Dict[str, Any]:
        """Crea un directorio (equivalente a mkdir -p)."""
        try:
            p = Path(path_str.strip()).expanduser()
            if not p.is_absolute():
                p = self.default_cwd / p
            p.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "path": str(p),
                "message": f"Directorio creado o ya existente: {p}",
            }
        except Exception as e:
            return {
                "success": False,
                "path": path_str,
                "message": f"Error creando directorio '{path_str}': {e}",
            }

    def open_app(self, app_name: str) -> Dict[str, Any]:
        """Abre una aplicación de escritorio de Arch Linux de forma desacoplada."""
        name = app_name.strip().lower()

        # Mapeo de nombres comunes a binarios de Arch Linux
        app_map = {
            "terminal": "kitty",
            "consola": "kitty",
            "kitty": "kitty",
            "browser": "firefox",
            "navegador": "firefox",
            "firefox": "firefox",
            "chrome": "google-chrome-stable",
            "google chrome": "google-chrome-stable",
            "chromium": "chromium",
            "code": "code",
            "vscode": "code",
            "antigravity": "antigravity",
            "ide": "antigravity",
            "spotify": "spotify",
            "archivos": "nautilus",
            "nautilus": "nautilus",
            "file manager": "nautilus",
            "discord": "discord",
            "telegram": "telegram-desktop",
            "gimp": "gimp",
            "vlc": "vlc",
            "tui": "/home/spider-man/.local/bin/spider-hud",
            "hud": "/home/spider-man/.local/bin/spider-hud",
        }

        cmd_target = app_map.get(name, app_name.strip())

        parts = shlex.split(cmd_target)
        if not parts:
            return {"success": False, "app": app_name, "message": "Nombre de aplicación inválido."}

        bin_name = parts[0]

        resolved = shutil.which(bin_name)
        if not resolved and Path(bin_name).exists():
            resolved = str(Path(bin_name).resolve())

        if not resolved:
            # Intentar con gtk-launch
            if shutil.which("gtk-launch"):
                try:
                    subprocess.Popen(
                        ["gtk-launch", bin_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return {
                        "success": True,
                        "app": bin_name,
                        "message": f"Aplicación '{bin_name}' iniciada vía gtk-launch.",
                    }
                except Exception:
                    pass
            return {
                "success": False,
                "app": bin_name,
                "message": f"No se encontró el ejecutable '{bin_name}' en el sistema.",
            }

        try:
            subprocess.Popen(
                parts,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {
                "success": True,
                "app": bin_name,
                "message": f"Aplicación '{bin_name}' iniciada en segundo plano.",
            }
        except Exception as e:
            return {
                "success": False,
                "app": bin_name,
                "message": f"Error iniciando '{bin_name}': {e}",
            }

    def write_file(self, path_str: str, content: str) -> Dict[str, Any]:
        """Escribe o edita un archivo de código o texto."""
        try:
            p = Path(path_str.strip()).expanduser()
            if not p.is_absolute():
                p = self.default_cwd / p
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            lines_count = len(content.splitlines())
            return {
                "success": True,
                "path": str(p),
                "lines": lines_count,
                "message": f"Archivo guardado en {p} ({lines_count} líneas).",
            }
        except Exception as e:
            return {
                "success": False,
                "path": path_str,
                "message": f"Error escribiendo en '{path_str}': {e}",
            }

    def read_file(self, path_str: str, max_lines: int = 150) -> Dict[str, Any]:
        """Lee el contenido de un archivo."""
        try:
            p = Path(path_str.strip()).expanduser()
            if not p.is_absolute():
                p = self.default_cwd / p
            if not p.exists():
                return {"success": False, "content": "", "message": f"El archivo no existe: {p}"}
            if p.is_dir():
                return {"success": False, "content": "", "message": f"La ruta es un directorio, no un archivo: {p}"}

            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            content = "\n".join(lines[:max_lines])
            if len(lines) > max_lines:
                content += f"\n... ({len(lines) - max_lines} líneas adicionales omitidas)"
            return {
                "success": True,
                "path": str(p),
                "content": content,
                "total_lines": len(lines),
                "message": f"Archivo leído exitosamente ({len(lines)} líneas).",
            }
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "message": f"Error leyendo '{path_str}': {e}",
            }
