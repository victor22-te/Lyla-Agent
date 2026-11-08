# SKILLS & Comandos de LYLA (2099)

Este documento registra todos los comandos interactivos y habilidades (skills) disponibles en el CLI de **LYLA**.

> **Regla de mantenimiento:** Cada vez que se cree o modifique un comando en LYLA, debe agregarse y documentarse en este archivo (`SKILLS.md`).

---

## 1. Comandos del CLI

Todos los comandos cuentan con **autocompletado mediante la tecla `Tab`** en la terminal.

| Comando | Alias soportados | Descripción |
| :--- | :--- | :--- |
| `/comands` | `/commands`, `/comandos`, `/help`, `comands` | Muestra la lista de todos los comandos disponibles en el CLI. |
| `/model [opción]` | `/modelo`, `model`, `modelo` | Sin argumentos, rota al siguiente proveedor/modelo disponible (Gemini ↔ Groq). Con argumento (`/model groq`, `/model gemini`, `/model 2`, `/model openai/gpt-oss-120b`), selecciona ese modelo directamente. Soporta autocompletado de modelos con `Tab`. |
| `/calendar [acción]` | `/agenda`, `calendar`, `agenda` | Muestra tu agenda próxima. Soporta `/calendar add <título> \| <YYYY-MM-DD HH:MM>`, `/calendar del <id>` y `/calendar auth` (vincular Google Calendar OAuth2). También puedes pedirle a LYLA en lenguaje natural que agende o consulte eventos. |
| `/status` | `/stats`, `status`, `stats` | Muestra el estado de todos los modelos configurados a nivel de tokens consumidos hoy, límite diario, **porcentaje (%) usado / libre**, llamadas y latencia. |
| `/alarm [tiempo] [msg]` | `/alarma`, `alarm`, `alarma` | Lista alarmas activas o programa una alarma con notificación de escritorio + voz (ej. `/alarm 5m Revisar deploy` o `/alarm 18:30 Llamada`). |
| `/sys` | `/system`, `sys`, `system` | Muestra la telemetría en tiempo real de Arch Linux (CPU, RAM, Disco, Batería, Uptime). |
| `/mobile [mensaje]` | `mobile` | Envía un ping o alerta a tu teléfono móvil vinculado mediante KDE Connect. |
| `/wallpaper` | `/fondo`, `wallpaper`, `fondo` | Cambia el fondo de pantalla de forma inteligente interactuando con la extensión Hanabi (fondos animados de vídeo) y fondos nativos de imagen estáticos de GNOME. |
| `/hud` | `hud` | Abre el Widget Holográfico de Escritorio (GTK4 + Cairo) con chat, micrófono y botón de Status de Modelos. |
| `/voice` | — | Activa o desactiva la síntesis de voz en la nube (Edge-TTS) para las respuestas de LYLA. |
| `/listen` | — | Inicia la grabación de voz por micrófono con PipeWire (`pw-record`), la transcribe en la nube (Groq Whisper / Gemini) y envía el mensaje a LYLA. |
| `/memory` | — | Consulta y muestra los últimos recuerdos almacenados en la Memoria Episódica (SQLite). |
| `/exit` | `exit`, `salir`, `quit` | Cierra la sesión interactiva de LYLA de forma segura. |

### Atajos de Teclado (Control de Voz en Vivo)

| Atajo | Acción |
| :--- | :--- |
| `Espacio` / `Enter` / `q` / `Esc` / `Ctrl+C` | Corta la voz de LYLA inmediatamente mientras está hablando y te devuelve al prompt `Víctor >` para seguir escribiendo **sin salir del CLI**. |

---

## 2. Habilidades Automáticas (Skills Pasivas)

- **Memoria Episódica Automática (`Recuerda que...`):**
  Al incluir frases como *"recuerda que..."*, *"anota que..."* o *"no olvides que..."* en cualquier mensaje, LYLA extrae el hecho automáticamente y lo guarda de forma persistente en SQLite (`lyla_memory.db`).
- **Router Multi-Proveedor con Fallback Instantáneo:**
  Opera con **Google Gemini** (`gemini-3.5-flash`) como proveedor principal y hace fallback automático a **Groq** (`openai/gpt-oss-120b`) en caso de saturación o falta de cuota.
- **Monitoreo Proactivo ("Oye Víctor..."):**
  Evalúa el consumo de tokens y latencia por proveedor durante la sesión para sugerir optimizaciones cuando se superan los umbrales configurados.

