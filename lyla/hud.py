#!/usr/bin/env python3
"""
LYLA 2099 // HOLOGRAPHIC DESKTOP HUD WIDGET (GTK4 + Cairo)
Interactive futuristic Spider-Man 2099 control deck, radar, voice/text chat & LLM token status for GNOME.
"""
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
        self._build_theme_popover()

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
                ["kitty", "--title", "LYLA // SPIDER-MAN 2099 TACTICAL HUD", "-e", "/home/spider-man/.local/bin/spider-hud"]
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
            f"󰯊  LYLA 2099 EN LÍNEA — Modelo activo: {prov} ({mod})\n"
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

    def _build_theme_popover(self):
        """Vista de temas: popover con un botón por tema (color + nombre; el activo en negrita)."""
        self.theme_popover = Gtk.Popover()
        self.theme_popover.set_parent(self.theme_button)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        self.theme_popover.set_child(box)
        self._theme_popover_buttons = {}
        for theme in self.agent.themes.list_themes():
            btn = Gtk.Button()
            btn.set_halign(Gtk.Align.FILL)
            label = Gtk.Label()
            label.set_xalign(0.0)
            label.set_use_markup(True)
            btn.set_child(label)
            btn.connect("clicked", self.on_theme_button_picked, theme.id)
            box.append(btn)
            self._theme_popover_buttons[theme.id] = (btn, label)
        self._refresh_theme_popover()

    def _refresh_theme_popover(self):
        """Actualiza el botón y la vista de temas (punto de color + activo en negrita)."""
        if not hasattr(self, "_theme_popover_buttons"):
            return
        for theme in self.agent.themes.list_themes():
            _btn, label = self._theme_popover_buttons[theme.id]
            name = f"<b>{theme.name}</b>" if theme.id == self.agent.themes.active_id else theme.name
            primary = theme.colors.get("primary", "#ffffff")
            label.set_markup(f"<span foreground='{primary}'>●</span>  {name}")
        if hasattr(self, "theme_button"):
            self.theme_button.set_label(f"{self.theme.name} ▾")

    def on_theme_button_clicked(self, _button):
        """Abre la vista de temas."""
        self._refresh_theme_popover()
        self.theme_popover.popup()

    def on_theme_button_picked(self, _button, theme_id):
        """Aplica el tema elegido en la vista de temas y la cierra."""
        if theme_id != self.agent.themes.active_id:
            theme = self.agent.set_theme(theme_id)
            self.apply_theme(theme)
        self._refresh_theme_popover()
        self.theme_popover.popdown()

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
        self._refresh_theme_popover()

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
        self.lbl_sub.set_text("  PROCESANDO EN LA NUBE 2099...")

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
                    self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK")
                    return False

                GLib.idle_add(_update_ui)

                if should_speak and raw_reply:
                    GLib.idle_add(lambda: self.lbl_sub.set_text("  LYLA HABLANDO... (Clic en ' Callar' o [Esc] para detener)") or False)
                    if self.voice_mode_aura:
                        GLib.idle_add(lambda: self.lbl_aura_status.set_text(" LYLA HABLANDO...") or False)
                    self.agent.speak_reply(raw_reply, interactive_cli=False, force=True)
                    GLib.idle_add(lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False)
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
                GLib.idle_add(lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False)
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
                        lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False
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
                    lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False
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
    # 2099 "futuristic" no añade nada: sus ondas y su radar ya son la animación.
    # Miles "electric": rayos. Simbionte "symbiote": tentáculos.
    # Clásico "web": telaraña estilo Tobey Maguire. Lyla "freckles": pecas.
    def _draw_theme_fx(self, cr, cx, cy, r, tick):
        """Efecto de animación del tema activo dentro de un círculo (cx, cy, r)."""
        style = self.theme.animation
        if style == "electric":
            self._fx_electric(cr, cx, cy, r, tick)
        elif style == "symbiote":
            self._fx_symbiote(cr, cx, cy, r, tick)
        elif style == "web":
            self._fx_web(cr, cx, cy, r, tick)
        elif style == "freckles":
            self._fx_freckles(cr, cx, cy, r, tick)
        # "futuristic": sin efecto extra (las ondas y el radar ya animan).

    def _fx_electric(self, cr, cx, cy, r, tick):
        """Rayos de Miles Morales: relámpagos que zigzaguean y parpadean."""
        step = int(tick * 10)
        rng = random.Random(1337 + step)
        for bolt in range(3):
            if rng.random() < 0.35:
                continue  # a veces el rayo no se ve (parpadeo)
            ang = rng.uniform(0, 2 * math.pi)
            cr.move_to(cx + math.cos(ang) * r, cy + math.sin(ang) * r)
            segs = 6
            for s in range(1, segs + 1):
                f = s / segs
                bx = cx + math.cos(ang) * r * (1 - f)
                by = cy + math.sin(ang) * r * (1 - f)
                off = rng.uniform(-r * 0.12, r * 0.12)
                px = bx + math.cos(ang + math.pi / 2) * off
                py = by + math.sin(ang + math.pi / 2) * off
                cr.line_to(px, py)
            cr.set_line_width(2.0)
            cr.set_line_cap(1)
            color = "success" if bolt % 2 == 0 else "accent"
            cr.set_source_rgba(*self.theme.rgb(color, 0.9))
            cr.stroke()

    def _fx_symbiote(self, cr, cx, cy, r, tick):
        """Tentáculos del simbionte: curvas orgánicas que pulsan y se balancean."""
        for i in range(4):
            ang = (i * 2 * math.pi / 4) + math.sin(tick * 0.6 + i) * 0.25
            length = r * (0.55 + 0.25 * math.sin(tick * 1.3 + i * 1.7))
            x0 = cx + math.cos(ang) * r
            y0 = cy + math.sin(ang) * r
            wx = math.sin(tick * 2.0 + i) * r * 0.12
            wy = math.cos(tick * 2.0 + i) * r * 0.12
            c1x = cx + math.cos(ang) * r * 0.66 + wx
            c1y = cy + math.sin(ang) * r * 0.66 + wy
            x2 = cx + math.cos(ang) * length
            y2 = cy + math.sin(ang) * length
            cr.set_line_width(5.0)
            cr.set_line_cap(1)
            color = "primary" if i % 2 == 0 else "accent"
            cr.set_source_rgba(*self.theme.rgb(color, 0.75))
            cr.move_to(x0, y0)
            cr.curve_to(c1x, c1y, c1x, c1y, x2, y2)
            cr.stroke()

    def _fx_web(self, cr, cx, cy, r, tick):
        """Telaraña estilo Tobey Maguire: 12 radios + anillos que se comban."""
        spokes = 12
        cr.set_line_width(1.0)
        cr.set_source_rgba(*self.theme.rgb("accent", 0.45))
        for i in range(spokes):
            a = (i * 2 * math.pi / spokes) + tick * 0.05
            cr.move_to(cx, cy)
            cr.line_to(cx + math.cos(a) * r, cy + math.sin(a) * r)
            cr.stroke()
        for r_fac in (0.3, 0.55, 0.8):
            rr = r * r_fac
            for i in range(spokes):
                a0 = (i * 2 * math.pi / spokes) + tick * 0.05
                a1 = ((i + 1) * 2 * math.pi / spokes) + tick * 0.05
                x0 = cx + math.cos(a0) * rr
                y0 = cy + math.sin(a0) * rr
                x1 = cx + math.cos(a1) * rr
                y1 = cy + math.sin(a1) * rr
                am = (a0 + a1) / 2.0
                sag = rr * 0.18
                xm = cx + math.cos(am) * (rr - sag)
                ym = cy + math.sin(am) * (rr - sag)
                cr.move_to(x0, y0)
                cr.curve_to(xm, ym, xm, ym, x1, y1)
                cr.stroke()

    def _fx_freckles(self, cr, cx, cy, r, tick):
        """Pecas de LYLA: puntitos que aparecen y desaparecen (parpadean)."""
        rng = random.Random(42)  # posiciones fijas; solo cambia la opacidad
        dots = []
        for _ in range(14):
            ang = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(0.15, 0.9) * r
            size = rng.uniform(2.0, 5.5)
            phase = rng.uniform(0, 2 * math.pi)
            dots.append((ang, dist, size, phase))
        for ang, dist, size, phase in dots:
            alpha = 0.25 + 0.65 * (0.5 + 0.5 * math.sin(tick * 2.0 + phase))
            x = cx + math.cos(ang) * dist
            y = cy + math.sin(ang) * dist
            color = "primary" if int(phase * 10) % 2 == 0 else "accent"
            cr.set_source_rgba(*self.theme.rgb(color, alpha))
            cr.arc(x, y, size, 0, 2 * math.pi)
            cr.fill()

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

        # Background subtle dark circle (color de fondo del tema)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(*self.theme.rgb("background", 0.92))
        cr.fill()

        if self.theme.animation == "web":
            # Telaraña estilo Tobey Maguire en lugar de radios rectos + anillos.
            self._fx_web(cr, cx, cy, radius, self.angle)
        else:
            # Spider-Web Radial Lines (color de acento del tema)
            cr.set_line_width(1.0)
            cr.set_source_rgba(*self.theme.rgb("accent", 0.28))
            spokes = 8
            for i in range(spokes):
                a = (i * 2 * math.pi / spokes) + self.angle * 0.25
                cr.move_to(cx, cy)
                cr.line_to(cx + math.cos(a) * radius, cy + math.sin(a) * radius)
                cr.stroke()

            # Concentric Web Rings
            for r_fac in (0.35, 0.62, 0.88):
                cr.arc(cx, cy, radius * r_fac, 0, 2 * math.pi)
                cr.stroke()

        # Rotating Outer HUD Arc (color de acento del tema)
        cr.set_line_width(3.0)
        cr.set_source_rgba(*self.theme.rgb("accent", 0.85))
        cr.arc(cx, cy, radius, self.angle, self.angle + math.pi * 0.8)
        cr.stroke()
        cr.arc(cx, cy, radius, self.angle + math.pi, self.angle + math.pi * 1.8)
        cr.stroke()

        # CPU Gauge Arc (color primario del tema)
        cpu_angle = (self.cpu_pct / 100.0) * (2 * math.pi)
        cr.set_line_width(4.5)
        cr.set_source_rgba(*self.theme.rgb("primary", 0.95))
        cr.arc(cx, cy, radius - 7, -math.pi / 2, -math.pi / 2 + cpu_angle)
        cr.stroke()

        # Center Stylized Skull-Spider Emblem (color primario del tema)
        cr.set_source_rgba(*self.theme.rgb("primary", 0.95))
        cr.set_line_width(2.2)

        # Spider body (diamond/skull shape)
        cr.move_to(cx, cy - 18)
        cr.line_to(cx + 11, cy - 4)
        cr.line_to(cx + 7, cy + 16)
        cr.line_to(cx, cy + 23)
        cr.line_to(cx - 7, cy + 16)
        cr.line_to(cx - 11, cy - 4)
        cr.close_path()
        cr.stroke()

        # Glowing eyes (color de acento del tema)
        cr.set_source_rgba(*self.theme.rgb("accent", 0.95))
        cr.move_to(cx - 6, cy - 4)
        cr.line_to(cx - 2, cy - 1)
        cr.stroke()
        cr.move_to(cx + 6, cy - 4)
        cr.line_to(cx + 2, cy - 1)
        cr.stroke()

        # 8 Sharp Cyber Spider Legs (color primario del tema)
        cr.set_source_rgba(*self.theme.rgb("primary", 0.95))
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
            cr.move_to(cx + x1, cy + y1)
            cr.line_to(cx + x2, cy + y2)
            cr.line_to(cx + x3, cy + y3)
            cr.stroke()

        # Efecto de animación del tema activo (rayos, tentáculos o pecas).
        # "web" ya se dibujó en lugar de los radios rectos; "futuristic" no añade nada.
        if self.theme.animation in ("electric", "symbiote", "freckles"):
            self._draw_theme_fx(cr, cx, cy, radius, self.angle)


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

