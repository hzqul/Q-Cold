"""
build_nuitka.py — сборка Q-Cold Brawl Bot и updater через Nuitka.

Использование:
    pip install nuitka ordered-set zstandard
    python build_nuitka.py

Результат:
    build/Q-Cold_Brawl_Bot.exe
    build/updater.exe
"""

import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_DIR, "build")


def _nuitka_base_args():
    """Общие аргументы Nuitka для обоих exe."""
    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--assume-yes-for-downloads",
        "--remove-output",
        f"--output-dir={BUILD_DIR}",
        "--windows-console-mode=disable",
        "--enable-plugin=pyside6",
    ]
    img_dir = os.path.join(PROJECT_DIR, "img")
    icons_dir = os.path.join(PROJECT_DIR, "icons")
    if os.path.isdir(img_dir):
        args.append(f"--include-data-dir={img_dir}=img")
    if os.path.isdir(icons_dir):
        args.append(f"--include-data-dir={icons_dir}=icons")
    return args


def build_bot():
    """Сборка основного бота."""
    print("=== Сборка Q-Cold_Brawl_Bot.exe ===")
    cmd = _nuitka_base_args() + [
        "--output-filename=Q-Cold_Brawl_Bot.exe",
        "--include-module=version",
        "--include-module=auto_update",
        "--include-module=telegram_notifier",
        "--include-module=settings_store",
        "--include-module=data_store",
        "--include-module=bot_core",
        os.path.join(PROJECT_DIR, "gui_app.py"),
    ]
    subprocess.check_call(cmd, cwd=PROJECT_DIR)


def build_updater():
    """Сборка updater.exe."""
    print("=== Сборка updater.exe ===")
    cmd = _nuitka_base_args() + [
        "--output-filename=updater.exe",
        os.path.join(PROJECT_DIR, "updater.py"),
    ]
    subprocess.check_call(cmd, cwd=PROJECT_DIR)


def copy_defaults():
    """Копирует settings.json по умолчанию в build/, если его там нет."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    src_settings = os.path.join(PROJECT_DIR, "settings.json")
    dst_settings = os.path.join(BUILD_DIR, "settings.json")
    if os.path.isfile(src_settings):
        shutil.copy2(src_settings, dst_settings)
    elif not os.path.isfile(dst_settings):
        from settings_store import DEFAULT_SETTINGS
        import json
        with open(dst_settings, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, ensure_ascii=False, indent=2)
        print(f"Создан settings.json по умолчанию: {dst_settings}")


def main():
    os.makedirs(BUILD_DIR, exist_ok=True)
    build_bot()
    build_updater()
    copy_defaults()
    print("\n=== Сборка завершена ===")
    print(f"  {os.path.join(BUILD_DIR, 'Q-Cold_Brawl_Bot.exe')}")
    print(f"  {os.path.join(BUILD_DIR, 'updater.exe')}")


if __name__ == "__main__":
    main()
