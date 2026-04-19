"""System capability probes (macOS version, iPhone Mirroring, permissions)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

_IPHONE_MIRRORING_PATH = Path("/System/Applications/iPhone Mirroring.app")


def check_macos_version() -> tuple[bool, str]:
    if platform.system() != "Darwin":
        return False, (
            f"Pilot requires macOS (detected {platform.system()}). "
            "iPhone Mirroring is macOS-only."
        )
    version_str = platform.mac_ver()[0]
    if not version_str:
        return False, "Could not determine macOS version"
    try:
        major = int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return False, f"Could not parse macOS version: {version_str}"
    if major >= 15:
        return True, f"macOS {version_str} (Sequoia+)"
    return False, (
        f"macOS {version_str} — need 15 (Sequoia) or later. "
        "Update via System Settings > General > Software Update."
    )


def check_iphone_mirroring_available() -> bool:
    return _IPHONE_MIRRORING_PATH.exists()


def check_iphone_mirroring_window() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of every process '
                'whose name contains "iPhone Mirroring"',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "iPhone Mirroring" in result.stdout:
            return True, "iPhone Mirroring window detected"
        return False, (
            "iPhone Mirroring is not running. Open it from Applications or "
            "Spotlight (Cmd+Space). Keep your iPhone locked (screen off)."
        )
    except FileNotFoundError:
        return False, "osascript not available (this is unusual for macOS)"
    except subprocess.TimeoutExpired:
        return False, "Timed out checking iPhone Mirroring"
    except Exception as exc:
        return False, f"Error checking iPhone Mirroring: {exc}"


def check_accessibility_permission() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first process',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, "Accessibility permission granted"
        return False, (
            "Accessibility permission not granted. Pilot needs this to simulate "
            "input. Open System Settings > Privacy & Security > Accessibility "
            "and add your terminal / Pilot.app."
        )
    except FileNotFoundError:
        return False, "osascript not available"
    except subprocess.TimeoutExpired:
        return False, "Timed out checking Accessibility permission"
    except Exception as exc:
        return False, f"Error checking Accessibility: {exc}"


def check_screen_recording_permission() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-t", "png", "/dev/null"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, "Screen Recording permission granted"
        return False, (
            "Screen Recording permission not granted. Pilot needs this to capture "
            "the iPhone Mirroring window. Open System Settings > Privacy & "
            "Security > Screen Recording and enable your terminal / Pilot.app."
        )
    except FileNotFoundError:
        return False, "screencapture not available"
    except subprocess.TimeoutExpired:
        return False, "Timed out checking Screen Recording permission"
    except Exception as exc:
        return False, f"Error checking Screen Recording: {exc}"


def check_disk_space(min_mb: float = 500.0) -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(Path.home())
        free_mb = usage.free / (1024 * 1024)
        if free_mb >= min_mb:
            return True, f"{free_mb:.0f} MB free"
        return False, f"Only {free_mb:.0f} MB free (need {min_mb:.0f} MB)"
    except OSError as exc:
        return False, f"Error checking disk space: {exc}"


def check_dependencies() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for pkg in ("pyautogui", "PIL", "anthropic"):
        label = "Pillow" if pkg == "PIL" else pkg
        try:
            __import__(pkg)
            results[label] = True
        except ImportError:
            results[label] = False
    results["cliclick"] = shutil.which("cliclick") is not None
    return results


def check_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def run_system_check() -> dict[str, Any]:
    macos_ok, macos_desc = check_macos_version()
    iphone_app = check_iphone_mirroring_available()
    iphone_win_ok, iphone_win_desc = check_iphone_mirroring_window()
    deps = check_dependencies()
    api_key = check_api_key()
    acc_ok, acc_desc = check_accessibility_permission()
    scr_ok, scr_desc = check_screen_recording_permission()
    disk_ok, disk_desc = check_disk_space()

    all_ok = (
        macos_ok and iphone_app and iphone_win_ok and all(deps.values())
        and api_key and acc_ok and scr_ok and disk_ok
    )
    return {
        "macos_version": (macos_ok, macos_desc),
        "iphone_mirroring": iphone_app,
        "iphone_mirroring_window": (iphone_win_ok, iphone_win_desc),
        "dependencies": deps,
        "api_key": api_key,
        "accessibility": (acc_ok, acc_desc),
        "screen_recording": (scr_ok, scr_desc),
        "disk_space": (disk_ok, disk_desc),
        "all_ok": all_ok,
    }
