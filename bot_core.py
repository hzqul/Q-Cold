import os
import sys
import time
import random
import threading

os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

import cv2
import numpy as np

try:
    from ppadb.client import Client as AdbClient
except Exception:
    AdbClient = None

from settings_store import SettingsStore
from data_store import DataStore
from telegram_notifier import TelegramNotifier

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    try:
        __compiled__  # noqa: F821
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        EXE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
    except NameError:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        EXE_DIR = BASE_DIR

IMG_DIR = os.path.join(BASE_DIR, "img")
SETTINGS_FILE = os.path.join(EXE_DIR, "settings.json")
STATS_FILE = os.path.join(EXE_DIR, "stats_data.json")

MAX_WINDOWS = 5


def _load_templates():
    old_stderr = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    templates = {}
    try:
        names = [
            "play", "next", "exit", "exit2", "attack", "starr", "yellow_star",
            "close", "forward", "lets_go", "hold", "reconnect", "reload",
            "home", "back", "continue", "mega_quest", "brawlers_btn",
            "select_brawler", "trophy_icon", "understand", "next_green",
            "prime_tag", "anr_title", "anr_close", "battle_indicator",
        ]
        file_map = {
            "play": "play_btn.png", "next": "next_btn.png", "exit": "exit_btn.png",
            "exit2": "exit_btn2.png", "attack": "attack_btn.png",
            "starr": "starr_trigger.png", "yellow_star": "yellow_star.png",
            "close": "close_btn.png", "forward": "forward_btn.png",
            "lets_go": "letsgo_btn.png", "hold": "hold_trigger.png",
            "reconnect": "reconnect_btn.png", "reload": "reload_btn.png",
            "home": "home_btn.png", "back": "back_btn.png",
            "continue": "continue_btn.png", "mega_quest": "mega_quest.png",
            "brawlers_btn": "brawlers_menu_btn.png", "select_brawler": "select_btn.png",
            "trophy_icon": "trophy_icon.png", "understand": "understand_btn.png",
            "next_green": "next_green_btn.png", "prime_tag": "prime_tag.png",
            "anr_title": "anr_title.png", "anr_close": "anr_close_btn.png",
            "battle_indicator": "battle_indicator.png",
        }
        for key in names:
            templates[key] = cv2.imread(os.path.join(IMG_DIR, file_map[key]), cv2.IMREAD_COLOR)
        for i in range(10):
            templates[f"num_{i}"] = cv2.imread(os.path.join(IMG_DIR, f"num_{i}.png"), cv2.IMREAD_COLOR)
    except Exception:
        pass
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
    return templates


def format_time_string(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def smart_sleep(base_seconds):
    time.sleep(random.uniform(base_seconds * 0.85, base_seconds * 1.15))


class WindowRuntime:
    """Состояние одного окна/эмулятора, видимое интерфейсу."""

    def __init__(self, window_id):
        self.window_id = window_id
        self.status = "Инициализация..."
        self.status_since = time.time()
        self.matches = 0
        self.start_trophies = None
        self.current_trophies = None
        self.last_screenshot = None
        self.connected = True
        self.paused = threading.Event()
        self.stop_flag = threading.Event()
        self._manual_restart = False
        self._last_match_trophies = None


class BotEngine:
    def __init__(self):
        self.settings = SettingsStore(SETTINGS_FILE)
        self.stats = DataStore(STATS_FILE)
        self.templates = _load_templates()
        self.telegram = TelegramNotifier(
            enabled=self.settings.get("telegram_enabled"),
            token=self.settings.get("telegram_token"),
            chat_id=self.settings.get("telegram_chat_id"),
        )

        self.lock = threading.RLock()
        self.windows = {}
        self.active_serials = {}

        self.start_time = time.time()
        self._current_angle = random.uniform(0, 360)
        self._stride_counter = 0

        self.adb = None
        self.adb_error = None
        try:
            self.adb = AdbClient(host="127.0.0.1", port=5037)
        except Exception as e:
            self.adb_error = str(e)

        self._running = False

    # ------------------------------------------------------------ lifecycle
    def start(self):
        if self._running:
            return
        self._running = True
        self.telegram.notify("bot_started")
        threading.Thread(target=self._device_scanner, daemon=True).start()
        threading.Thread(target=self._autosave_loop, daemon=True).start()

    def stop(self):
        self._running = False
        with self.lock:
            for w in self.windows.values():
                w.stop_flag.set()
        self.stats.add_session_time(int(time.time() - self.start_time))
        self.stats.save()
        self.settings.save()
        self.telegram.notify("bot_stopped")

    def refresh_telegram_config(self):
        """Обновить настройки Telegram после изменения в GUI."""
        self.telegram.configure(
            enabled=self.settings.get("telegram_enabled"),
            token=self.settings.get("telegram_token"),
            chat_id=self.settings.get("telegram_chat_id"),
        )

    def _autosave_loop(self):
        while self._running:
            self.stats.maybe_autosave(min_interval=15)
            time.sleep(5)

    # -------------------------------------------------------------- public
    def get_window_display_name(self, window_id):
        return self.settings.get_window_display_name(window_id)

    def set_window_display_name(self, window_id, display_name):
        self.settings.set_window_display_name(window_id, display_name)

    def session_uptime_str(self):
        return format_time_string(time.time() - self.start_time)

    def total_uptime_str(self):
        return format_time_string(self.stats.get_total_time() + (time.time() - self.start_time))

    def get_window_ids(self):
        with self.lock:
            return sorted(self.windows.keys())

    def get_snapshot(self, window_id):
        with self.lock:
            w = self.windows.get(window_id)
            if not w:
                return None
            return {
                "status": w.status,
                "status_seconds": int(time.time() - w.status_since),
                "matches": w.matches,
                "start_trophies": w.start_trophies,
                "current_trophies": w.current_trophies,
                "connected": w.connected,
                "paused": w.paused.is_set(),
                "display_name": self.settings.get_window_display_name(window_id),
            }

    def get_screenshot(self, window_id):
        with self.lock:
            w = self.windows.get(window_id)
            return None if not w else w.last_screenshot

    def toggle_pause(self, window_id):
        with self.lock:
            w = self.windows.get(window_id)
            if not w:
                return
            if w.paused.is_set():
                w.paused.clear()
            else:
                w.paused.set()

    def is_paused(self, window_id):
        with self.lock:
            w = self.windows.get(window_id)
            return bool(w and w.paused.is_set())

    def force_restart(self, window_id):
        with self.lock:
            w = self.windows.get(window_id)
            if w:
                w.status = "🔄 Рестарт запрошен вручную"
                w.status_since = time.time()
                w._manual_restart = True

    def total_matches(self):
        return self.stats.total_matches()

    def get_window_stats(self, window_id):
        return self.stats.get_window_stats(window_id)

    def get_total_stats(self):
        return self.stats.get_total_stats()

    # ---------------------------------------------------------- internals
    def _notify(self, event_key, window_id, extra=""):
        name = self.get_window_display_name(window_id)
        details = f"Окно: {name}"
        if extra:
            details += f"\n{extra}"
        self.telegram.notify(event_key, details)

    def _update_status(self, w: WindowRuntime, text):
        if w.status != text:
            w.status = text
            w.status_since = time.time()

    def _next_free_index(self):
        with self.lock:
            used = set()
            for wid in self.windows.keys():
                try:
                    used.add(int(wid.split("#")[1]))
                except Exception:
                    pass
            idx = 1
            while idx in used and idx <= MAX_WINDOWS:
                idx += 1
            return idx

    def _device_scanner(self):
        active_threads = {}
        while self._running:
            try:
                if self.adb is None:
                    try:
                        self.adb = AdbClient(host="127.0.0.1", port=5037)
                    except Exception:
                        smart_sleep(3.0)
                        continue

                all_devices = self.adb.devices()
                current_devices = [d for d in all_devices if d.get_state() == "device"]

                dead = [s for s in active_threads if not active_threads[s].is_alive()]
                for s in dead:
                    del active_threads[s]

                for device in current_devices:
                    serial = device.serial
                    if serial in active_threads:
                        continue
                    with self.lock:
                        if len(self.windows) >= MAX_WINDOWS:
                            break
                        idx = self._next_free_index()
                        if idx > MAX_WINDOWS:
                            break
                        w_id = f"Окно #{idx}"
                        saved_tr, saved_mt = self.stats.load_saved_window(w_id)
                        w = WindowRuntime(w_id)
                        w.start_trophies = saved_tr
                        w.current_trophies = saved_tr
                        w.matches = saved_mt
                        self.windows[w_id] = w

                    t = threading.Thread(target=self._bot_worker, args=(device, w_id), daemon=True)
                    t.start()
                    active_threads[serial] = t
            except Exception:
                pass
            smart_sleep(3.0)

    # ----------------------------------------------------- vision helpers
    def _get_screenshot(self, device):
        try:
            image_bytes = device.screencap()
            if not image_bytes:
                return None
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def _find_template(self, screen, template_img, threshold=0.65):
        if template_img is None or screen is None:
            return None
        try:
            res = cv2.matchTemplate(screen, template_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                h, w, _ = template_img.shape
                return max_loc[0] + w // 2, max_loc[1] + h // 2
        except Exception:
            return None
        return None

    def _random_click(self, device, x, y):
        try:
            ox = x + random.randint(-6, 6)
            oy = y + random.randint(-5, 5)
            device.shell(f"input tap {ox} {oy}")
            smart_sleep(0.5)
        except Exception:
            pass

    def _long_press(self, device, x, y, duration_ms=2500):
        try:
            ox = x + random.randint(-5, 5)
            oy = y + random.randint(-5, 5)
            device.shell(f"input swipe {ox} {oy} {ox} {oy} {duration_ms}")
            smart_sleep(1.2)
        except Exception:
            pass

    def _get_current_trophies(self, device, screen):
        if screen is None:
            return None
        icon = self._find_template(screen, self.templates.get("trophy_icon"), threshold=0.80)
        if not icon:
            return None
        sx, sy = icon[0] + 15, icon[1] - 15
        crop = screen[sy:sy + 30, sx:sx + 80]
        found = []
        for i in range(10):
            tmpl = self.templates.get(f"num_{i}")
            if tmpl is None:
                continue
            res = cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= 0.85)
            for pt in zip(*loc[::-1]):
                found.append((pt[0], str(i)))
        if not found:
            return None
        found.sort(key=lambda x: x[0])
        final_str = ""
        last_x = -10
        for x, digit in found:
            if x - last_x > 5:
                final_str += digit
                last_x = x
        return int(final_str) if final_str else None

    def _is_gray_error_plate(self, screen):
        """
        Настоящая серая плашка сетевой ошибки — это ровный, однотонный
        прямоугольник. Раньше проверялся один пиксель (270, 480) на
        попадание B и G в диапазон 50-65 без учёта R вообще — из-за этого
        портрет некоторых бойцов на экране выбора (например, Булла) в этой
        же точке экрана случайно попадал в диапазон и бот принимал обычный
        экран за ошибку сети.
        Теперь проверяем небольшую область вокруг точки:
          1) все три канала должны быть серыми (близки друг к другу),
          2) разброс (variance) внутри области должен быть маленьким —
             у арта персонажа всегда есть текстура/тени, у плашки нет.
        """
        if screen is None:
            return False
        region = screen[260:280, 470:490]
        if region.size == 0:
            return False
        mean_b, mean_g, mean_r = (float(region[:, :, i].mean()) for i in range(3))
        if not (45 <= mean_b <= 70 and 45 <= mean_g <= 70 and 45 <= mean_r <= 70):
            return False
        if max(abs(mean_b - mean_g), abs(mean_g - mean_r), abs(mean_b - mean_r)) > 8:
            return False
        std_max = float(region.reshape(-1, 3).std(axis=0).max())
        return std_max < 6

    def _is_brawl_running(self, device):
        try:
            focus = device.shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
            if not focus or "error" in focus.lower():
                return False
            return "com.supercell.brawlstars" in focus
        except Exception:
            return False

    def _resolve_match_result(self, w: WindowRuntime, trophies):
        """Определяет победу/поражение по изменению кубков после матча."""
        if w._last_match_trophies is None or trophies is None:
            return
        diff = trophies - w._last_match_trophies
        if diff > 0:
            self.stats.record_victory(w.window_id)
        elif diff < 0:
            self.stats.record_loss(w.window_id)
        w._last_match_trophies = None

    def _skip_starr_drop_screens(self, device, w):
        self._update_status(w, "🌟 Пробиваю Starr Drop")
        attempts = 0
        while attempts < 25:
            self._random_click(device, 750, 270)
            smart_sleep(0.4)
            screen = self._get_screenshot(device)
            if screen is not None and self._find_template(screen, self.templates.get("play"), 0.70):
                break
            attempts += 1
        smart_sleep(0.5)

    def _start_brawl_fresh(self, device, w, screen):
        self._update_status(w, "⚠️ Вылет! Перезапуск игры...")
        self.stats.record_game_crash(w.window_id)
        self._notify("game_crash", w.window_id)
        try:
            # Если процесс просто завис (ANR) или "зомби", повторная отправка
            # launch-intent через monkey может просто вернуть на передний план
            # тот же зависший экран, ничего не перезапуская. force-stop гарантирует
            # чистый старт в любом случае.
            device.shell("am force-stop com.supercell.brawlstars")
            smart_sleep(1.5)
            device.shell("monkey -p com.supercell.brawlstars -c android.intent.category.LAUNCHER 1")
            smart_sleep(15)
        except Exception:
            pass

    def _restart_brawl(self, device, w):
        self._update_status(w, "🔄 Профилактический рестарт")
        try:
            device.shell("am force-stop com.supercell.brawlstars")
            smart_sleep(3)
            device.shell("pm trim-caches 999G")
            device.shell("monkey -p com.supercell.brawlstars -c android.intent.category.LAUNCHER 1")
            smart_sleep(15)
        except Exception:
            pass

    def _simulate_battle_actions(self, device):
        attack_x, attack_y = 810, 390
        if random.random() < 0.50:
            device.shell(f"input tap {attack_x + random.randint(-5, 5)} {attack_y + random.randint(-5, 5)}")
        else:
            angle = self._current_angle + random.randint(-20, 20)
            rad = np.radians(angle)
            ax = int(attack_x + 70 * np.cos(rad))
            ay = int(attack_y + 70 * np.sin(rad))
            device.shell(f"input swipe {attack_x} {attack_y} {ax} {ay} 120")

        joy_x = 150 + random.randint(-8, 8)
        joy_y = 400 + random.randint(-8, 8)
        if self._stride_counter % 3 == 0:
            self._current_angle += random.randint(-60, 60)
        self._stride_counter += 1
        rad = np.radians(self._current_angle)
        radius = random.randint(130, 160)
        end_x = int(joy_x + radius * np.cos(rad))
        end_y = int(joy_y + radius * np.sin(rad))
        duration = random.randint(1000, 1500)
        device.shell(f"input swipe {joy_x} {joy_y} {end_x} {end_y} {duration}")

    def _solve_mega_quests(self, device, w):
        self._update_status(w, "🧪 Кликаю Мегаквесты")
        for x, y in [(155, 380), (330, 420), (500, 430)]:
            self._random_click(device, x, y)
            smart_sleep(0.8)
        smart_sleep(1.5)

    def _auto_change_brawler(self, device, w):
        self._update_status(w, "🔍 Смена бойца: Ищу меню...")
        screen = self._get_screenshot(device)
        coords = self._find_template(screen, self.templates.get("brawlers_btn"), 0.75)
        if coords:
            device.shell(f"input tap {coords[0]} {coords[1]}")
        else:
            device.shell("input tap 65 270")
        smart_sleep(4.0)

        self._update_status(w, "🎯 Выбираю следующего бойца")
        device.shell("input tap 200 170")
        smart_sleep(3.5)

        screen = self._get_screenshot(device)
        sel = self._find_template(screen, self.templates.get("select_brawler"), 0.70)
        if sel:
            device.shell(f"input tap {sel[0]} {sel[1]}")
        else:
            device.shell("input tap 130 490")
        self._update_status(w, "✅ Персонаж изменен")
        smart_sleep(3.5)

    # -------------------------------------------------------------- worker
    def _bot_worker(self, device, window_id):
        w = self.windows[window_id]
        w._manual_restart = False
        matches_since_change = 0
        self._update_status(w, "Поток запущен")

        last_time_tick = time.time()

        while not w.stop_flag.is_set():
            try:
                if w.paused.is_set():
                    self._update_status(w, "⏸ На паузе")
                    time.sleep(1.0)
                    last_time_tick = time.time()
                    continue

                now = time.time()
                self.stats.add_active_time(window_id, now - last_time_tick)
                last_time_tick = now

                try:
                    device.shell("echo 1")
                except Exception as adb_err:
                    if "not found" in str(adb_err).lower() or "device offline" in str(adb_err).lower():
                        with self.lock:
                            self.windows.pop(window_id, None)
                        return

                t = self.templates

                # Скриншот берём ДО проверки "запущена ли игра": системный диалог
                # "Приложение не отвечает" (ANR) может не принадлежать фокусу
                # com.supercell.brawlstars, поэтому раньше бот считал игру
                # незапущенной и просто слал launch-intent поверх зависшего экрана,
                # диалог не закрывался и игра реально не открывалась.
                screen = self._get_screenshot(device)

                anr_hit = self._find_template(screen, t.get("anr_title"), 0.70) if screen is not None else None
                if anr_hit:
                    self._update_status(w, "💥 Игра зависла (ANR). Закрываю и перезапускаю...")
                    close_btn = self._find_template(screen, t.get("anr_close"), 0.70)
                    self._random_click(device, *(close_btn or (357, 284)))
                    smart_sleep(2)
                    try:
                        device.shell("am force-stop com.supercell.brawlstars")
                    except Exception:
                        pass
                    smart_sleep(1)
                    self._start_brawl_fresh(device, w, None)
                    continue

                if not self._is_brawl_running(device):
                    self._start_brawl_fresh(device, w, screen)
                    continue

                if screen is not None:
                    w.last_screenshot = screen
                if screen is None:
                    self._update_status(w, "⏳ Ожидание скриншота")
                    smart_sleep(2)
                    continue

                if w._manual_restart:
                    w._manual_restart = False
                    self._restart_brawl(device, w)
                    continue

                reconnect = self._find_template(screen, t.get("reconnect"), 0.65)
                if reconnect:
                    self._update_status(w, "📡 Ошибка сети! Переподключение")
                    self.stats.record_reconnect(window_id)
                    self._notify("reconnect", window_id)
                    self._random_click(device, *reconnect)
                    smart_sleep(10)
                    continue

                reload_c = self._find_template(screen, t.get("reload"), 0.65)
                if reload_c:
                    self._update_status(w, "⚠️ АФК-кик! Перезагрузка")
                    self.stats.record_afk_kick(window_id)
                    self._notify("afk_kick", window_id)
                    self._random_click(device, *reload_c)
                    smart_sleep(12)
                    continue

                if self._is_gray_error_plate(screen):
                    self._update_status(w, "📡 Серая плашка ошибки")
                    self.stats.record_reconnect(window_id)
                    self._notify("reconnect", window_id)
                    self._random_click(device, 350, 410)
                    self._random_click(device, 150, 410)
                    smart_sleep(12)
                    continue

                understand = self._find_template(screen, t.get("understand"), 0.75)
                if understand:
                    self._update_status(w, "💚 Нажимаю 'Понятно!'")
                    self._random_click(device, *understand)
                    smart_sleep(1.5)
                    continue

                next_green = self._find_template(screen, t.get("next_green"), 0.75)
                if next_green:
                    self._update_status(w, "💚 Нажимаю 'Далее'")
                    self._random_click(device, *next_green)
                    smart_sleep(1.5)
                    continue

                mega = self._find_template(screen, t.get("mega_quest"), 0.60)
                if mega:
                    self._solve_mega_quests(device, w)
                    continue

                hold_c = self._find_template(screen, t.get("hold"), 0.70)
                if hold_c:
                    self._update_status(w, "✊ Зажимаю экран удержания")
                    self._long_press(device, 480, 270, 2500)
                    continue

                starr = self._find_template(screen, t.get("starr"), 0.70)
                yellow = self._find_template(screen, t.get("yellow_star"), 0.75)
                if starr or yellow:
                    self._skip_starr_drop_screens(device, w)
                    continue

                close_c = self._find_template(screen, t.get("close"), 0.70)
                if close_c:
                    self._update_status(w, "❌ Закрываю баннер")
                    self._random_click(device, *close_c)
                    smart_sleep(1.5)
                    continue

                forward_c = self._find_template(screen, t.get("forward"), 0.75)
                if forward_c:
                    self._update_status(w, "➡️ Нажимаю 'Вперед'")
                    self._random_click(device, *forward_c)
                    smart_sleep(1.5)
                    continue

                letsgo = self._find_template(screen, t.get("lets_go"), 0.75)
                if letsgo:
                    self._update_status(w, "🚀 Нажимаю 'Погнали!'")
                    self._random_click(device, *letsgo)
                    smart_sleep(1.5)
                    continue

                home_c = self._find_template(screen, t.get("home"), 0.80)
                if home_c:
                    self._update_status(w, "🏠 Выхожу в меню через Домик")
                    self._random_click(device, *home_c)
                    smart_sleep(1.5)
                    continue

                back_c = self._find_template(screen, t.get("back"), 0.80)
                if back_c:
                    self._update_status(w, "⬅️ Нажимаю стрелку назад")
                    self._random_click(device, *back_c)
                    smart_sleep(1.5)
                    continue

                continue_c = self._find_template(screen, t.get("continue"), 0.75)
                if continue_c:
                    self._update_status(w, "🔵 Нажимаю 'Продолжить'")
                    self._random_click(device, *continue_c)
                    smart_sleep(1.5)
                    continue

                play_c = self._find_template(screen, t.get("play"), 0.70)
                if play_c:
                    try:
                        trophies = self._get_current_trophies(device, screen)
                        if trophies:
                            self._resolve_match_result(w, trophies)
                            w.current_trophies = trophies
                            if w.start_trophies is None or trophies < w.start_trophies:
                                w.start_trophies = trophies
                            self.stats.record_trophies(window_id, trophies)
                    except Exception:
                        pass

                    mode = self.settings.get("auto_change_mode")
                    if mode == "prime":
                        prime = self._find_template(screen, t.get("prime_tag"), 0.72)
                        if prime:
                            self._update_status(w, "💎 Прайм апнут. Меняю бойца...")
                            self.stats.record_prime_upgrade(window_id)
                            self._notify("prime_upgraded", window_id)
                            self._auto_change_brawler(device, w)
                            continue
                    elif mode == "matches":
                        need = int(self.settings.get("auto_change_matches") or 10)
                        if need > 0 and matches_since_change >= need:
                            matches_since_change = 0
                            self._update_status(w, f"🔁 {need} катков сыграно. Меняю бойца...")
                            self._auto_change_brawler(device, w)
                            continue

                    self._update_status(w, "💤 В лобби. Играть")
                    self._random_click(device, *play_c)
                    smart_sleep(6)
                    continue

                next_c = self._find_template(screen, t.get("next"), 0.75)
                if next_c:
                    self._update_status(w, "⏩ Нажимаю 'Далее'")
                    self._random_click(device, *next_c)
                    smart_sleep(3)
                    continue

                exit_c = self._find_template(screen, t.get("exit"), 0.75)
                exit2_c = self._find_template(screen, t.get("exit2"), 0.75)
                target_exit = exit_c or exit2_c
                if target_exit:
                    w._last_match_trophies = w.current_trophies
                    w.matches += 1
                    matches_since_change += 1
                    self.stats.record_match(window_id)
                    self._update_status(w, "🎉 Выхожу из матча")
                    self.stats.save()
                    self._random_click(device, *target_exit)
                    smart_sleep(7)

                    if self.settings.get("auto_restart_enabled"):
                        need = int(self.settings.get("auto_restart_matches") or 30)
                        if need > 0 and w.matches % need == 0:
                            self._restart_brawl(device, w)
                    continue

                # Раньше "в матче" считалось единственным вариантом, если ни одна
                # другая кнопка не нашлась (определение "от противного"). Теперь
                # дополнительно ищем реальный индикатор боя на экране — так бот
                # не начнёт слать боевые тапы на незнакомом/непредусмотренном экране.
                battle_icon = self._find_template(screen, t.get("battle_indicator"), 0.70)
                if battle_icon:
                    self._update_status(w, "⚔️ В матче")
                    self._simulate_battle_actions(device)
                    if random.random() < 0.30:
                        self._random_click(device, 480, 30)
                    smart_sleep(1.0)
                else:
                    self._update_status(w, "❓ Неизвестный экран")
                    smart_sleep(1.5)

            except Exception as exc:
                self._update_status(w, "⚠️ Ошибка цикла")
                self._notify("fatal_error", window_id, str(exc))
                smart_sleep(4)
