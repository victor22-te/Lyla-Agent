#!/usr/bin/env python3
"""
LYLA 2099 // HOLOGRAPHIC DESKTOP HUD WIDGET (GTK4 + Cairo)
Interactive futuristic Spider-Man 2099 control deck, radar, voice/text chat & LLM token status for GNOME.
"""
import math
import os
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

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from lyla.core.agent import LylaAgent


HUD_COMMANDS = [
    "/comands",
    "/commands",
    "/comandos",
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
    "/memory",
    "/voice",
    "/stop",
]


CSS = b"""
window.lyla-hud-window {
    background-color: rgba(8, 10, 18, 0.95);
    border: 2px solid #ff2a4b;
    border-radius: 16px;
}
.lyla-title {
    color: #ff2a4b;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 14px;
}
.lyla-subtitle {
    color: #00f0ff;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 11px;
}
.lyla-metric-label {
    color: #d4e0ff;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 700;
    font-size: 11.5px;
}
.lyla-model-badge {
    color: #00ff9d;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 11.5px;
}
.lyla-btn {
    background: linear-gradient(135deg, rgba(255,42,75,0.22) 0%, rgba(0,240,255,0.12) 100%);
    color: #00f0ff;
    border: 1px solid rgba(0, 240, 255, 0.55);
    border-radius: 8px;
    padding: 5px 9px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 700;
    font-size: 11px;
}
.lyla-btn:hover {
    background: linear-gradient(135deg, #ff2a4b 0%, #a00028 100%);
    color: #ffffff;
    border-color: #00f0ff;
}
.lyla-btn-status {
    background: linear-gradient(135deg, rgba(0,240,255,0.25) 0%, rgba(255,42,75,0.20) 100%);
    color: #ffffff;
    border: 1px solid #00f0ff;
    border-radius: 8px;
    padding: 6px 10px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 11.5px;
}
.lyla-btn-status:hover {
    background: linear-gradient(135deg, #00f0ff 0%, #007799 100%);
    color: #080a12;
}
.lyla-btn-mic {
    background: linear-gradient(135deg, rgba(255,42,75,0.30) 0%, rgba(160,0,40,0.35) 100%);
    color: #ff2a4b;
    border: 1px solid #ff2a4b;
    border-radius: 8px;
    padding: 6px 12px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 12px;
}
.lyla-btn-mic-active {
    background: #ff0000;
    color: #ffffff;
    border: 2px solid #00f0ff;
    border-radius: 8px;
    padding: 6px 12px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-weight: 800;
    font-size: 12px;
}
.lyla-entry {
    background-color: rgba(12, 18, 32, 0.95);
    color: #00f0ff;
    border: 1px solid rgba(0, 240, 255, 0.65);
    border-radius: 8px;
    padding: 6px 10px;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 12px;
}
.lyla-console-frame {
    background-color: rgba(5, 8, 15, 0.92);
    border: 1px solid rgba(255, 42, 75, 0.55);
    border-radius: 10px;
    padding: 8px;
}
.lyla-console-text {
    background-color: transparent;
    color: #e2eeff;
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 11.5px;
}
"""


class LylaHudWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("LYLA // SPIDER-MAN 2099 HUD")
        self.set_default_size(560, 540)
        self.set_resizable(True)
        self.add_css_class("lyla-hud-window")

        self.agent = LylaAgent()
        self.voice_enabled = self.agent.config.audio_enabled
        self.is_recording = False
        self.rec_file = None

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
        lbl_title = Gtk.Label(label="󱇪  ALCHEMAX 2099 // LYLA NEURAL HUD")
        lbl_title.add_css_class("lyla-title")
        lbl_title.set_xalign(0.0)
        self.lbl_sub = Gtk.Label(label="OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK")
        self.lbl_sub.add_css_class("lyla-subtitle")
        self.lbl_sub.set_xalign(0.0)
        hdr.append(lbl_title)
        hdr.append(self.lbl_sub)
        main_box.append(hdr)

        # Center area: Left Cairo Spider-Web Radar + Right Telemetry & Actions
        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(mid)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_content_width(165)
        self.canvas.set_content_height(165)
        self.canvas.set_draw_func(self.on_draw)
        mid.append(self.canvas)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        right.set_hexpand(True)
        right.set_valign(Gtk.Align.CENTER)
        mid.append(right)

        self.lbl_cpu = Gtk.Label(label="  CPU NEURAL: 0%")
        self.lbl_cpu.add_css_class("lyla-metric-label")
        self.lbl_cpu.set_xalign(0.0)
        right.append(self.lbl_cpu)

        self.lbl_ram = Gtk.Label(label="󰍛  MEMORIA: 0%")
        self.lbl_ram.add_css_class("lyla-metric-label")
        self.lbl_ram.set_xalign(0.0)
        right.append(self.lbl_ram)

        self.lbl_model = Gtk.Label(label="󰯊  MODELO: cargando...")
        self.lbl_model.add_css_class("lyla-model-badge")
        self.lbl_model.set_xalign(0.0)
        right.append(self.lbl_model)

        self.lbl_sense = Gtk.Label(label="  SPIDER-SENSE: NOMINAL")
        self.lbl_sense.add_css_class("lyla-subtitle")
        self.lbl_sense.set_xalign(0.0)
        right.append(self.lbl_sense)

        # Quick Action Buttons
        btn_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        right.append(btn_grid)

        # Botón principal de STATUS de Modelos (Tokens & Porcentajes) + Silenciar Voz
        row_top_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_grid.append(row_top_btns)

        b_status = Gtk.Button(label="󰐷  Status Modelos (Tokens/%)")
        b_status.add_css_class("lyla-btn-status")
        b_status.set_hexpand(True)
        b_status.connect("clicked", self.on_show_status)
        row_top_btns.append(b_status)

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

        # Panel de Consola Holográfica (respuestas de LYLA, comandos y Status de Tokens)
        console_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        console_frame.add_css_class("lyla-console-frame")
        console_frame.set_vexpand(True)
        main_box.append(console_frame)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        console_frame.append(scroll)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.add_css_class("lyla-console-text")
        scroll.set_child(self.text_view)
        self.text_buffer = self.text_view.get_buffer()

        # Barra inferior para hablar con LYLA: Entrada de texto + Botón Enviar + Micrófono
        chat_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_box.append(chat_bar)

        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("Habla con LYLA o usa /comands, /model, /status, /calendar... (Tab autocompleta)")
        self.entry.add_css_class("lyla-entry")
        self.entry.connect("activate", self.on_send_text)
        chat_bar.append(self.entry)

        # Controlador de teclado para autocompletar con Tab y silenciar con Esc
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_entry_key_pressed)
        self.entry.add_controller(key_ctrl)

        b_send = Gtk.Button(label="󰒊  Enviar")
        b_send.add_css_class("lyla-btn")
        b_send.connect("clicked", self.on_send_text)
        chat_bar.append(b_send)

        self.b_mic = Gtk.Button(label="  Hablar")
        self.b_mic.add_css_class("lyla-btn-mic")
        self.b_mic.set_tooltip_text("Hablar por micrófono con LYLA (clic para grabar, clic para enviar)")
        self.b_mic.connect("clicked", self.on_toggle_mic)
        chat_bar.append(self.b_mic)

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

    def _refresh_model_badge(self):
        prov, mod = self.agent.router.get_active_model()
        v_icon = "" if self.voice_enabled else ""
        self.lbl_model.set_text(f"󰯊  LLM: {prov.upper()} ({mod}) {v_icon}")

    def append_console(self, text: str):
        end_iter = self.text_buffer.get_end_iter()
        if self.text_buffer.get_char_count() > 0:
            self.text_buffer.insert(end_iter, "\n" + "─" * 54 + "\n")
            end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(end_iter, text.strip() + "\n")
        # Auto-scroll al final
        mark = self.text_buffer.create_mark(None, self.text_buffer.get_end_iter(), False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

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

        # Escape silencia la voz inmediatamente sin cerrar la ventana
        if keyval == Gdk.KEY_Escape:
            self.on_stop_voice()
            return True

        return False

    def on_stop_voice(self, *_):
        self.agent.tts.player.stop()
        self.lbl_sub.set_text("  VOZ SILENCIADA • LISTO PARA ESCRIBIR")

    def on_show_status(self, *_):
        status_txt = self.agent.format_models_status_text()
        self.append_console(status_txt)
        self._refresh_model_badge()

    def on_send_text(self, *_):
        user_text = self.entry.get_text().strip()
        if not user_text:
            return
        self.entry.set_text("")
        self.process_user_input(user_text)

    def process_user_input(self, user_text: str):
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
                should_speak = res.get("speak", False)
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
                    self.agent.speak_reply(raw_reply)
                    GLib.idle_add(lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False)
            except Exception as e:
                GLib.idle_add(lambda: self.append_console(f"  [Error]: {e}") or False)
                GLib.idle_add(lambda: self.lbl_sub.set_text("OPERADOR: VÍCTOR • NUEVA YORK 2099 • SYNC OK") or False)

        threading.Thread(target=_worker, daemon=True).start()

    def on_toggle_mic(self, *_):
        if not self.is_recording:
            # Iniciar grabación con PipeWire
            self.agent.tts.player.stop()
            self.is_recording = True
            self.b_mic.set_label("󰒊  Enviar")
            self.b_mic.remove_css_class("lyla-btn-mic")
            self.b_mic.add_css_class("lyla-btn-mic-active")
            self.lbl_sub.set_text("  GRABANDO VOZ... HAZ CLIC EN '󰒊 Enviar' AL TERMINAR")
            self.rec_file = self.agent.capture.start_recording()
        else:
            # Detener grabación y transcribir en segundo plano
            self.is_recording = False
            self.b_mic.set_label("  Hablar")
            self.b_mic.remove_css_class("lyla-btn-mic-active")
            self.b_mic.add_css_class("lyla-btn-mic")
            self.agent.capture.stop_recording()
            self.lbl_sub.set_text("  TRANSCRIBIENDO AUDIO EN LA NUBE...")

            rec_path = self.rec_file

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
                        return
                    GLib.idle_add(lambda: self.process_user_input(transcription) or False)
                except Exception as e:
                    GLib.idle_add(lambda: self.append_console(f"  Error STT: {e}") or False)

            threading.Thread(target=_stt_worker, daemon=True).start()

    def on_switch_wallpaper(self, *_):
        wallpapers = [
            "file:///home/spider-man/Pictures/spiderman_2099_cyber.jpg",
            "file:///home/spider-man/Pictures/spiderman_2099_hud_blueprint.png",
        ]
        self.wall_idx = (self.wall_idx + 1) % len(wallpapers)
        uri = wallpapers[self.wall_idx]
        subprocess.Popen(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
        subprocess.Popen(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])

    def on_tick(self):
        self.angle = (self.angle + 0.045) % (2 * math.pi)
        self.canvas.queue_draw()
        return True

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

        # Background subtle dark circle
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.04, 0.06, 0.12, 0.92)
        cr.fill()

        # Spider-Web Radial Lines (Cyan Holographic)
        cr.set_line_width(1.0)
        cr.set_source_rgba(0.0, 0.94, 1.0, 0.28)
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

        # Rotating Cyan Outer HUD Arc
        cr.set_line_width(3.0)
        cr.set_source_rgba(0.0, 0.94, 1.0, 0.85)
        cr.arc(cx, cy, radius, self.angle, self.angle + math.pi * 0.8)
        cr.stroke()
        cr.arc(cx, cy, radius, self.angle + math.pi, self.angle + math.pi * 1.8)
        cr.stroke()

        # CPU Gauge Arc (Neon Crimson #ff2a4b)
        cpu_angle = (self.cpu_pct / 100.0) * (2 * math.pi)
        cr.set_line_width(4.5)
        cr.set_source_rgba(1.0, 0.165, 0.294, 0.95)
        cr.arc(cx, cy, radius - 7, -math.pi / 2, -math.pi / 2 + cpu_angle)
        cr.stroke()

        # Center Spider-Man 2099 Stylized Skull-Spider Emblem
        cr.set_source_rgba(1.0, 0.165, 0.294, 0.95)
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

        # Glowing eyes in cyan
        cr.set_source_rgba(0.0, 0.94, 1.0, 0.95)
        cr.move_to(cx - 6, cy - 4)
        cr.line_to(cx - 2, cy - 1)
        cr.stroke()
        cr.move_to(cx + 6, cy - 4)
        cr.line_to(cx + 2, cy - 1)
        cr.stroke()

        # 8 Sharp 2099 Cyber Spider Legs
        cr.set_source_rgba(1.0, 0.165, 0.294, 0.95)
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


class LylaApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.spiderman2099.LylaHud")

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        win = LylaHudWindow(self)
        win.present()


if __name__ == "__main__":
    app = LylaApp()
    app.run()

