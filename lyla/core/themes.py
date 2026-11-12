"""
Sistema de temas de LYLA.

Cada tema es un YAML en config/themes/ con:
  - colores del HUD (CSS + aura + radar)
  - textos de cabecera (header, tagline, título de ventana)
  - persona: texto que se inyecta al system prompt de LYLA

El tema activo se guarda en settings.yaml bajo theme.active.
"""
from pathlib import Path
from string import Template
from typing import Dict, List, Optional
import json
import re
import yaml

DEFAULT_THEME_ID = "spider-man-2099"

# Orden fijo en el selector del HUD y en el ciclo [m] del TUI.
THEME_ORDER = [
    "spider-man-2099",
    "miles-morales",
    "symbiote",
    "spider-man-classic",
    "lyla-default",
]

REQUIRED_COLORS = [
    "primary", "primary_dark", "accent", "accent_dark",
    "background", "surface", "surface_active", "entry_bg", "console_bg",
    "text", "text_dim", "text_bright", "success", "danger",
]


def hex_to_rgb(hex_color: str):
    """'#ff2a4b' -> (255, 42, 75)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_to_rgb_str(hex_color: str) -> str:
    """'#ff2a4b' -> '255, 42, 75' (para rgba() en CSS)."""
    r, g, b = hex_to_rgb(hex_color)
    return f"{r}, {g}, {b}"


def hex_to_rgb_floats(hex_color: str):
    """'#ff2a4b' -> (1.0, 0.165, 0.294) (para Cairo)."""
    r, g, b = hex_to_rgb(hex_color)
    return (r / 255.0, g / 255.0, b / 255.0)


def _normalize(text: str) -> str:
    """Quita acentos, guiones y espacios y pasa a minúsculas: 'Spider-Man Clásico' -> 'spidermanclasico'."""
    import unicodedata
    no_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", no_accents.lower())


# Estilos de animación del HUD (uno por tema, definido en su YAML).
# Diseños de la V2 de Victor: futuristic (2099 holograma), electric (Miles),
# symbiote (Venom brea viscosa), web (clásico / Tobey), orb (LYLA Apple).
ANIMATION_STYLES = ("futuristic", "electric", "symbiote", "web", "orb")


# Puente con el escritorio GNOME (Arch-Spidey-v1, extensión spider-hud).
# El agente publica el tema activo en ~/.config/lyla/active-theme.json y la
# extensión lo lee para actualizar la barra superior y el shell theme.
# badge: texto corto de la barra superior. shell_theme: directorio del tema
# en ~/.themes/ (generado a partir de SpiderMan-2099-Cyber por recolor).
from lyla.core.gnome_theme import apply_desktop_theme

DESKTOP_THEME_META = {
    "spider-man-2099": {"badge": "2099 // LYLA", "shell_theme": "SpiderMan-2099-Cyber", "gnome_accent": "red"},
    "miles-morales": {"badge": "MILES // LYLA", "shell_theme": "SpiderMan-Miles-Morales", "gnome_accent": "red"},
    "symbiote": {"badge": "SYMBIOTE // LYLA", "shell_theme": "SpiderMan-Symbiote", "gnome_accent": "slate"},
    "spider-man-classic": {"badge": "CLASSIC // LYLA", "shell_theme": "SpiderMan-Classic", "gnome_accent": "blue"},
    "lyla-default": {"badge": "LYLA", "shell_theme": "Lyla-Default", "gnome_accent": "purple"},
}


class Theme:
    """Un tema cargado desde config/themes/<id>.yaml."""

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.name: str = data.get("name", self.id)
        self.header: str = data.get("header", "")
        self.tagline: str = data.get("tagline", "")
        self.window_title: str = data.get("window_title", f"LYLA // {self.name} HUD")
        # Estilo de animación del HUD: futuristic (2099), electric (Miles),
        # symbiote (Venom), web (clásico / Tobey Maguire) u orb (LYLA Apple).
        # Un valor desconocido cae a "futuristic" (la animación original).
        style = str(data.get("animation", "futuristic")).strip().lower()
        self.animation: str = style if style in ANIMATION_STYLES else "futuristic"
        self.colors: Dict[str, str] = data.get("colors", {})
        self.aura: Dict[str, list] = data.get("aura", {})
        self.persona: str = (data.get("persona") or "").strip()

    def rgb(self, color_key: str, alpha: float = 1.0):
        """Color del tema como tupla RGBA de floats 0..1 para Cairo."""
        r, g, b = hex_to_rgb_floats(self.colors[color_key])
        return (r, g, b, alpha)

    def aura_stops(self, layer: str):
        """Lista de paradas [r, g, b, a] del aura (glow / sphere / waves)."""
        stops = self.aura.get(layer)
        if stops:
            return [[float(v) for v in stop] for stop in stops]
        return [list(stop) for stop in _DEFAULT_AURA.get(layer, [])]

    def aura_ring(self):
        """Color del anillo del aura como [r, g, b, a]."""
        ring = self.aura.get("ring") or _DEFAULT_AURA["ring"]
        return [float(v) for v in ring]


# Aura por defecto (2099) si un tema no define la suya.
_DEFAULT_AURA = {
    "glow": [[0.9, 0.1, 0.4, 0.45], [0.2, 0.0, 0.6, 0.25], [0.0, 0.0, 0.0, 0.0]],
    "sphere": [[0.1, 0.2, 0.6, 0.95], [0.3, 0.05, 0.5, 0.95], [0.05, 0.05, 0.15, 0.98]],
    "waves": [[0.0, 0.95, 1.0, 0.75], [1.0, 0.15, 0.5, 0.70], [0.85, 0.95, 1.0, 0.85]],
    "ring": [0.15, 0.2, 0.4, 0.8],
}


# Plantilla CSS del HUD. Es el CSS original de hud.py con los colores
# reemplazados por variables $... que se sustituyen con el tema activo.
CSS_TEMPLATE = Template(r"""
window.lyla-hud-window {
    background-color: rgba($background_rgb, 0.95);
    border: 2px solid $primary;
    border-radius: 16px;
}
.lyla-title {
    color: $primary;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 14px;
}
.lyla-subtitle {
    color: $accent;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 11px;
}
.lyla-metric-label {
    color: $text;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 700;
    font-size: 11.5px;
}
.lyla-model-badge {
    color: $success;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 11.5px;
}
.lyla-btn {
    background: linear-gradient(135deg, rgba($primary_rgb, 0.22) 0%, rgba($accent_rgb, 0.12) 100%);
    color: $accent;
    border: 1px solid rgba($accent_rgb, 0.55);
    border-radius: 8px;
    padding: 5px 9px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 700;
    font-size: 11px;
}
.lyla-btn:hover {
    background: linear-gradient(135deg, $primary 0%, $primary_dark 100%);
    color: #ffffff;
    border-color: $accent;
}
.lyla-btn-status {
    background: linear-gradient(135deg, rgba($accent_rgb, 0.25) 0%, rgba($primary_rgb, 0.20) 100%);
    color: #ffffff;
    border: 1px solid $accent;
    border-radius: 8px;
    padding: 6px 10px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 11.5px;
}
.lyla-btn-status:hover {
    background: linear-gradient(135deg, $accent 0%, $accent_dark 100%);
    color: $background;
}
.lyla-btn-mic {
    background: linear-gradient(135deg, rgba($primary_rgb, 0.30) 0%, rgba($primary_dark_rgb, 0.35) 100%);
    color: $primary;
    border: 1px solid $primary;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 15px;
}
.lyla-btn-mic:hover {
    background: linear-gradient(135deg, $primary 0%, $primary_dark 100%);
    color: #ffffff;
    border-color: $accent;
}
.lyla-btn-trash {
    background: linear-gradient(135deg, rgba($primary_rgb, 0.25) 0%, rgba($primary_dark_rgb, 0.35) 100%);
    color: $primary;
    border: 1px solid rgba($primary_rgb, 0.7);
    border-radius: 8px;
    padding: 6px 14px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 15px;
}
.lyla-btn-trash:hover {
    background: $danger;
    color: #ffffff;
    border-color: $primary;
}
.lyla-btn-rec-send {
    background: linear-gradient(135deg, rgba($accent_rgb, 0.30) 0%, rgba($success_rgb, 0.35) 100%);
    color: $success;
    border: 1.5px solid $success;
    border-radius: 8px;
    padding: 6px 14px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 15px;
}
.lyla-btn-rec-send:hover {
    background: $success;
    color: $background;
    border-color: $success;
}
.lyla-rec-time {
    color: $accent;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 11.5px;
}
.lyla-btn-icon {
    background: linear-gradient(135deg, rgba($accent_rgb, 0.22) 0%, rgba($primary_rgb, 0.18) 100%);
    color: $accent;
    border: 1px solid rgba($accent_rgb, 0.65);
    border-radius: 8px;
    padding: 6px 14px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 15px;
}
.lyla-btn-icon:hover {
    background: linear-gradient(135deg, $accent 0%, $accent_dark 100%);
    color: $background;
    border-color: $accent;
}
.lyla-dash-card {
    background-color: rgba($surface_rgb, 0.88);
    border: 1px solid rgba($accent_rgb, 0.35);
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 6px;
}
.lyla-dash-card-active {
    background-color: rgba($surface_active_rgb, 0.95);
    border: 1.5px solid $success;
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 6px;
}
.lyla-dash-title {
    color: $accent;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 12px;
}
.lyla-dash-sub {
    color: $text_dim;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 10.5px;
}
.lyla-progressbar progress {
    background-color: $primary;
    border-radius: 4px;
}
.lyla-progressbar-active progress {
    background-color: $success;
    border-radius: 4px;
}
.lyla-progressbar trough {
    background-color: rgba(255, 255, 255, 0.12);
    border-radius: 4px;
    min-height: 8px;
}
.lyla-entry {
    background-color: rgba($entry_bg_rgb, 0.95);
    color: $accent;
    border: 1px solid rgba($accent_rgb, 0.65);
    border-radius: 8px;
    padding: 6px 10px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 12px;
}
.lyla-console-frame {
    background-color: rgba($console_bg_rgb, 0.92);
    border: 1px solid rgba($primary_rgb, 0.55);
    border-radius: 10px;
    padding: 8px;
}
.lyla-console-text {
    background-color: transparent;
    color: $text_bright;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 11.5px;
}
""")


class ThemeManager:
    """Carga los temas de config/themes/ y maneja el tema activo."""

    def __init__(self, themes_dir: Path, settings_file: Path,
                 default_id: str = DEFAULT_THEME_ID):
        self.themes_dir = Path(themes_dir)
        self.settings_file = Path(settings_file)
        self.default_id = default_id
        self.themes: Dict[str, Theme] = {}
        self._load_all()
        self._active_id = self._read_active_id()
        if self._active_id not in self.themes:
            self._active_id = default_id if default_id in self.themes else self._first_id()
        # Publicar el tema activo para el escritorio GNOME (la extensión lo lee).
        self.publish_desktop_theme()

    @property
    def desktop_theme_file(self) -> Path:
        """Archivo que la extensión spider-hud lee para seguir el tema activo."""
        return Path.home() / ".config" / "lyla" / "active-theme.json"

    def publish_desktop_theme(self, theme: Optional[Theme] = None) -> None:
        """Escribe el tema activo en ~/.config/lyla/active-theme.json.

        La extensión spider-hud de GNOME lo lee cada 2 s y actualiza la barra
        superior (badge), el menú y el shell theme. Si no se puede escribir
        (p. ej. HOME no escribible), no rompe nada: solo avisa por consola.
        """
        theme = theme or self.active
        if theme is None:
            return
        meta = DESKTOP_THEME_META.get(theme.id, {})
        payload = {
            "id": theme.id,
            "name": theme.name,
            "badge": meta.get("badge", theme.name.upper()),
            "header": theme.header,
            "tagline": theme.tagline,
            "shell_theme": meta.get("shell_theme", "SpiderMan-2099-Cyber"),
            "animation": theme.animation,
            "colors": {
                "primary": theme.colors.get("primary", "#ffffff"),
                "accent": theme.colors.get("accent", "#ffffff"),
                "background": theme.colors.get("background", "#000000"),
                "text": theme.colors.get("text", "#ffffff"),
            },
        }
        try:
            target = self.desktop_theme_file
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(target)
        except Exception as e:
            print(f"[Temas] No se pudo publicar el tema de escritorio: {e}")

    def _load_all(self):
        if not self.themes_dir.exists():
            return
        for path in sorted(self.themes_dir.glob("*.yaml")) + sorted(self.themes_dir.glob("*.yml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                theme = Theme(data)
                self.themes[theme.id] = theme
            except Exception as e:
                print(f"[Temas] No se pudo cargar {path.name}: {e}")

    def _first_id(self) -> str:
        ordered = self.ordered_ids()
        return ordered[0] if ordered else self.default_id

    def ordered_ids(self) -> List[str]:
        """IDs en el orden del selector (THEME_ORDER primero, resto alfabético)."""
        known = [t for t in THEME_ORDER if t in self.themes]
        rest = sorted(t for t in self.themes if t not in THEME_ORDER)
        return known + rest

    def list_themes(self) -> List[Theme]:
        return [self.themes[t] for t in self.ordered_ids()]

    def get(self, theme_id: str) -> Optional[Theme]:
        return self.themes.get(theme_id)

    def find(self, query: str) -> Optional[Theme]:
        """Busca por id exacto o por fragmento del nombre (insensible a mayúsculas,
        acentos, guiones y espacios: 'spiderman clasico' encuentra 'Spider-Man Clásico')."""
        q = (query or "").strip().lower()
        if not q:
            return None
        if q in self.themes:
            return self.themes[q]
        nq = _normalize(q)
        for theme in self.list_themes():
            if nq and (nq in _normalize(theme.name) or nq in _normalize(theme.id)):
                return theme
        for theme in self.list_themes():
            if q in theme.name.lower() or q in theme.id.lower():
                return theme
        return None

    @property
    def active(self) -> Theme:
        theme = self.themes.get(self._active_id)
        if theme is None:
            theme = self.themes.get(self._first_id())
        return theme

    @property
    def active_id(self) -> str:
        return self.active.id

    def _read_active_id(self) -> str:
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                theme_cfg = raw.get("theme", {}) or {}
                if isinstance(theme_cfg, dict) and theme_cfg.get("active"):
                    return str(theme_cfg["active"])
        except Exception:
            pass
        return self.default_id

    def set_active(self, theme_id: str) -> Theme:
        """Cambia el tema activo, lo persiste en settings.yaml y sincroniza GNOME."""
        theme = self.get(theme_id)
        if theme is None:
            raise ValueError(f"Tema no encontrado: {theme_id}")
        self._active_id = theme.id
        self._persist_active_id(theme.id)
        self.publish_desktop_theme(theme)
        self.sync_desktop_theme(theme)
        return theme

    def sync_desktop_theme(self, theme: Optional[Theme] = None) -> None:
        """Aplica el tema al escritorio GNOME completo (GTK4, GTK3, Shell, Kitty)."""
        theme = theme or self.active
        if theme is None:
            return
        meta = DESKTOP_THEME_META.get(theme.id, {})
        apply_desktop_theme(theme, meta)

    def _persist_active_id(self, theme_id: str):
        """Escribe theme.active en settings.yaml preservando el resto del archivo y sus comentarios."""
        try:
            lines = []
            if self.settings_file.exists():
                lines = self.settings_file.read_text(encoding="utf-8").splitlines()
            out = []
            i = 0
            found_theme = False
            found_active = False
            while i < len(lines):
                line = lines[i]
                if re.match(r"^theme:\s*$", line):
                    found_theme = True
                    out.append(line)
                    i += 1
                    # Recorrer el bloque indentado de theme:
                    while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t") or lines[i].strip() == ""):
                        if re.match(r"^\s*active:\s*.*$", lines[i]):
                            indent = re.match(r"^(\s*)active:", lines[i]).group(1) or "  "
                            out.append(f"{indent}active: {theme_id}")
                            found_active = True
                        else:
                            out.append(lines[i])
                        i += 1
                    if not found_active:
                        out.append(f"  active: {theme_id}")
                        found_active = True
                    continue
                out.append(line)
                i += 1
            if not found_theme:
                if out and out[-1].strip() != "":
                    out.append("")
                out.append("theme:")
                out.append(f"  active: {theme_id}")
            self.settings_file.write_text("\n".join(out) + "\n", encoding="utf-8")
        except Exception as e:
            print(f"[Temas] No se pudo persistir el tema activo: {e}")

    def persona_prompt(self, theme: Optional[Theme] = None) -> str:
        """Texto de personalidad del tema activo, para inyectar al system prompt."""
        theme = theme or self.active
        if not theme or not theme.persona:
            return ""
        return f"\n\n---\n\n{theme.persona}"

    def build_css(self, theme: Optional[Theme] = None) -> bytes:
        """Genera el CSS del HUD con los colores del tema. Devuelve bytes para Gtk.CssProvider."""
        theme = theme or self.active
        colors = dict(theme.colors)
        # Valores por defecto si al tema le falta algún color (no romper el HUD).
        fallback = self.themes.get(DEFAULT_THEME_ID)
        if fallback is not None and fallback is not theme:
            for key in REQUIRED_COLORS:
                colors.setdefault(key, fallback.colors.get(key, "#ffffff"))
        mapping = {}
        for key in REQUIRED_COLORS:
            value = colors.get(key, "#ffffff")
            mapping[key] = value
            mapping[f"{key}_rgb"] = hex_to_rgb_str(value)
        css = CSS_TEMPLATE.safe_substitute(mapping)
        # Estilo Apple UI / visionOS sereno para el tema LYLA ("orb")
        if theme.animation == "orb":
            css += """
window.lyla-hud-window {
    background-color: rgba(18, 20, 32, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 20px;
}
.lyla-title, .lyla-subtitle, .lyla-metric-label, .lyla-model-badge,
.lyla-btn, .lyla-btn-status, .lyla-dash-title, .lyla-dash-sub,
.lyla-entry, .lyla-console-text {
    font-family: "Inter", "Cantarell", system-ui, sans-serif;
}
.lyla-title { color: #f8fafc; font-weight: 700; }
.lyla-btn, .lyla-btn-status, .lyla-btn-icon, .lyla-btn-mic {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 10px;
    color: #e2e8f0;
}
.lyla-btn:hover, .lyla-btn-status:hover, .lyla-btn-icon:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(56, 189, 248, 0.55);
    color: #ffffff;
}
.lyla-console-frame {
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-left: 2px solid #38bdf8;
    border-radius: 12px;
}
.lyla-entry {
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 12px;
    color: #f8fafc;
}
"""
        elif theme.animation == "symbiote":
            css += """
window.lyla-hud-window {
    background-color: rgba(2, 2, 3, 0.97);
    border: 2px solid rgba(255, 255, 255, 0.85);
}
.lyla-console-frame {
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-left: 3px solid #ffffff;
}
"""
        return css.encode("utf-8")
