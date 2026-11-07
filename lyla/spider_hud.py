#!/usr/bin/env python3
"""
SPIDER-MAN 2099 // LYLA TACTICAL CYBER-HUD (Terminal Monitor + AI Voice/Text Interface)
Interactive futuristic system telemetry, LLM token/percentage status, and live LYLA chat/voice HUD.
Controls (Normal Mode):
  [Enter] / [t] / [/] : Enfocar barra de texto para hablar con LYLA o ejecutar comandos (/model, /status, /comands...)
  [v] o Clic en [🎤]  : Hablar por micrófono con LYLA (iniciar/detener grabación)
  [s] o Clic en [📊]  : Mostrar/Ocultar panel de Status de Modelos (Tokens & Porcentajes %)
  [x]                 : Silenciar la voz de LYLA inmediatamente
  [m]                 : Cambiar modo de color (2099 Carmesí/Cian, Miles Morales, Simbionte)
  [p]                 : Pulso de Telaraña / Escaneo Multiversal
  [q]                 : Salir del HUD
"""
import curses
import math
import os
import sys
import textwrap
import threading
import time
from pathlib import Path

# Conectar con el motor de lyla-agent y su .venv
LYLA_PROJECT_DIR = Path("/home/spider-man/Proyectos/lyla-agent")
VENV_SITE_PACKAGES = LYLA_PROJECT_DIR / ".venv" / "lib" / "python3.14" / "site-packages"
if str(LYLA_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(LYLA_PROJECT_DIR))
if VENV_SITE_PACKAGES.exists() and str(VENV_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_SITE_PACKAGES))

from lyla.core.agent import LylaAgent


SPIDER_LOGO = [
    r"      /\             /\      ",
    r"     /  \   .---.   /  \     ",
    r"    / /\ \ /     \ / /\ \    ",
    r"   / /  \ | () () | /  \ \   ",
    r"  /_/ /\ \ \  ^  / / /\ \_\  ",
    r"     /  \ \_\___/_/ /  \     ",
    r"  __/ /\ \ / _ _ \ / /\ \__  ",
    r" /___/  \ V | | | V /  \___\ ",
    r"    /  / |  |_|_|  | \  \    ",
    r"   /__/ / \  | |  / \ \__\   ",
    r"       /   \ / \ /   \       ",
    r"       \   /  V  \   /       ",
    r"        \ /       \ /        ",
    r"         V         V         ",
]

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
    inner = max(4, width - 2)
    filled = int(round((pct / 100.0) * inner))
    filled = max(0, min(inner, filled))
    try:
        win.addstr(y, x, "[", curses.color_pair(2) | curses.A_BOLD)
        win.addstr(y, x + 1, "█" * filled, curses.color_pair(color_pair_fill) | curses.A_BOLD)
        win.addstr(y, x + 1 + filled, "░" * (inner - filled), curses.color_pair(color_pair_empty))
        win.addstr(y, x + 1 + inner, "]", curses.color_pair(2) | curses.A_BOLD)
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
        f"● LYLA 2099 EN LÍNEA — Modelo activo: {prov_init} ({mod_init})",
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
        status_banner = "⏳ LYLA procesando en la nube 2099..."

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
                    status_banner = "🔊 LYLA hablando... (Presiona [X] o [Esc] para silenciar la voz)"
                    # Reproducir voz sin tocar termios de curses
                    clean_speech = raw_reply.replace("*", "").replace("#", "").replace("`", "")
                    out_mp3 = agent.tts.output_dir / "lyla_response.mp3"
                    import asyncio
                    asyncio.run(agent.tts._generate_audio(clean_speech, out_mp3))
                    if agent.tts.player.player_cmd:
                        import subprocess as _sp
                        agent.tts.player.stop()
                        agent.tts.player.current_process = _sp.Popen(
                            agent.tts.player.player_cmd + [str(out_mp3)],
                            stdin=_sp.DEVNULL,
                            stdout=_sp.DEVNULL,
                            stderr=_sp.DEVNULL,
                            start_new_session=True,
                        )
                        while agent.tts.player.current_process and agent.tts.player.current_process.poll() is None:
                            time.sleep(0.08)
                status_banner = "LISTO — [Enter] escribir │ [V] 🎤 Micrófono │ [S] 📊 Status Modelos │ [X] Callar"
            except Exception as e:
                is_busy = False
                add_chat_log(f"⚠️ [Error]: {e}")
                status_banner = "LISTO — [Enter] escribir │ [V] 🎤 Micrófono │ [S] 📊 Status Modelos"

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_mic():
        nonlocal is_recording, rec_file, status_banner
        if not is_recording:
            agent.tts.player.stop()
            is_recording = True
            rec_file = agent.capture.start_recording()
            status_banner = "🎤 GRABANDO VOZ CON PIPEWIRE... Presiona [V] o clic en [⏹ ENVIAR] para terminar"
        else:
            is_recording = False
            agent.capture.stop_recording()
            status_banner = "⏳ Transcribiendo audio en la nube (Groq Whisper / Gemini)..."
            r_path = rec_file

            def _stt_job():
                nonlocal status_banner
                try:
                    transcription = agent.stt.transcribe(r_path) if r_path else ""
                    if not transcription:
                        add_chat_log("⚠️ No se detectó voz clara en el micrófono.")
                        status_banner = "LISTO — [Enter] escribir │ [V] 🎤 Micrófono │ [S] 📊 Status Modelos"
                        return
                    send_to_lyla(transcription)
                except Exception as e:
                    add_chat_log(f"⚠️ Error STT: {e}")
                    status_banner = "LISTO — [Enter] escribir │ [V] 🎤 Micrófono │ [S] 📊 Status Modelos"

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
                    status_banner = "🔇 Voz de LYLA silenciada."
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

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        active_prov, active_mod = agent.router.get_active_model()
        v_badge = "🔊 VOZ ON" if voice_enabled else "🔇 VOZ OFF"
        mode_name = modes[mode_idx][0]
        header = f"╔══ 󱇪  ALCHEMAX 2099 // LYLA HUD [{mode_name}] • LLM: {active_prov.upper()}:{active_mod} ({v_badge}) ══╗"
        try:
            stdscr.addstr(0, max(0, (w - len(header)) // 2), header[: w - 1], curses.color_pair(1) | curses.A_BOLD)
        except curses.error:
            pass

        # Left Column: Animated Spider-Man 2099 Emblem + Telemetry
        left_w = 34
        for idx, line in enumerate(SPIDER_LOGO):
            y = 2 + idx
            if y >= h - 9:
                break
            col = 1 if (idx + (tick // 3)) % 3 != 0 else 2
            if pulse_frames > 0:
                col = 2 if (idx + tick) % 2 == 0 else 1
            try:
                stdscr.addstr(y, 2, line, curses.color_pair(col) | curses.A_BOLD)
            except curses.error:
                pass

        total_cpu = cpu_pcts.get("cpu", 0.0)
        sense_y = 16
        if sense_y + 5 < h - 4:
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

        # Right Column: Upper Telemetry or Model Token/Percentage Status + Lower LYLA Chat Console
        rx_x = left_w + 2
        rem_w = max(24, w - rx_x - 2)

        try:
            if show_status_panel:
                # PANEL DE STATUS DE MODELOS (TOKENS & PORCENTAJES %)
                stdscr.addstr(2, rx_x, "📊 STATUS DE MODELOS CLOUD (TOKENS & PORCENTAJES DE CUOTA DIARIA) — [S] Volver", curses.color_pair(5) | curses.A_BOLD)
                report = agent.get_models_status_report()
                ry = 4
                for item in report:
                    if ry >= (h // 2) + 2:
                        break
                    mark = "●" if item["active"] else " "
                    col_m = 4 if item["active"] else 6
                    label = f"{mark} {item['provider'].upper():<6} {item['model']:<21}"
                    stats_str = f"{item['tokens_total']:>6}/{item['daily_limit']:<7} ({item['used_pct']:5.1f}% usado │ {item['remaining_pct']:5.1f}% libre)"
                    stdscr.addstr(ry, rx_x, label[:rem_w], curses.color_pair(col_m) | curses.A_BOLD)
                    if rem_w > 55:
                        stdscr.addstr(ry, rx_x + 30, stats_str[: rem_w - 30], curses.color_pair(2))
                    if rem_w > 85:
                        draw_bar(stdscr, ry, rx_x + 82, min(20, rem_w - 83), item["used_pct"], 1, 3)
                    ry += 1
                cy_chat_top = ry + 1
            else:
                # TELEMETRÍA NORMAL (CPU + RAM)
                stdscr.addstr(2, rx_x, "  NÚCLEOS NEURALES (CPU MATRIX)", curses.color_pair(2) | curses.A_BOLD)
                stdscr.addstr(3, rx_x, f"Carga Global: {total_cpu:5.1f}%", curses.color_pair(1) | curses.A_BOLD)
                draw_bar(stdscr, 3, rx_x + 22, rem_w - 22, total_cpu, 1, 3)

                core_keys = sorted([k for k in cpu_pcts.keys() if k != "cpu"])
                cy = 4
                for i in range(0, min(len(core_keys), 8), 2):
                    if cy >= 8:
                        break
                    k1 = core_keys[i]
                    p1 = cpu_pcts.get(k1, 0.0)
                    col_w = (rem_w // 2) - 1
                    stdscr.addstr(cy, rx_x, f"{k1.upper():<4} {p1:4.0f}%", curses.color_pair(6))
                    draw_bar(stdscr, cy, rx_x + 11, max(6, col_w - 12), p1, 2, 3)

                    if i + 1 < len(core_keys):
                        k2 = core_keys[i + 1]
                        p2 = cpu_pcts.get(k2, 0.0)
                        x2 = rx_x + col_w + 1
                        stdscr.addstr(cy, x2, f"{k2.upper():<4} {p2:4.0f}%", curses.color_pair(6))
                        draw_bar(stdscr, cy, x2 + 11, max(6, col_w - 12), p2, 2, 3)
                    cy += 1

                used_gb, total_gb, mem_pct, _, _ = read_memory()
                my = cy
                stdscr.addstr(my, rx_x, f"󰍛  RAM : {used_gb:4.1f}/{total_gb:4.1f} GiB ({mem_pct:4.1f}%)", curses.color_pair(2) | curses.A_BOLD)
                draw_bar(stdscr, my, rx_x + 29, rem_w - 29, mem_pct, 1, 3)
                cy_chat_top = my + 2

            # CONSOLA INTERACTIVA DE LYLA EN EL HUD
            chat_bottom = h - 5
            chat_height = max(3, chat_bottom - cy_chat_top)
            stdscr.addstr(
                cy_chat_top - 1,
                rx_x,
                "╔══ 🤖 COMUNICACIÓN NEURAL CON LYLA 2099 (Comandos y Voz Activos) ══╗"[:rem_w],
                curses.color_pair(1) | curses.A_BOLD,
            )

            wrapped_lines = []
            wrap_w = max(20, rem_w - 2)
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
                l_col = 2 if wline.startswith("Víctor >") else (4 if wline.startswith("●") else 6)
                if wline.startswith("LYLA"):
                    l_col = 1
                stdscr.addstr(ly, rx_x, wline[:rem_w], curses.color_pair(l_col))

        except curses.error:
            pass

        # =====================================================================
        # BARRA DE TEXTO + BOTÓN MICRÓFONO + BOTÓN STATUS EN LA PARTE INFERIOR
        # =====================================================================
        bar_y = h - 3
        status_y = h - 4
        if bar_y > 6:
            try:
                stdscr.addstr(status_y, 2, f"⚡ {status_banner}"[: w - 4], curses.color_pair(5) | curses.A_BOLD)

                mic_label = " [⏹ ENVIAR VOZ (V)] " if is_recording else " [🎤 MIC (V)] "
                stat_label = " [📊 STATUS TOKENS/% (S)] "
                right_btns_w = len(mic_label) + len(stat_label) + 4
                entry_w = max(16, w - right_btns_w - 4)

                prompt_prefix = "Víctor (ESCRIBIENDO) > " if typing_mode else "Víctor [Enter para escribir] > "
                avail_txt_w = max(5, entry_w - len(prompt_prefix) - 2)
                shown_input = input_buffer[-avail_txt_w:] if input_buffer else ""
                cursor_char = "█" if (typing_mode and (tick % 2 == 0)) else ""

                box_text = f"{prompt_prefix}{shown_input}{cursor_char}"
                box_padded = f"[{box_text:<{entry_w - 2}}]"

                input_col = curses.color_pair(2) | curses.A_BOLD if typing_mode else curses.color_pair(6)
                stdscr.addstr(bar_y, 2, box_padded[:entry_w], input_col)
                input_bar_coords = (bar_y, 2, 2 + entry_w)

                # Botón Micrófono al lado de la barra de texto
                mic_x = 3 + entry_w
                mic_col = (curses.color_pair(1) | curses.A_REVERSE | curses.A_BOLD) if is_recording else (curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(bar_y, mic_x, mic_label, mic_col)
                mic_btn_coords = (bar_y, mic_x, mic_x + len(mic_label))

                # Botón Status de Modelos (Tokens & %) al lado del micrófono
                stat_x = mic_x + len(mic_label) + 1
                stat_col = (curses.color_pair(4) | curses.A_REVERSE | curses.A_BOLD) if show_status_panel else (curses.color_pair(2) | curses.A_BOLD)
                if stat_x + len(stat_label) < w - 1:
                    stdscr.addstr(bar_y, stat_x, stat_label, stat_col)
                    status_btn_coords = (bar_y, stat_x, stat_x + len(stat_label))
            except curses.error:
                pass

        # Footer Controls
        footer = " [Enter] Escribir/Comandos (Tab autocompleta) │ [V] 🎤 Mic │ [S] 📊 Status Tokens/% │ [X] Callar │ [M] Traje │ [Q] Salir "
        try:
            stdscr.addstr(h - 1, max(0, (w - len(footer)) // 2), footer[: w - 1], curses.color_pair(2) | curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass

        if pulse_frames > 0:
            pulse_frames -= 1
        tick += 1
        stdscr.refresh()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
