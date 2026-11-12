#!/usr/bin/env python3
"""
LYLA 2099 // HOLOGRAPHIC DESKTOP HUD WIDGET (GTK4 + Cairo)
Interactive futuristic Spider-Man 2099 control deck, radar, voice/text chat & LLM token status for GNOME.
"""
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

# Asegurar acceso al paquete lyla y a las librerías del .venv
LYLA_PROJECT_DIR = Path("/home/spider-man/Proyectos/lyla-agent")
VENV_SITE_PACKAGES = LYLA_PROJECT_DIR / ".venv" / "lib" / "python3.14" / "site-packages"
if str(LYLA_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(LYLA_PROJECT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

import cairo
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from lyla.core.agent import LylaAgent
from lyla.audio.hotword import HotwordDetector


HUD_COMMANDS = [
    "/comands",
    "/commands",
    "/comandos",
    "/run",
    "/exec",
    "/open",
    "/mkdir",
    "/model",
    "/modelo",
    "/status",
    "/stats",
    "/calendar",
    "/agenda",
    "/alarm",
    "/alarma",
    "/sys",
    "/system",
    "/mobile",
    "/wallpaper",
    "/fondo",
    "/memory",
    "/recordar",
    "/olvidar",
    "/tema",
    "/theme",
    "/voice",
    "/stop",
]


# Los colores del HUD viven en config/themes/*.yaml y se generan con
# lyla.core.themes.build_css(). El CSS original (tema 2099) quedó como
# config/themes/spider-man-2099.yaml.
from lyla.core.themes import ThemeManager


class LylaHudWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.agent = LylaAgent()
        self.theme = self.agent.themes.active
        # Asegurar que el escritorio GNOME (GTK4/GTK3/Shell/Kitty) coincida al iniciar
        self.agent.themes.sync_desktop_theme(self.theme)
        self.set_title(self.theme.window_title)
        self.set_default_size(580, 540)
        self.set_size_request(420, 380)
        self.set_resizable(True)
        self.add_css_class("lyla-hud-window")

        self.voice_enabled = self.agent.config.audio_enabled
        self.is_recording = False
        self.rec_file = None
        self.rec_start_time = 0.0
        self.rec_tick = 0
        self.voice_mode_aura = False
        self.aura_tick = 0.0

        self.angle = 0.0
        self.prev_idle = 0
        self.prev_total = 0
        self.cpu_pct = 0.0
        self.ram_pct = 0.0
        self.ram_text = "0.0 / 0.0 GB"
        self.wall_idx = 0

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        main_box.set_margin_start(14)
        main_box.set_margin_end(14)
        self.set_child(main_box)

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.lbl_title = Gtk.Label(label=f"󱇪  {self.theme.header}")
        self.lbl_title.add_css_class("lyla-title")
        self.lbl_title.set_xalign(0.0)
        self.lbl_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_sub = Gtk.Label(label=self.theme.tagline)
        self.lbl_sub.add_css_class("lyla-subtitle")
        self.lbl_sub.set_xalign(0.0)
        self.lbl_sub.set_ellipsize(Pango.EllipsizeMode.END)
        hdr.append(self.lbl_title)
        hdr.append(self.lbl_sub)

        # Selector de tema: botón que abre la vista de temas (colores del HUD + personalidad de LYLA)
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_theme = Gtk.Label(label="TEMA:")
        lbl_theme.add_css_class("lyla-subtitle")
        lbl_theme.set_xalign(0.0)
        theme_row.append(lbl_theme)
        self.theme_button = Gtk.Button(label=f"{self.theme.name} ▾")
        self.theme_button.set_tooltip_text("Cambia los colores del HUD y la personalidad de LYLA")
        self.theme_button.connect("clicked", self.on_theme_button_clicked)
        theme_row.append(self.theme_button)
        hdr.append(theme_row)
        main_box.append(hdr)

        # Seguir cambios de tema hechos fuera del HUD (TUI [m], /tema en otro
        # proceso): el agente publica el tema en active-theme.json y el HUD lo
        # aplica en vivo, igual que la extensión de GNOME.
        GLib.timeout_add_seconds(2, self._sync_external_theme)

        # Center area: Left Cairo Spider-Web Radar + Right Telemetry & Actions
        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(mid)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_content_width(150)
        self.canvas.set_content_height(150)
        self.canvas.set_draw_func(self.on_draw)
        mid.append(self.canvas)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        right.set_hexpand(True)
        right.set_valign(Gtk.Align.CENTER)
        mid.append(right)

        self.lbl_cpu = Gtk.Label(label="  CPU NEURAL: 0%")
        self.lbl_cpu.add_css_class("lyla-metric-label")
        self.lbl_cpu.set_xalign(0.0)
        self.lbl_cpu.set_ellipsize(Pango.EllipsizeMode.END)
        right.append(self.lbl_cpu)

        self.lbl_ram = Gtk.Label(label="󰍛  MEMORIA: 0%")
        self.lbl_ram.add_css_class("lyla-metric-label")
        self.lbl_ram.set_xalign(0.0)
        self.lbl_ram.set_ellipsize(Pango.EllipsizeMode.END)
        right.append(self.lbl_ram)

        self.lbl_model = Gtk.Label(label="󰯊  MODELO: cargando...")
        self.lbl_model.add_css_class("lyla-model-badge")
        self.lbl_model.set_xalign(0.0)
        self.lbl_model.set_ellipsize(Pango.EllipsizeMode.END)
        right.append(self.lbl_model)

        self.lbl_sense = Gtk.Label(label="  SPIDER-SENSE: NOMINAL")
        self.lbl_sense.add_css_class("lyla-subtitle")
        self.lbl_sense.set_xalign(0.0)
        self.lbl_sense.set_ellipsize(Pango.EllipsizeMode.END)
        right.append(self.lbl_sense)

        # Quick Action Buttons
        btn_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        right.append(btn_grid)

        # Botón principal de STATUS de Modelos (Tokens & Porcentajes) + Voz ON/OFF + Callar
        row_top_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_grid.append(row_top_btns)

        self.b_status = Gtk.Button(label="󰐷  Status Modelos (Tokens/%)")
        self.b_status.add_css_class("lyla-btn-status")
        self.b_status.set_hexpand(True)
        self.b_status.connect("clicked", self.on_show_status)
        row_top_btns.append(self.b_status)

        self.b_voice_toggle = Gtk.Button(label="  Voz ON" if self.voice_enabled else "  Voz OFF")
        self.b_voice_toggle.add_css_class("lyla-btn")
        self.b_voice_toggle.set_tooltip_text("Activar o desactivar respuestas por voz de LYLA")
        self.b_voice_toggle.connect("clicked", self.on_toggle_voice_mode)
        row_top_btns.append(self.b_voice_toggle)

        self.b_mute = Gtk.Button(label="  Callar")
        self.b_mute.add_css_class("lyla-btn")
        self.b_mute.set_tooltip_text("Detiene inmediatamente la voz de LYLA")
        self.b_mute.connect("clicked", self.on_stop_voice)
        row_top_btns.append(self.b_mute)

        # Fila de botones del sistema 2099
        row_sys_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_grid.append(row_sys_btns)

        b_term = Gtk.Button(label="  Terminal")
        b_term.add_css_class("lyla-btn")
        b_term.set_hexpand(True)
        b_term.connect("clicked", lambda *_: subprocess.Popen(["kitty"]))
        row_sys_btns.append(b_term)

        b_tui = Gtk.Button(label="󰯊  TUI HUD")
        b_tui.add_css_class("lyla-btn")
        b_tui.set_hexpand(True)
        b_tui.connect(
            "clicked",
            lambda *_: subprocess.Popen(
                ["kitty", "--title", self.theme.window_title, "-e", "/home/spider-man/.local/bin/spider-hud"]
            ),
        )
        row_sys_btns.append(b_tui)

        b_wall = Gtk.Button(label="󰋩  Fondo")
        b_wall.add_css_class("lyla-btn")
        b_wall.set_hexpand(True)
        b_wall.connect("clicked", self.on_switch_wallpaper)
        row_sys_btns.append(b_wall)

        # Panel de Consola Holográfica y Dashboard (Stack conmutable)
        console_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        console_frame.add_css_class("lyla-console-frame")
        console_frame.set_vexpand(True)
        main_box.append(console_frame)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)
        console_frame.append(self.stack)

        # Página 1: Consola de Chat con LYLA
        scroll_chat = Gtk.ScrolledWindow()
        scroll_chat.set_vexpand(True)
        scroll_chat.set_hexpand(True)
        scroll_chat.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.add_css_class("lyla-console-text")
        scroll_chat.set_child(self.text_view)
        self.text_buffer = self.text_view.get_buffer()
        self.stack.add_named(scroll_chat, "chat")

        # Página 2: Dashboard Visual de Modelos Cloud (Tokens & Porcentajes %)
        scroll_dash = Gtk.ScrolledWindow()
        scroll_dash.set_vexpand(True)
        scroll_dash.set_hexpand(True)
        scroll_dash.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.dash_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.dash_box.set_margin_top(4)
        self.dash_box.set_margin_bottom(4)
        self.dash_box.set_margin_start(4)
        self.dash_box.set_margin_end(4)
        scroll_dash.set_child(self.dash_box)
        self.stack.add_named(scroll_dash, "dashboard")

        # Página 3: Modo de Voz - Esfera Aura Neuronal (Spider-Man 2099 / Siri Aura)
        aura_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        aura_box.set_vexpand(True)
        aura_box.set_hexpand(True)
        aura_box.set_valign(Gtk.Align.CENTER)
        aura_box.set_halign(Gtk.Align.CENTER)

        self.aura_canvas = Gtk.DrawingArea()
        self.aura_canvas.set_content_width(260)
        self.aura_canvas.set_content_height(260)
        self.aura_canvas.set_draw_func(self.on_draw_aura)
        aura_box.append(self.aura_canvas)

        self.lbl_aura_status = Gtk.Label(label=" LYLA ESCUCHANDO... HABLA LIBREMENTE")
        self.lbl_aura_status.add_css_class("lyla-subtitle")
        aura_box.append(self.lbl_aura_status)

        self.stack.add_named(aura_box, "aura")

        # Controlador de teclado global para silenciar con Esc o cancelar grabación
        win_key_ctrl = Gtk.EventControllerKey()
        win_key_ctrl.connect("key-pressed", self.on_window_key_pressed)
        self.add_controller(win_key_ctrl)

        # Barra inferior para hablar con LYLA: Stack conmutable entre "normal" y "recording"
        self.bottom_stack = Gtk.Stack()
        self.bottom_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        main_box.append(self.bottom_stack)

        # ─── Vista Normal: Texto + Enviar + Micrófono ───
        self.chat_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.bottom_stack.add_named(self.chat_bar, "normal")

        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("Habla con LYLA o usa /comands, /model, /status, /wallpaper... (Tab)")
        self.entry.add_css_class("lyla-entry")
        self.entry.connect("activate", self.on_send_text)
        self.chat_bar.append(self.entry)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_entry_key_pressed)
        self.entry.add_controller(key_ctrl)

        b_send = Gtk.Button(label="󰒊")
        b_send.add_css_class("lyla-btn-icon")
        b_send.set_tooltip_text("Enviar mensaje a LYLA (Enter)")
        b_send.connect("clicked", self.on_send_text)
        self.chat_bar.append(b_send)

        self.b_mic = Gtk.Button(label="")
        self.b_mic.add_css_class("lyla-btn-mic")
        self.b_mic.set_tooltip_text("Hablar por micrófono con LYLA")
        self.b_mic.connect("clicked", self.on_start_recording)
        self.chat_bar.append(self.b_mic)

        # ─── Vista Grabación: [ Cancelar] + [00:00] + [~~~~ Ondas ~~~~] + [󰒊 Enviar] ───
        self.rec_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bottom_stack.add_named(self.rec_bar, "recording")

        b_trash = Gtk.Button(label="")
        b_trash.add_css_class("lyla-btn-trash")
        b_trash.set_tooltip_text("Cancelar grabación (descartar y borrar audio)")
        b_trash.connect("clicked", self.on_cancel_recording)
        self.rec_bar.append(b_trash)

        self.lbl_rec_time = Gtk.Label(label="00:00")
        self.lbl_rec_time.add_css_class("lyla-rec-time")
        self.rec_bar.append(self.lbl_rec_time)

        self.wave_canvas = Gtk.DrawingArea()
        self.wave_canvas.set_hexpand(True)
        self.wave_canvas.set_content_height(34)
        self.wave_canvas.set_draw_func(self.on_draw_waveform)
        self.rec_bar.append(self.wave_canvas)

        b_rec_send = Gtk.Button(label="󰒊")
        b_rec_send.add_css_class("lyla-btn-rec-send")
        b_rec_send.set_tooltip_text("Terminar grabación y enviar a LYLA")
        b_rec_send.connect("clicked", self.on_send_recording)
        self.rec_bar.append(b_rec_send)

        # Mensaje inicial en el HUD
        prov, mod = self.agent.router.get_active_model()
        self._refresh_model_badge()
        self.append_console(
            f"󰯊  {self.theme.name} EN LÍNEA — Modelo activo: {prov} ({mod})\n"
            "Escribe un mensaje abajo, usa el botón  Hablar, o ejecuta cualquier comando (/comands, /model, /status, /calendar, /alarm, /sys)."
        )

        self.update_stats()
        GLib.timeout_add(70, self.on_tick)
        GLib.timeout_add(1200, self.update_stats)

        # Iniciar detector de Hotword en segundo plano ("oye lyla", "oye laila")
        self.hotword_detector = HotwordDetector(
            agent=self.agent,
            on_wake=lambda: GLib.idle_add(self.on_hotword_triggered)
        )
        self.hotword_detector.start()

    def _refresh_theme_button(self):
        """Actualiza la etiqueta del botón Tema con el tema activo."""
        if hasattr(self, "theme_button"):
            self.theme_button.set_label(f"{self.theme.name} ▾")

    def on_theme_button_clicked(self, _button):
        """Abre la vista de temas con previa."""
        self._open_theme_view()

    def _open_theme_view(self):
        """Vista previa interactiva de los 5 temas (estilo V2 HTML) con animación en vivo."""
        win = Gtk.Window(title="Temas de LYLA — Vista Previa")
        win.set_transient_for(self)
        win.set_modal(True)
        win.set_default_size(900, 680)
        win.set_resizable(True)
        win.add_css_class("lyla-gallery-window")

        meta_ui = {
            "spider-man-2099": ("● LIVE", "Retícula holográfica & glitch RGB"),
            "miles-morales": ("⚡ ACTIVE", "Arco voltaico fractal & flash"),
            "symbiote": ("⬤ WE ARE", "Brea blanca/negra ultra viscosa"),
            "spider-man-classic": ("● WEB", "Red elástica & sentido arácnido"),
            "lyla-default": ("● ONLINE", "Orbe fluido sereno (Apple UI)"),
        }

        # CSS por tema para las tarjetas mini-HUD (una sola vez por sesión).
        if not getattr(self, "_theme_view_css_loaded", False):
            css_rules = [
                ".lyla-gallery-window { background-color: #070709; color: #eeeeee; }",
                ".theme-gallery-card { background-color: #121215; border: 1px solid #262630; border-radius: 16px; padding: 14px; }",
                ".theme-gallery-card:hover { border-color: #4b5563; }",
                ".theme-card-title { color: #ffffff; font-weight: 800; font-size: 15px; }",
                ".theme-card-anim { color: #9ca3af; font-size: 11px; }",
                ".theme-card-persona { color: #9ca3af; font-size: 11.5px; }",
            ]
            for t in self.agent.themes.list_themes():
                bg = t.colors.get("background", "#080a12")
                sf = t.colors.get("surface", "#101016")
                sf2 = t.colors.get("surface_active", "#161622")
                pr = t.colors.get("primary", "#ff2a4b")
                ac = t.colors.get("accent", "#00f0ff")
                tx = t.colors.get("text", "#d4e0ff")
                dim = t.colors.get("text_dim", "#94a3b8")
                ok = t.colors.get("success", "#00ff9d")
                is_orb = t.animation == "orb"
                border_col = "rgba(255,255,255,0.18)" if is_orb else pr
                mini_font = '"Inter", "Cantarell", system-ui, sans-serif' if is_orb else '"JetBrainsMono Nerd Font", monospace'
                css_rules.append(
                    f".theme-mini-{t.id} {{ background-color: {bg}; color: {tx}; "
                    f"border: 1.5px solid {border_col}; border-radius: 12px; padding: 12px; font-family: {mini_font}; }}"
                    f"\n.theme-mini-hdr-{t.id} {{ color: {'#f8fafc' if is_orb else pr}; font-weight: 800; font-size: 11.5px; }}"
                    f"\n.theme-mini-badge-{t.id} {{ color: {ok}; font-weight: 700; font-size: 10.5px; }}"
                    f"\n.theme-mini-sub-{t.id} {{ color: {dim if is_orb else ac}; font-size: 9.5px; }}"
                    f"\n.theme-mini-pill-{t.id} {{ background-color: {sf2}; color: {tx if is_orb else ac}; "
                    f"border: 1px solid {'rgba(255,255,255,0.16)' if is_orb else ac}; border-radius: 6px; padding: 3px 8px; font-size: 10px; font-weight: 700; }}"
                    f"\n.theme-mini-console-{t.id} {{ background-color: {sf}; color: {dim}; "
                    f"border-radius: 8px; border-left: 3px solid {ac if is_orb else pr}; padding: 6px 8px; font-size: 10px; }}"
                    f"\n.theme-apply-{t.id} {{ background-color: {sf2}; color: {tx}; "
                    f"border: 1.5px solid {pr}; border-radius: 8px; padding: 6px 12px; font-weight: 700; font-size: 11.5px; }}"
                    f"\n.theme-apply-{t.id}:hover {{ background-color: {pr}; color: {'#050507' if pr.lower() == '#ffffff' else '#ffffff'}; }}"
                )
            provider = Gtk.CssProvider()
            provider.load_from_data("\n".join(css_rules))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            self._theme_view_css_loaded = True

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        win.set_child(scrolled)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(18)
        outer.set_margin_end(18)
        scrolled.set_child(outer)

        heading = Gtk.Label(label="Temas de LYLA — Vista Previa")
        heading.add_css_class("theme-card-title")
        heading.set_xalign(0.0)
        outer.append(heading)

        lead = Gtk.Label(
            label="Cada tema cambia la física del radar/aura, la personalidad de LYLA y todo tu escritorio GNOME (Shell, GTK4/GTK3 y Kitty)."
        )
        lead.add_css_class("theme-card-persona")
        lead.set_wrap(True)
        lead.set_xalign(0.0)
        outer.append(lead)

        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_column_homogeneous(True)
        outer.append(grid)

        preview_state = {"tick": 0.0, "areas": []}

        for idx, theme in enumerate(self.agent.themes.list_themes()):
            is_active = theme.id == self.agent.themes.active_id
            badge_txt, anim_desc = meta_ui.get(theme.id, ("● LIVE", theme.animation))

            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class("theme-gallery-card")

            # Mini-HUD embebido con el estilo real de cada tema
            mini = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            mini.add_css_class(f"theme-mini-{theme.id}")

            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            lbl_hdr = Gtk.Label(label=f"󱇪  {theme.header}")
            lbl_hdr.add_css_class(f"theme-mini-hdr-{theme.id}")
            lbl_hdr.set_xalign(0.0)
            lbl_hdr.set_hexpand(True)
            lbl_hdr.set_ellipsize(Pango.EllipsizeMode.END)
            lbl_badge = Gtk.Label(label=badge_txt)
            lbl_badge.add_css_class(f"theme-mini-badge-{theme.id}")
            top_row.append(lbl_hdr)
            top_row.append(lbl_badge)
            mini.append(top_row)

            lbl_tag = Gtk.Label(label=theme.tagline)
            lbl_tag.add_css_class(f"theme-mini-sub-{theme.id}")
            lbl_tag.set_xalign(0.0)
            lbl_tag.set_ellipsize(Pango.EllipsizeMode.END)
            mini.append(lbl_tag)

            mid_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            area = Gtk.DrawingArea()
            area.set_size_request(92, 92)
            area.set_valign(Gtk.Align.CENTER)

            def _make_draw(t_obj):
                def _draw(_da, cr, w, h):
                    self._draw_radar_for_theme(cr, w / 2.0, h / 2.0, min(w, h) / 2.0 - 4, t_obj, preview_state["tick"], cpu_pct=36.0)
                return _draw

            area.set_draw_func(_make_draw(theme))
            preview_state["areas"].append(area)
            mid_row.append(area)

            pills_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            pills_box.set_valign(Gtk.Align.CENTER)
            pills_box.set_hexpand(True)
            row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            for p_lbl in ("Status", "Voz ON", "Fondo"):
                pl = Gtk.Label(label=p_lbl)
                pl.add_css_class(f"theme-mini-pill-{theme.id}")
                row1.append(pl)
            pills_box.append(row1)

            mini_console = Gtk.Label(label=f"{theme.name} EN LÍNEA • Listo para operar.")
            mini_console.add_css_class(f"theme-mini-console-{theme.id}")
            mini_console.set_xalign(0.0)
            mini_console.set_wrap(True)
            pills_box.append(mini_console)
            mid_row.append(pills_box)
            mini.append(mid_row)
            card.append(mini)

            # Pie de tarjeta: nombre, animación, persona, swatches y botón de activar
            title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl_name = Gtk.Label(label=theme.name)
            lbl_name.add_css_class("theme-card-title")
            lbl_name.set_xalign(0.0)
            lbl_name.set_hexpand(True)
            title_row.append(lbl_name)
            if is_active:
                lbl_act = Gtk.Label()
                lbl_act.set_use_markup(True)
                lbl_act.set_markup(f"<span foreground='{theme.colors.get('success', '#00ff9d')}'><b>● ACTIVO</b></span>")
                title_row.append(lbl_act)
            card.append(title_row)

            lbl_anim = Gtk.Label()
            lbl_anim.set_use_markup(True)
            lbl_anim.set_markup(f"<span foreground='#9ca3af'>Animación: </span><span foreground='#eeeeee'><b>{anim_desc}</b></span>")
            lbl_anim.set_xalign(0.0)
            card.append(lbl_anim)

            # Resumen de persona (primera línea significativa del bloque YAML)
            persona_lines = [ln.strip() for ln in (theme.persona or "").splitlines() if ln.strip() and not ln.strip().startswith("###")]
            persona_short = " ".join(persona_lines[:2])
            if len(persona_short) > 120:
                persona_short = persona_short[:117].rstrip() + "..."
            lbl_per = Gtk.Label(label=persona_short)
            lbl_per.add_css_class("theme-card-persona")
            lbl_per.set_wrap(True)
            lbl_per.set_xalign(0.0)
            card.append(lbl_per)

            pr = theme.colors.get("primary", "#ffffff")
            ac = theme.colors.get("accent", "#ffffff")
            bg = theme.colors.get("background", "#000000")
            swatches = Gtk.Label()
            swatches.set_use_markup(True)
            swatches.set_markup(
                f"<span foreground='{pr}'>■</span> <span foreground='#aaaaaa'>Primario</span> <b>{pr}</b>   "
                f"<span foreground='{ac}'>■</span> <span foreground='#aaaaaa'>Acento</span> <b>{ac}</b>   "
                f"<span foreground='{bg}'>■</span> <span foreground='#aaaaaa'>Fondo</span> <b>{bg}</b>"
            )
            swatches.set_xalign(0.0)
            card.append(swatches)

            btn_apply = Gtk.Button(label="Tema activo ✓" if is_active else f"Aplicar {theme.name}")
            btn_apply.add_css_class(f"theme-apply-{theme.id}")
            btn_apply.connect("clicked", self.on_theme_view_picked, theme.id, win)
            card.append(btn_apply)

            grid.attach(card, idx % 2, idx // 2, 1, 1)

        def _tick_preview():
            preview_state["tick"] = (preview_state["tick"] + 0.065) % (200 * math.pi)
            for a in preview_state["areas"]:
                a.queue_draw()
            return True

        timer_id = GLib.timeout_add(33, _tick_preview)

        def _on_close(_w):
            nonlocal timer_id
            if timer_id is not None:
                GLib.Source.remove(timer_id)
                timer_id = None
            return False

        win.connect("close-request", _on_close)
        win.present()

    def on_theme_view_picked(self, _button, theme_id, win):
        """Aplica el tema elegido en la vista de temas y la cierra."""
        if theme_id != self.agent.themes.active_id:
            theme = self.agent.set_theme(theme_id)
            self.apply_theme(theme)
        win.close()

    def _sync_external_theme(self):
        """Aplica el tema si cambió fuera del HUD (TUI [m], /tema en otro proceso).

        Lee ~/.config/lyla/active-theme.json (el mismo archivo que lee la
        extensión de GNOME) cada 2 s. Devuelve True para seguir sondeando.
        """
        try:
            theme_file = Path.home() / ".config" / "lyla" / "active-theme.json"
            if theme_file.exists():
                data = json.loads(theme_file.read_text(encoding="utf-8"))
                theme_id = data.get("id")
                if theme_id and theme_id != self.theme.id:
                    theme = self.agent.themes.get(theme_id)
                    if theme is not None:
                        self.agent.set_theme(theme_id)
                        self.apply_theme(theme)
        except Exception:
            pass
        return True

    def apply_theme(self, theme):
        """Aplica un tema en vivo: CSS, textos de cabecera y colores de dibujo."""
        self.theme = theme
        self.set_title(theme.window_title)
        self.lbl_title.set_text(f"󱇪  {theme.header}")
        self.lbl_sub.set_text(theme.tagline)
        app = self.get_application()
        if app is not None and hasattr(app, "reload_theme_css"):
            app.reload_theme_css(self.agent.themes.build_css(theme))
        self.canvas.queue_draw()
        if hasattr(self, "aura_canvas"):
            self.aura_canvas.queue_draw()
        if hasattr(self, "wave_canvas"):
            self.wave_canvas.queue_draw()
        self._refresh_theme_button()

    def _refresh_model_badge(self):
        prov, mod = self.agent.router.get_active_model()
        v_icon = "" if self.voice_enabled else ""
        self.lbl_model.set_text(f"󰯊  LLM: {prov.upper()} ({mod}) {v_icon}")
        if hasattr(self, "b_voice_toggle"):
            self.b_voice_toggle.set_label("  Voz ON" if self.voice_enabled else "  Voz OFF")

    def on_toggle_voice_mode(self, *_):
        self.voice_enabled = not self.voice_enabled
        if not self.voice_enabled:
            self.agent.tts.player.stop()
        self._refresh_model_badge()
        state_lbl = "  VOZ DE LYLA ACTIVADA" if self.voice_enabled else "  VOZ DE LYLA DESACTIVADA"
        self.lbl_sub.set_text(state_lbl)

    def append_console(self, text: str):
        end_iter = self.text_buffer.get_end_iter()
        if self.text_buffer.get_char_count() > 0:
            self.text_buffer.insert(end_iter, "\n" + "─" * 54 + "\n")
            end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(end_iter, text.strip() + "\n")
        # Auto-scroll al final
        mark = self.text_buffer.create_mark(None, self.text_buffer.get_end_iter(), False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def on_window_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.is_recording:
                self.on_cancel_recording()
                return True
            else:
                self.on_stop_voice()
                return True
        return False

    def on_entry_key_pressed(self, _controller, keyval, _keycode, _state):
        # Tab (GDK_KEY_Tab) -> autocompletar comandos y modelos igual que en el CLI
        if keyval == Gdk.KEY_Tab:
            current = self.entry.get_text()
            stripped = current.lstrip()
            if stripped.startswith(("/model ", "/modelo ", "model ", "modelo ")):
                parts = stripped.split(maxsplit=1)
                prefix_cmd = parts[0] + " "
                partial = parts[1] if len(parts) > 1 else ""
                candidates = ["gemini", "groq"] + [o["model"] for o in self.agent.router.get_available_models()]
                matches = [c for c in candidates if c.lower().startswith(partial.lower())]
                if matches:
                    idx = (matches.index(partial) + 1) % len(matches) if partial in matches else 0
                    new_txt = prefix_cmd + matches[idx]
                    self.entry.set_text(new_txt)
                    self.entry.set_position(-1)
            else:
                matches = [c for c in HUD_COMMANDS if c.startswith(stripped.lower())]
                if matches:
                    idx = (matches.index(stripped.lower()) + 1) % len(matches) if stripped.lower() in matches else 0
                    chosen = matches[idx]
                    if chosen in ("/model", "/modelo"):
                        chosen += " "
                    self.entry.set_text(chosen)
                    self.entry.set_position(-1)
            return True

        # Escape silencia la voz o cancela grabación
        if keyval == Gdk.KEY_Escape:
            if self.is_recording:
                self.on_cancel_recording()
            else:
                self.on_stop_voice()
            return True

        return False

    def on_stop_voice(self, *_):
        self.agent.tts.player.stop()
        if self.voice_mode_aura:
            self.voice_mode_aura = False
            self.stack.set_visible_child_name("chat")
            if hasattr(self, "hotword_detector"):
                self.hotword_detector.set_dialog_state(False)
        self.lbl_sub.set_text("  VOZ SILENCIADA • LISTO PARA ESCRIBIR")

    def on_show_status(self, *_):
        if self.stack.get_visible_child_name() == "chat":
            self.refresh_dashboard()
            self.stack.set_visible_child_name("dashboard")
            self.b_status.set_label("󱇪  Volver al Chat")
        else:
            self.stack.set_visible_child_name("chat")
            self.b_status.set_label("󰐷  Status Modelos (Tokens/%)")

    def refresh_dashboard(self):
        # Limpiar dashboard previo
        while child := self.dash_box.get_first_child():
            self.dash_box.remove(child)

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl_dash_title = Gtk.Label(label="󰐷  STATUS DE MODELOS CLOUD (TOKENS & CUOTA)")
        lbl_dash_title.add_css_class("lyla-dash-title")
        lbl_dash_title.set_hexpand(True)
        lbl_dash_title.set_xalign(0.0)
        hdr_box.append(lbl_dash_title)

        b_back = Gtk.Button(label="󰁍 Volver")
        b_back.add_css_class("lyla-btn")
        b_back.connect("clicked", lambda *_: self.on_show_status())
        hdr_box.append(b_back)
        self.dash_box.append(hdr_box)

        report = self.agent.get_models_status_report()
        for item in report:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.add_css_class("lyla-dash-card-active" if item["active"] else "lyla-dash-card")

            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            mark = "● [ACTIVO]" if item["active"] else "○"
            prov_str = item["provider"].upper()
            mod_str = item["model"]
            lbl_m = Gtk.Label(label=f"{mark} {prov_str} → {mod_str}")
            lbl_m.set_xalign(0.0)
            lbl_m.set_hexpand(True)
            lbl_m.add_css_class("lyla-model-badge" if item["active"] else "lyla-dash-title")
            top_row.append(lbl_m)

            if not item["active"]:
                b_select = Gtk.Button(label="󰯊 Usar")
                b_select.add_css_class("lyla-btn")
                b_select.connect("clicked", lambda *_, m=mod_str: self._switch_model_from_dash(m))
                top_row.append(b_select)

            card.append(top_row)

            # Barra de Progreso
            pbar = Gtk.ProgressBar()
            pbar.set_fraction(max(0.0, min(1.0, item["used_pct"] / 100.0)))
            pbar.add_css_class("lyla-progressbar-active" if item["active"] else "lyla-progressbar")
            card.append(pbar)

            # Métricas
            lbl_det = Gtk.Label(
                label=f"Tokens: {item['tokens_total']:,} / {item['daily_limit']:,} "
                      f"({item['used_pct']:.1f}% usado │ {item['remaining_pct']:.1f}% libre) • "
                      f"Llamadas: {item['calls']} • Lat: {item['last_latency']:.2f}s"
            )
            lbl_det.add_css_class("lyla-dash-sub")
            lbl_det.set_xalign(0.0)
            card.append(lbl_det)

            self.dash_box.append(card)

        # Resumen general de la sesión
        stats = self.agent.tracker.get_summary()
        lbl_sess = Gtk.Label(
            label=f" Sesión: {stats['total_tokens_in']} in / {stats['total_tokens_out']} out "
                  f"({stats['total_tokens']} total) • Uptime: {stats['uptime_seconds']}s"
        )
        lbl_sess.add_css_class("lyla-dash-sub")
        lbl_sess.set_xalign(0.0)
        self.dash_box.append(lbl_sess)

    def _switch_model_from_dash(self, model_name: str):
        try:
            self.agent.router.switch_model(model_name)
        except Exception:
            pass
        self._refresh_model_badge()
        self.refresh_dashboard()

    def on_send_text(self, *_):
        user_text = self.entry.get_text().strip()
        if not user_text:
            return
        self.entry.set_text("")
        self.process_user_input(user_text)

    def process_user_input(self, user_text: str, force_speak: bool = False):
        # Si envía un comando para callar o /exit en el HUD
        if user_text.lower() in ("/exit", "exit", "salir", "quit"):
            self.agent.tts.player.stop()
            self.close()
            return

        self.append_console(f"Víctor > {user_text}")
        self.lbl_sub.set_text(f"  PROCESANDO EN LA NUBE • {self.theme.name.upper()}...")

        def _worker():
            try:
                res = self.agent.handle_hud_input(user_text, voice_enabled=self.voice_enabled)
                self.voice_enabled = res.get("voice_enabled", self.voice_enabled)
                reply_display = res.get("text", "")
                should_speak = res.get("speak", False) or force_speak
                raw_reply = res.get("raw_reply", reply_display)

                def _update_ui():
                    if reply_display:
                        self.append_console(reply_display)
                    self._refresh_model_badge()
                    # Si el comando cambió el tema (/tema), aplicarlo en vivo
                    # sin esperar al sondeo de 2 s.
                    if self.agent.themes.active_id != self.theme.id:
                        self.apply_theme(self.agent.themes.active)
                    else:
                        self.lbl_sub.set_text(self.theme.tagline)
                    return False

                GLib.idle_add(_update_ui)

                if should_speak and raw_reply:
                    GLib.idle_add(lambda: self.lbl_sub.set_text("  LYLA HABLANDO... (Clic en ' Callar' o [Esc] para detener)") or False)
                    if self.voice_mode_aura:
                        GLib.idle_add(lambda: self.lbl_aura_status.set_text(" LYLA HABLANDO...") or False)
                    self.agent.speak_reply(raw_reply, interactive_cli=False, force=True)
                    GLib.idle_add(lambda: self.lbl_sub.set_text(self.theme.tagline) or False)
                    # Si estamos en modo conversación continua de voz, tras responder entra de nuevo en modo escucha
                    if self.voice_mode_aura:
                        time.sleep(0.5)
                        GLib.idle_add(self.start_aura_voice_mode)
                else:
                    if self.voice_mode_aura:
                        GLib.idle_add(lambda: self.stack.set_visible_child_name("chat") or False)
                        self.voice_mode_aura = False
                        if hasattr(self, "hotword_detector"):
                            self.hotword_detector.set_dialog_state(False)
            except Exception as e:
                GLib.idle_add(lambda: self.append_console(f"  [Error]: {e}") or False)
                GLib.idle_add(lambda: self.lbl_sub.set_text(self.theme.tagline) or False)
                if self.voice_mode_aura:
                    GLib.idle_add(lambda: self.stack.set_visible_child_name("chat") or False)
                    self.voice_mode_aura = False
                    if hasattr(self, "hotword_detector"):
                        self.hotword_detector.set_dialog_state(False)

        threading.Thread(target=_worker, daemon=True).start()

    def on_hotword_triggered(self):
        """Disparado cuando el detector escucha 'oye lyla' u 'oye laila'."""
        self.voice_enabled = True
        self.b_voice_toggle.set_label("  Voz ON")
        self.start_aura_voice_mode()

    def start_aura_voice_mode(self):
        """Activa el modo de conversación con la esfera Aura (ocultando el chat de texto)."""
        if hasattr(self, "hotword_detector"):
            self.hotword_detector.set_dialog_state(True)
        self.voice_mode_aura = True
        self.stack.set_visible_child_name("aura")
        self.lbl_aura_status.set_text(" LYLA ESCUCHANDO... HABLA LIBREMENTE")
        self.on_start_recording()

    def on_start_recording(self, *_):
        self.agent.tts.player.stop()
        self.is_recording = True
        self.rec_start_time = time.time()
        self.rec_tick = 0
        self.lbl_rec_time.set_text("00:00")
        self.bottom_stack.set_visible_child_name("recording")
        self.lbl_sub.set_text("  GRABANDO VOZ... [󰒊 ENVIAR] O [ CANCELAR]")
        self.rec_file = self.agent.capture.start_recording()

    def on_cancel_recording(self, *_):
        self.is_recording = False
        self.voice_mode_aura = False
        self.stack.set_visible_child_name("chat")
        if hasattr(self, "hotword_detector"):
            self.hotword_detector.set_dialog_state(False)
        self.bottom_stack.set_visible_child_name("normal")
        self.agent.capture.stop_recording()
        if self.rec_file and os.path.exists(self.rec_file):
            try:
                os.unlink(self.rec_file)
            except Exception:
                pass
        self.rec_file = None
        self.lbl_sub.set_text("OPERADOR: VÍCTOR • GRABACIÓN CANCELADA")

    def on_send_recording(self, *_):
        self.is_recording = False
        self.bottom_stack.set_visible_child_name("normal")
        self.agent.capture.stop_recording()
        self.lbl_sub.set_text("  TRANSCRIBIENDO AUDIO EN LA NUBE...")
        if self.voice_mode_aura:
            self.lbl_aura_status.set_text("󰯊 LYLA PROCESANDO TU VOZ...")

        rec_path = self.rec_file
        self.rec_file = None

        def _stt_worker():
            try:
                transcription = self.agent.stt.transcribe(rec_path) if rec_path else ""
                if not transcription:
                    GLib.idle_add(
                        lambda: self.append_console("  No se detectó voz clara en la grabación.") or False
                    )
                    GLib.idle_add(
                        lambda: self.lbl_sub.set_text(self.theme.tagline) or False
                    )
                    if self.voice_mode_aura:
                        GLib.idle_add(lambda: self.stack.set_visible_child_name("chat") or False)
                        self.voice_mode_aura = False
                    if hasattr(self, "hotword_detector"):
                        self.hotword_detector.set_dialog_state(False)
                    return
                self.voice_enabled = True
                GLib.idle_add(lambda: self.process_user_input(transcription, force_speak=True) or False)
            except Exception as e:
                GLib.idle_add(lambda: self.append_console(f"  Error STT: {e}") or False)
                GLib.idle_add(
                    lambda: self.lbl_sub.set_text(self.theme.tagline) or False
                )
                if self.voice_mode_aura:
                    GLib.idle_add(lambda: self.stack.set_visible_child_name("chat") or False)
                    self.voice_mode_aura = False
                if hasattr(self, "hotword_detector"):
                    self.hotword_detector.set_dialog_state(False)

        threading.Thread(target=_stt_worker, daemon=True).start()

    def on_toggle_mic(self, *_):
        self.on_start_recording()

    def on_draw_waveform(self, _area, cr, width, height):
        # Fondo sutil con bordes redondeados
        cr.save()
        radius = 8.0
        cr.new_sub_path()
        cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*self.theme.rgb("surface", 0.9))
        cr.fill_preserve()
        cr.set_source_rgba(*self.theme.rgb("accent", 0.35))
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()

        # Dibujar barras de onda dinámicas estilo WhatsApp / Telegram
        bar_width = 3.5
        bar_gap = 2.5
        total_step = bar_width + bar_gap
        usable_width = width - 16.0
        if usable_width <= 0:
            return

        num_bars = int(usable_width // total_step)
        if num_bars <= 0:
            return

        start_x = 8.0 + (usable_width - (num_bars * total_step - bar_gap)) / 2.0
        mid_y = height / 2.0
        cr.set_line_width(bar_width)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND

        for i in range(num_bars):
            x = start_x + i * total_step + bar_width / 2.0
            # Simulación armónica de voz fluida
            w1 = math.sin(self.rec_tick * 0.16 + i * 0.32) * 0.48
            w2 = math.cos(self.rec_tick * 0.09 - i * 0.18) * 0.36
            w3 = math.sin(self.rec_tick * 0.28 + i * 0.65) * 0.16
            comb = abs(w1 + w2 + w3)
            norm_h = max(0.12, min(0.88, comb))
            bar_h = norm_h * (height - 12)
            half_h = bar_h / 2.0

            # Alternancia sutil de color del tema: acento con pulsos del color primario
            if (i + self.rec_tick // 4) % 6 == 0:
                cr.set_source_rgba(*self.theme.rgb("primary", 0.95))
            else:
                cr.set_source_rgba(*self.theme.rgb("accent", 0.88))

            cr.move_to(x, mid_y - half_h)
            cr.line_to(x, mid_y + half_h)
            cr.stroke()

    def on_switch_wallpaper(self, *_):
        res = self.agent.system.cycle_wallpaper(self.wall_idx)
        self.wall_idx = res.get("index", (self.wall_idx + 1))
        msg = res.get("message", "Fondo de pantalla actualizado")
        self.lbl_sub.set_text(msg)

    def on_tick(self):
        self.angle = (self.angle + 0.045) % (2 * math.pi)
        self.canvas.queue_draw()
        if self.voice_mode_aura:
            self.aura_tick = (self.aura_tick + 0.07) % (2 * math.pi)
            if hasattr(self, "aura_canvas"):
                self.aura_canvas.queue_draw()
        if self.is_recording:
            self.rec_tick += 1
            elapsed = int(time.time() - self.rec_start_time)
            mins, secs = divmod(elapsed, 60)
            self.lbl_rec_time.set_text(f"{mins:02d}:{secs:02d}")
            self.wave_canvas.queue_draw()
        return True

    # --- Efectos de animación por tema (Cairo) ---
    # Cada tema define su estilo en config/themes/<id>.yaml (animation: ...).
    # Diseños de la V2 de Victor (temas_de_lyla_vista_pre-V2.html):
    # 2099 "futuristic": holograma Alchemax (scanlines + barra + glitch RGB).
    # Miles "electric": arco voltaico fractal + anillo Tesla punteado.
    # Simbionte "symbiote": brea ultra viscosa (masas negras con borde blanco + tendrils).
    # Clásico "web": telaraña elástica estilo Tobey Maguire + sentido arácnido.
    # LYLA "orb": orbe fluido sereno estilo Apple (Siri) — 3 capas + anillos.
    def _draw_theme_fx(self, cr, cx, cy, r, tick, theme=None):
        """Efecto de animación del tema activo dentro de un círculo (cx, cy, r)."""
        theme = theme or self.theme
        style = theme.animation
        if style == "futuristic":
            self._fx_futuristic(cr, cx, cy, r, tick, theme)
        elif style == "electric":
            self._fx_electric(cr, cx, cy, r, tick, theme)
        elif style == "symbiote":
            self._fx_symbiote(cr, cx, cy, r, tick, theme)
        elif style == "web":
            self._fx_web(cr, cx, cy, r, tick, theme)
        elif style == "orb":
            self._fx_orb(cr, cx, cy, r, tick, theme)

    def _fx_futuristic(self, cr, cx, cy, r, tick, theme):
        """2099: retícula holográfica Alchemax, anillos contrarrotatorios, scanlines y glitch RGB."""
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.clip()
        # Scanlines horizontales sutiles
        cr.set_line_width(1.0)
        cr.set_source_rgba(*theme.rgb("accent", 0.06))
        y = cy - r
        while y < cy + r:
            cr.move_to(cx - r, y)
            cr.line_to(cx + r, y)
            cr.stroke()
            y += 3.5

        # Anillo exterior cian rotatorio con marcas cardinales
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(tick * 0.4)
        cr.set_line_width(1.3)
        cr.set_dash([14, 6, 4, 6])
        cr.set_source_rgba(*theme.rgb("accent", 0.72))
        cr.arc(0, 0, r * 0.90, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])
        cr.set_line_width(1.8)
        for k in range(4):
            ang = k * math.pi / 2.0
            cr.move_to(math.cos(ang) * r * 0.80, math.sin(ang) * r * 0.80)
            cr.line_to(math.cos(ang) * r * 0.98, math.sin(ang) * r * 0.98)
            cr.stroke()
        cr.restore()

        # Anillo interior rojo contrarrotatorio con muescas de garra
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(-tick * 0.75)
        cr.set_line_width(1.8)
        cr.set_dash([10, 12])
        cr.set_source_rgba(*theme.rgb("primary", 0.85))
        cr.arc(0, 0, r * 0.68, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])
        cr.restore()

        # Emblema hexagonal / octogonal con salto cuántico y glitch RGB
        glitch_on = int(tick * 5) % 14 == 6
        gx = -3.0 if glitch_on else 0.0
        gy = 1.5 if glitch_on else 0.0
        for off_x, off_y, col, al in (
            (gx, gy, "accent", 0.55),
            (-gx if glitch_on else 0.0, -gy if glitch_on else 0.0, "primary", 0.70 if glitch_on else 0.45),
        ):
            cr.set_line_width(1.2)
            cr.set_source_rgba(*theme.rgb(col, al))
            hex_r = r * 0.48
            for i in range(6):
                a = i * math.pi / 3.0 - math.pi / 2.0
                px = cx + off_x + math.cos(a) * hex_r
                py = cy + off_y + math.sin(a) * hex_r
                if i == 0:
                    cr.move_to(px, py)
                else:
                    cr.line_to(px, py)
            cr.close_path()
            cr.stroke()

        # Barra de escaneo vertical brillante
        scan_y = cy + math.sin(tick * 1.15) * r * 0.88
        grad_scan = cairo.LinearGradient(cx - r, scan_y, cx + r, scan_y)
        grad_scan.add_color_stop_rgba(0.0, *theme.rgb("accent", 0.0))
        grad_scan.add_color_stop_rgba(0.35, *theme.rgb("accent", 0.65))
        grad_scan.add_color_stop_rgba(0.65, *theme.rgb("primary", 0.65))
        grad_scan.add_color_stop_rgba(1.0, *theme.rgb("primary", 0.0))
        cr.set_source(grad_scan)
        cr.set_line_width(3.5)
        cr.move_to(cx - r, scan_y)
        cr.line_to(cx + r, scan_y)
        cr.stroke()
        cr.restore()

    def _fx_electric(self, cr, cx, cy, r, tick, theme):
        """Miles Morales: núcleo bio-eléctrico dorado/cian + bobina Tesla + arcos fractales."""
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.clip()
        # Resplandor de núcleo dorado + cian
        core = cairo.RadialGradient(cx, cy, 2, cx, cy, r * 0.88)
        core.add_color_stop_rgba(0.0, 1.0, 0.835, 0.0, 0.24)
        core.add_color_stop_rgba(0.5, *theme.rgb("accent", 0.16))
        core.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
        cr.set_source(core)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

        # Bobina Tesla perimetral giratoria (alternando cian y dorado)
        surge = (int(tick * 6) % 9) in (0, 1)
        cr.set_line_width(1.8 if surge else 1.4)
        cr.set_dash([12, 18, 5, 14], tick * 48)
        ring_col = "success" if surge else "accent"
        cr.set_source_rgba(*theme.rgb(ring_col, 0.92 if surge else 0.72))
        cr.arc(cx, cy, r * 0.92, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])

        # Rayos fractales bio-eléctricos en oro y cian con destello blanco
        step = int(tick * 11)
        rng = random.Random(1337 + step)
        for bolt in range(4):
            if rng.random() < 0.28 and not surge:
                continue
            ang = rng.uniform(0, 2 * math.pi)
            start_r = r * 0.96
            cr.move_to(cx + math.cos(ang) * start_r, cy + math.sin(ang) * start_r)
            segs = 6
            pts = [(cx + math.cos(ang) * start_r, cy + math.sin(ang) * start_r)]
            for s in range(1, segs + 1):
                f = s / segs
                cur_r = start_r * (1 - f * 1.4)
                bx = cx + math.cos(ang) * cur_r
                by = cy + math.sin(ang) * cur_r
                off = rng.uniform(-r * 0.14, r * 0.14)
                pts.append((bx + math.cos(ang + math.pi / 2) * off, by + math.sin(ang + math.pi / 2) * off))
            color = "success" if bolt % 2 == 0 else "accent"
            # Halo del rayo
            cr.set_line_width(3.2)
            cr.set_line_cap(1)
            cr.set_source_rgba(*theme.rgb(color, 0.45))
            cr.move_to(*pts[0])
            for px, py in pts[1:]:
                cr.line_to(px, py)
            cr.stroke()
            # Núcleo nítido del rayo
            cr.set_line_width(1.6)
            cr.set_source_rgba(*theme.rgb(color, 0.98))
            cr.move_to(*pts[0])
            for px, py in pts[1:]:
                cr.line_to(px, py)
            cr.stroke()
        cr.restore()

    def _fx_symbiote(self, cr, cx, cy, r, tick, theme):
        """Simbionte (Venom): brea negro azabache ultra viscosa con bordes blanco puro y brillo húmedo."""
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.clip()

        # Tendrils pesados que cruzan y se estiran desde los bordes
        for i in range(4):
            ang = (i * math.pi / 2.0) + 0.55 + math.sin(tick * 0.7 + i) * 0.28
            reach = r * (0.20 + 0.35 * math.sin(tick * 1.15 + i * 1.4))
            perp = ang + math.pi / 2.0
            w_base = r * 0.14
            w_tip = r * 0.05
            x0, y0 = cx + math.cos(ang) * r * 1.05, cy + math.sin(ang) * r * 1.05
            x1, y1 = cx + math.cos(ang) * reach, cy + math.sin(ang) * reach
            bend = math.sin(tick * 1.6 + i) * r * 0.18
            mx, my = (x0 + x1) / 2.0 + math.cos(perp) * bend, (y0 + y1) / 2.0 + math.sin(perp) * bend

            cr.move_to(x0 + math.cos(perp) * w_base, y0 + math.sin(perp) * w_base)
            cr.curve_to(
                mx + math.cos(perp) * w_base * 0.6, my + math.sin(perp) * w_base * 0.6,
                mx + math.cos(perp) * w_tip, my + math.sin(perp) * w_tip,
                x1, y1,
            )
            cr.curve_to(
                mx - math.cos(perp) * w_tip, my - math.sin(perp) * w_tip,
                mx - math.cos(perp) * w_base * 0.6, my - math.sin(perp) * w_base * 0.6,
                x0 - math.cos(perp) * w_base, y0 - math.sin(perp) * w_base,
            )
            cr.close_path()
            cr.set_source_rgba(0.015, 0.015, 0.02, 0.98)
            cr.fill_preserve()
            cr.set_line_width(1.8)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.90)
            cr.stroke()

        # Masas orgánicas negro azabache con reborde blanco puro y reflejo húmedo
        blobs = [
            (0.0, 0.0, 0.42, 0.0),
            (-0.36, -0.32, 0.26, 1.2),
            (0.36, 0.34, 0.27, 2.2),
            (0.34, -0.32, 0.21, 3.1),
            (-0.32, 0.34, 0.18, 4.3),
        ]
        for bx, by, br, phase in blobs:
            dx = math.sin(tick * 0.75 + phase) * r * 0.14
            dy = math.cos(tick * 0.65 + phase) * r * 0.14
            scale = 1.0 + 0.14 * math.sin(tick * 1.15 + phase)
            x = cx + bx * r + dx
            y = cy + by * r + dy
            cr.save()
            cr.translate(x, y)
            cr.scale(
                scale * (1.0 + 0.12 * math.sin(tick * 0.9 + phase)),
                scale * (1.0 - 0.12 * math.sin(tick * 0.9 + phase)),
            )
            cr.set_source_rgba(0.012, 0.012, 0.016, 0.98)
            cr.arc(0, 0, br * r, 0, 2 * math.pi)
            cr.fill_preserve()
            cr.set_line_width(2.0)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
            cr.stroke()
            # Brillo especular húmedo en el borde superior izquierdo de cada masa
            cr.set_line_width(1.3)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.55)
            cr.arc(0, 0, br * r * 0.74, math.pi * 1.1, math.pi * 1.55)
            cr.stroke()
            cr.restore()

        cr.restore()

    def _fx_web(self, cr, cx, cy, r, tick, theme):
        """Spider-Man Clásico: red elástica con tensión + ondas zig-zag del Sentido Arácnido."""
        wobble = 1.0 + 0.045 * math.sin(tick * 2.1)
        cr.save()
        cr.translate(cx, cy)
        cr.scale(wobble, wobble)
        cr.translate(-cx, -cy)
        spokes = 12
        cr.set_line_width(1.0)
        cr.set_source_rgba(*theme.rgb("accent", 0.55))
        for i in range(spokes):
            a = (i * 2 * math.pi / spokes) + tick * 0.04
            cr.move_to(cx, cy)
            cr.line_to(cx + math.cos(a) * r, cy + math.sin(a) * r)
            cr.stroke()
        for r_fac in (0.30, 0.55, 0.80):
            rr = r * r_fac
            for i in range(spokes):
                a0 = (i * 2 * math.pi / spokes) + tick * 0.04
                a1 = ((i + 1) * 2 * math.pi / spokes) + tick * 0.04
                x0, y0 = cx + math.cos(a0) * rr, cy + math.sin(a0) * rr
                x1, y1 = cx + math.cos(a1) * rr, cy + math.sin(a1) * rr
                am = (a0 + a1) / 2.0
                sag = rr * 0.18
                xm, ym = cx + math.cos(am) * (rr - sag), cy + math.sin(am) * (rr - sag)
                cr.move_to(x0, y0)
                cr.curve_to(xm, ym, xm, ym, x1, y1)
                cr.stroke()
        cr.restore()

        # Doble onda en zig-zag del Sentido Arácnido (roja y dorada)
        period = 2.4
        waves = [
            (0.0, (*theme.rgb("primary", 1.0)[:3],), 1.8),
            (0.35, (1.0, 0.835, 0.0), 1.3),
        ]
        for delay, rgb_tuple, lw in waves:
            phase = ((tick - delay) % period) / period
            alpha = 0.95 * (1.0 - phase)
            if alpha <= 0.03:
                continue
            scale = 0.32 + 0.80 * phase
            cr.save()
            cr.set_line_width(lw)
            cr.set_source_rgba(*rgb_tuple, alpha)
            pts = []
            for i in range(20):
                ang = i * 2 * math.pi / 20
                rr = r * scale * (0.95 if i % 2 == 0 else 0.76)
                pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
            cr.move_to(*pts[0])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.close_path()
            cr.stroke()
            cr.restore()

    def _fx_orb(self, cr, cx, cy, r, tick, theme):
        """LYLA (Apple UI / visionOS): 3 capas luminosas suaves + anillos armónicos serenos."""
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.clip()
        # Fondo radial suave visionOS
        bg = cairo.RadialGradient(cx, cy, 2, cx, cy, r)
        bg.add_color_stop_rgba(0.0, 0.075, 0.086, 0.149, 0.95)
        bg.add_color_stop_rgba(1.0, 0.035, 0.039, 0.063, 0.98)
        cr.set_source(bg)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

        layers = [
            ("primary", 0.56, 0.0, 0.85),     # lavanda (#a78bfa)
            ("accent", 0.52, 2.0, 1.05),      # azul cielo (#38bdf8)
            ("text_bright", 0.36, 3.8, 0.70), # perla blanco
        ]
        for color, rad, phase, speed in layers:
            ang = tick * 0.42 * speed + phase
            ox = math.cos(ang) * r * 0.16
            oy = math.sin(ang) * r * 0.16
            rr = r * rad * (1.0 + 0.10 * math.sin(tick * 0.75 + phase))
            grad = cairo.RadialGradient(cx + ox, cy + oy, 1, cx + ox, cy + oy, rr)
            grad.add_color_stop_rgba(0.0, *theme.rgb(color, 0.65))
            grad.add_color_stop_rgba(0.55, *theme.rgb(color, 0.25))
            grad.add_color_stop_rgba(1.0, *theme.rgb(color, 0.0))
            cr.set_source(grad)
            cr.arc(cx + ox, cy + oy, rr, 0, 2 * math.pi)
            cr.fill()

        # 2 anillos armónicos finos estilo visionOS
        for idx, (rx_fac, ry_fac, rot, col, alpha) in enumerate([
            (0.76, 0.68, tick * 0.35, "text_bright", 0.32),
            (0.68, 0.76, -tick * 0.42, "accent", 0.36),
        ]):
            cr.save()
            cr.translate(cx, cy)
            cr.rotate(rot)
            cr.scale(rx_fac, ry_fac)
            cr.set_line_width(1.2)
            cr.set_source_rgba(*theme.rgb(col, alpha))
            cr.arc(0, 0, r, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
        cr.restore()

    def _draw_spider_emblem(self, cr, cx, cy, scale, theme):
        """Dibuja el emblema de araña estilizada escalado al radio actual."""
        cr.save()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        cr.set_source_rgba(*theme.rgb("primary", 0.95))
        cr.set_line_width(2.2)

        # Cuerpo de araña (diamante)
        cr.move_to(0, -18)
        cr.line_to(11, -4)
        cr.line_to(7, 16)
        cr.line_to(0, 23)
        cr.line_to(-7, 16)
        cr.line_to(-11, -4)
        cr.close_path()
        cr.stroke()

        # Ojos brillantes
        cr.set_source_rgba(*theme.rgb("accent", 0.95))
        cr.move_to(-6, -4)
        cr.line_to(-2, -1)
        cr.stroke()
        cr.move_to(6, -4)
        cr.line_to(2, -1)
        cr.stroke()

        # 8 patas cyber
        cr.set_source_rgba(*theme.rgb("primary", 0.95))
        legs = [
            ((-9, -8), (-24, -26), (-18, -42)),
            ((-11, -2), (-32, -10), (-38, -26)),
            ((-10, 5), (-30, 14), (-34, 32)),
            ((-7, 12), (-20, 28), (-14, 44)),
            ((9, -8), (24, -26), (18, -42)),
            ((11, -2), (32, -10), (38, -26)),
            ((10, 5), (30, 14), (34, 32)),
            ((7, 12), (20, 28), (14, 44)),
        ]
        for (x1, y1), (x2, y2), (x3, y3) in legs:
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.line_to(x3, y3)
            cr.stroke()
        cr.restore()

    def _draw_radar_for_theme(self, cr, cx, cy, radius, theme, tick, cpu_pct=0.0):
        """Renderiza el radar completo (HUD principal y mini-previas de la galería)."""
        style = theme.animation

        # Fondo circular oscuro del tema
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(*theme.rgb("background", 0.95))
        cr.fill()

        if style == "orb":
            # LYLA Apple UI: orbe fluido sereno sin rejilla cyber ni araña
            self._fx_orb(cr, cx, cy, radius, tick, theme)
            cr.set_line_width(1.6)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.24)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()
            return

        if style == "symbiote":
            # Venom: brea negro/blanco ultra viscosa sin rejilla cian encima
            self._fx_symbiote(cr, cx, cy, radius, tick, theme)
            cr.set_line_width(2.0)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()
            self._draw_spider_emblem(cr, cx, cy, (radius / 80.0) * 0.72, theme)
            return

        if style == "web":
            self._fx_web(cr, cx, cy, radius, tick, theme)
        else:
            # Telaraña sutil de fondo para 2099 / Miles
            cr.set_line_width(1.0)
            cr.set_source_rgba(*theme.rgb("accent", 0.20 if style == "electric" else 0.26))
            for i in range(8):
                a = (i * 2 * math.pi / 8) + tick * 0.25
                cr.move_to(cx, cy)
                cr.line_to(cx + math.cos(a) * radius, cy + math.sin(a) * radius)
                cr.stroke()
            for r_fac in (0.35, 0.62, 0.88):
                cr.arc(cx, cy, radius * r_fac, 0, 2 * math.pi)
                cr.stroke()
            self._draw_theme_fx(cr, cx, cy, radius, tick, theme)

        # Arco exterior rotatorio + indicador de CPU
        cr.set_line_width(2.8)
        cr.set_source_rgba(*theme.rgb("accent", 0.85))
        cr.arc(cx, cy, radius, tick, tick + math.pi * 0.8)
        cr.stroke()
        cr.arc(cx, cy, radius, tick + math.pi, tick + math.pi * 1.8)
        cr.stroke()

        cpu_angle = (cpu_pct / 100.0) * (2 * math.pi)
        cr.set_line_width(4.0)
        cr.set_source_rgba(*theme.rgb("primary", 0.95))
        cr.arc(cx, cy, radius - 6, -math.pi / 2, -math.pi / 2 + cpu_angle)
        cr.stroke()

        self._draw_spider_emblem(cr, cx, cy, radius / 80.0, theme)

    def on_draw_aura(self, _area, cr, width, height):
        """
        Dibuja el Orbe / Esfera Aura Neuronal de LYLA (Spider-Man 2099 / Siri Orb).
        Renderiza ondas de luz fluidas en degradado radial (Púrpura, Magenta, Cian 2099)
        que reaccionan con movimiento constante según el sonido y estado de escucha.
        """
        cx = width / 2.0
        cy = height / 2.0
        base_radius = min(width, height) * 0.36

        # Fondo sutil con viñeta
        cr.save()

        # Pulso armónico de respiración del aura
        pulse = math.sin(self.aura_tick * 2.2) * 4.5 + math.cos(self.aura_tick * 1.4) * 3.0
        active_r = base_radius + pulse

        # Capa 1: Resplandor exterior difuminado (Glow) — colores del tema
        rad_pat1 = cairo.RadialGradient(cx, cy, active_r * 0.4, cx, cy, active_r * 1.35)
        for offset, stop in zip((0.0, 0.5, 1.0), self.theme.aura_stops("glow")):
            rad_pat1.add_color_stop_rgba(offset, *stop)
        cr.set_source(rad_pat1)
        cr.arc(cx, cy, active_r * 1.35, 0, 2 * math.pi)
        cr.fill()

        # Capa 2: Esfera base con degradado cósmico — colores del tema
        rad_pat2 = cairo.RadialGradient(cx - active_r * 0.25, cy - active_r * 0.25, 5, cx, cy, active_r)
        for offset, stop in zip((0.0, 0.5, 0.9), self.theme.aura_stops("sphere")):
            rad_pat2.add_color_stop_rgba(offset, *stop)
        cr.set_source(rad_pat2)
        cr.arc(cx, cy, active_r, 0, 2 * math.pi)
        cr.fill()

        # Capa 3: Anillo de corte y borde de la esfera
        cr.set_line_width(2.5)
        cr.set_source_rgba(*self.theme.aura_ring())
        cr.arc(cx, cy, active_r, 0, 2 * math.pi)
        cr.stroke()

        # Capa 4: Ondas de luz entrelazadas internas (Cintas de Siri / Alchemax Aura)
        cr.save()
        # Recortar dibujo al interior de la esfera
        cr.arc(cx, cy, active_r - 2.0, 0, 2 * math.pi)
        cr.clip()

        num_waves = 5
        for w_idx in range(num_waves):
            phase = self.aura_tick * (1.8 + w_idx * 0.4) + w_idx * (math.pi / 2.5)
            cr.save()
            cr.set_line_width(12.0 + w_idx * 3.5)
            cr.set_line_cap(1)

            # Paleta de ondas del tema activo
            wave_colors = self.theme.aura_stops("waves")
            if wave_colors:
                cr.set_source_rgba(*wave_colors[w_idx % len(wave_colors)])
            else:
                cr.set_source_rgba(*self.theme.rgb("accent", 0.75))

            cr.move_to(cx - active_r, cy)
            # Curva Bézier fluida que ondula con la voz
            c1x = cx - active_r * 0.45
            c1y = cy + math.sin(phase) * (active_r * 0.65)
            c2x = cx + active_r * 0.45
            c2y = cy - math.cos(phase * 0.9) * (active_r * 0.65)
            end_x = cx + active_r
            end_y = cy

            cr.curve_to(c1x, c1y, c2x, c2y, end_x, end_y)
            cr.stroke()
            cr.restore()

        # Efecto de animación del tema activo dentro de la esfera
        self._draw_theme_fx(cr, cx, cy, active_r, self.aura_tick)

        # Destello central brillante (Core Glow)
        glow_pat = cairo.RadialGradient(cx, cy, 2, cx, cy, active_r * 0.45)
        glow_pat.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.9)
        glow_pat.add_color_stop_rgba(0.4, 0.2, 0.9, 1.0, 0.4)
        glow_pat.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
        cr.set_source(glow_pat)
        cr.arc(cx, cy, active_r * 0.45, 0, 2 * math.pi)
        cr.fill()

        cr.restore()
        cr.restore()

    def update_stats(self):
        try:
            with open("/proc/stat", "r") as f:
                parts = [int(x) for x in f.readline().split()[1:]]
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                total = sum(parts)
                d_idle = idle - self.prev_idle
                d_total = total - self.prev_total
                if d_total > 0 and self.prev_total > 0:
                    self.cpu_pct = max(0.0, min(100.0, ((d_total - d_idle) * 100.0) / d_total))
                self.prev_idle = idle
                self.prev_total = total
        except Exception:
            pass

        try:
            info = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        info[k.strip()] = int(v.strip().split()[0])
            tot = info.get("MemTotal", 1)
            avail = info.get("MemAvailable", tot)
            used = tot - avail
            self.ram_pct = (used * 100.0) / tot
            self.ram_text = f"{used / 1048576:.1f}/{tot / 1048576:.1f} GB"
        except Exception:
            pass

        self.lbl_cpu.set_text(f"  CPU NEURAL : {self.cpu_pct:4.1f}%")
        self.lbl_ram.set_text(f"󰍛  RAM MATRIZ : {self.ram_pct:4.1f}% ({self.ram_text})")
        if self.cpu_pct > 75:
            self.lbl_sense.set_text("  SPIDER-SENSE: ALERTA DE CARGA")
        else:
            self.lbl_sense.set_text(f"  SPIDER-SENSE: ACTIVO [{time.strftime('%H:%M:%S')}]")
        return True

    def on_draw(self, _area, cr, width, height):
        cx, cy = width / 2.0, height / 2.0
        radius = min(cx, cy) - 10
        self._draw_radar_for_theme(cr, cx, cy, radius, self.theme, self.angle, cpu_pct=self.cpu_pct)


class LylaApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.spiderman2099.LylaHud")
        self._css_provider = None
        self._themes = None

    def do_activate(self):
        # El CSS se genera con el tema activo (config/themes/*.yaml).
        # El ThemeManager de la app solo se usa para la carga inicial; el
        # cambio de tema en vivo lo maneja el ThemeManager del agente.
        self._themes = ThemeManager(
            themes_dir=Path(__file__).resolve().parent.parent / "config" / "themes",
            settings_file=Path(__file__).resolve().parent.parent / "config" / "settings.yaml",
        )
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(self._themes.build_css())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = LylaHudWindow(self)
        win.present()

    def reload_theme_css(self, css_bytes):
        """Recarga el CSS del HUD (llamado por la ventana al cambiar de tema)."""
        if self._css_provider is not None:
            self._css_provider.load_from_data(css_bytes)


if __name__ == "__main__":
    app = LylaApp()
    app.run()

