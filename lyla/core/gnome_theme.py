"""
Generador y aplicador del tema completo de escritorio GNOME para LYLA.

Al cambiar el tema en LYLA, sincroniza el escritorio completo siguiendo la
estructura de Spider-Man 2099 (spiderman-2099-dotfiles):
  - ~/.config/gtk-4.0/{gtk.css, settings.ini}  (apps Libadwaita / GTK4: Nautilus, Settings...)
  - ~/.config/gtk-3.0/{gtk.css, settings.ini}  (apps GTK3)
  - ~/.themes/<ShellTheme>/ & ~/.local/share/themes/<ShellTheme>/
      (gnome-shell/gnome-shell.css, gtk-3.0/gtk.css, gtk-4.0/gtk.css, index.theme)
  - ~/.config/kitty/lyla-theme.conf (+ include en kitty.conf + SIGUSR1 en vivo)
  - gsettings: gtk-theme, accent-color y user-theme
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path
from string import Template
from typing import Dict


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_str(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"{r}, {g}, {b}"


def _mix_hex(hex_a: str, hex_b: str, t: float) -> str:
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    r = max(0, min(255, round(ra + (rb - ra) * t)))
    g = max(0, min(255, round(ga + (gb - ga) * t)))
    b = max(0, min(255, round(ba + (bb - ba) * t)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast_fg(hex_bg: str) -> str:
    r, g, b = _hex_to_rgb(hex_bg)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#06070a" if luminance > 0.62 else "#ffffff"


def _theme_mapping(theme, meta: Dict[str, str]) -> Dict[str, str]:
    c = theme.colors
    bg = c.get("background", "#080a12")
    sf = c.get("surface", "#0a0e19")
    sf_act = c.get("surface_active", "#0e1923")
    entry_bg = c.get("entry_bg", "#0c1220")
    console_bg = c.get("console_bg", "#05080f")
    pr = c.get("primary", "#ff2a4b")
    pr_dark = c.get("primary_dark", "#a00028")
    ac = c.get("accent", "#00f0ff")
    ac_dark = c.get("accent_dark", "#007799")
    tx = c.get("text", "#d4e0ff")
    tx_dim = c.get("text_dim", "#a0c0ff")
    tx_bright = c.get("text_bright", "#ffffff")
    ok = c.get("success", "#00ff9d")
    danger = c.get("danger", "#ff2a4b")

    is_orb = getattr(theme, "animation", "futuristic") == "orb"
    is_symbiote = getattr(theme, "animation", "futuristic") == "symbiote"

    window_bg = _mix_hex(bg, sf, 0.35)
    header_bg = _mix_hex(sf, sf_act, 0.45)
    header_mid = _mix_hex(sf_act, pr if not is_orb else ac, 0.08)
    card_bg = _mix_hex(sf, sf_act, 0.55)

    # En LYLA (Apple UI) usamos acentos de cristal translúcidos más suaves;
    # en Simbionte contrastes blanco/negro puros.
    panel_border = pr if not is_orb else "rgba(255, 255, 255, 0.18)"
    panel_shadow_rgb = _rgb_str(ac if is_orb else pr)
    header_border = pr if not is_orb else "rgba(255, 255, 255, 0.16)"
    selected_fg = _contrast_fg(pr)
    accent_fg = _contrast_fg(ac)
    font_family = '"Inter", "Cantarell", system-ui, sans-serif' if is_orb else '"JetBrainsMono Nerd Font", monospace'

    return {
        "theme_id": theme.id,
        "theme_name": theme.name,
        "shell_theme": meta.get("shell_theme", "SpiderMan-2099-Cyber"),
        "gnome_accent": meta.get("gnome_accent", "red"),
        "primary": pr,
        "primary_rgb": _rgb_str(pr),
        "primary_dark": pr_dark,
        "primary_fg": selected_fg,
        "accent": ac,
        "accent_rgb": _rgb_str(ac),
        "accent_dark": ac_dark,
        "accent_fg": accent_fg,
        "background": bg,
        "background_rgb": _rgb_str(bg),
        "window_bg": window_bg,
        "window_bg_rgb": _rgb_str(window_bg),
        "surface": sf,
        "surface_rgb": _rgb_str(sf),
        "surface_active": sf_act,
        "surface_active_rgb": _rgb_str(sf_act),
        "header_bg": header_bg,
        "header_bg_rgb": _rgb_str(header_bg),
        "header_mid": header_mid,
        "card_bg": card_bg,
        "card_bg_rgb": _rgb_str(card_bg),
        "entry_bg": entry_bg,
        "console_bg": console_bg,
        "text": tx,
        "text_rgb": _rgb_str(tx),
        "text_dim": tx_dim,
        "text_dim_rgb": _rgb_str(tx_dim),
        "text_bright": tx_bright,
        "success": ok,
        "success_rgb": _rgb_str(ok),
        "danger": danger,
        "danger_rgb": _rgb_str(danger),
        "panel_border": panel_border,
        "panel_shadow_rgb": panel_shadow_rgb,
        "header_border": header_border,
        "font_family": font_family,
        "badge_color": pr if not is_orb else tx_bright,
        "menu_header_color": pr if not is_orb else tx_bright,
        "selection_bg": ac if is_symbiote else pr,
        "selection_fg": _contrast_fg(ac if is_symbiote else pr),
    }


GTK4_TEMPLATE = Template(r"""/* ============================================================================
 * LYLA DESKTOP THEME: $theme_name ($theme_id) - GTK4 / LIBADWAITA
 * Generado automáticamente por lyla.core.gnome_theme
 * ============================================================================ */

@define-color accent_bg_color $primary;
@define-color accent_fg_color $primary_fg;
@define-color accent_color $accent;

@define-color destructive_bg_color $danger;
@define-color destructive_fg_color #ffffff;
@define-color destructive_color $danger;

@define-color success_bg_color $success;
@define-color success_fg_color #090b12;
@define-color success_color $success;

@define-color warning_bg_color #ffc777;
@define-color warning_fg_color #090b12;
@define-color warning_color #ffd89b;

@define-color error_bg_color $danger;
@define-color error_fg_color #ffffff;
@define-color error_color $danger;

@define-color window_bg_color $window_bg;
@define-color window_fg_color $text;

@define-color view_bg_color $background;
@define-color view_fg_color $text;

@define-color headerbar_bg_color $header_bg;
@define-color headerbar_fg_color $accent;
@define-color headerbar_border_color $header_border;
@define-color headerbar_backdrop_color $background;
@define-color headerbar_shade_color rgba($primary_rgb, 0.25);

@define-color sidebar_bg_color $surface;
@define-color sidebar_fg_color $text;
@define-color sidebar_backdrop_color $console_bg;
@define-color sidebar_shade_color rgba($accent_rgb, 0.18);

@define-color secondary_sidebar_bg_color $surface;
@define-color secondary_sidebar_fg_color $text;

@define-color card_bg_color rgba($card_bg_rgb, 0.90);
@define-color card_fg_color $text;
@define-color card_shade_color rgba($accent_rgb, 0.20);

@define-color dialog_bg_color $header_bg;
@define-color dialog_fg_color $text;

@define-color popover_bg_color $surface;
@define-color popover_fg_color $text;

@define-color thumbnail_bg_color $surface_active;
@define-color thumbnail_fg_color $text;

/* --- Window Borders & Glow --- */
window,
window.background {
    background-color: @window_bg_color;
    color: @window_fg_color;
    border: 1px solid rgba($accent_rgb, 0.32);
}

window:focus-within {
    border-color: rgba($primary_rgb, 0.72);
    box-shadow: 0 0 18px rgba($primary_rgb, 0.22);
}

/* --- Headerbar --- */
headerbar {
    background: linear-gradient(90deg, $background 0%, $header_mid 50%, $background 100%);
    color: $accent;
    border-bottom: 2px solid $header_border;
    box-shadow: 0 2px 12px rgba($panel_shadow_rgb, 0.22);
}

headerbar:backdrop {
    background: $console_bg;
    border-bottom: 1px solid rgba($accent_rgb, 0.30);
    color: $text_dim;
}

headerbar .title {
    color: $accent;
    font-weight: 800;
    letter-spacing: 0.4px;
}

headerbar .subtitle {
    color: $primary;
    font-size: 0.85em;
}

/* Window Control Buttons */
windowcontrols > button > image {
    border-radius: 50%;
    transition: all 150ms ease;
}

windowcontrols > button.close > image {
    background-color: rgba($primary_rgb, 0.24);
    color: $primary;
    border: 1px solid $primary;
}

windowcontrols > button.close:hover > image {
    background-color: $primary;
    color: $primary_fg;
    box-shadow: 0 0 10px $primary;
}

windowcontrols > button.maximize > image,
windowcontrols > button.minimize > image {
    background-color: rgba($accent_rgb, 0.15);
    color: $accent;
    border: 1px solid rgba($accent_rgb, 0.50);
}

windowcontrols > button.maximize:hover > image,
windowcontrols > button.minimize:hover > image {
    background-color: $accent;
    color: $accent_fg;
    box-shadow: 0 0 10px $accent;
}

/* --- Sidebars & Navigation --- */
.navigation-sidebar,
placessidebar,
.sidebar {
    background-color: $surface;
    border-right: 1px solid rgba($accent_rgb, 0.24);
}

.navigation-sidebar > row:selected,
placessidebar row:selected,
listview > row:selected {
    background: linear-gradient(90deg, rgba($primary_rgb, 0.30) 0%, rgba($accent_rgb, 0.12) 100%);
    color: $accent;
    border-left: 3px solid $primary;
    font-weight: 700;
}

.navigation-sidebar > row:hover:not(:selected),
placessidebar row:hover:not(:selected) {
    background-color: rgba($accent_rgb, 0.10);
    color: $text_bright;
}

/* --- Cards & Lists --- */
card,
.card,
boxed-list {
    background-color: rgba($card_bg_rgb, 0.90);
    border: 1px solid rgba($accent_rgb, 0.26);
    border-radius: 10px;
}

/* --- Buttons --- */
button.suggested-action {
    background: linear-gradient(135deg, $primary 0%, $primary_dark 100%);
    color: $primary_fg;
    border: 1px solid $accent;
    box-shadow: 0 0 10px rgba($primary_rgb, 0.40);
}

button:hover {
    border-color: $accent;
}

/* --- Entries / Search Bars --- */
entry {
    background-color: $entry_bg;
    border: 1px solid rgba($accent_rgb, 0.40);
    color: $accent;
}

entry:focus-within {
    border: 1px solid $primary;
    box-shadow: 0 0 10px rgba($primary_rgb, 0.32);
}

/* --- Switches & Progress Bars --- */
switch:checked {
    background-color: $primary;
    border: 1px solid $accent;
}

progressbar > trough > progress,
levelbar > trough > block.filled {
    background: linear-gradient(90deg, $primary 0%, $accent 100%);
}

/* --- Scrollbars --- */
scrollbar slider {
    background-color: rgba($primary_rgb, 0.55);
    border-radius: 4px;
}
""")


GTK3_TEMPLATE = Template(r"""/* ============================================================================
 * LYLA DESKTOP THEME: $theme_name ($theme_id) - GTK3 OVERRIDES
 * Generado automáticamente por lyla.core.gnome_theme
 * ============================================================================ */

@define-color theme_bg_color $window_bg;
@define-color theme_fg_color $text;
@define-color theme_base_color $background;
@define-color theme_text_color $text;
@define-color theme_selected_bg_color $primary;
@define-color theme_selected_fg_color $primary_fg;
@define-color insensitive_bg_color $console_bg;
@define-color insensitive_fg_color $text_dim;
@define-color borders rgba($accent_rgb, 0.30);

window,
.background {
    background-color: $window_bg;
    color: $text;
}

headerbar,
.titlebar {
    background-image: linear-gradient(to right, $background, $header_mid, $background);
    color: $accent;
    border-bottom: 2px solid $header_border;
    box-shadow: 0 2px 10px rgba($panel_shadow_rgb, 0.25);
}

headerbar .title,
.titlebar .title {
    color: $accent;
    font-weight: bold;
}

.sidebar,
placessidebar,
treeview.view {
    background-color: $surface;
    color: $text;
}

row:selected,
treeview.view:selected,
*:selected {
    background-color: $primary;
    color: $primary_fg;
}

entry {
    background-color: $entry_bg;
    color: $accent;
    border: 1px solid rgba($accent_rgb, 0.45);
}

entry:focus {
    border-color: $primary;
    box-shadow: 0 0 8px rgba($primary_rgb, 0.38);
}

button {
    background-image: none;
    background-color: $surface_active;
    color: $text;
    border: 1px solid rgba($accent_rgb, 0.35);
    border-radius: 6px;
}

button:hover {
    background-color: rgba($primary_rgb, 0.22);
    border-color: $accent;
    color: $accent;
}

scrollbar slider {
    background-color: $primary;
}

scrollbar slider:hover {
    background-color: $accent;
}
""")


GNOME_SHELL_TEMPLATE = Template(r"""/* ============================================================================
 * LYLA DESKTOP THEME: $theme_name ($theme_id) - GNOME SHELL STYLESHEET
 * Generado automáticamente por lyla.core.gnome_theme
 * ============================================================================ */

/* --- 1. TOP PANEL --- */
#panel {
    background-color: rgba($background_rgb, 0.92) !important;
    border-bottom: 2px solid $panel_border !important;
    box-shadow: 0 3px 16px rgba($panel_shadow_rgb, 0.40) !important;
    height: 34px !important;
    font-family: $font_family;
    font-weight: 700;
}

#panel .panel-button {
    color: $text !important;
    border-radius: 8px !important;
    margin: 3px 3px !important;
    padding: 0 10px !important;
    border: 1px solid transparent !important;
    transition-duration: 150ms !important;
}

#panel .panel-button:hover {
    background-color: rgba($accent_rgb, 0.16) !important;
    color: $accent !important;
    border: 1px solid rgba($accent_rgb, 0.70) !important;
    box-shadow: inset 0 0 8px rgba($accent_rgb, 0.22) !important;
}

#panel .panel-button:active,
#panel .panel-button:overview,
#panel .panel-button:focus,
#panel .panel-button:checked {
    background-color: rgba($primary_rgb, 0.24) !important;
    color: $accent !important;
    border: 1px solid $primary !important;
    box-shadow: 0 0 12px rgba($primary_rgb, 0.50) !important;
}

#panel .panel-button.clock-display .clock {
    color: $accent !important;
    text-shadow: 0 0 8px rgba($accent_rgb, 0.42);
}

.workspace-dot {
    background-color: $primary !important;
    box-shadow: 0 0 6px $primary !important;
}

/* --- SPIDER-HUD CUSTOM INDICATOR --- */
.spider-hud-box {
    spacing: 8px;
    padding: 0 4px;
}

.spider-hud-badge {
    color: $badge_color;
    font-weight: 800;
    text-shadow: 0 0 8px rgba($primary_rgb, 0.55);
}

.spider-hud-telemetry {
    color: $accent;
    font-weight: 700;
    font-size: 11.5px;
}

.spider-hud-sense-ok {
    color: $success;
    font-weight: 800;
}

.spider-hud-sense-alert {
    color: $danger;
    font-weight: 800;
}

.spider-hud-menu-header {
    font-weight: 800;
    color: $menu_header_color;
    font-size: 13px;
}

.spider-hud-menu-sub {
    color: $accent;
    font-size: 11px;
}

/* --- 2. POPUP MENUS, CALENDAR & NOTIFICATIONS --- */
.popup-menu-content,
.datemenu-popover,
.candidate-popup-content,
.modal-dialog {
    background-color: rgba($surface_rgb, 0.96) !important;
    border: 1px solid rgba($accent_rgb, 0.55) !important;
    border-top: 2px solid $panel_border !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 32px rgba(0, 0, 0, 0.88), 0 0 22px rgba($panel_shadow_rgb, 0.28) !important;
    color: $text !important;
}

#calendarArea {
    padding: 6px !important;
}

.datemenu-calendar-column {
    border-left: 1px solid rgba($accent_rgb, 0.28) !important;
    padding-left: 14px !important;
}

.datemenu-today-button {
    border-radius: 10px !important;
    padding: 8px !important;
    border: 1px solid transparent !important;
}

.datemenu-today-button:hover {
    background-color: rgba($primary_rgb, 0.16) !important;
    border: 1px solid rgba($accent_rgb, 0.45) !important;
}

.datemenu-today-button .day-label {
    color: $accent !important;
    font-weight: 800 !important;
    letter-spacing: 0.8px;
}

.datemenu-today-button .date-label {
    color: $primary !important;
    font-weight: 800 !important;
    text-shadow: 0 0 10px rgba($primary_rgb, 0.35);
}

.calendar {
    background-color: rgba($surface_active_rgb, 0.88) !important;
    border: 1px solid rgba($accent_rgb, 0.32) !important;
    border-radius: 12px !important;
    padding: 8px !important;
}

.calendar-month-label {
    color: $accent !important;
    font-weight: 800 !important;
    font-size: 13px !important;
}

.calendar-change-month-back,
.calendar-change-month-forward,
.pager-button {
    color: $primary !important;
    border-radius: 8px !important;
}

.pager-button:hover {
    background-color: rgba($accent_rgb, 0.20) !important;
    color: $accent !important;
}

.calendar-day-heading {
    color: $accent !important;
    font-weight: 700 !important;
}

.calendar-day {
    color: $text !important;
    border-radius: 50% !important;
    border: 1px solid transparent !important;
}

.calendar-day:hover {
    background-color: rgba($accent_rgb, 0.22) !important;
    color: $text_bright !important;
    border-color: $accent !important;
}

.calendar-today {
    background-color: $primary !important;
    color: $primary_fg !important;
    font-weight: 900 !important;
    border: 1px solid $accent !important;
    box-shadow: 0 0 12px rgba($primary_rgb, 0.65) !important;
}

.calendar-other-month {
    color: rgba($text_dim_rgb, 0.38) !important;
}

.events-button,
.world-clocks-button,
.weather-button {
    background-color: rgba($surface_active_rgb, 0.92) !important;
    border: 1px solid rgba($accent_rgb, 0.35) !important;
    border-left: 3px solid $primary !important;
    border-radius: 10px !important;
    color: $text !important;
    padding: 10px 12px !important;
    transition-duration: 150ms !important;
}

.events-button:hover,
.world-clocks-button:hover,
.weather-button:hover {
    background-color: rgba($primary_rgb, 0.20) !important;
    border-color: $accent !important;
    color: $accent !important;
    box-shadow: 0 0 12px rgba($accent_rgb, 0.28) !important;
}

.events-title,
.world-clocks-header,
.weather-header {
    color: $accent !important;
    font-weight: 800 !important;
}

.message-list-placeholder {
    color: $accent !important;
    font-weight: 700 !important;
}

.message-list-clear-button {
    background-color: rgba($primary_rgb, 0.25) !important;
    border: 1px solid $primary !important;
    color: $text_bright !important;
    border-radius: 8px !important;
}

.message-list-clear-button:hover {
    background-color: $primary !important;
    color: $primary_fg !important;
    border-color: $accent !important;
}

/* --- 3. QUICK SETTINGS & SYSTEM MENU --- */
.popup-menu-item {
    border-radius: 8px !important;
    color: $text !important;
}

.popup-menu-item:hover,
.popup-menu-item:focus,
.popup-menu-item.selected {
    background-color: rgba($primary_rgb, 0.20) !important;
    color: $accent !important;
    border-left: 3px solid $primary !important;
}

.quick-toggle,
.quick-menu-toggle .quick-toggle {
    background-color: rgba($surface_active_rgb, 0.92) !important;
    border: 1px solid rgba($accent_rgb, 0.32) !important;
    border-radius: 10px !important;
    color: $text !important;
}

.quick-toggle:hover {
    border-color: $accent !important;
    background-color: rgba($accent_rgb, 0.15) !important;
}

.quick-toggle:checked {
    background-color: $primary !important;
    border-color: $accent !important;
    color: $primary_fg !important;
    box-shadow: 0 0 14px rgba($primary_rgb, 0.50) !important;
}

.slider {
    color: $accent !important;
    -barlevel-active-background-color: $primary !important;
    -barlevel-active-border-color: $accent !important;
}

/* --- 4. LOCK SCREEN / UNLOCK DIALOG --- */
.unlock-dialog-clock {
    spacing: 1.2em !important;
}

.unlock-dialog-clock .unlock-dialog-clock-time {
    color: $text_bright !important;
    font-family: $font_family !important;
    font-size: 5.2em !important;
    font-weight: 400 !important;
    padding: 0 20px !important;
    text-shadow: 0 2px 12px rgba(0, 0, 0, 0.85) !important;
}

.unlock-dialog-clock .unlock-dialog-clock-date {
    color: $text_dim !important;
    font-family: $font_family !important;
    font-size: 1.4em !important;
    font-weight: 600 !important;
    padding: 0 16px !important;
    text-shadow: 0 1px 6px rgba(0, 0, 0, 0.80) !important;
}

.unlock-dialog-clock .unlock-dialog-clock-hint {
    color: $text_dim !important;
    font-family: $font_family !important;
    text-shadow: none !important;
}

.user-widget .user-widget-label,
.login-dialog-username {
    color: $accent !important;
    font-weight: 800 !important;
    text-shadow: 0 0 10px rgba($accent_rgb, 0.50);
}

.user-icon {
    border: 3px solid $primary !important;
    box-shadow: 0 0 22px rgba($primary_rgb, 0.65) !important;
    background-color: rgba($surface_rgb, 0.90) !important;
}

.login-dialog-prompt-entry {
    background-color: rgba($surface_rgb, 0.92) !important;
    border: 2px solid $accent !important;
    border-radius: 10px !important;
    color: $accent !important;
    box-shadow: 0 0 16px rgba($primary_rgb, 0.40) !important;
}

.login-dialog-prompt-entry:focus {
    border-color: $primary !important;
    box-shadow: 0 0 20px rgba($primary_rgb, 0.70) !important;
}

/* --- 5. DASH / DOCK & OVERVIEW --- */
#dash .dash-background {
    background-color: rgba($background_rgb, 0.88) !important;
    border: 1px solid rgba($accent_rgb, 0.52) !important;
    border-bottom: 2px solid $panel_border !important;
    border-radius: 18px !important;
    box-shadow: 0 4px 24px rgba($panel_shadow_rgb, 0.32), inset 0 0 12px rgba($accent_rgb, 0.12) !important;
}

#dash .app-well-app:hover .overview-icon,
#dash .show-apps:hover .overview-icon {
    background-color: rgba($primary_rgb, 0.24) !important;
    border: 1px solid $accent !important;
    box-shadow: 0 0 12px rgba($accent_rgb, 0.42) !important;
}

.app-well-app-running-dot {
    background-color: $primary !important;
    box-shadow: 0 0 8px $primary !important;
    width: 10px !important;
    height: 4px !important;
    border-radius: 2px !important;
}

#overviewGroup {
    background-color: rgba($console_bg_rgb, 0.85) !important;
}

.search-entry {
    background-color: rgba($surface_active_rgb, 0.92) !important;
    border: 2px solid $primary !important;
    border-radius: 12px !important;
    color: $accent !important;
    box-shadow: 0 0 18px rgba($primary_rgb, 0.36) !important;
}

.search-entry:focus {
    border-color: $accent !important;
    box-shadow: 0 0 22px rgba($accent_rgb, 0.50) !important;
}

.workspace-thumbnail-indicator {
    border: 2px solid $primary !important;
    box-shadow: 0 0 12px rgba($primary_rgb, 0.52) !important;
    border-radius: 6px !important;
}

.message,
.notification-banner {
    background-color: rgba($surface_rgb, 0.95) !important;
    border: 1px solid rgba($accent_rgb, 0.48) !important;
    border-left: 4px solid $primary !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba($panel_shadow_rgb, 0.28) !important;
}
""")


KITTY_TEMPLATE = Template(r"""# Generado automáticamente por LYLA ($theme_name)
background            $background
foreground            $text
selection_background  $selection_bg
selection_foreground  $selection_fg
cursor                $primary
cursor_text_color     $background
url_color             $accent

active_border_color   $primary
inactive_border_color $accent_dark

active_tab_background   $primary
active_tab_foreground   $primary_fg
inactive_tab_background $surface
inactive_tab_foreground $accent
tab_bar_background      $console_bg

color0  $console_bg
color8  $surface_active
color1  $primary
color9  $danger
color2  $success
color10 $success
color4  $accent_dark
color12 $accent
color6  $accent
color14 $accent
color7  $text
color15 $text_bright
""")


def _write_text_safe(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _update_gtk_settings_ini(path: Path, shell_theme: str) -> None:
    if not path.exists():
        content = (
            "[Settings]\n"
            "gtk-application-prefer-dark-theme=1\n"
            f"gtk-theme-name={shell_theme}\n"
            "gtk-icon-theme-name=Adwaita\n"
            "gtk-font-name=JetBrainsMono Nerd Font 10\n"
            "gtk-decoration-layout=appmenu:minimize,maximize,close\n"
        )
        _write_text_safe(path, content)
        return
    raw = path.read_text(encoding="utf-8")
    if re.search(r"^gtk-theme-name=", raw, flags=re.MULTILINE):
        updated = re.sub(r"^gtk-theme-name=.*$", f"gtk-theme-name={shell_theme}", raw, flags=re.MULTILINE)
    else:
        updated = raw.rstrip("\n") + f"\ngtk-theme-name={shell_theme}\n"
    _write_text_safe(path, updated)


def _sync_kitty_theme(home: Path, kitty_css: str) -> None:
    kitty_dir = home / ".config" / "kitty"
    if not kitty_dir.exists():
        return
    _write_text_safe(kitty_dir / "lyla-theme.conf", kitty_css)
    kitty_conf = kitty_dir / "kitty.conf"
    if kitty_conf.exists():
        conf_text = kitty_conf.read_text(encoding="utf-8")
        if "include lyla-theme.conf" not in conf_text:
            _write_text_safe(
                kitty_conf,
                conf_text.rstrip("\n") + "\n\n# Tema sincronizado con LYLA\ninclude lyla-theme.conf\n",
            )
    # Recargar ventanas de Kitty abiertas si hay alguna.
    subprocess.run(["pkill", "-USR1", "-x", "kitty"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _apply_gsettings_async(home: Path, shell_theme: str, gnome_accent: str) -> None:
    def _worker():
        cmds = [
            ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark"],
            ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", shell_theme],
            ["gsettings", "set", "org.gnome.desktop.interface", "accent-color", gnome_accent],
        ]
        user_schemadir = home / ".local" / "share" / "glib-2.0" / "schemas"
        if user_schemadir.exists():
            cmds.append([
                "gsettings", "--schemadir", str(user_schemadir),
                "set", "org.gnome.shell.extensions.user-theme", "name", shell_theme,
            ])
        for cmd in cmds:
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


def apply_desktop_theme(theme, meta: Dict[str, str], apply_gsettings: bool = True) -> None:
    """Genera y aplica GTK4, GTK3, GNOME Shell theme, Kitty y gsettings."""
    if theme is None:
        return
    home = Path.home()
    mapping = _theme_mapping(theme, meta)
    shell_theme = mapping["shell_theme"]

    gtk4_css = GTK4_TEMPLATE.safe_substitute(mapping)
    gtk3_css = GTK3_TEMPLATE.safe_substitute(mapping)
    shell_css = GNOME_SHELL_TEMPLATE.safe_substitute(mapping)
    kitty_conf = KITTY_TEMPLATE.safe_substitute(mapping)
    index_ini = (
        "[Desktop Entry]\n"
        "Type=X-GNOME-Metatheme\n"
        f"Name={shell_theme}\n"
        "Comment=LYLA Dynamic Desktop Theme\n"
        "Encoding=UTF-8\n\n"
        "[X-GNOME-Metatheme]\n"
        f"GtkTheme={shell_theme}\n"
        "MetacityTheme=Adwaita-dark\n"
        "IconTheme=Adwaita\n"
        "CursorTheme=Adwaita\n"
        "ButtonLayout=appmenu:minimize,maximize,close\n"
    )

    try:
        # 1. GTK4 / Libadwaita + GTK3 activos de usuario
        _write_text_safe(home / ".config" / "gtk-4.0" / "gtk.css", gtk4_css)
        _write_text_safe(home / ".config" / "gtk-3.0" / "gtk.css", gtk3_css)
        _update_gtk_settings_ini(home / ".config" / "gtk-4.0" / "settings.ini", shell_theme)
        _update_gtk_settings_ini(home / ".config" / "gtk-3.0" / "settings.ini", shell_theme)

        # 2. Paquete de tema completo en ~/.themes y ~/.local/share/themes
        for root in (home / ".themes", home / ".local" / "share" / "themes"):
            theme_dir = root / shell_theme
            _write_text_safe(theme_dir / "index.theme", index_ini)
            _write_text_safe(theme_dir / "gnome-shell" / "gnome-shell.css", shell_css)
            _write_text_safe(theme_dir / "gtk-3.0" / "gtk.css", gtk3_css)
            _write_text_safe(theme_dir / "gtk-4.0" / "gtk.css", gtk4_css)

        # 3. Kitty terminal
        _sync_kitty_theme(home, kitty_conf)

        # 4. gsettings (GNOME accent color, gtk-theme, user-theme)
        if apply_gsettings and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            _apply_gsettings_async(home, shell_theme, mapping["gnome_accent"])
    except Exception as e:
        print(f"[Temas] No se pudo sincronizar el tema completo de GNOME: {e}")

