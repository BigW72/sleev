"""Apply a folder's artwork as its Finder icon. macOS only.

The AppKit import is deferred to `set_folder_icon` so that importing sleev —
and so running any other command — still works where pyobjc isn't installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

log = logging.getLogger(__name__)

# macOS stores a folder's custom icon in a file literally named "Icon\r".
# The carriage return is real, and is how we tell an icon has been set.
ICON_RESOURCE = "Icon\r"


class IconError(RuntimeError):
    """Setting a folder icon failed in a way worth reporting per folder."""


def is_supported() -> bool:
    return sys.platform == "darwin"


def has_custom_icon(folder: Path) -> bool:
    return (folder / ICON_RESOURCE).exists()


def set_folder_icon(icon: Path, folder: Path) -> None:
    """Apply the .icns at *icon* as *folder*'s icon."""
    if not is_supported():
        raise IconError("folder icons can only be set on macOS")

    try:
        from AppKit import NSImage, NSWorkspace
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise IconError("pyobjc is missing; reinstall sleev to pull it in") from exc

    image = NSImage.alloc().initWithContentsOfFile_(str(icon))
    if image is None:
        raise IconError(f"{icon.name} could not be loaded as an image")

    if not NSWorkspace.sharedWorkspace().setIcon_forFile_options_(image, str(folder), 0):
        raise IconError("macOS refused to set the icon")
