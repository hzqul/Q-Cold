"""
updater.py — отдельный процесс обновления Q-Cold Brawl Bot.

Сборка: python build_nuitka.py (создаёт updater.exe)

Запуск:
    updater.exe --url <download_url> --pid <bot_pid> --target <path_to_bot_exe>
"""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF
WAIT_FAILED = 0xFFFFFFFF


def wait_for_process(pid):
    """Ожидает завершения процесса по PID (Windows)."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    try:
        result = kernel32.WaitForSingleObject(handle, INFINITE)
        return result != WAIT_FAILED
    finally:
        kernel32.CloseHandle(handle)


def download_file(url, dest_path, progress_callback):
    """Скачивает файл с отображением прогресса."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Q-Cold-Brawl-Bot-Updater/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length", 0) or 0)
        downloaded = 0
        chunk_size = 64 * 1024
        with open(dest_path, "wb") as output:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress_callback(int(downloaded * 100 / total), downloaded, total)
                else:
                    progress_callback(-1, downloaded, 0)
        progress_callback(100, downloaded, total)


class UpdateWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, url, pid, target_path):
        super().__init__()
        self.url = url
        self.pid = int(pid)
        self.target_path = target_path

    def run(self):
        try:
            self.progress.emit(0, "Ожидание завершения бота...")
            if not wait_for_process(self.pid):
                self.finished.emit(False, f"Не удалось дождаться процесса PID {self.pid}")
                return

            self.progress.emit(0, "Загрузка обновления...")
            temp_dir = tempfile.mkdtemp(prefix="qcold_update_")
            temp_exe = os.path.join(temp_dir, "Q-Cold_Brawl_Bot_new.exe")

            def on_progress(percent, downloaded, total):
                if percent >= 0:
                    if total > 0:
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        self.progress.emit(
                            percent,
                            f"Загрузка: {percent}% ({mb_done:.1f} / {mb_total:.1f} МБ)",
                        )
                    else:
                        self.progress.emit(percent, f"Загрузка: {percent}%")
                else:
                    mb_done = downloaded / (1024 * 1024)
                    self.progress.emit(0, f"Загрузка: {mb_done:.1f} МБ...")

            download_file(self.url, temp_exe, on_progress)

            self.progress.emit(100, "Установка обновления...")
            target_dir = os.path.dirname(os.path.abspath(self.target_path))
            os.makedirs(target_dir, exist_ok=True)

            backup_path = self.target_path + ".bak"
            if os.path.isfile(self.target_path):
                if os.path.isfile(backup_path):
                    os.remove(backup_path)
                os.replace(self.target_path, backup_path)

            shutil.move(temp_exe, self.target_path)

            self.progress.emit(100, "Запуск обновлённого бота...")
            subprocess.Popen(
                [self.target_path],
                cwd=target_dir,
                close_fds=False,
            )

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

            self.finished.emit(True, "Обновление завершено успешно")
        except urllib.error.URLError as exc:
            self.finished.emit(False, f"Ошибка загрузки: {exc}")
        except OSError as exc:
            self.finished.emit(False, f"Ошибка файловой системы: {exc}")
        except Exception as exc:
            self.finished.emit(False, f"Неожиданная ошибка: {exc}")


class UpdaterWindow(QWidget):
    def __init__(self, url, pid, target_path):
        super().__init__()
        self.setWindowTitle("Q-Cold — Обновление")
        self.setFixedSize(460, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.status_label = QLabel("Подготовка...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.worker = UpdateWorker(url, pid, target_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, percent, message):
        self.status_label.setText(message)
        if percent >= 0:
            self.progress_bar.setValue(min(100, percent))

    def _on_finished(self, success, message):
        if success:
            self.status_label.setText(message)
            self.progress_bar.setValue(100)
            QApplication.instance().quit()
        else:
            QMessageBox.critical(self, "Ошибка обновления", message)
            QApplication.instance().quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Q-Cold Brawl Bot Updater")
    parser.add_argument("--url", required=True, help="URL загрузки нового exe")
    parser.add_argument("--pid", required=True, type=int, help="PID процесса бота")
    parser.add_argument("--target", required=True, help="Путь к Q-Cold_Brawl_Bot.exe")
    return parser.parse_args()


def main():
    args = parse_args()
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: #141014;
            color: #f2e6e8;
            font-family: 'Segoe UI', Arial;
            font-size: 13px;
        }
        QProgressBar {
            border: 1px solid #4a353b;
            border-radius: 6px;
            background-color: #2c2024;
            text-align: center;
            color: #f2e6e8;
            height: 22px;
        }
        QProgressBar::chunk {
            background-color: #c62b3a;
            border-radius: 5px;
        }
    """)
    window = UpdaterWindow(args.url, args.pid, args.target)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
