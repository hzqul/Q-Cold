"""
data_store.py
Статистика по окнам и по дням: матчи, победы, праймы, вылеты и т.д.
Хранится в stats_data.json потокобезопасно.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta

TOTAL_KEY = "ВСЕГО"


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _empty_window_stats():
    return {
        "start_trophies": None,
        "current_trophies": None,
        "matches": 0,
        "victories": 0,
        "losses": 0,
        "primes_upgraded": 0,
        "afk_kicks": 0,
        "reconnects": 0,
        "game_crashes": 0,
        "running_time_seconds": 0.0,
        "last_activity": None,
    }


class DataStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self._data = {
            "total_time": 0,
            "windows": {},
            "daily": {},
        }
        self._last_saved = 0
        self.load()

    # ------------------------------------------------------------------ IO
    def load(self):
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    self._data.update(loaded)
                    for wid, wdata in self._data.get("windows", {}).items():
                        base = _empty_window_stats()
                        base.update(wdata)
                        self._data["windows"][wid] = base
                except Exception:
                    pass

    def save(self):
        with self._lock:
            try:
                tmp_path = self.path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.path)
            except Exception:
                pass

    # ------------------------------------------------------------- helpers
    def _window_bucket(self, window_id):
        windows = self._data.setdefault("windows", {})
        entry = windows.setdefault(window_id, _empty_window_stats())
        for key, default in _empty_window_stats().items():
            entry.setdefault(key, default if not isinstance(default, float) else 0.0)
        return entry

    def _day_bucket(self, date_str, window_id):
        day = self._data["daily"].setdefault(date_str, {})
        entry = day.setdefault(window_id, {
            "matches": 0,
            "victories": 0,
            "losses": 0,
            "primes_upgraded": 0,
            "afk_kicks": 0,
            "reconnects": 0,
            "game_crashes": 0,
            "trophies_gained": 0,
            "time_seconds": 0.0,
            "_day_start_trophies": None,
        })
        return entry

    def _touch_activity(self, window_id):
        entry = self._window_bucket(window_id)
        entry["last_activity"] = _now_iso()

    # -------------------------------------------------------------- public
    def get_window_snapshot(self, window_id):
        with self._lock:
            return dict(self._window_bucket(window_id))

    def load_saved_window(self, window_id):
        """Восстановить сохранённые кубки/катки окна после перезапуска."""
        with self._lock:
            w = self._window_bucket(window_id)
            return w.get("start_trophies"), w.get("matches", 0)

    def get_total_time(self):
        with self._lock:
            return self._data.get("total_time", 0)

    def add_session_time(self, seconds):
        with self._lock:
            self._data["total_time"] = self._data.get("total_time", 0) + seconds

    def record_trophies(self, window_id, trophies):
        with self._lock:
            w = self._window_bucket(window_id)
            if w["start_trophies"] is None or trophies < w["start_trophies"]:
                w["start_trophies"] = trophies
            w["current_trophies"] = trophies
            self._touch_activity(window_id)

            today = self._day_bucket(_today_str(), window_id)
            if today["_day_start_trophies"] is None:
                today["_day_start_trophies"] = trophies
            today["trophies_gained"] = trophies - today["_day_start_trophies"]

    def record_match(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["matches"] = w.get("matches", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["matches"] += 1
            self._touch_activity(window_id)

    def record_victory(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["victories"] = w.get("victories", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["victories"] = today.get("victories", 0) + 1
            self._touch_activity(window_id)

    def record_loss(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["losses"] = w.get("losses", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["losses"] = today.get("losses", 0) + 1
            self._touch_activity(window_id)

    def record_prime_upgrade(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["primes_upgraded"] = w.get("primes_upgraded", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["primes_upgraded"] = today.get("primes_upgraded", 0) + 1
            self._touch_activity(window_id)

    def record_afk_kick(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["afk_kicks"] = w.get("afk_kicks", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["afk_kicks"] = today.get("afk_kicks", 0) + 1
            self._touch_activity(window_id)

    def record_reconnect(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["reconnects"] = w.get("reconnects", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["reconnects"] = today.get("reconnects", 0) + 1
            self._touch_activity(window_id)

    def record_game_crash(self, window_id):
        with self._lock:
            w = self._window_bucket(window_id)
            w["game_crashes"] = w.get("game_crashes", 0) + 1
            today = self._day_bucket(_today_str(), window_id)
            today["game_crashes"] = today.get("game_crashes", 0) + 1
            self._touch_activity(window_id)

    def add_active_time(self, window_id, seconds):
        with self._lock:
            w = self._window_bucket(window_id)
            w["running_time_seconds"] = w.get("running_time_seconds", 0.0) + seconds
            today = self._day_bucket(_today_str(), window_id)
            today["time_seconds"] = today.get("time_seconds", 0.0) + seconds

    def total_matches(self):
        with self._lock:
            return sum(w.get("matches", 0) for w in self._data.get("windows", {}).values())

    def get_window_stats(self, window_id):
        """Полная статистика одного окна."""
        with self._lock:
            return dict(self._window_bucket(window_id))

    def get_total_stats(self):
        """Суммарная статистика по всем окнам."""
        with self._lock:
            totals = _empty_window_stats()
            totals.pop("start_trophies", None)
            totals.pop("current_trophies", None)
            totals.pop("last_activity", None)
            latest_activity = None
            for w in self._data.get("windows", {}).values():
                for key in ("matches", "victories", "losses", "primes_upgraded",
                            "afk_kicks", "reconnects", "game_crashes"):
                    totals[key] += w.get(key, 0)
                totals["running_time_seconds"] += w.get("running_time_seconds", 0.0)
                la = w.get("last_activity")
                if la and (latest_activity is None or la > latest_activity):
                    latest_activity = la
            totals["last_activity"] = latest_activity
            return totals

    def get_known_window_ids(self):
        with self._lock:
            return sorted(self._data.get("windows", {}).keys())

    def maybe_autosave(self, min_interval=15):
        now = time.time()
        if now - self._last_saved >= min_interval:
            self.save()
            self._last_saved = now

    def get_period_stats(self, days, window_id=None):
        """
        Статистика по дням за последние `days` дней.
        window_id=None — суммарно по всем окнам.
        """
        with self._lock:
            result = []
            for i in range(days):
                d = datetime.now() - timedelta(days=i)
                d_str = d.strftime("%Y-%m-%d")
                day_data = self._data["daily"].get(d_str, {})
                matches = victories = losses = trophies = 0
                time_s = 0.0
                if window_id:
                    entry = day_data.get(window_id)
                    if entry:
                        matches = entry.get("matches", 0)
                        victories = entry.get("victories", 0)
                        losses = entry.get("losses", 0)
                        trophies = entry.get("trophies_gained", 0)
                        time_s = entry.get("time_seconds", 0.0)
                else:
                    for w_entry in day_data.values():
                        matches += w_entry.get("matches", 0)
                        victories += w_entry.get("victories", 0)
                        losses += w_entry.get("losses", 0)
                        trophies += w_entry.get("trophies_gained", 0)
                        time_s += w_entry.get("time_seconds", 0.0)
                result.append({
                    "date": d_str,
                    "date_display": d.strftime("%d.%m.%y"),
                    "matches": matches,
                    "victories": victories,
                    "losses": losses,
                    "trophies": trophies,
                    "time_seconds": time_s,
                })
            return result
