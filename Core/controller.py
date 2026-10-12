"""Gamepad and controller support (Steam Input / Steam Controller style).

Provides zero-dependency Windows XInput detection and polling, supporting
Xbox 360/One/Series, PlayStation controllers (via XInput/emulation), and
generic gamepads. Automatically captures the Guide/Xbox/PS button (ordinal 100)
and Back+Start combo to open Big Picture Mode, and generates debounced menu
navigation events.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, Signal

from Core.logger import get_logger

log = get_logger(__name__)

# XInput button bitmasks
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_GUIDE = 0x0400  # Xbox / PS / Guide button exposed via XInputGetStateEx
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167

BUTTON_MAP = {
    XINPUT_GAMEPAD_DPAD_UP: "UP",
    XINPUT_GAMEPAD_DPAD_DOWN: "DOWN",
    XINPUT_GAMEPAD_DPAD_LEFT: "LEFT",
    XINPUT_GAMEPAD_DPAD_RIGHT: "RIGHT",
    XINPUT_GAMEPAD_START: "START",
    XINPUT_GAMEPAD_BACK: "BACK",
    XINPUT_GAMEPAD_LEFT_THUMB: "THUMB_L",
    XINPUT_GAMEPAD_RIGHT_THUMB: "THUMB_R",
    XINPUT_GAMEPAD_LEFT_SHOULDER: "LB",
    XINPUT_GAMEPAD_RIGHT_SHOULDER: "RB",
    XINPUT_GAMEPAD_GUIDE: "GUIDE",
    XINPUT_GAMEPAD_A: "A",
    XINPUT_GAMEPAD_B: "B",
    XINPUT_GAMEPAD_X: "X",
    XINPUT_GAMEPAD_Y: "Y",
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


class ControllerSignals(QObject):
    connected = Signal(int, str)      # (user_index, device_name)
    disconnected = Signal(int)        # (user_index)
    guide_pressed = Signal()          # Guide / Home / Xbox / PS button
    button_down = Signal(str)         # Button name ("A", "B", etc.)
    button_up = Signal(str)

    # Navigation signals with repeat
    nav_up = Signal()
    nav_down = Signal()
    nav_left = Signal()
    nav_right = Signal()
    nav_select = Signal()             # A / Cross
    nav_back = Signal()               # B / Circle
    nav_action = Signal()             # X / Square
    nav_extra = Signal()              # Y / Triangle
    nav_tab_prev = Signal()           # LB / L1
    nav_tab_next = Signal()           # RB / R1


class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", ctypes.c_wchar * 32),
        ("wXmin", wintypes.UINT),
        ("wXmax", wintypes.UINT),
        ("wYmin", wintypes.UINT),
        ("wYmax", wintypes.UINT),
        ("wZmin", wintypes.UINT),
        ("wZmax", wintypes.UINT),
        ("wNumButtons", wintypes.UINT),
        ("wPeriodMin", wintypes.UINT),
        ("wPeriodMax", wintypes.UINT),
        ("wRmin", wintypes.UINT),
        ("wRmax", wintypes.UINT),
        ("wUmin", wintypes.UINT),
        ("wUmax", wintypes.UINT),
        ("wVmin", wintypes.UINT),
        ("wVmax", wintypes.UINT),
        ("wCaps", wintypes.UINT),
        ("wMaxAxes", wintypes.UINT),
        ("wNumAxes", wintypes.UINT),
        ("wMaxButtons", wintypes.UINT),
        ("szRegKey", ctypes.c_wchar * 32),
        ("szOEMVxD", ctypes.c_wchar * 260),
    ]


class ControllerManager:
    """Detects gamepads and emits navigation / guide button events."""

    _instance: ControllerManager | None = None

    @classmethod
    def get_instance(cls) -> ControllerManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.signals = ControllerSignals()
        self._running = False
        self._thread: threading.Thread | None = None
        self._xinput_lib = None
        self._get_state_fn = None
        self._winmm_lib = None
        self._has_ex = False
        self._xinput_connected: dict[int, bool] = {i: False for i in range(4)}
        self._winmm_connected: dict[int, bool] = {i: False for i in range(4)}
        self._connected: dict[int, bool] = {i: False for i in range(8)}
        self._prev_buttons: dict[int, int] = {i: 0 for i in range(4)}
        self._winmm_prev_buttons: dict[int, int] = {i: 0 for i in range(4)}
        self._nav_repeat_dir: dict[int, str | None] = {i: None for i in range(4)}
        self._nav_repeat_start: dict[int, float] = {i: 0.0 for i in range(4)}
        self._nav_last_repeat: dict[int, float] = {i: 0.0 for i in range(4)}
        self._winmm_nav_repeat_dir: dict[int, str | None] = {i: None for i in range(4)}
        self._winmm_nav_repeat_start: dict[int, float] = {i: 0.0 for i in range(4)}
        self._winmm_nav_last_repeat: dict[int, float] = {i: 0.0 for i in range(4)}
        self._init_xinput()
        self._init_winmm()

    def _init_xinput(self):
        if sys.platform != "win32":
            log.info("Non-Windows OS: XInput disabled")
            return

        for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                lib = ctypes.windll.LoadLibrary(dll)
                # Check for ordinal 100 (XInputGetStateEx) which reports the Guide button
                try:
                    fn = lib[100]
                    fn.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
                    fn.restype = wintypes.DWORD
                    self._xinput_lib = lib
                    self._get_state_fn = fn
                    self._has_ex = True
                    log.info("XInput loaded via %s (with Guide button support)", dll)
                    break
                except Exception:
                    fn = getattr(lib, "XInputGetState", None)
                    if fn:
                        fn.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
                        fn.restype = wintypes.DWORD
                        self._xinput_lib = lib
                        self._get_state_fn = fn
                        self._has_ex = False
                        log.info("XInput loaded via %s (standard mode)", dll)
                        break
            except Exception:
                continue

    def _init_winmm(self):
        if sys.platform != "win32":
            return
        try:
            if hasattr(ctypes.windll, "winmm"):
                self._winmm_lib = ctypes.windll.winmm
        except Exception:
            pass

    def is_connected(self) -> bool:
        return any(self._xinput_connected.values()) or any(self._winmm_connected.values())

    def connected_count(self) -> int:
        return sum(1 for v in self._xinput_connected.values() if v) + sum(1 for v in self._winmm_connected.values() if v)

    def get_status_text(self) -> str:
        count = self.connected_count()
        if count == 0:
            return "No controller detected"
        elif count == 1:
            return "1 Controller Connected (Gamepad / Steam Input)"
        return f"{count} Controllers Connected"

    def start(self):
        if self._running or (not self._get_state_fn and not self._winmm_lib):
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="GamepadPollThread")
        self._thread.start()
        log.info("Gamepad polling started")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll_loop(self):
        while self._running:
            try:
                self._poll_step()
            except Exception as exc:
                log.warning("Gamepad poll error: %s", exc)
            time.sleep(0.02)  # ~50 Hz polling

    def _poll_step(self):
        DEADZONE = 15000
        REPEAT_DELAY = 0.26
        REPEAT_RATE = 0.12

        has_xinput = False

        # 1. Primary XInput check
        if self._get_state_fn:
            for user_idx in range(4):
                state = XINPUT_STATE()
                res = self._get_state_fn(user_idx, ctypes.byref(state))

                was_conn = self._xinput_connected[user_idx]
                is_conn = (res == ERROR_SUCCESS)

                if is_conn:
                    has_xinput = True

                if is_conn != was_conn:
                    self._xinput_connected[user_idx] = is_conn
                    self._connected[user_idx] = is_conn
                    if is_conn:
                        dev_name = f"Controller {user_idx + 1}"
                        log.info("%s connected", dev_name)
                        self.signals.connected.emit(user_idx, dev_name)
                    else:
                        log.info("Controller %d disconnected", user_idx + 1)
                        self.signals.disconnected.emit(user_idx)
                        self._prev_buttons[user_idx] = 0
                        self._nav_repeat_dir[user_idx] = None

                if not is_conn:
                    continue

                curr_buttons = state.Gamepad.wButtons
                prev_buttons = self._prev_buttons[user_idx]
                self._prev_buttons[user_idx] = curr_buttons

                # Newly pressed buttons
                pressed = curr_buttons & ~prev_buttons
                released = prev_buttons & ~curr_buttons

                # Guide button (0x0400) or Back + Start combo
                guide_hit = (pressed & XINPUT_GAMEPAD_GUIDE) != 0
                combo_hit = ((curr_buttons & (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START)) == (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START)) and \
                            ((prev_buttons & (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START)) != (XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_START))
                if guide_hit or combo_hit:
                    log.info("Controller Guide / Main button triggered Big Picture Mode")
                    self.signals.guide_pressed.emit()

                # Face buttons and shoulders
                if pressed & XINPUT_GAMEPAD_A:
                    self.signals.button_down.emit("A")
                    self.signals.nav_select.emit()
                if pressed & XINPUT_GAMEPAD_B:
                    self.signals.button_down.emit("B")
                    self.signals.nav_back.emit()
                if pressed & XINPUT_GAMEPAD_X:
                    self.signals.button_down.emit("X")
                    self.signals.nav_action.emit()
                if pressed & XINPUT_GAMEPAD_Y:
                    self.signals.button_down.emit("Y")
                    self.signals.nav_extra.emit()
                if pressed & XINPUT_GAMEPAD_LEFT_SHOULDER:
                    self.signals.button_down.emit("LB")
                    self.signals.nav_tab_prev.emit()
                if pressed & XINPUT_GAMEPAD_RIGHT_SHOULDER:
                    self.signals.button_down.emit("RB")
                    self.signals.nav_tab_next.emit()

                for mask, name in BUTTON_MAP.items():
                    if released & mask:
                        self.signals.button_up.emit(name)

                # Directional navigation (D-pad + Left Analog Stick)
                dir_held = None
                if (curr_buttons & XINPUT_GAMEPAD_DPAD_UP) or state.Gamepad.sThumbLY > DEADZONE:
                    dir_held = "UP"
                elif (curr_buttons & XINPUT_GAMEPAD_DPAD_DOWN) or state.Gamepad.sThumbLY < -DEADZONE:
                    dir_held = "DOWN"
                elif (curr_buttons & XINPUT_GAMEPAD_DPAD_LEFT) or state.Gamepad.sThumbLX < -DEADZONE:
                    dir_held = "LEFT"
                elif (curr_buttons & XINPUT_GAMEPAD_DPAD_RIGHT) or state.Gamepad.sThumbLX > DEADZONE:
                    dir_held = "RIGHT"

                now = time.time()
                if dir_held:
                    if self._nav_repeat_dir[user_idx] != dir_held:
                        self._nav_repeat_dir[user_idx] = dir_held
                        self._nav_repeat_start[user_idx] = now
                        self._nav_last_repeat[user_idx] = now
                        self._emit_nav(dir_held)
                    elif now - self._nav_repeat_start[user_idx] > REPEAT_DELAY and now - self._nav_last_repeat[user_idx] > REPEAT_RATE:
                        self._nav_last_repeat[user_idx] = now
                        self._emit_nav(dir_held)
                else:
                    self._nav_repeat_dir[user_idx] = None

        # 2. Handle active XInput taking priority over WinMM fallback
        if has_xinput and self._winmm_lib:
            for dev_idx in range(2):
                if self._winmm_connected[dev_idx]:
                    self._winmm_connected[dev_idx] = False
                    self._connected[dev_idx + 4] = False
                    log.info("Generic Gamepad %d disconnected (XInput active)", dev_idx + 1)
                    self.signals.disconnected.emit(dev_idx + 4)
                    self._winmm_prev_buttons[dev_idx] = 0
                    self._winmm_nav_repeat_dir[dev_idx] = None

        # 3. Secondary WinMM fallback for generic USB / DirectInput gamepads
        if not has_xinput and self._winmm_lib:
            for dev_idx in range(2):
                info = JOYINFOEX()
                info.dwSize = ctypes.sizeof(JOYINFOEX)
                info.dwFlags = 0xFF
                res = self._winmm_lib.joyGetPosEx(dev_idx, ctypes.byref(info))
                was_conn = self._winmm_connected[dev_idx]
                is_conn = (res == 0)

                if is_conn != was_conn:
                    self._winmm_connected[dev_idx] = is_conn
                    self._connected[dev_idx + 4] = is_conn
                    if is_conn:
                        dev_name = f"Generic Gamepad {dev_idx + 1}"
                        try:
                            caps = JOYCAPSW()
                            if hasattr(self._winmm_lib, "joyGetDevCapsW") and self._winmm_lib.joyGetDevCapsW(dev_idx, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                                if caps.wMid == 0x054C:
                                    dev_name = f"PlayStation Controller {dev_idx + 1}"
                                elif caps.szPname:
                                    name_str = caps.szPname.strip()
                                    if name_str and name_str != "Microsoft PC-joystick driver":
                                        dev_name = name_str
                        except Exception:
                            pass
                        log.info("%s connected", dev_name)
                        self.signals.connected.emit(dev_idx + 4, dev_name)
                    else:
                        log.info("Generic Gamepad %d disconnected", dev_idx + 1)
                        self.signals.disconnected.emit(dev_idx + 4)
                        self._winmm_prev_buttons[dev_idx] = 0
                        self._winmm_nav_repeat_dir[dev_idx] = None

                if not is_conn:
                    continue

                curr_b = info.dwButtons
                prev_b = self._winmm_prev_buttons[dev_idx]
                self._winmm_prev_buttons[dev_idx] = curr_b
                pressed_b = curr_b & ~prev_b

                # Common DirectInput mappings:
                # B0 = Cross/A, B1 = Circle/B, B2 = Square/X, B3 = Triangle/Y
                # B4 = L1, B5 = R1, B6 = Select/Share, B7 = Start/Options
                # B8/B12 = Guide / Home / PS
                if (pressed_b & 0x0100) or (pressed_b & 0x1000) or ((curr_b & 0xC0) == 0xC0 and (prev_b & 0xC0) != 0xC0):
                    self.signals.guide_pressed.emit()
                if pressed_b & 0x01:
                    self.signals.nav_select.emit()
                if pressed_b & 0x02:
                    self.signals.nav_back.emit()
                if pressed_b & 0x04:
                    self.signals.nav_action.emit()
                if pressed_b & 0x08:
                    self.signals.nav_extra.emit()
                if pressed_b & 0x10:
                    self.signals.nav_tab_prev.emit()
                if pressed_b & 0x20:
                    self.signals.nav_tab_next.emit()

                # POV Hat / Analog stick
                dir_held = None
                pov = info.dwPOV
                if pov != 65535:
                    if pov == 0 or pov >= 31500 or pov <= 4500:
                        dir_held = "UP"
                    elif 4500 < pov <= 13500:
                        dir_held = "RIGHT"
                    elif 13500 < pov <= 22500:
                        dir_held = "DOWN"
                    elif 22500 < pov < 31500:
                        dir_held = "LEFT"
                elif info.dwYpos < 16000:
                    dir_held = "UP"
                elif info.dwYpos > 48000:
                    dir_held = "DOWN"
                elif info.dwXpos < 16000:
                    dir_held = "LEFT"
                elif info.dwXpos > 48000:
                    dir_held = "RIGHT"

                now = time.time()
                if dir_held:
                    if self._winmm_nav_repeat_dir[dev_idx] != dir_held:
                        self._winmm_nav_repeat_dir[dev_idx] = dir_held
                        self._winmm_nav_repeat_start[dev_idx] = now
                        self._winmm_nav_last_repeat[dev_idx] = now
                        self._emit_nav(dir_held)
                    elif now - self._winmm_nav_repeat_start[dev_idx] > REPEAT_DELAY and now - self._winmm_nav_last_repeat[dev_idx] > REPEAT_RATE:
                        self._winmm_nav_last_repeat[dev_idx] = now
                        self._emit_nav(dir_held)
                else:
                    self._winmm_nav_repeat_dir[dev_idx] = None

    def _emit_nav(self, direction: str):
        if direction == "UP":
            self.signals.nav_up.emit()
        elif direction == "DOWN":
            self.signals.nav_down.emit()
        elif direction == "LEFT":
            self.signals.nav_left.emit()
        elif direction == "RIGHT":
            self.signals.nav_right.emit()
