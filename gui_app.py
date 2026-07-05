"""
gui_app.py
Современный интерфейс для мульти-бота Brawl Stars.

Запуск:
    pip install -r requirements.txt
    python gui_app.py
"""

import os
import sys
import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QGridLayout, QFrame, QCheckBox, QSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QMessageBox,
    QButtonGroup, QInputDialog,
)

from bot_core import BotEngine, MAX_WINDOWS, format_time_string
from version import VERSION
from auto_update import check_for_update, launch_updater, get_updater_path

ACCENT = "#c62b3a"
ACCENT_DIM = "#7a1c27"
BG_DARK = "#141014"
BG_PANEL = "#1c161a"
BG_CARD = "#221a1e"
TEXT_MAIN = "#f2e6e8"
TEXT_DIM = "#a98f93"
GREEN = "#3ecf6c"
YELLOW = "#e0b23e"

STYLE_SHEET = f"""
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_MAIN};
    font-family: 'Segoe UI', 'Arial';
    font-size: 13px;
}}
QFrame#TopBar {{
    background-color: {BG_PANEL};
    border-bottom: 2px solid {ACCENT_DIM};
}}
QFrame#Card {{
    background-color: {BG_CARD};
    border: 1px solid #382a2e;
    border-radius: 10px;
}}
QFrame#SettingsPanel, QFrame#StatsPanel {{
    background-color: {BG_PANEL};
    border-radius: 10px;
    border: 1px solid #2a2024;
}}
QLabel#Title {{
    color: {ACCENT};
    font-size: 20px;
    font-weight: 700;
}}
QLabel#TimerBig {{
    color: {TEXT_MAIN};
    font-size: 16px;
    font-weight: 600;
}}
QLabel#TimerLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel#WindowTitle {{
    color: {ACCENT};
    font-weight: 700;
    font-size: 14px;
}}
QLabel#Status {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel#Trophies {{
    color: {YELLOW};
    font-weight: 600;
    font-size: 13px;
}}
QLabel#Screenshot {{
    background-color: black;
    border: 2px solid #3a2a2e;
    border-radius: 6px;
}}
QPushButton {{
    background-color: #2c2024;
    border: 1px solid #4a353b;
    border-radius: 6px;
    padding: 6px 10px;
    color: {TEXT_MAIN};
}}
QPushButton:hover {{
    background-color: {ACCENT_DIM};
}}
QPushButton#Primary {{
    background-color: {ACCENT};
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background-color: #e0364a;
}}
QPushButton:checked {{
    background-color: {ACCENT};
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QComboBox, QSpinBox, QLineEdit {{
    background-color: #2c2024;
    border: 1px solid #4a353b;
    border-radius: 5px;
    padding: 4px 6px;
    color: {TEXT_MAIN};
}}
QTableWidget {{
    background-color: {BG_CARD};
    gridline-color: #3a2a2e;
    border: none;
    border-radius: 6px;
}}
QHeaderView::section {{
    background-color: #2c2024;
    color: {TEXT_DIM};
    padding: 4px;
    border: none;
}}
QLabel#SectionTitle {{
    color: {TEXT_MAIN};
    font-weight: 700;
    font-size: 13px;
}}
QLabel#VersionLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
"""


def cv_to_pixmap(bgr_image, target_w, target_h):
    if bgr_image is None:
        return None
    try:
        rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg.copy())
        return pix.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:
        return None


class WindowCard(QFrame):
    def __init__(self, engine: BotEngine, window_id: str, on_renamed=None):
        super().__init__()
        self.engine = engine
        self.window_id = window_id
        self.on_renamed = on_renamed
        self.setObjectName("Card")
        self.setMinimumWidth(200)
        self.setMaximumWidth(240)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.title_label = QLabel(engine.get_window_display_name(window_id))
        self.title_label.setObjectName("WindowTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setToolTip("Двойной клик — переименовать окно")
        self.title_label.mouseDoubleClickEvent = self._on_title_double_click
        layout.addWidget(self.title_label)

        self.screenshot_label = QLabel("Ожидание\nподключения...")
        self.screenshot_label.setObjectName("Screenshot")
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setFixedSize(200, 130)
        self.screenshot_label.setWordWrap(True)
        layout.addWidget(self.screenshot_label, alignment=Qt.AlignCenter)

        self.trophies_label = QLabel("??? → ???")
        self.trophies_label.setObjectName("Trophies")
        self.trophies_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.trophies_label)

        self.matches_label = QLabel("Матчей: 0")
        self.matches_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.matches_label)

        self.status_label = QLabel("Не подключено")
        self.status_label.setObjectName("Status")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.pause_btn = QPushButton("⏸ Пауза")
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        btn_row.addWidget(self.pause_btn)

        self.restart_btn = QPushButton("🔄")
        self.restart_btn.setToolTip("Рестарт игры сейчас")
        self.restart_btn.setMaximumWidth(36)
        self.restart_btn.clicked.connect(self.on_restart_clicked)
        btn_row.addWidget(self.restart_btn)
        layout.addLayout(btn_row)

        self.set_empty_state()

    def _on_title_double_click(self, _event):
        current = self.engine.get_window_display_name(self.window_id)
        text, ok = QInputDialog.getText(
            self,
            "Переименование окна",
            f"Имя для {self.window_id}:",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if ok and text.strip():
            self.engine.set_window_display_name(self.window_id, text.strip())
            self.title_label.setText(self.engine.get_window_display_name(self.window_id))
            if self.on_renamed:
                self.on_renamed()

    def set_empty_state(self):
        self.screenshot_label.setText("Ожидание\nподключения...")
        self.screenshot_label.setPixmap(QPixmap())
        self.trophies_label.setText("??? → ???")
        self.matches_label.setText("Матчей: 0")
        self.status_label.setText("Не подключено")
        self.pause_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)

    def on_pause_clicked(self):
        self.engine.toggle_pause(self.window_id)

    def on_restart_clicked(self):
        self.engine.force_restart(self.window_id)

    def refresh(self):
        snap = self.engine.get_snapshot(self.window_id)
        if not snap:
            self.set_empty_state()
            self.title_label.setText(self.engine.get_window_display_name(self.window_id))
            return

        self.pause_btn.setEnabled(True)
        self.restart_btn.setEnabled(True)
        self.title_label.setText(snap.get("display_name", self.window_id))

        shot = self.engine.get_screenshot(self.window_id)
        pix = cv_to_pixmap(shot, 200, 130)
        if pix is not None:
            self.screenshot_label.setPixmap(pix)
            self.screenshot_label.setText("")

        st = snap["start_trophies"]
        cur = snap["current_trophies"]
        st_s = st if st is not None else "???"
        cur_s = cur if cur is not None else "???"
        if st is not None and cur is not None:
            diff = cur - st
            diff_s = f"+{diff}" if diff >= 0 else str(diff)
            self.trophies_label.setText(f"{st_s} → {cur_s} ({diff_s})")
        else:
            self.trophies_label.setText(f"{st_s} → {cur_s}")

        self.matches_label.setText(f"Матчей: {snap['matches']}")

        m, s = divmod(snap["status_seconds"], 60)
        self.status_label.setText(f"{snap['status']}  ({m}:{s:02d})")

        if snap["paused"]:
            self.pause_btn.setText("▶ Продолжить")
        else:
            self.pause_btn.setText("⏸ Пауза")


class TelegramPanel(QFrame):
    def __init__(self, engine: BotEngine):
        super().__init__()
        self.engine = engine
        self.setObjectName("SettingsPanel")

        root = QVBoxLayout(self)
        title = QLabel("Telegram-уведомления")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        root.addLayout(grid)

        self.enabled_checkbox = QCheckBox("Включить уведомления")
        self.enabled_checkbox.setChecked(bool(engine.settings.get("telegram_enabled")))
        self.enabled_checkbox.stateChanged.connect(self._on_enabled_toggle)
        grid.addWidget(self.enabled_checkbox, 0, 0, 1, 2)

        grid.addWidget(QLabel("Bot Token:"), 1, 0)
        self.token_edit = QLineEdit(engine.settings.get("telegram_token") or "")
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.editingFinished.connect(self._save_token)
        grid.addWidget(self.token_edit, 1, 1, 1, 2)

        grid.addWidget(QLabel("Chat ID:"), 2, 0)
        self.chat_edit = QLineEdit(str(engine.settings.get("telegram_chat_id") or ""))
        self.chat_edit.editingFinished.connect(self._save_chat_id)
        grid.addWidget(self.chat_edit, 2, 1)

        self.test_btn = QPushButton("Тест")
        self.test_btn.clicked.connect(self._on_test)
        grid.addWidget(self.test_btn, 2, 2)

    def _apply_config(self):
        self.engine.refresh_telegram_config()

    def _on_enabled_toggle(self, state):
        self.engine.settings.set("telegram_enabled", bool(state))
        self._apply_config()

    def _save_token(self):
        self.engine.settings.set("telegram_token", self.token_edit.text().strip())
        self._apply_config()

    def _save_chat_id(self):
        self.engine.settings.set("telegram_chat_id", self.chat_edit.text().strip())
        self._apply_config()

    def _on_test(self):
        self._save_token()
        self._save_chat_id()
        self.engine.settings.set("telegram_enabled", self.enabled_checkbox.isChecked())
        self._apply_config()
        ok, message = self.engine.telegram.test_connection()
        if ok:
            QMessageBox.information(self, "Telegram", message)
        else:
            QMessageBox.warning(self, "Telegram", message)


class SettingsPanel(QFrame):
    def __init__(self, engine: BotEngine):
        super().__init__()
        self.engine = engine
        self.setObjectName("SettingsPanel")

        root = QVBoxLayout(self)
        title = QLabel("Настройки бота")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        root.addLayout(grid)

        self.restart_checkbox = QCheckBox("Автоматический перезапуск")
        self.restart_checkbox.setChecked(bool(engine.settings.get("auto_restart_enabled")))
        self.restart_checkbox.stateChanged.connect(self.on_restart_toggle)
        grid.addWidget(self.restart_checkbox, 0, 0)

        self.restart_label = QLabel("Матчей для перезапуска:")
        self.restart_spin = QSpinBox()
        self.restart_spin.setRange(1, 999)
        self.restart_spin.setValue(int(engine.settings.get("auto_restart_matches")))
        self.restart_spin.valueChanged.connect(self.on_restart_matches_change)
        grid.addWidget(self.restart_label, 0, 1)
        grid.addWidget(self.restart_spin, 0, 2)

        change_label = QLabel("Автоматическая смена персонажа:")
        grid.addWidget(change_label, 1, 0)

        self.change_combo = QComboBox()
        self.change_combo.addItem("После получение прайма", "prime")
        self.change_combo.addItem("После матчей", "matches")
        self.change_combo.addItem("Не менять", "none")
        current_mode = engine.settings.get("auto_change_mode")
        idx = {"prime": 0, "matches": 1, "none": 2}.get(current_mode, 0)
        self.change_combo.setCurrentIndex(idx)
        self.change_combo.currentIndexChanged.connect(self.on_change_mode)
        grid.addWidget(self.change_combo, 1, 1)

        self.change_matches_label = QLabel("Кол-во матчей:")
        self.change_matches_spin = QSpinBox()
        self.change_matches_spin.setRange(1, 999)
        self.change_matches_spin.setValue(int(engine.settings.get("auto_change_matches")))
        self.change_matches_spin.valueChanged.connect(self.on_change_matches)
        grid.addWidget(self.change_matches_label, 1, 2)
        grid.addWidget(self.change_matches_spin, 1, 3)

        adb_label = QLabel("Путь к adb.exe (LDPlayer):")
        grid.addWidget(adb_label, 2, 0)
        self.adb_edit = QLineEdit(engine.settings.get("adb_path"))
        self.adb_edit.editingFinished.connect(self.on_adb_path_change)
        grid.addWidget(self.adb_edit, 2, 1, 1, 3)

        grid.addWidget(QLabel("GitHub Owner:"), 3, 0)
        self.github_owner_edit = QLineEdit(engine.settings.get("github_owner") or "")
        self.github_owner_edit.editingFinished.connect(self._save_github_owner)
        grid.addWidget(self.github_owner_edit, 3, 1)

        grid.addWidget(QLabel("GitHub Repo:"), 3, 2)
        self.github_repo_edit = QLineEdit(engine.settings.get("github_repo") or "")
        self.github_repo_edit.editingFinished.connect(self._save_github_repo)
        grid.addWidget(self.github_repo_edit, 3, 3)

        self.update_visibility()

    def update_visibility(self):
        enabled = self.restart_checkbox.isChecked()
        self.restart_label.setVisible(enabled)
        self.restart_spin.setVisible(enabled)

        mode = self.change_combo.currentData()
        show_matches = (mode == "matches")
        self.change_matches_label.setVisible(show_matches)
        self.change_matches_spin.setVisible(show_matches)

    def on_restart_toggle(self, state):
        self.engine.settings.set("auto_restart_enabled", bool(state))
        self.update_visibility()

    def on_restart_matches_change(self, val):
        self.engine.settings.set("auto_restart_matches", int(val))

    def on_change_mode(self, _idx):
        mode = self.change_combo.currentData()
        self.engine.settings.set("auto_change_mode", mode)
        self.update_visibility()

    def on_change_matches(self, val):
        self.engine.settings.set("auto_change_matches", int(val))

    def on_adb_path_change(self):
        self.engine.settings.set("adb_path", self.adb_edit.text().strip())

    def _save_github_owner(self):
        self.engine.settings.set("github_owner", self.github_owner_edit.text().strip())

    def _save_github_repo(self):
        self.engine.settings.set("github_repo", self.github_repo_edit.text().strip())


class StatsPanel(QFrame):
    LIFETIME_COLUMNS = [
        ("Матчи", "matches"),
        ("Победы", "victories"),
        ("Поражения", "losses"),
        ("Праймы", "primes_upgraded"),
        ("АФК-кики", "afk_kicks"),
        ("Реконнекты", "reconnects"),
        ("Вылеты", "game_crashes"),
        ("Время", "running_time_seconds"),
        ("Активность", "last_activity"),
    ]

    def __init__(self, engine: BotEngine):
        super().__init__()
        self.engine = engine
        self.setObjectName("StatsPanel")
        self.period_days = 1
        self.selected_window = None

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("Статистика")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("Окно:"))
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(160)
        self.window_combo.currentIndexChanged.connect(self._on_window_changed)
        header.addWidget(self.window_combo)

        self.btn_group = QButtonGroup(self)
        for days, text in [(1, "1 день"), (3, "3 дня"), (7, "7 дней")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(days == 1)
            btn.clicked.connect(lambda checked, d=days: self.set_period(d))
            self.btn_group.addButton(btn)
            header.addWidget(btn)
        root.addLayout(header)

        self.lifetime_table = QTableWidget(1, len(self.LIFETIME_COLUMNS))
        self.lifetime_table.setHorizontalHeaderLabels([c[0] for c in self.LIFETIME_COLUMNS])
        self.lifetime_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lifetime_table.verticalHeader().setVisible(False)
        self.lifetime_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.lifetime_table.setMaximumHeight(70)
        root.addWidget(self.lifetime_table)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Дата", "Матчи", "Победы", "Поражения", "Время"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMaximumHeight(160)
        root.addWidget(self.table)

        self._rebuild_window_combo()
        self.refresh()

    def _rebuild_window_combo(self):
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("Все окна", None)
        for i in range(1, MAX_WINDOWS + 1):
            wid = f"Окно #{i}"
            display = self.engine.get_window_display_name(wid)
            self.window_combo.addItem(display, wid)
        idx = 0
        if self.selected_window:
            for i in range(self.window_combo.count()):
                if self.window_combo.itemData(i) == self.selected_window:
                    idx = i
                    break
        self.window_combo.setCurrentIndex(idx)
        self.window_combo.blockSignals(False)

    def _on_window_changed(self, _idx):
        self.selected_window = self.window_combo.currentData()
        self.refresh()

    def set_period(self, days):
        self.period_days = days
        self.refresh()

    def on_window_renamed(self):
        self._rebuild_window_combo()

    def _format_lifetime_value(self, key, stats):
        value = stats.get(key, 0)
        if key == "running_time_seconds":
            return format_time_string(value)
        if key == "last_activity":
            if not value:
                return "—"
            return str(value).replace("T", " ")
        return str(value)

    def refresh(self):
        if self.selected_window:
            lifetime = self.engine.get_window_stats(self.selected_window)
        else:
            lifetime = self.engine.get_total_stats()

        for col, (_, key) in enumerate(self.LIFETIME_COLUMNS):
            self.lifetime_table.setItem(
                0, col,
                QTableWidgetItem(self._format_lifetime_value(key, lifetime)),
            )

        rows = self.engine.stats.get_period_stats(self.period_days, self.selected_window)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(row["date_display"]))
            self.table.setItem(r, 1, QTableWidgetItem(str(row["matches"])))
            self.table.setItem(r, 2, QTableWidgetItem(str(row.get("victories", 0))))
            self.table.setItem(r, 3, QTableWidgetItem(str(row.get("losses", 0))))
            self.table.setItem(r, 4, QTableWidgetItem(format_time_string(row["time_seconds"])))


def check_updates_on_startup(settings):
    """Проверка обновлений при запуске. Возвращает True, если нужно завершить приложение."""
    update_info = check_for_update(
        settings.get("github_owner"),
        settings.get("github_repo"),
        VERSION,
    )
    if not update_info:
        return False

    notes = update_info.get("release_notes", "").strip()
    notes_block = f"\n\n{notes[:500]}" if notes else ""
    msg = (
        f"Доступна новая версия: {update_info['latest_version']}\n"
        f"Текущая версия: {VERSION}"
        f"{notes_block}\n\n"
        "Установить обновление сейчас?"
    )
    reply = QMessageBox.question(
        None,
        "Доступно обновление",
        msg,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if reply != QMessageBox.Yes:
        return False

    if not os.path.isfile(get_updater_path()):
        QMessageBox.warning(
            None,
            "Обновление",
            "Файл updater.exe не найден рядом с программой.\n"
            "Поместите updater.exe в ту же папку, что и бот.",
        )
        return False

    if not launch_updater(update_info["download_url"]):
        QMessageBox.warning(None, "Обновление", "Не удалось запустить updater.exe")
        return False

    return True


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Q-Cold Brawl Bot v{VERSION}")
        self.resize(1280, 920)

        self.engine = BotEngine()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(14)
        root.setContentsMargins(16, 16, 16, 16)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)

        title_box = QVBoxLayout()
        title = QLabel("🤖 Q-COLD BRAWL BOT")
        title.setObjectName("Title")
        version_label = QLabel(f"v{VERSION}")
        version_label.setObjectName("VersionLabel")
        title_box.addWidget(title)
        title_box.addWidget(version_label)
        top_layout.addLayout(title_box)
        top_layout.addStretch()

        session_box = QVBoxLayout()
        self.session_timer_label = QLabel("00:00:00")
        self.session_timer_label.setObjectName("TimerBig")
        self.session_timer_label.setAlignment(Qt.AlignCenter)
        session_caption = QLabel("Текущая сессия")
        session_caption.setObjectName("TimerLabel")
        session_caption.setAlignment(Qt.AlignCenter)
        session_box.addWidget(session_caption)
        session_box.addWidget(self.session_timer_label)
        top_layout.addLayout(session_box)

        top_layout.addSpacing(30)

        total_box = QVBoxLayout()
        self.total_timer_label = QLabel("00:00:00")
        self.total_timer_label.setObjectName("TimerBig")
        self.total_timer_label.setAlignment(Qt.AlignCenter)
        total_caption = QLabel("Общее время работы")
        total_caption.setObjectName("TimerLabel")
        total_caption.setAlignment(Qt.AlignCenter)
        total_box.addWidget(total_caption)
        total_box.addWidget(self.total_timer_label)
        top_layout.addLayout(total_box)

        top_layout.addSpacing(30)

        matches_box = QVBoxLayout()
        self.total_matches_label = QLabel("0")
        self.total_matches_label.setObjectName("TimerBig")
        self.total_matches_label.setAlignment(Qt.AlignCenter)
        matches_caption = QLabel("Матчей всего")
        matches_caption.setObjectName("TimerLabel")
        matches_caption.setAlignment(Qt.AlignCenter)
        matches_box.addWidget(matches_caption)
        matches_box.addWidget(self.total_matches_label)
        top_layout.addLayout(matches_box)

        top_layout.addSpacing(30)

        self.pause_all_btn = QPushButton("⏸ Пауза всех")
        self.pause_all_btn.clicked.connect(self.on_pause_all)
        top_layout.addWidget(self.pause_all_btn)

        self.resume_all_btn = QPushButton("▶ Продолжить всех")
        self.resume_all_btn.setObjectName("Primary")
        self.resume_all_btn.clicked.connect(self.on_resume_all)
        top_layout.addWidget(self.resume_all_btn)

        root.addWidget(top_bar)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.cards = {}
        for i in range(1, MAX_WINDOWS + 1):
            wid = f"Окно #{i}"
            card = WindowCard(self.engine, wid, on_renamed=self._on_window_renamed)
            self.cards[wid] = card
            cards_row.addWidget(card)
        root.addLayout(cards_row)

        self.stats_panel = StatsPanel(self.engine)
        root.addWidget(self.stats_panel)

        self.telegram_panel = TelegramPanel(self.engine)
        root.addWidget(self.telegram_panel)

        self.settings_panel = SettingsPanel(self.engine)
        root.addWidget(self.settings_panel)

        root.addStretch()

        if self.engine.adb_error:
            QMessageBox.warning(
                self, "ADB недоступен",
                f"Не удалось подключиться к ADB-серверу:\n{self.engine.adb_error}\n\n"
                "Убедитесь, что LDPlayer запущен, а adb-сервер поднят. "
                "Программа продолжит попытки подключения автоматически."
            )

        self.engine.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start(500)

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.stats_panel.refresh)
        self.stats_timer.start(10000)

    def _on_window_renamed(self):
        self.stats_panel.on_window_renamed()

    def on_pause_all(self):
        for wid in self.cards:
            snap = self.engine.get_snapshot(wid)
            if snap and not snap["paused"]:
                self.engine.toggle_pause(wid)

    def on_resume_all(self):
        for wid in self.cards:
            snap = self.engine.get_snapshot(wid)
            if snap and snap["paused"]:
                self.engine.toggle_pause(wid)

    def refresh_ui(self):
        self.session_timer_label.setText(self.engine.session_uptime_str())
        self.total_timer_label.setText(self.engine.total_uptime_str())
        self.total_matches_label.setText(str(self.engine.total_matches()))
        for card in self.cards.values():
            card.refresh()

    def closeEvent(self, event):
        self.engine.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)

    from settings_store import SettingsStore
    from auto_update import get_exe_dir
    settings_path = os.path.join(get_exe_dir(), "settings.json")
    settings = SettingsStore(settings_path)

    if check_updates_on_startup(settings):
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
