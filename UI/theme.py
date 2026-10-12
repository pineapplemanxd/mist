"""Theme palettes, layout presets, and application stylesheets."""
from __future__ import annotations

from typing import Any
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

DARK: dict[str, str] = {
    "bg": "#171a21",             # Steam client main background
    "surface": "#1b2838",        # Steam cards, dialogs, content panels
    "surface2": "#1e2f42",       # Steam card hover, elevated controls
    "surface3": "#2a475e",       # Steam button/control borders and accents
    "border": "#2a475e",         # Steam distinctive blue-grey border
    "text": "#c7d5e0",           # Steam primary readable light grey
    "muted": "#8f98a0",          # Steam muted secondary text
    "accent": "#66c0f4",         # Steam cyan accent
    "accent_hover": "#8ed6ff",   # Steam bright cyan hover
    "accent_text": "#ffffff",
    "danger": "#a63232",         # Steam danger / red
    "success": "#5c7e10",        # Steam green (Install / Play button)
    "success_hover": "#759c14",  # Steam green hover
    "warning": "#e5a100",        # Steam warning / amber
    "sidebar": "#121418",        # Steam dark sidebar / title area
    "overlay": "#000000",
}

LIGHT: dict[str, str] = {
    "bg": "#eef2f7",
    "surface": "#ffffff",
    "surface2": "#e2e8f0",
    "surface3": "#cbd5e1",
    "border": "#94a3b8",
    "text": "#1a1e26",
    "muted": "#64748b",
    "accent": "#0284c7",
    "accent_hover": "#0369a1",
    "accent_text": "#ffffff",
    "danger": "#dc2626",
    "success": "#16a34a",
    "success_hover": "#15803d",
    "warning": "#d97706",
    "sidebar": "#0f172a",
    "overlay": "#000000",
}

CLASSIC_2003: dict[str, str] = {
    "bg": "#4c5844",             # Valve 2003 vintage olive-green
    "surface": "#3e4637",        # Nostalgic dark olive card/panel
    "surface2": "#4a5342",       # Elevated control surface
    "surface3": "#586953",       # Bevel border / accent highlight
    "border": "#283023",         # Deep shadow border
    "text": "#d8ded3",           # Crisp muted phosphor text
    "muted": "#9aa694",          # Nostalgic olive secondary
    "accent": "#8ca07e",         # Retro sage highlight
    "accent_hover": "#a6bc97",   # Hover sage tint
    "accent_text": "#ffffff",
    "danger": "#8b3333",
    "success": "#58753a",        # Classic olive-green action button
    "success_hover": "#6d9148",
    "warning": "#c28d28",
    "sidebar": "#384032",
    "overlay": "#000000",
}

EPIC_SIDEBAR: dict[str, str] = {
    "bg": "#121212",             # Obsidian flat dark
    "surface": "#1e1e1e",        # Modern cards
    "surface2": "#282828",       # Elevated / hover
    "surface3": "#333333",       # Borders & dividers
    "border": "#2a2a2a",         # Hairline border
    "text": "#f5f5f5",           # High-contrast white
    "muted": "#8a8a8a",          # Muted gray
    "accent": "#0078f2",         # Epic electric blue
    "accent_hover": "#2e93ff",   # Electric blue hover
    "accent_text": "#ffffff",
    "danger": "#e53935",
    "success": "#00b06f",        # Vibrant action green
    "success_hover": "#10c984",
    "warning": "#ffb300",
    "sidebar": "#181818",        # Clean sidebar drawer
    "overlay": "#000000",
}

GOG_GALAXY: dict[str, str] = {
    "bg": "#151022",             # Cyber violet deep dark
    "surface": "#1f1633",        # Purple card surface
    "surface2": "#2a1e45",       # Hover card surface
    "surface3": "#3a2a5e",       # Chip / badge surface
    "border": "#3e2d64",         # Neon purple outline
    "text": "#eae6f5",           # Pale violet text
    "muted": "#9f93ba",          # Muted lilac
    "accent": "#8b5cf6",         # Cyber neon violet
    "accent_hover": "#a78bfa",   # Bright neon lilac
    "accent_text": "#ffffff",
    "danger": "#ef4444",
    "success": "#10b981",        # Emerald green
    "success_hover": "#34d399",
    "warning": "#f59e0b",
    "sidebar": "#110d1c",        # Deep cyber navigation
    "overlay": "#000000",
}

PRESETS: dict[str, dict[str, Any]] = {
    "steam_modern": {
        "id": "steam_modern",
        "name": "Steam Modern",
        "tagline": "Modern Valve aesthetic with top navigation tabs",
        "description": "Top navigation bar with Steam uppercase tab styling (STORE, LIBRARY, DOWNLOADS, SETTINGS), #171a21 dark background, #1b2838 cards, and #66c0f4 cyan accent.",
        "layout_mode": "top_nav",
        "palette": DARK,
        "font_family": '"Segoe UI Variable Text", "Segoe UI", "Motiva Sans", "Inter", sans-serif',
        "border_radius": 3,
        "card_radius": 4,
        "variant": "steam_modern",
    },
    "steam_2003": {
        "id": "steam_2003",
        "name": "Classic Steam (2003 / Retro Green)",
        "tagline": "Vintage Valve/Steam olive-green aesthetic",
        "description": "Vintage Valve/Steam olive-green aesthetic (#4c5844 / #3e4637), classic 3D bevelled borders, compact nostalgic toolbar header, square corners, and retro typography.",
        "layout_mode": "top_nav",
        "palette": CLASSIC_2003,
        "font_family": '"Tahoma", "Segoe UI", "Verdana", "MS Sans Serif", sans-serif',
        "border_radius": 0,
        "card_radius": 0,
        "variant": "steam_2003",
    },
    "epic_sidebar": {
        "id": "epic_sidebar",
        "name": "Epic / Sidebar Modern",
        "tagline": "Obsidian dark theme with left vertical navigation drawer",
        "description": "Left sidebar vertical navigation drawer with Store, Library, Downloads, and Settings. Minimalist deep obsidian dark background (#121212), high contrast white/blue accents, and flat modern card geometry.",
        "layout_mode": "sidebar",
        "palette": EPIC_SIDEBAR,
        "font_family": '"Segoe UI", "Inter", "Helvetica Neue", sans-serif',
        "border_radius": 4,
        "card_radius": 4,
        "variant": "epic_sidebar",
    },
    "gog_galaxy": {
        "id": "gog_galaxy",
        "name": "GOG Galaxy / Cyber Minimalist",
        "tagline": "Cyber neon violet aesthetic with top slim navigation bar",
        "description": "Clean purple/violet neon accents (#6b2cf5, #8b5cf6, #1f1633), pill-shaped category chips, top slim nav with integrated quick search, and glassy translucent card styling.",
        "layout_mode": "top_nav",
        "palette": GOG_GALAXY,
        "font_family": '"Segoe UI Variable Text", "Inter", "Segoe UI", sans-serif',
        "border_radius": 8,
        "card_radius": 10,
        "variant": "gog_galaxy",
    },
    "light": {
        "id": "light",
        "name": "Clean Light",
        "tagline": "High-contrast clean daylight theme",
        "description": "Bright daylight theme with high-contrast surfaces, slate borders, and crisp readability.",
        "layout_mode": "top_nav",
        "palette": LIGHT,
        "font_family": '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif',
        "border_radius": 3,
        "card_radius": 4,
        "variant": "light",
    },
}

PRESET_ALIASES: dict[str, str] = {
    "dark": "steam_modern",
    "steam": "steam_modern",
    "modern": "steam_modern",
    "steam_modern": "steam_modern",
    "retro": "steam_2003",
    "retro_green": "steam_2003",
    "classic": "steam_2003",
    "steam_2003": "steam_2003",
    "epic": "epic_sidebar",
    "sidebar": "epic_sidebar",
    "epic_sidebar": "epic_sidebar",
    "gog": "gog_galaxy",
    "galaxy": "gog_galaxy",
    "cyber": "gog_galaxy",
    "gog_galaxy": "gog_galaxy",
    "light": "light",
}

# Current palette (mutated by apply_theme so delegates can read colours cheaply).
C: dict[str, str] = dict(DARK)
_CURRENT_PRESET_ID: str = "steam_modern"


def get_preset(name: str) -> dict[str, Any]:
    """Retrieve preset by ID or alias, defaulting safely to steam_modern."""
    key = str(name).lower().strip()
    target_id = PRESET_ALIASES.get(key, key)
    if target_id in PRESETS:
        return PRESETS[target_id]
    return PRESETS["steam_modern"]


def list_presets() -> list[dict[str, Any]]:
    """Return list of all configured presets in display order."""
    return [
        PRESETS["steam_modern"],
        PRESETS["steam_2003"],
        PRESETS["epic_sidebar"],
        PRESETS["gog_galaxy"],
        PRESETS["light"],
    ]


def get_current_preset_id() -> str:
    """Return the currently applied preset identifier."""
    return _CURRENT_PRESET_ID


def card_radius() -> int:
    """Return active preset card corner radius."""
    return int(get_preset(_CURRENT_PRESET_ID).get("card_radius", 4))


def border_radius() -> int:
    """Return active preset button/control border radius."""
    return int(get_preset(_CURRENT_PRESET_ID).get("border_radius", 3))


def current_variant() -> str:
    """Return active preset variant identifier."""
    return str(get_preset(_CURRENT_PRESET_ID).get("variant", "steam_modern"))


def color(name: str, alpha: int | None = None) -> QColor:
    c = QColor(C.get(name, "#ffffff"))
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def stylesheet(c: dict[str, str], preset: dict[str, Any] | str | None = None) -> str:
    """Compile application stylesheet according to active palette and preset geometry."""
    if isinstance(preset, str):
        p = get_preset(preset)
    elif isinstance(preset, dict):
        p = preset
    else:
        p = get_preset(_CURRENT_PRESET_ID)

    font_fam = p.get("font_family", '"Segoe UI Variable Text", "Segoe UI", sans-serif')
    br = p.get("border_radius", 3)
    cr = p.get("card_radius", 4)
    var = p.get("variant", "steam_modern")

    # Retro 2003 Beveled styling
    if var == "steam_2003":
        btn_border = f"border-top: 1px solid #75866f; border-left: 1px solid #75866f; border-right: 1px solid #232a20; border-bottom: 1px solid #232a20;"
        btn_pressed = f"border-top: 1px solid #232a20; border-left: 1px solid #232a20; border-right: 1px solid #75866f; border-bottom: 1px solid #75866f;"
        card_border = f"border-top: 1px solid #232a20; border-left: 1px solid #232a20; border-right: 1px solid #75866f; border-bottom: 1px solid #75866f;"
        input_border = f"border: 2px solid #232a20; background: #353c2f;"
        play_btn = f"""
QPushButton#Play {{
    background: {c['success']};
    border-top: 2px solid #75866f; border-left: 2px solid #75866f;
    border-right: 2px solid #232a20; border-bottom: 2px solid #232a20;
    border-radius: 0px; color: #ffffff; padding: 9px 26px; font-size: 11pt; font-weight: 700;
}}
QPushButton#Play:hover {{ background: {c['success_hover']}; }}
QPushButton#Play:pressed {{
    border-top: 2px solid #232a20; border-left: 2px solid #232a20;
    border-right: 2px solid #75866f; border-bottom: 2px solid #75866f;
}}
"""
    elif var == "gog_galaxy":
        btn_border = f"border: 1px solid {c['border']}; border-radius: {br}px;"
        btn_pressed = f"background: {c['surface2']};"
        card_border = f"border: 1px solid {c['border']}; border-radius: {cr}px;"
        input_border = f"border: 1px solid {c['border']}; border-radius: {br}px;"
        play_btn = f"""
QPushButton#Play {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #9333ea);
    border: none; border-radius: {br}px; color: #ffffff; padding: 9px 26px; font-size: 11pt; font-weight: 700;
}}
QPushButton#Play:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #a855f7); color: #ffffff;
}}
QPushButton#Play:pressed {{ background: #6d28d9; }}
"""
    elif var == "epic_sidebar":
        btn_border = f"border: 1px solid {c['border']}; border-radius: {br}px;"
        btn_pressed = f"background: {c['surface2']};"
        card_border = f"border: 1px solid {c['border']}; border-radius: {cr}px;"
        input_border = f"border: 1px solid {c['border']}; border-radius: {br}px;"
        play_btn = f"""
QPushButton#Play {{
    background: {c['accent']}; border: none; border-radius: {br}px; color: #ffffff;
    padding: 9px 26px; font-size: 11pt; font-weight: 700;
}}
QPushButton#Play:hover {{ background: {c['accent_hover']}; }}
QPushButton#Play:pressed {{ background: #0056b3; }}
"""
    else:  # steam_modern or light
        btn_border = f"border: 1px solid rgba(255, 255, 255, 0.08); border-radius: {br}px;"
        btn_pressed = f"background: {c['surface']};"
        card_border = f"border: 1px solid {c['border']}; border-radius: {cr}px;"
        input_border = f"border: 1px solid {c['border']}; border-radius: {br}px;"
        play_btn = f"""
QPushButton#Play {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5c7e10, stop:1 #759c14);
    border: none; border-radius: {br}px; color: #ffffff; padding: 9px 26px; font-size: 11pt; font-weight: 700; letter-spacing: 0.5px;
}}
QPushButton#Play:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d9313, stop:1 #85b017); color: #ffffff;
}}
QPushButton#Play:pressed {{ background: #4b660c; }}
"""

    return f"""
* {{ font-family: {font_fam}; font-size: 10pt; color: {c['text']}; }}
QMainWindow, QWidget#Page, QScrollArea, QScrollArea > QWidget > QWidget#ScrollBody, QDialog {{ background: {c['bg']}; }}

QWidget#TopNavBar {{
    background: {c['sidebar'] if var in ('epic_sidebar', 'gog_galaxy') else (c['surface'] if var == 'steam_2003' else c['bg'])};
    border-bottom: {2 if var == 'steam_2003' else 1}px solid {c['border']};
}}

QWidget#Sidebar {{
    background: {c['sidebar']};
    border-right: {2 if var == 'steam_2003' else 1}px solid {c['border']};
}}

QLabel#AppName {{ font-size: 13pt; font-weight: 800; letter-spacing: 2px; color: #ffffff; text-transform: uppercase; }}
QLabel#PageTitle {{ font-size: 20pt; font-weight: 800; letter-spacing: 1px; color: #ffffff; text-transform: uppercase; }}
QLabel#SectionTitle {{ font-size: 11pt; font-weight: 700; letter-spacing: 0.5px; color: #ffffff; text-transform: uppercase; padding-top: 4px; }}
QLabel#Muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
QLabel#HeroTitle {{ font-size: 26pt; font-weight: 800; color: #ffffff; background: transparent; }}
QLabel#HeroSub {{ color: {c['muted']}; background: transparent; font-size: 10.5pt; }}
QLabel#Chip {{ background: {c['surface3']}; color: {c['text']}; border-radius: {12 if var == 'gog_galaxy' else (0 if var == 'steam_2003' else 3)}px; padding: 3px 8px; font-size: 9pt; font-weight: 600; }}
QLabel#EmptyState {{ color: {c['muted']}; font-size: 12pt; }}

QPushButton#NavButton {{
    text-align: left; padding: 11px 16px; border: none; border-radius: {br}px;
    background: transparent; color: {c['muted']}; font-size: 10pt; font-weight: 700; letter-spacing: 1px;
}}
QPushButton#NavButton:hover {{ background: {c['surface2']}; color: #ffffff; }}
QPushButton#NavButton:checked {{ background: {c['surface']}; color: #ffffff; border-left: 3px solid {c['accent']}; }}

QPushButton#NavButton[nav_layout="top"] {{
    text-align: center;
    padding: 8px 18px;
    border: none;
    border-left: none;
    border-bottom: 3px solid transparent;
    border-radius: {0 if var == 'steam_2003' else 2}px;
    background: transparent;
    color: {c['muted']};
}}
QPushButton#NavButton[nav_layout="top"]:hover {{
    background: {c['surface2']};
    color: #ffffff;
}}
QPushButton#NavButton[nav_layout="top"]:checked {{
    background: {c['surface'] if var == 'steam_2003' else ('rgba(139, 92, 246, 0.15)' if var == 'gog_galaxy' else 'transparent')};
    color: #ffffff;
    border-bottom: 3px solid {c['accent']};
    border-left: none;
}}

QPushButton#NavButton[nav_layout="sidebar"] {{
    text-align: left;
    padding: 11px 16px;
    border: none;
    border-left: 3px solid transparent;
    border-bottom: none;
    border-radius: {br}px;
}}
QPushButton#NavButton[nav_layout="sidebar"]:checked {{
    background: {c['surface']};
    color: #ffffff;
    border-left: 3px solid {c['accent']};
    border-bottom: none;
}}

QPushButton {{
    background: {c['surface3']};
    {btn_border}
    color: {c['text']}; padding: 7px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {c['surface2']}; color: #ffffff; }}
QPushButton:pressed {{ {btn_pressed} }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['bg']}; border-color: {c['border']}; }}

QPushButton#Primary {{ background: {c['accent']}; border: none; border-radius: {br}px; color: #ffffff; font-weight: 700; }}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {c['surface3']}; color: {c['muted']}; }}

{play_btn}
QPushButton#Play:disabled {{ background: {c['surface3']}; color: {c['muted']}; }}

QPushButton#Danger {{ background: #3a1c1c; border: 1px solid {c['danger']}; color: #ff7777; border-radius: {br}px; }}
QPushButton#Danger:hover {{ background: {c['danger']}; color: #ffffff; }}
QPushButton#Pill {{ border-radius: {14 if var == 'gog_galaxy' else (0 if var == 'steam_2003' else 12)}px; padding: 4px 14px; background: transparent; border: 1px solid {c['border']}; color: {c['muted']}; }}
QPushButton#Pill:hover {{ color: #ffffff; border-color: {c['accent']}; }}
QPushButton#Pill:checked {{ background: {c['surface3']}; border-color: {c['accent']}; color: #ffffff; }}
QPushButton#Flat {{ background: transparent; border: none; padding: 6px 10px; color: {c['muted']}; }}
QPushButton#Flat:hover {{ background: {c['surface2']}; color: #ffffff; }}
QToolButton {{ background: {c['surface3']}; border: 1px solid {c['border']}; border-radius: {br}px; padding: 6px 9px; }}
QToolButton:checked {{ background: {c['accent']}; color: #ffffff; border-color: {c['accent']}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {c['surface']};
    {input_border}
    padding: 6px 10px;
    color: {c['text']}; selection-background-color: {c['accent']}; selection-color: #171a21;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
QLineEdit#Search {{ padding-left: 12px; min-width: 240px; border-radius: {14 if var == 'gog_galaxy' else br}px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['surface3']}; color: {c['text']}; outline: 0; }}

QListView, QListWidget {{ background: transparent; border: none; outline: 0; }}
QTabBar::tab {{
    background: transparent; padding: 8px 18px; color: {c['muted']}; font-weight: 700;
    font-size: 10pt; letter-spacing: 0.5px; border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{ color: #ffffff; border-bottom: 3px solid {c['accent']}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}

QMenuBar#RetroMenuBar {{
    background: {c['surface'] if var == 'steam_2003' else c['sidebar']};
    border-bottom: {2 if var == 'steam_2003' else 1}px solid {c['border']};
    padding: 2px 6px;
    font-size: 9.5pt;
}}
QMenuBar#RetroMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    color: {c['text']};
    border-radius: {0 if var == 'steam_2003' else br}px;
}}
QMenuBar#RetroMenuBar::item:selected {{
    background: {c['surface3']};
    color: #ffffff;
}}
QMenuBar#RetroMenuBar::item:pressed {{
    background: {'#232a20' if var == 'steam_2003' else c['surface2']};
    color: #ffffff;
}}

QGroupBox {{
    background: {'rgba(31, 22, 51, 0.65)' if var == 'gog_galaxy' else c['surface']};
    border: {2 if var == 'steam_2003' else 1}px solid {c['border']};
    border-radius: {cr}px;
    margin-top: 14px; padding: 16px 14px 12px 14px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: {2 if var == 'gog_galaxy' else 0}px {8 if var == 'gog_galaxy' else 4}px;
    color: {c['accent']};
    background: {'rgba(58, 42, 94, 0.75)' if var == 'gog_galaxy' else 'transparent'};
    border-radius: {6 if var == 'gog_galaxy' else 0}px;
}}

QFrame#Card {{
    background: {'rgba(31, 22, 51, 0.65)' if var == 'gog_galaxy' else c['surface']};
    {card_border}
}}
QFrame#CardHeader, QWidget#CardHeader {{
    background: {'rgba(58, 42, 94, 0.45)' if var == 'gog_galaxy' else (c['surface2'] if var == 'steam_2003' else c['surface3'])};
    border-bottom: 1px solid {c['border']};
    border-top-left-radius: {cr}px;
    border-top-right-radius: {cr}px;
    padding: 8px 12px;
}}
QFrame#Separator {{ background: {c['border']}; max-height: 1px; }}

QLineEdit#TopQuickSearch {{
    background: {'#1f1633' if var == 'gog_galaxy' else c['surface']};
    border: 1px solid {c['border']};
    border-radius: {13 if var == 'gog_galaxy' else (0 if var == 'steam_2003' else br)}px;
    padding: 5px 12px;
    color: {c['text']};
    font-size: 9.5pt;
    min-width: 190px;
    selection-background-color: {c['accent']};
}}
QLineEdit#TopQuickSearch:focus {{
    border-color: {c['accent']};
}}

QPushButton#BpNavBtn {{
    text-align: left;
    padding: 11px 16px;
    border: none;
    border-radius: {br}px;
    background: transparent;
    color: {c['accent']};
    font-size: 10pt;
    font-weight: 800;
    letter-spacing: 1px;
}}
QPushButton#BpNavBtn:hover {{
    background: {c['surface2']};
    color: {c['accent_hover']};
}}
QPushButton#BpNavBtn[nav_layout="top"] {{
    text-align: center;
    padding: 8px 16px;
    border-radius: {0 if var == 'steam_2003' else 2}px;
    border-bottom: 3px solid transparent;
}}
QPushButton#BpNavBtn[nav_layout="top"]:hover {{
    background: {c['surface2']};
    color: {c['accent_hover']};
}}

QPushButton#QuickThemeBtn {{
    background: {c['surface3'] if var == 'steam_2003' else 'transparent'};
    border: 1px solid {c['border']};
    border-radius: {0 if var == 'steam_2003' else br}px;
    color: {c['text']};
    padding: 5px 11px;
    font-size: 9pt;
    font-weight: 600;
}}
QPushButton#QuickThemeBtn:hover {{
    background: {c['surface2']};
    color: #ffffff;
    border-color: {c['accent']};
}}

QPushButton#CollapseBtn {{
    background: transparent;
    border: 1px solid {c['border']};
    border-radius: {0 if var == 'steam_2003' else br}px;
    color: {c['muted']};
    padding: 4px 8px;
    font-weight: 800;
    font-size: 9pt;
}}
QPushButton#CollapseBtn:hover {{
    background: {c['surface2']};
    color: #ffffff;
    border-color: {c['accent']};
}}

QProgressBar {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: {br}px; height: 8px; text-align: center; font-size: 1px; color: transparent; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: {max(0, br - 1)}px; }}

QScrollBar:vertical {{ background: {c['sidebar']}; width: 10px; margin: 0px; }}
QScrollBar::handle:vertical {{ background: {c['surface3']}; border-radius: {br}px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
QScrollBar:horizontal {{ background: {c['sidebar']}; height: 10px; margin: 0px; }}
QScrollBar::handle:horizontal {{ background: {c['surface3']}; border-radius: {br}px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}
QScrollBar:add-line, QScrollBar:sub-line, QScrollBar:add-page, QScrollBar:sub-page {{ background: none; border: none; width: 0; height: 0; }}

QMenu {{
    background: {c['surface']};
    border: {2 if var == 'steam_2003' else 1}px solid {c['border']};
    {f"border-top: 2px solid #75866f; border-left: 2px solid #75866f; border-right: 2px solid #232a20; border-bottom: 2px solid #232a20;" if var == 'steam_2003' else ""}
    padding: 4px;
    border-radius: {cr}px;
}}
QMenu::item {{ padding: 6px 22px; border-radius: {br}px; color: {c['text']}; }}
QMenu::item:selected {{ background: {c['surface3']}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; border-radius: {br}px; }}
QCheckBox {{ spacing: 8px; color: {c['text']}; }}
QLabel#Toast {{ background: {c['surface']}; border: 1px solid {c['accent']}; border-radius: {cr}px; padding: 10px 16px; color: #ffffff; }}
QWizard, QWizard QWidget {{ background: {c['bg']}; }}
"""


def apply_theme(app: QApplication, name: str) -> str:
    """Apply theme preset by name or alias to the QApplication instance."""
    global _CURRENT_PRESET_ID
    preset = get_preset(name)
    _CURRENT_PRESET_ID = preset["id"]

    C.clear()
    C.update(preset["palette"])

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C["bg"]))
    pal.setColor(QPalette.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.Base, QColor(C["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(C["surface2"]))
    pal.setColor(QPalette.Text, QColor(C["text"]))
    pal.setColor(QPalette.Button, QColor(C["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.Highlight, QColor(C["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor(C["muted"]))
    app.setPalette(pal)

    app.setStyleSheet(stylesheet(C, preset))
    return _CURRENT_PRESET_ID
