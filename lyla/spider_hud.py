#!/usr/bin/env python3
"""
SPIDER-MAN 2099 // LYLA TACTICAL CYBER-HUD (Terminal Monitor + AI Voice/Text Interface)
Interactive futuristic system telemetry, LLM token/percentage status, and live LYLA chat/voice HUD.
Controls (Normal Mode):
  [Enter] / [t] / [/] : Enfocar barra de texto para hablar con LYLA o ejecutar comandos (/model, /status, /comands...)
  [v] o Clic en []   : Hablar por micrófono con LYLA (iniciar/detener grabación)
  [s] o Clic en [󰐷]   : Mostrar/Ocultar panel de Status de Modelos (Tokens & Porcentajes %)
  [x]                 : Silenciar la voz de LYLA inmediatamente
  [m]                 : Cambiar modo de color (2099 Carmesí/Cian, Miles Morales, Simbionte)
  [p]                 : Pulso de Telaraña / Escaneo Multiversal
  [q]                 : Salir del HUD
"""
import base64
import curses
import io
import math
import os
import sys
import textwrap
import threading
import time
from pathlib import Path

# Conectar con el motor de lyla-agent, su .venv y librerías del sistema (cairo)
LYLA_PROJECT_DIR = Path("/home/spider-man/Proyectos/lyla-agent")
VENV_SITE_PACKAGES = LYLA_PROJECT_DIR / ".venv" / "lib" / "python3.14" / "site-packages"
SYS_SITE_PACKAGES = Path("/usr/lib/python3.14/site-packages")
if str(LYLA_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(LYLA_PROJECT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))
if SYS_SITE_PACKAGES.exists() and str(SYS_SITE_PACKAGES) not in sys.path:
    sys.path.append(str(SYS_SITE_PACKAGES))

try:
    import cairo
except ImportError:
    cairo = None

from lyla.core.agent import LylaAgent


SPIDER_ASSET_FILE = LYLA_PROJECT_DIR / "lyla" / "assets" / "spider.txt"

# Fallback ASCII proporcional de spider.txt para terminales sin protocolo gráfico de Kitty
SPIDER_LOGO = [
    r"    __          _.._..___     ",
    r"   /  l     _.-'    '-. '-._  ",
    r"  (`-: '--.'     _..J.  '-. '.",
    r"   '''y  ,.' \ _.-'  `+'-. `.'",
    r"    ; _.' .-j    `.    \  '-. ",
    r"    :_:/  ::\    ;:  (  / .-' ",
    r"     /  .- :  `. '. : .-' /.-'",
    r"    : :     ,\''   ;.'  .-''  ",
    r"   / '-:    /'-.b-.'  .'   ;  ",
    r"  :`.  :   / :    `-i',_: _ \ ",
    r"   \ \     '-._     `' :_/:_/ ",
    r"    :_'-._      '-.  )   `.   ",
    r"      ''^--'^-. :   \ `._ '-. ",
    r"              / / : : :  `. '-",
]

SPIDER_LOGO_COMPACT = [
    r"   /  l     _.-'    '-. '-._  ",
    r"  (`-: '--.'     _..J.  '-. '.",
    r"    ; _.' .-j    `.    \  '-. ",
    r"    :_:/  ::\    ;:  (  / .-' ",
    r"   / '-:    /'-.b-.'  .'   ;  ",
    r"   \ \     '-._     `' :_/:_/ ",
    r"    :_'-._      '-.  )   `.   ",
    r"              / / : : :  `. '-",
]


def is_kitty_terminal() -> bool:
    return bool(os.environ.get("KITTY_WINDOW_ID") or "kitty" in os.environ.get("TERM", "").lower())


def render_spider_txt_png(out_path: Path, primary_rgb=(1.0, 0.12, 0.25), secondary_rgb=(0.0, 0.95, 1.0)) -> bool:
    """
    Renderiza el archivo completo lyla/assets/spider.txt con tamaño de fuente reducido (mini-font)
    en una cuadrícula monoespaciada exacta y lo guarda en out_path para Kitty Graphics (t=f).
    """
    if cairo is None or not SPIDER_ASSET_FILE.exists():
        return False
    raw_lines = SPIDER_ASSET_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not raw_lines:
        return False

    img_w, img_h = 520, 490
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, img_w, img_h)
    cr = cairo.Context(surf)

    # Fondo 100% transparente
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()

    cr.select_font_face("JetBrainsMono Nerd Font", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(14.0)

    for idx, line in enumerate(raw_lines):
        line_clean = line.replace("bug", "   ").rstrip()
        y = 16 + idx * 13.0
        if idx % 3 != 0:
            cr.set_source_rgba(primary_rgb[0], primary_rgb[1], primary_rgb[2], 1.0)
        else:
            cr.set_source_rgba(secondary_rgb[0], secondary_rgb[1], secondary_rgb[2], 1.0)
        for col_i, ch in enumerate(line_clean):
            if ch != " ":
                cr.move_to(6 + col_i * 8.2, y)
                cr.text_path(ch)
        cr.set_line_width(0.55)
        cr.stroke_preserve()
        cr.fill()

    surf.write_to_png(str(out_path))
    return out_path.exists()


def kitty_display_png_file(png_path: Path, image_id: int, row_1idx: int, col_1idx: int, cols: int, rows: int):
    """Transmite y muestra el PNG en un solo comando atómico (a=T,t=f) directo al descriptor de la terminal."""
    if not png_path.exists():
        return
    b64_path = base64.standard_b64encode(str(png_path).encode("utf-8")).decode("ascii")
    seq = (
        f"\x1b[{row_1idx};{col_1idx}H"
        f"\x1b_Ga=T,t=f,f=100,i={image_id},p=1,c={cols},r={rows},z=1,C=1,q=2;{b64_path}\x1b\\"
    )
    try:
        os.write(1, seq.encode("ascii"))
    except Exception:
        pass


def kitty_clear_images():
    try:
        os.write(1, b"\x1b_Ga=d,d=a,q=2\x1b\\")
    except Exception:
        pass

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
    "/exit",
]


def read_cpu_times():
    cores = {}
    try:
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu"):
                    parts = line.split()
                    name = parts[0]
                    vals = [int(x) for x in parts[1:]]
                    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
                    total = sum(vals)
                    cores[name] = (idle, total)
    except Exception:
        pass
    return cores


def read_memory():
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = int(parts[1].strip().split()[0])
                    info[k] = v
    except Exception:
        pass
    total = info.get("MemTotal", 1)
    avail = info.get("MemAvailable", total)
    used = total - avail
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used = swap_total - swap_free
    return (
        used / 1048576.0,
        total / 1048576.0,
        (used * 100.0) / total,
        swap_used / 1048576.0,
        swap_total / 1048576.0,
    )


def read_net_bytes():
    rx, tx = 0, 0
    try:
        with open("/proc/net/dev", "r") as f:
            for line in f.readlines()[2:]:
                if ":" in line:
                    iface, data = line.split(":", 1)
                    if iface.strip() == "lo":
                        continue
                    fields = data.split()
                    rx += int(fields[0])
                    tx += int(fields[8])
    except Exception:
        pass
    return rx, tx


def read_top_procs(limit=4):
    procs = []
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/comm", "r") as fc:
                    comm = fc.read().strip()
                with open(f"/proc/{pid}/status", "r") as fs:
                    vm_rss = 0
                    for line in fs:
                        if line.startswith("VmRSS:"):
                            vm_rss = int(line.split()[1]) // 1024
                            break
                if vm_rss > 0:
                    procs.append((vm_rss, int(pid), comm))
            except Exception:
                continue
    except Exception:
        pass
    procs.sort(reverse=True)
    return procs[:limit]


def draw_bar(win, y, x, width, pct, color_pair_fill, color_pair_empty):
    inner = max(4, width)
    filled = int(round((pct / 100.0) * inner))
    filled = max(0, min(inner, filled))
    try:
        if filled > 0:
            win.addstr(y, x, "━" * filled, curses.color_pair(color_pair_fill) | curses.A_BOLD)
        if inner - filled > 0:
            win.addstr(y, x + filled, "─" * (inner - filled), curses.color_pair(color_pair_empty))
    except curses.error:
        pass


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(80)
    stdscr.keypad(True)
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    except Exception:
        pass

    curses.start_color()
    curses.use_default_colors()

    modes = [
        ("SPIDER-MAN 2099 // MIGUEL O'HARA", curses.COLOR_RED, curses.COLOR_CYAN, curses.COLOR_BLUE),
        ("MILES MORALES // BIO-VENOM GLITCH", curses.COLOR_RED, curses.COLOR_MAGENTA, curses.COLOR_YELLOW),
        ("SYMBIOTE OVERRIDE // BLACK SUIT", curses.COLOR_WHITE, curses.COLOR_CYAN, curses.COLOR_MAGENTA),
    ]
    mode_idx = 0

    def apply_palette(idx):
        _, c1, c2, c3 = modes[idx]
        curses.init_pair(1, c1, -1)              # Primary Neon (Crimson)
        curses.init_pair(2, c2, -1)              # Secondary Holo (Cyan)
        curses.init_pair(3, c3, -1)              # Deep Accent (Blue)
        curses.init_pair(4, curses.COLOR_GREEN, -1)
        curses.init_pair(5, curses.COLOR_YELLOW, -1)
        curses.init_pair(6, curses.COLOR_WHITE, -1)

    apply_palette(mode_idx)

    # Si estamos en Kitty, renderizar spider.txt completo con fuente reducida (mini-font) para los 3 trajes
    spider_png_files = [
        Path("/tmp/lyla_spider_2099.png"),
        Path("/tmp/lyla_spider_2100.png"),
        Path("/tmp/lyla_spider_2101.png"),
    ]
    use_kitty_gfx = is_kitty_terminal() and (cairo is not None) and SPIDER_ASSET_FILE.exists()
    if use_kitty_gfx:
        try:
            ok0 = render_spider_txt_png(spider_png_files[0], (1.0, 0.12, 0.25), (0.0, 0.95, 1.0))
            render_spider_txt_png(spider_png_files[1], (1.0, 0.12, 0.25), (0.90, 0.20, 1.0))
            render_spider_txt_png(spider_png_files[2], (0.95, 0.97, 1.0), (0.0, 0.95, 1.0))
            use_kitty_gfx = ok0
        except Exception:
            use_kitty_gfx = False
    last_kitty_state = None
    last_hw = (0, 0)

    # Inicializar LYLA Engine
    agent = LylaAgent()
    voice_enabled = agent.config.audio_enabled
    typing_mode = False
    show_status_panel = False
    input_buffer = ""
    is_recording = False
    rec_file = None
    is_busy = False
    status_banner = "LISTO — Presiona [Enter] o [/] para escribir, [V] para micrófono, [S] para Status de Modelos"

    prov_init, mod_init = agent.router.get_active_model()
    chat_logs = [
        f"󰯊  LYLA 2099 EN LÍNEA — Modelo activo: {prov_init} ({mod_init})",
        "Escribe comandos (/comands, /model, /status, /calendar, /alarm, /sys) o habla con LYLA.",
    ]

    def add_chat_log(text: str):
        for line in text.splitlines():
            chat_logs.append(line)
        if len(chat_logs) > 200:
            del chat_logs[:-200]

    def send_to_lyla(user_text: str):
        nonlocal voice_enabled, is_busy, status_banner, show_status_panel
        user_text = user_text.strip()
        if not user_text:
            return
        if user_text.lower() in ("/status", "/stats", "status", "stats"):
            show_status_panel = True

        add_chat_log(f"Víctor > {user_text}")
        is_busy = True
        status_banner = "  LYLA procesando en la nube 2099..."

        def _worker():
            nonlocal voice_enabled, is_busy, status_banner
            try:
                res = agent.handle_hud_input(user_text, voice_enabled=voice_enabled)
                voice_enabled = res.get("voice_enabled", voice_enabled)
                reply_txt = res.get("text", "")
                should_speak = res.get("speak", False)
                raw_reply = res.get("raw_reply", reply_txt)

                if reply_txt:
                    add_chat_log(reply_txt)
                is_busy = False
                if should_speak and raw_reply:
                    status_banner = "  LYLA hablando... (Presiona [X] o [Esc] para silenciar la voz)"
                    agent.speak_reply(raw_reply, interactive_cli=False, force=True)
                status_banner = "LISTO — [Enter] escribir │ [V]  Micrófono │ [S] 󰐷 Status Modelos │ [X] Callar"
            except Exception as e:
                is_busy = False
                add_chat_log(f"  [Error]: {e}")
                status_banner = "LISTO — [Enter] escribir │ [V]  Micrófono │ [S] 󰐷 Status Modelos"

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_mic():
        nonlocal is_recording, rec_file, status_banner
        if not is_recording:
            agent.tts.player.stop()
            is_recording = True
            rec_file = agent.capture.start_recording()
            status_banner = "  GRABANDO VOZ CON PIPEWIRE... Presiona [V] o clic en [󰒊 ENVIAR] para terminar"
        else:
            is_recording = False
            agent.capture.stop_recording()
            status_banner = "  Transcribiendo audio en la nube (Groq Whisper / Gemini)..."
            r_path = rec_file

            def _stt_job():
                nonlocal status_banner
                try:
                    transcription = agent.stt.transcribe(r_path) if r_path else ""
                    if not transcription:
                        add_chat_log("  No se detectó voz clara en el micrófono.")
                        status_banner = "LISTO — [Enter] escribir │ [V]  Micrófono │ [S] 󰐷 Status Modelos"
                        return
                    send_to_lyla(transcription)
                except Exception as e:
                    add_chat_log(f"  Error STT: {e}")
                    status_banner = "LISTO — [Enter] escribir │ [V]  Micrófono │ [S] 󰐷 Status Modelos"

            threading.Thread(target=_stt_job, daemon=True).start()

    def autocomplete_input(buf: str) -> str:
        stripped = buf.lstrip()
        if stripped.startswith(("/model ", "/modelo ", "model ", "modelo ")):
            parts = stripped.split(maxsplit=1)
            prefix_cmd = parts[0] + " "
            partial = parts[1] if len(parts) > 1 else ""
            candidates = ["gemini", "groq"] + [o["model"] for o in agent.router.get_available_models()]
            matches = [c for c in candidates if c.lower().startswith(partial.lower())]
            if matches:
                idx = (matches.index(partial) + 1) % len(matches) if partial in matches else 0
                return prefix_cmd + matches[idx]
        else:
            matches = [c for c in HUD_COMMANDS if c.startswith(stripped.lower())]
            if matches:
                idx = (matches.index(stripped.lower()) + 1) % len(matches) if stripped.lower() in matches else 0
                chosen = matches[idx]
                if chosen in ("/model", "/modelo"):
                    chosen += " "
                return chosen
        return buf

    prev_cpu = read_cpu_times()
    prev_rx, prev_tx = read_net_bytes()
    prev_time = time.time()
    cpu_pcts = {}
    rx_rate, tx_rate = 0.0, 0.0
    procs = read_top_procs(4)
    tick = 0
    pulse_frames = 0

    # Coordenadas de botones interactivos para clic con mouse
    mic_btn_coords = (0, 0, 0)     # (y, x1, x2)
    status_btn_coords = (0, 0, 0)  # (y, x1, x2)
    input_bar_coords = (0, 0, 0)   # (y, x1, x2)

    while True:
        ch = stdscr.getch()
        if ch != -1:
            if ch == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bstate = curses.getmouse()
                    if bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                        if my == mic_btn_coords[0] and mic_btn_coords[1] <= mx <= mic_btn_coords[2]:
                            toggle_mic()
                        elif my == status_btn_coords[0] and status_btn_coords[1] <= mx <= status_btn_coords[2]:
                            show_status_panel = not show_status_panel
                        elif my == input_bar_coords[0] and input_bar_coords[1] <= mx <= input_bar_coords[2]:
                            typing_mode = True
                except Exception:
                    pass
            elif typing_mode:
                if ch in (10, 13, curses.KEY_ENTER):
                    cmd_to_run = input_buffer.strip()
                    input_buffer = ""
                    typing_mode = False
                    if cmd_to_run.lower() in ("/exit", "exit", "salir", "quit"):
                        agent.tts.player.stop()
                        break
                    elif cmd_to_run:
                        send_to_lyla(cmd_to_run)
                elif ch == 27:  # Esc: salir de modo escritura y callar voz
                    typing_mode = False
                    agent.tts.player.stop()
                elif ch == 9:   # Tab: autocompletar comando o modelo
                    input_buffer = autocomplete_input(input_buffer)
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    input_buffer = input_buffer[:-1]
                elif 32 <= ch <= 255:
                    try:
                        input_buffer += chr(ch)
                    except Exception:
                        pass
            else:
                # Modo atajos rápidos del HUD
                if ch in (ord("q"), ord("Q")):
                    agent.tts.player.stop()
                    break
                elif ch == 27 or ch in (ord("x"), ord("X"), ord(" ")):
                    agent.tts.player.stop()
                    status_banner = "  Voz de LYLA silenciada."
                elif ch in (10, 13, curses.KEY_ENTER, ord("t"), ord("T")):
                    typing_mode = True
                elif ch == ord("/"):
                    typing_mode = True
                    input_buffer = "/"
                elif ch in (ord("v"), ord("V")):
                    toggle_mic()
                elif ch in (ord("s"), ord("S")):
                    show_status_panel = not show_status_panel
                elif ch in (ord("m"), ord("M")):
                    mode_idx = (mode_idx + 1) % len(modes)
                    apply_palette(mode_idx)
                elif ch in (ord("p"), ord("P")):
                    pulse_frames = 15

        now = time.time()
        dt = now - prev_time
        if dt >= 0.6 or not cpu_pcts:
            cur_cpu = read_cpu_times()
            for k, (idle, total) in cur_cpu.items():
                p_idle, p_total = prev_cpu.get(k, (idle, total))
                d_total = total - p_total
                d_idle = idle - p_idle
                if d_total > 0:
                    cpu_pcts[k] = max(0.0, min(100.0, ((d_total - d_idle) * 100.0) / d_total))
                else:
                    cpu_pcts[k] = 0.0
            prev_cpu = cur_cpu

            cur_rx, cur_tx = read_net_bytes()
            if dt > 0:
                rx_rate = (cur_rx - prev_rx) / (1024.0 * dt)
                tx_rate = (cur_tx - prev_tx) / (1024.0 * dt)
            prev_rx, prev_tx = cur_rx, cur_tx
            prev_time = now
            procs = read_top_procs(4)

        h, w = stdscr.getmaxyx()
        show_left_col = w >= 72
        left_w = 32 if show_left_col else 0
        spider_rows = 14 if h >= 26 else (8 if h >= 19 else 0)

        # Evitar que ncurses emita \x1b[2J (que en Kitty borra las imágenes gráficas) en cada frame
        if (h, w) != last_hw:
            stdscr.erase()
            last_hw = (h, w)
            last_kitty_state = None
        else:
            blank_full = " " * max(1, w - 1)
            for ry_clr in range(h):
                try:
                    if use_kitty_gfx and show_left_col and (2 <= ry_clr < 2 + spider_rows):
                        # No sobrescribir el área de la imagen de Kitty en la esquina superior izquierda
                        rx_start = left_w + 2
                        if rx_start < w - 1:
                            stdscr.addstr(ry_clr, rx_start, " " * (w - 1 - rx_start))
                    else:
                        stdscr.addstr(ry_clr, 0, blank_full)
                except curses.error:
                    pass

        active_prov, active_mod = agent.router.get_active_model()
        v_badge = " VOZ ON" if voice_enabled else " VOZ OFF"
        mode_name = modes[mode_idx][0]

        # Header auto-ajustable al ancho de la ventana
        header_candidates = [
            f"╔══ 󱇪  ALCHEMAX 2099 // LYLA HUD [{mode_name}] • LLM: {active_prov.upper()}:{active_mod} ({v_badge}) ══╗",
            f"╔══ 󱇪  ALCHEMAX 2099 // LYLA HUD • LLM: {active_prov.upper()}:{active_mod} ({v_badge}) ══╗",
            f"╔═ 󱇪  LYLA 2099 • {active_prov.upper()}:{active_mod} ({v_badge}) ═╗",
            f"󱇪 LYLA 2099 • {active_mod} ({v_badge})",
        ]
        header = header_candidates[-1]
        for hc in header_candidates:
            if len(hc) <= w - 2:
                header = hc
                break
        try:
            stdscr.addstr(0, max(0, (w - len(header)) // 2), header[: max(1, w - 1)], curses.color_pair(1) | curses.A_BOLD)
        except curses.error:
            pass

        total_cpu = cpu_pcts.get("cpu", 0.0)

        if show_left_col:
            if not use_kitty_gfx and spider_rows > 0:
                logo_to_use = SPIDER_LOGO if spider_rows >= 14 else SPIDER_LOGO_COMPACT
                for idx, line in enumerate(logo_to_use):
                    y = 2 + idx
                    if y >= h - 6:
                        break
                    col = 1 if (idx + (tick // 3)) % 3 != 0 else 2
                    if pulse_frames > 0:
                        col = 2 if (idx + tick) % 2 == 0 else 1
                    try:
                        stdscr.addstr(y, 2, line[:left_w], curses.color_pair(col) | curses.A_BOLD)
                    except curses.error:
                        pass

            sense_y = 2 + spider_rows + (1 if h >= 27 else 0)
            if sense_y + 5 <= h - 4:
                try:
                    stdscr.addstr(sense_y, 2, "┌── SPIDER-SENSE TELEMETRY ──┐", curses.color_pair(2) | curses.A_BOLD)
                    wave = "".join(
                        "▲" if math.sin((i + tick) * 0.6) > 0.3 else ("▼" if math.sin((i + tick) * 0.6) < -0.3 else "─")
                        for i in range(26)
                    )
                    sense_color = 1 if (total_cpu > 75 or pulse_frames > 0) else 2
                    stdscr.addstr(sense_y + 1, 2, f"│ {wave} │", curses.color_pair(sense_color) | curses.A_BOLD)
                    status_txt = "ALERTA MULTIVERSAL!" if pulse_frames > 0 else ("CARGA ALTA" if total_cpu > 75 else "SIN ANOMALÍAS (2099)")
                    stdscr.addstr(sense_y + 2, 2, f"│ Estado: {status_txt:<18} │", curses.color_pair(4 if total_cpu <= 75 and pulse_frames == 0 else 1) | curses.A_BOLD)
                    stdscr.addstr(sense_y + 3, 2, f"│ Red RX: {rx_rate:6.1f} KB/s        │", curses.color_pair(6))
                    stdscr.addstr(sense_y + 4, 2, f"│ Red TX: {tx_rate:6.1f} KB/s        │", curses.color_pair(6))
                    stdscr.addstr(sense_y + 5, 2, "└────────────────────────────┘", curses.color_pair(2) | curses.A_BOLD)
                except curses.error:
                    pass

        # Right Column: Upper Telemetry List or Model Status + Lower LYLA Chat Console
        rx_x = (left_w + 3) if show_left_col else 2
        rem_w = max(20, w - rx_x - 2)
        chat_bottom = h - 4
        min_chat_rows = 4 if h < 24 else 5

        try:
            if show_status_panel:
                # PANEL DE STATUS DE MODELOS EN LISTA AUTO-AJUSTABLE
                st_title = "󰐷  STATUS DE MODELOS CLOUD (TOKENS & % CUOTA HOY) — [S] Volver"
                stdscr.addstr(2, rx_x, st_title[:rem_w], curses.color_pair(5) | curses.A_BOLD)
                report = agent.get_models_status_report()
                ry = 3
                max_status_y = max(ry + 1, chat_bottom - min_chat_rows - 1)
                for item in report:
                    if ry >= max_status_y:
                        break
                    mark = "●" if item["active"] else "○"
                    col_m = 4 if item["active"] else 6
                    if rem_w >= 76:
                        line_str = (
                            f" {mark} {item['provider'].upper():<6} {item['model']:<21} "
                            f"{item['tokens_total']:>6}/{item['daily_limit']:<7} "
                            f"({item['used_pct']:5.1f}% usado │ {item['remaining_pct']:5.1f}% libre)"
                        )
                    else:
                        line_str = (
                            f" {mark} {item['provider'].upper()}:{item['model']} "
                            f"• {item['tokens_total']} tk ({item['used_pct']:.1f}% usado)"
                        )
                    stdscr.addstr(ry, rx_x, line_str[:rem_w], curses.color_pair(col_m) | (curses.A_BOLD if item["active"] else 0))
                    ry += 1
                cy_chat_top = ry + 2
            else:
                # TELEMETRÍA EN LISTA VERTICAL (CPU + NÚCLEOS + RAM) AUTO-AJUSTABLE
                tele_title = "  TELEMETRÍA DEL SISTEMA (LISTA DE NÚCLEOS & MEMORIA)"
                stdscr.addstr(2, rx_x, tele_title[:rem_w], curses.color_pair(2) | curses.A_BOLD)

                used_gb, total_gb, mem_pct, _, _ = read_memory()
                core_keys = sorted([k for k in cpu_pcts.keys() if k != "cpu"])

                # Construir elementos de la lista vertical
                list_items = [
                    ("  CPU Global", total_cpu, 1, f"{total_cpu:5.1f}%", ""),
                    ("󰍛  Memoria RAM", mem_pct, 2, f"{mem_pct:5.1f}%", f"{used_gb:.1f}/{total_gb:.1f} GiB"),
                ]
                if not show_left_col:
                    list_items.append(("  Red RX/TX", 0.0, 4, f"{rx_rate:.1f}/{tx_rate:.1f} KB/s", ""))

                # Calcular cuántos núcleos caben verticalmente sin comerse el chat de LYLA
                max_list_end_y = max(6, chat_bottom - min_chat_rows - 1)
                avail_core_rows = max(0, max_list_end_y - (3 + len(list_items)))

                if avail_core_rows >= len(core_keys):
                    for k in core_keys:
                        p = cpu_pcts.get(k, 0.0)
                        list_items.append((f"  Núcleo {k.upper()}", p, 2, f"{p:5.1f}%", ""))
                elif avail_core_rows > 0:
                    shown_cores = max(0, avail_core_rows - 1)
                    for k in core_keys[:shown_cores]:
                        p = cpu_pcts.get(k, 0.0)
                        list_items.append((f"  Núcleo {k.upper()}", p, 2, f"{p:5.1f}%", ""))
                    rem_cores = core_keys[shown_cores:]
                    if rem_cores:
                        avg_rem = sum(cpu_pcts.get(rk, 0.0) for rk in rem_cores) / len(rem_cores)
                        lbl_rem = f"  {rem_cores[0].upper()}..{rem_cores[-1].upper()}"
                        list_items.append((lbl_rem, avg_rem, 2, f"{avg_rem:5.1f}%", "(prom)"))

                cy = 3
                label_col_w = 24
                bar_w = max(8, min(20, rem_w - label_col_w - 16)) if rem_w >= 48 else max(6, rem_w - label_col_w - 2)

                for lbl, pct_val, bar_col, val_str, extra_txt in list_items:
                    if cy >= max_list_end_y:
                        break
                    row_prefix = f" • {lbl:<14} {val_str:>6}  "
                    stdscr.addstr(cy, rx_x, row_prefix[:rem_w], curses.color_pair(6) | (curses.A_BOLD if "Global" in lbl or "RAM" in lbl else 0))
                    bar_x = rx_x + len(row_prefix)
                    if bar_x + bar_w < rx_x + rem_w:
                        draw_bar(stdscr, cy, bar_x, bar_w, pct_val, bar_col, 3)
                        if extra_txt and (bar_x + bar_w + 2 + len(extra_txt) <= rx_x + rem_w):
                            stdscr.addstr(cy, bar_x + bar_w + 2, extra_txt, curses.color_pair(2))
                    cy += 1

                cy_chat_top = cy + 2

            # CONSOLA INTERACTIVA DE LYLA EN EL HUD (AUTO-AJUSTADA)
            if cy_chat_top < chat_bottom:
                chat_hdr_candidates = [
                    "╔══ 󱇪  COMUNICACIÓN NEURAL CON LYLA 2099 (Comandos y Voz Activos) ══╗",
                    "╔══ 󱇪  COMUNICACIÓN NEURAL CON LYLA 2099 ══╗",
                    "󱇪  CONSOLA NEURAL LYLA 2099",
                ]
                chat_hdr = chat_hdr_candidates[-1]
                for chc in chat_hdr_candidates:
                    if len(chc) <= rem_w:
                        chat_hdr = chc
                        break
                stdscr.addstr(
                    cy_chat_top - 1,
                    rx_x,
                    chat_hdr[:rem_w],
                    curses.color_pair(1) | curses.A_BOLD,
                )

                chat_height = max(1, chat_bottom - cy_chat_top)
                wrapped_lines = []
                wrap_w = max(18, rem_w - 2)
                for raw_l in chat_logs[-30:]:
                    if not raw_l.strip():
                        wrapped_lines.append("")
                    else:
                        wrapped_lines.extend(textwrap.wrap(raw_l, width=wrap_w) or [""])

                visible_lines = wrapped_lines[-chat_height:]
                for idx_l, wline in enumerate(visible_lines):
                    ly = cy_chat_top + idx_l
                    if ly >= chat_bottom:
                        break
                    l_col = 2 if wline.startswith("Víctor >") else (4 if wline.startswith("󰯊") else 6)
                    if wline.startswith("LYLA"):
                        l_col = 1
                    stdscr.addstr(ly, rx_x, wline[:rem_w], curses.color_pair(l_col))

        except curses.error:
            pass

        # =====================================================================
        # BARRA DE TEXTO + BOTÓN MICRÓFONO + BOTÓN STATUS (AUTO-AJUSTABLE)
        # =====================================================================
        bar_y = h - 2
        status_y = h - 3
        if bar_y > 5:
            try:
                stdscr.addstr(status_y, 2, f"  {status_banner}"[: max(1, w - 4)], curses.color_pair(5) | curses.A_BOLD)

                if w >= 96:
                    mic_label = " [󰒊 ENVIAR VOZ (V)] " if is_recording else " [ MIC (V)] "
                    stat_label = " [󰐷 STATUS TOKENS/% (S)] "
                    prompt_prefix = "Víctor (ESCRIBIENDO) > " if typing_mode else "Víctor [Enter] > "
                elif w >= 72:
                    mic_label = " [󰒊 ENVIAR (V)] " if is_recording else " [ MIC (V)] "
                    stat_label = " [󰐷 STATUS (S)] "
                    prompt_prefix = "Víctor > "
                else:
                    mic_label = " [󰒊 V] " if is_recording else " [ V] "
                    stat_label = " [󰐷 S] "
                    prompt_prefix = "> "

                right_btns_w = len(mic_label) + len(stat_label) + 3
                entry_w = max(12, w - right_btns_w - 4)

                avail_txt_w = max(4, entry_w - len(prompt_prefix) - 2)
                shown_input = input_buffer[-avail_txt_w:] if input_buffer else ""
                cursor_char = "█" if (typing_mode and (tick % 2 == 0)) else ""

                box_text = f"{prompt_prefix}{shown_input}{cursor_char}"
                box_padded = f"[{box_text:<{max(1, entry_w - 2)}}]"

                input_col = curses.color_pair(2) | curses.A_BOLD if typing_mode else curses.color_pair(6)
                stdscr.addstr(bar_y, 2, box_padded[:entry_w], input_col)
                input_bar_coords = (bar_y, 2, 2 + entry_w)

                # Botón Micrófono al lado de la barra de texto
                mic_x = 3 + entry_w
                mic_col = (curses.color_pair(1) | curses.A_REVERSE | curses.A_BOLD) if is_recording else (curses.color_pair(1) | curses.A_BOLD)
                if mic_x + len(mic_label) < w:
                    stdscr.addstr(bar_y, mic_x, mic_label, mic_col)
                    mic_btn_coords = (bar_y, mic_x, mic_x + len(mic_label))

                # Botón Status de Modelos (Tokens & %) al lado del micrófono
                stat_x = mic_x + len(mic_label) + 1
                stat_col = (curses.color_pair(4) | curses.A_REVERSE | curses.A_BOLD) if show_status_panel else (curses.color_pair(2) | curses.A_BOLD)
                if stat_x + len(stat_label) < w:
                    stdscr.addstr(bar_y, stat_x, stat_label, stat_col)
                    status_btn_coords = (bar_y, stat_x, stat_x + len(stat_label))
            except curses.error:
                pass

        # Footer Controls auto-ajustable al ancho de la ventana
        footer_candidates = [
            " [Enter] Escribir/Comandos (Tab) │ [V]  Mic │ [S] 󰐷 Status Tokens/% │ [X] Callar │ [M] Traje │ [Q] Salir ",
            " [Enter] Escribir (Tab) │ [V]  Mic │ [S] 󰐷 Status/% │ [X] Callar │ [M] Traje │ [Q] Salir ",
            " [Enter] Chat/Cmd │ [V]  Mic │ [S] 󰐷 Status │ [X] Callar │ [M] Traje │ [Q] Salir ",
            " [Enter] Chat │ [V]  │ [S] 󰐷 │ [X] Callar │ [M] │ [Q] Salir ",
        ]
        footer = footer_candidates[-1]
        for fc in footer_candidates:
            if len(fc) <= w - 2:
                footer = fc
                break
        try:
            stdscr.addstr(h - 1, max(0, (w - len(footer)) // 2), footer[: max(1, w - 1)], curses.color_pair(2) | curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass

        if pulse_frames > 0:
            pulse_frames -= 1
        tick += 1
        stdscr.refresh()

        if use_kitty_gfx:
            cur_state = (show_left_col, spider_rows, mode_idx, h, w)
            if show_left_col and spider_rows > 0:
                if cur_state != last_kitty_state or tick <= 3 or (tick % 12 == 0):
                    kitty_display_png_file(
                        spider_png_files[mode_idx],
                        2099 + mode_idx,
                        row_1idx=3,
                        col_1idx=3,
                        cols=30,
                        rows=spider_rows,
                    )
                    last_kitty_state = cur_state
            elif last_kitty_state is not None and last_kitty_state[0]:
                kitty_clear_images()
                last_kitty_state = cur_state

    if use_kitty_gfx:
        kitty_clear_images()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    finally:
        if is_kitty_terminal():
            kitty_clear_images()
