"""
Проверка обновлений через GitHub Releases API и запуск updater.exe.
"""

import json
import os
import sys
import subprocess
import urllib.error
import urllib.request

from version import VERSION


def _parse_version(version_str):
    """Преобразует строку версии в кортеж для сравнения."""
    if not version_str:
        return (0, 0, 0)
    cleaned = str(version_str).strip().lstrip("vV")
    parts = cleaned.split(".")
    result = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        result.append(int(digits) if digits else 0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


def is_newer_version(latest, current):
    """True, если latest новее current."""
    return _parse_version(latest) > _parse_version(current)


def get_exe_dir():
    """Каталог, где лежит исполняемый файл (или скрипт в режиме разработки)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    try:
        __compiled__  # noqa: F821 — маркер Nuitka
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    except NameError:
        return os.path.dirname(os.path.abspath(__file__))


def _find_exe_asset(release_data):
    """Ищет URL exe-файла бота среди assets релиза."""
    preferred_names = (
        "Q-Cold_Brawl_Bot.exe",
        "Q-Cold-Brawl-Bot.exe",
        "bot.exe",
    )
    assets = release_data.get("assets") or []
    for name in preferred_names:
        for asset in assets:
            if asset.get("name", "").lower() == name.lower():
                return asset.get("browser_download_url")
    for asset in assets:
        if asset.get("name", "").lower().endswith(".exe"):
            return asset.get("browser_download_url")
    return None


def check_for_update(github_owner, github_repo, current_version=None):
    """
    Проверяет GitHub Releases на наличие новой версии.

    Возвращает None или словарь:
        {
            "latest_version": "1.0.1",
            "download_url": "https://...",
            "release_notes": "...",
        }
    """
    owner = (github_owner or "").strip()
    repo = (github_repo or "").strip()
    if not owner or not repo:
        return None

    current = current_version or VERSION
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Q-Cold-Brawl-Bot-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    tag = (data.get("tag_name") or "").strip()
    if not tag or not is_newer_version(tag, current):
        return None

    download_url = _find_exe_asset(data)
    if not download_url:
        return None

    return {
        "latest_version": tag.lstrip("vV"),
        "download_url": download_url,
        "release_notes": data.get("body") or "",
    }


def get_updater_path():
    """Путь к updater.exe рядом с основным exe."""
    return os.path.join(get_exe_dir(), "updater.exe")


def get_bot_exe_path():
    """Путь к exe бота."""
    exe_dir = get_exe_dir()
    for name in ("Q-Cold_Brawl_Bot.exe", "Q-Cold-Brawl-Bot.exe"):
        path = os.path.join(exe_dir, name)
        if os.path.isfile(path):
            return path
    return os.path.join(exe_dir, "Q-Cold_Brawl_Bot.exe")


def launch_updater(download_url, parent_pid=None):
    """
    Запускает updater.exe и передаёт URL загрузки и PID текущего процесса.
    Возвращает True при успешном запуске.
    """
    updater = get_updater_path()
    if not os.path.isfile(updater):
        return False

    pid = parent_pid if parent_pid is not None else os.getpid()
    target = get_bot_exe_path()
    cmd = [
        updater,
        "--url", download_url,
        "--pid", str(pid),
        "--target", target,
    ]
    try:
        subprocess.Popen(cmd, cwd=get_exe_dir())
        return True
    except OSError:
        return False
