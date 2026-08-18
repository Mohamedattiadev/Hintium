"""Hyprland's own IPC, standing in for X11/EWMH where there is no X window.

_NET_ACTIVE_WINDOW and _NET_CLIENT_LIST answer through the rootless XWayland
display (see x11.py), and XWayland only ever knows about XWayland clients --
a native-Wayland one (which is every window on a modern Hyprland desktop) has
no X window behind it at all. `hyprctl -j` asks the compositor directly and
answers correctly for every window regardless of how it was drawn, so it is
preferred wherever it is available; x11.py stays exactly as it was for a
plain X11 desktop, which is still the fallback here.

No config toggle for any of this: same auto-detect-and-fall-back shape as
x11.available(), since hyprctl either answers or it does not.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

from . import config

_HYPRCTL = "hyprctl"


@dataclass
class Window:
    """A Hyprland client. Mirrors the (pid, x, y, w, h) shape x11.py answers."""

    address: str
    pid: int
    title: str
    x: int
    y: int
    w: int
    h: int


def available():
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and \
        shutil.which(_HYPRCTL) is not None


def _query(args):
    """Run `hyprctl -j <args>`, parsed. None on any failure."""
    try:
        result = subprocess.run(
            [_HYPRCTL, "-j", *args],
            capture_output=True, text=True, timeout=1,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _window(data):
    try:
        x, y = data["at"]
        w, h = data["size"]
        return Window(data["address"], data["pid"],
                     data.get("title", ""), x, y, w, h)
    except (KeyError, TypeError, ValueError):
        return None


def active_window():
    """The focused window, or None. No window is a legitimate answer.

    "Focused" and "on screen" are not the same fact to Hyprland: a window
    dispatched into focus on a workspace that is not the one currently shown
    on any monitor stays `activewindow` without ever being drawn -- measured
    live, `hyprctl dispatch focuswindow` on such a window left activewindow
    pointing at it while the monitor kept showing whatever was really in
    front. Hinting or opening an editor against a window nobody can see is
    exactly the "hints in the wrong place" this guards against; `visible` is
    Hyprland's own answer to whether that gap exists right now.
    """
    data = _query(["activewindow"])
    if not data or not data.get("visible"):
        return None
    return _window(data)


def clients():
    """Every mapped, visible, on-screen-sized window worth offering."""
    data = _query(["clients"])
    if not data:
        return []
    found = []
    for entry in data:
        if not (entry.get("mapped") and not entry.get("hidden")
                and entry.get("visible")):
            continue
        window = _window(entry)
        if window is None:
            continue
        if window.w < config.MIN_WINDOW_SIZE or \
                window.h < config.MIN_WINDOW_SIZE:
            continue
        found.append(window)
    return found


def activate(address):
    """Focus a window by its Hyprland address."""
    try:
        result = subprocess.run(
            [_HYPRCTL, "dispatch", "focuswindow", f"address:{address}"],
            capture_output=True, timeout=2, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def active_workspace_id():
    """The workspace on screen, or None -- see x11.current_desktop()."""
    data = _query(["activeworkspace"])
    if not data:
        return None
    return data.get("id")
