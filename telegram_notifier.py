"""
Отправка уведомлений в Telegram.
"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request


class TelegramNotifier:
    """Потокобезопасная отправка сообщений в Telegram."""

    EVENT_LABELS = {
        "bot_started": "🟢 Бот запущен",
        "bot_stopped": "🔴 Бот остановлен",
        "prime_upgraded": "💎 Прайм улучшен",
        "afk_kick": "⚠️ АФК-кик",
        "reconnect": "📡 Переподключение",
        "game_crash": "💥 Вылет игры",
        "fatal_error": "❌ Критическая ошибка",
    }

    def __init__(self, enabled=False, token="", chat_id=""):
        self._lock = threading.Lock()
        self.enabled = bool(enabled)
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()

    def configure(self, enabled=None, token=None, chat_id=None):
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)
            if token is not None:
                self.token = (token or "").strip()
            if chat_id is not None:
                self.chat_id = str(chat_id or "").strip()

    def is_configured(self):
        with self._lock:
            return self.enabled and bool(self.token) and bool(self.chat_id)

    def _send_sync(self, text):
        with self._lock:
            if not self.enabled or not self.token or not self.chat_id:
                return False, "Telegram отключён или не настроен"
            token = self.token
            chat_id = self.chat_id

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("ok"):
                return True, "Сообщение отправлено"
            return False, body.get("description", "Неизвестная ошибка Telegram")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("description", str(exc))
            except Exception:
                detail = str(exc)
            return False, detail
        except Exception as exc:
            return False, str(exc)

    def send_async(self, text):
        """Отправка в фоновом потоке, не блокирует бота."""
        if not self.is_configured():
            return
        threading.Thread(target=self._send_sync, args=(text,), daemon=True).start()

    def notify(self, event_key, details=""):
        """Уведомление о событии с опциональными деталями."""
        label = self.EVENT_LABELS.get(event_key, event_key)
        text = f"<b>{label}</b>"
        if details:
            text += f"\n{details}"
        self.send_async(text)

    def test_connection(self):
        """Синхронная проверка — для кнопки «Тест» в настройках."""
        return self._send_sync("✅ Тестовое сообщение от Q-Cold Brawl Bot")
