import json
import os
import sqlite3
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests


SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"


class CalendarManager:
    """
    Gestor Híbrido de Agenda y Google Calendar (Fase 4).
    - Conecta con Google Calendar API v3 (OAuth2 con config/credentials.json) para lectura/escritura en la nube.
    - Soporta feed privado iCal (GOOGLE_CALENDAR_ICS_URL en .env) para lectura rápida.
    - Mantiene respaldo y agenda local ultraligera en SQLite (lyla_memory.db) para disponibilidad inmediata.
    """

    def __init__(self, config_dir: Path, db_path: Path):
        self.config_dir = config_dir
        self.db_path = db_path
        self.credentials_path = config_dir / "credentials.json"
        self.token_path = config_dir / "google_token.json"
        self.ics_url = os.getenv("GOOGLE_CALENDAR_ICS_URL", "").strip()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    description TEXT,
                    source TEXT DEFAULT 'local',
                    external_id TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Estado de conexión con Google Calendar
    # -------------------------------------------------------------------------
    def is_google_authenticated(self) -> bool:
        return self.token_path.exists()

    def get_status_label(self) -> str:
        if self.is_google_authenticated():
            return "Google Calendar API (OAuth2 Conectado)"
        if self.ics_url:
            return "Google Calendar (Feed iCal Conectado + Agenda Local)"
        return "Agenda Local SQLite (Usa '/calendar auth' para vincular Google Calendar)"

    # -------------------------------------------------------------------------
    # Flujo OAuth2 ligero sin dependencias extra
    # -------------------------------------------------------------------------
    def authenticate_oauth(self, port: int = 8765) -> Tuple[bool, str]:
        """
        Inicia el flujo OAuth2 en el navegador usando config/credentials.json
        y guarda el token en config/google_token.json.
        """
        if not self.credentials_path.exists():
            return (
                False,
                f"No se encontró '{self.credentials_path}'.\n"
                "  Para conectar Google Calendar API con lectura/escritura:\n"
                "  1. Ve a https://console.cloud.google.com/apis/credentials\n"
                "  2. Habilita 'Google Calendar API' en tu proyecto.\n"
                "  3. Crea un ID de cliente OAuth 2.0 (Aplicación de escritorio) y descarga el JSON.\n"
                f"  4. Guárdalo como: {self.credentials_path}\n"
                "  5. Ejecuta nuevamente '/calendar auth'.\n"
                "  (Alternativa rápida de solo lectura: agrega GOOGLE_CALENDAR_ICS_URL en tu archivo .env)"
            )

        try:
            raw = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            client_info = raw.get("installed") or raw.get("web")
            if not client_info:
                return False, "El archivo credentials.json no contiene un bloque 'installed' o 'web' válido."

            client_id = client_info["client_id"]
            client_secret = client_info["client_secret"]
            redirect_uri = f"http://localhost:{port}/"

            auth_code_holder: Dict[str, Optional[str]] = {"code": None, "error": None}

            class OAuthCallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "code" in params:
                        auth_code_holder["code"] = params["code"][0]
                        body = "<html><body style='font-family:sans-serif;background:#0d1117;color:#00ffcc;text-align:center;padding:50px;'><h2>LYLA // Google Calendar vinculado con exito.</h2><p>Ya puedes cerrar esta ventana y volver a la terminal.</p></body></html>"
                    else:
                        auth_code_holder["error"] = params.get("error", ["unknown"])[0]
                        body = "<html><body style='font-family:sans-serif;padding:50px;'><h2>Error al autorizar Google Calendar.</h2></body></html>"

                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body.encode("utf-8"))

                def log_message(self, format, *args):
                    pass

            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "access_type": "offline",
                "prompt": "consent",
            }
            auth_url = f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

            server = HTTPServer(("localhost", port), OAuthCallbackHandler)
            server.timeout = 120
            print(f"\n🌐 Abriendo navegador para autorizar Google Calendar...\n   Si no se abre automáticamente, entra a:\n   {auth_url}\n")
            webbrowser.open(auth_url)
            server.handle_request()
            server.server_close()

            if not auth_code_holder["code"]:
                return False, f"No se recibió código de autorización ({auth_code_holder['error'] or 'tiempo agotado'})."

            token_resp = requests.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": auth_code_holder["code"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            token_data["client_id"] = client_id
            token_data["client_secret"] = client_secret
            expires_in = int(token_data.get("expires_in", 3600))
            token_data["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)).isoformat()

            self.token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
            return True, "Cuenta de Google Calendar vinculada exitosamente."
        except Exception as e:
            return False, f"Fallo en la autenticación OAuth: {e}"

    def _get_valid_access_token(self) -> Optional[str]:
        if not self.token_path.exists():
            return None
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            expires_at_str = data.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) < expires_at:
                    return data.get("access_token")

            refresh_token = data.get("refresh_token")
            if not refresh_token:
                return data.get("access_token")

            resp = requests.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "client_id": data["client_id"],
                    "client_secret": data["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            resp.raise_for_status()
            refreshed = resp.json()
            data["access_token"] = refreshed["access_token"]
            expires_in = int(refreshed.get("expires_in", 3600))
            data["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)).isoformat()
            self.token_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data["access_token"]
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Consulta y creación de eventos
    # -------------------------------------------------------------------------
    def list_upcoming_events(self, limit: int = 10) -> List[Dict[str, str]]:
        """Devuelve próximos eventos combinando Google Calendar (si está activo) y la base local."""
        events: List[Dict[str, str]] = []

        # 1. Intentar Google Calendar OAuth API
        token = self._get_valid_access_token()
        if token:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                resp = requests.get(
                    f"{GCAL_API_BASE}/calendars/primary/events",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "timeMin": now_iso,
                        "maxResults": limit,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                    },
                    timeout=10,
                )
                if resp.ok:
                    items = resp.json().get("items", [])
                    for item in items:
                        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
                        events.append({
                            "id": f"gcal:{item.get('id', '')[:8]}",
                            "title": item.get("summary", "(Sin título)"),
                            "start_time": start[:16].replace("T", " "),
                            "source": "gcal",
                        })
            except Exception as e:
                print(f"[Calendar] Aviso consultando Google Calendar API: {e}")

        # 2. Intentar feed ICS si está configurado y no hay OAuth
        elif self.ics_url:
            try:
                events.extend(self._fetch_ics_events(limit=limit))
            except Exception as e:
                print(f"[Calendar] Aviso leyendo feed ICS: {e}")

        # 3. Eventos locales en SQLite
        today_str = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, start_time, source
                FROM calendar_events
                WHERE start_time >= ?
                ORDER BY start_time ASC
                LIMIT ?
                """,
                (today_str, limit),
            )
            for row in cursor.fetchall():
                events.append({
                    "id": str(row["id"]),
                    "title": row["title"],
                    "start_time": row["start_time"],
                    "source": row["source"],
                })

        events.sort(key=lambda x: x["start_time"])
        return events[:limit]

    def _fetch_ics_events(self, limit: int = 10) -> List[Dict[str, str]]:
        resp = requests.get(self.ics_url, timeout=10)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        now_str = datetime.now().strftime("%Y%m%d")
        parsed: List[Dict[str, str]] = []
        in_event = False
        summary = ""
        dtstart = ""

        for raw_line in lines:
            line = raw_line.strip()
            if line == "BEGIN:VEVENT":
                in_event = True
                summary = ""
                dtstart = ""
            elif line == "END:VEVENT" and in_event:
                in_event = False
                if summary and dtstart >= now_str:
                    fmt_time = f"{dtstart[:4]}-{dtstart[4:6]}-{dtstart[6:8]}"
                    if "T" in dtstart and len(dtstart) >= 13:
                        t_part = dtstart.split("T")[1]
                        fmt_time += f" {t_part[:2]}:{t_part[2:4]}"
                    parsed.append({
                        "id": "ics",
                        "title": summary,
                        "start_time": fmt_time,
                        "source": "gcal-ics",
                    })
            elif in_event:
                if line.startswith("SUMMARY"):
                    summary = line.split(":", 1)[-1].strip()
                elif line.startswith("DTSTART"):
                    dtstart = line.split(":", 1)[-1].strip()

        parsed.sort(key=lambda x: x["start_time"])
        return parsed[:limit]

    def add_event(self, title: str, start_time: str, description: str = "") -> Dict[str, str]:
        """
        Agrega un evento a Google Calendar (si OAuth está conectado) y/o a la base local SQLite.
        `start_time` puede ser 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD' o texto descriptivo.
        """
        title = title.strip()
        start_time = start_time.strip()
        token = self._get_valid_access_token()

        if token:
            try:
                # Si tiene formato YYYY-MM-DD HH:MM usamos insert estructurado; si no, quickAdd
                dt_obj = None
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        dt_obj = datetime.strptime(start_time, fmt)
                        break
                    except ValueError:
                        continue

                if dt_obj:
                    local_tz = datetime.now().astimezone().tzinfo
                    dt_aware = dt_obj.replace(tzinfo=local_tz)
                    end_aware = dt_aware + timedelta(hours=1)
                    resp = requests.post(
                        f"{GCAL_API_BASE}/calendars/primary/events",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "summary": title,
                            "description": description or "Agendado por LYLA (2099)",
                            "start": {"dateTime": dt_aware.isoformat()},
                            "end": {"dateTime": end_aware.isoformat()},
                        },
                        timeout=10,
                    )
                else:
                    resp = requests.post(
                        f"{GCAL_API_BASE}/calendars/primary/events/quickAdd",
                        headers={"Authorization": f"Bearer {token}"},
                        params={"text": f"{title} {start_time}"},
                        timeout=10,
                    )

                if resp.ok:
                    data = resp.json()
                    gcal_start = data.get("start", {}).get("dateTime") or data.get("start", {}).get("date") or start_time
                    return {
                        "id": f"gcal:{data.get('id', '')[:8]}",
                        "title": data.get("summary", title),
                        "start_time": gcal_start[:16].replace("T", " "),
                        "source": "gcal",
                    }
            except Exception as e:
                print(f"[Calendar] Falló creación en Google Calendar API ({e}), guardando en agenda local...")

        # Guardar en SQLite local
        now_iso = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO calendar_events (title, start_time, description, source, created_at)
                VALUES (?, ?, ?, 'local', ?)
                """,
                (title, start_time, description, now_iso),
            )
            conn.commit()
            row_id = cursor.lastrowid

        return {
            "id": str(row_id),
            "title": title,
            "start_time": start_time,
            "source": "local",
        }

    def delete_event(self, event_id: str) -> bool:
        """Elimina un evento de la agenda local por su ID numérico."""
        event_id = event_id.strip()
        if event_id.isdigit():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM calendar_events WHERE id = ?", (int(event_id),))
                conn.commit()
                return cursor.rowcount > 0
        return False

    def get_prompt_context(self) -> str:
        """Formatea los próximos eventos para inyectarlos en el system prompt de LYLA."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        events = self.list_upcoming_events(limit=8)
        lines = [f"### Fecha/Hora Actual del Sistema: {now_str}"]
        lines.append("### Agenda Próxima de Víctor:")
        if not events:
            lines.append("- (Sin eventos próximos agendados)")
        else:
            for ev in events:
                lines.append(f"- [{ev['start_time']}] {ev['title']} (ID: {ev['id']}, Origen: {ev['source']})")
        return "\n".join(lines)

