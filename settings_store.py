"""
settings_store.py
Настройки бота: автоперезапуск, Telegram, GitHub-обновления, имена окон.
Хранится в settings.json рядом с программой, потокобезопасно.
"""

import json
import os
import threading

from version import VERSION

DEFAULT_SETTINGS = {
    "adb_path": r"C:\LDPlayer\LDPlayer9\adb.exe",

    # Автоматический профилактический рестарт игры
    "auto_restart_enabled": True,
    "auto_restart_matches": 30,

    # Автоматическая смена бойца
    # mode: "prime" | "matches" | "none"
    "auto_change_mode": "prime",
    "auto_change_matches": 10,

    "action_delay": 1.0,

    # Telegram-уведомления
    "telegram_enabled": False,
    "telegram_token": "",
    "telegram_chat_id": "",

    # Пользовательские имена окон: {"Окно #1": "Мой эмулятор", ...}
    "window_display_names": {},

    # GitHub Releases для автообновления
    "github_owner": "",
    "github_repo": "",
    "current_version": VERSION,
}


class SettingsStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    merged = dict(DEFAULT_SETTINGS)
                    merged.update(loaded)
                    if not isinstance(merged.get("window_display_names"), dict):
                        merged["window_display_names"] = {}
                    self._data = merged
                except Exception:
                    self._data = dict(DEFAULT_SETTINGS)
            else:
                self._data = dict(DEFAULT_SETTINGS)
                self.save()
            self._data["current_version"] = VERSION

    def save(self):
        with self._lock:
            self._data["current_version"] = VERSION
            try:
                tmp_path = self.path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)
            except Exception:
                pass

    def get(self, key):
        with self._lock:
            if key == "current_version":
                return VERSION
            return self._data.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        with self._lock:
            if key == "current_version":
                return
            self._data[key] = value
        self.save()

    def get_window_display_name(self, window_id):
        with self._lock:
            names = self._data.get("window_display_names") or {}
            return names.get(window_id, window_id)

    def set_window_display_name(self, window_id, display_name):
        with self._lock:
            names = dict(self._data.get("window_display_names") or {})
            display_name = (display_name or "").strip()
            if display_name and display_name != window_id:
                names[window_id] = display_name
            else:
                names.pop(window_id, None)
            self._data["window_display_names"] = names
        self.save()

    def as_dict(self):
        with self._lock:
            data = dict(self._data)
            data["current_version"] = VERSION
            return data
