# requires:
# scope: hikka_only
# meta name: FunStatFarm
# meta developer: @ItzNeedlemouseNB
# meta version: 1.1.1

from .. import loader, utils
from telethon.tl.types import Message
import asyncio
import contextlib
from datetime import datetime


@loader.tds
class FunStatFarmMod(loader.Module):
    """Модуль для фарма в фанстате."""

    strings = {
        "name": "FunStatFarm",
        "already_active": "ℹ️ Фарм уже активен. Используйте <code>.stopfs</code> для остановки.",
        "not_active": "ℹ️ Фарм не активен.",
        "stopped": "✅ Фарм FunStat остановлен.",
        "started": "✅ Фарм FunStat запущен. Отправлена первая команда <code>/rand</code> боту <code>{}</code>.",
        "search_error": "🚫 <b>Ошибка:</b> Не удалось получить ID бота <code>{}</code>. Убедитесь, что бот существует и доступен.",
        "target_error": "🚫 <b>Ошибка:</b> Не удалось получить ID бота <code>{}</code>. Убедитесь, что бот существует и доступен.",
        "first_send_error": "❌ <b>Ошибка при отправке первого запроса боту {}</b>: <code>{}</code>. Фарм не запущен.",
        "next_send_error": "❌ <b>Ошибка при отправке следующего запроса боту {}</b>: <code>{}</code>. Фарм остановлен.",
        "forward_error": "❌ <b>Ошибка при отправке сообщения боту {}</b>: <code>{}</code>. Фарм остановлен.",
        "runtime_error": "❌ <b>Фарм остановлен из-за ошибки:</b> <code>{}</code>",
        "status": (
            "<b>FunStat Farm — статус</b>\n\n"
            "<b>Состояние:</b> {}\n"
            "<b>Бот поиска:</b> <code>{}</code>\n"
            "<b>Целевой бот:</b> <code>{}</code>\n"
            "<b>Задержка:</b> <code>{}</code> сек.\n"
            "<b>Аптайм текущей сессии:</b> <code>{}</code>\n\n"
            "<b>Отправлено /rand:</b> <code>{}</code>\n"
            "<b>Получено ответов:</b> <code>{}</code>\n"
            "<b>Переслано сообщений:</b> <code>{}</code>\n"
            "<b>Пустых ответов:</b> <code>{}</code>\n"
            "<b>Ошибок:</b> <code>{}</code>\n"
            "<b>Последний /rand:</b> <code>{}</code>\n"
            "<b>Последняя пересылка:</b> <code>{}</code>\n"
            "<b>Последняя ошибка:</b> <code>{}</code>"
        ),
    }

    strings_ru = strings

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "search_bot_username",
                "@en_SearchBot",
                "Юзернейм бота для поиска каналов/чатов.",
            ),
            loader.ConfigValue(
                "target_bot_username",
                "@JDHXYU_bot",
                "Юзернейм бота, куда будут пересылаться найденные ссылки FunStat.",
            ),
            loader.ConfigValue(
                "farm_delay",
                10,
                "Задержка между циклами фарма в секундах.",
                validator=loader.validators.Integer(minimum=1, maximum=3600),
            ),
        )
        self.client = None
        self.db = None
        self.is_farming_active = False
        self.reply_chat_id = None
        self.search_bot_id = None
        self.target_bot_id = None
        self._farm_task = None
        self._session_started_at = None

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        await self._refresh_entities()
        self.is_farming_active = False
        self.reply_chat_id = None
        self._farm_task = None
        self._session_started_at = None

    async def _refresh_entities(self):
        try:
            search_bot_entity = await self.client.get_entity(self.config["search_bot_username"])
            self.search_bot_id = search_bot_entity.id
        except Exception:
            self.search_bot_id = None

        try:
            target_bot_entity = await self.client.get_entity(self.config["target_bot_username"])
            self.target_bot_id = target_bot_entity.id
        except Exception:
            self.target_bot_id = None

    def _get_stat(self, key, default=0):
        return self.db.get(self.strings["name"], key, default)

    def _set_stat(self, key, value):
        self.db.set(self.strings["name"], key, value)

    def _inc_stat(self, key, step=1):
        self._set_stat(key, self._get_stat(key, 0) + step)

    def _set_last_error(self, text):
        self._set_stat("last_error", text)
        self._inc_stat("errors")

    def _format_dt(self, value):
        if not value:
            return "—"
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "—"

    def _format_duration(self, seconds):
        seconds = int(max(seconds, 0))
        hours, rem = divmod(seconds, 3600)
        minutes, sec = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"

    async def _notify(self, text):
        if not self.reply_chat_id:
            return
        with contextlib.suppress(Exception):
            await self.client.send_message(self.reply_chat_id, text)

    async def _send_rand(self):
        await self.client.send_message(self.search_bot_id, "/rand")
        self._inc_stat("rand_sent")
        self._set_stat("last_rand_at", int(datetime.now().timestamp()))

    async def _forward_payload(self, payload):
        await self.client.send_message(self.target_bot_id, payload)
        self._inc_stat("forwarded")
        self._set_stat("last_forward_at", int(datetime.now().timestamp()))

    async def _farm_loop(self):
        try:
            while self.is_farming_active:
                await self._send_rand()
                await asyncio.sleep(self.config["farm_delay"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._set_last_error(str(e))
            await self._notify(self.strings["runtime_error"].format(utils.escape_html(str(e))))
            self.is_farming_active = False
            self.reply_chat_id = None
            self._farm_task = None

    @loader.unrestricted
    @loader.command(ru_doc="Запустить фарм FunStat.", en_doc="Start FunStat farming.")
    async def farmfs(self, message: Message):
        """Запустить фарм FunStat без аргументов."""
        if self.is_farming_active:
            await utils.answer(message, self.strings["already_active"])
            return

        await self._refresh_entities()

        if not self.search_bot_id:
            await utils.answer(message, self.strings["search_error"].format(self.config["search_bot_username"]))
            return

        if not self.target_bot_id:
            await utils.answer(message, self.strings["target_error"].format(self.config["target_bot_username"]))
            return

        self.is_farming_active = True
        self.reply_chat_id = message.chat_id
        self._session_started_at = datetime.now().timestamp()
        self._farm_task = asyncio.create_task(self._farm_loop())

        await utils.answer(message, self.strings["started"].format(self.config["search_bot_username"]))

    @loader.unrestricted
    @loader.command(ru_doc="Остановить фарм FunStat.", en_doc="Stop FunStat farming.")
    async def stopfs(self, message: Message):
        """Остановить фарм FunStat без аргументов."""
        if not self.is_farming_active:
            await utils.answer(message, self.strings["not_active"])
            return

        self.is_farming_active = False
        self.reply_chat_id = None
        if self._farm_task:
            self._farm_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._farm_task
        self._farm_task = None
        await utils.answer(message, self.strings["stopped"])

    @loader.unrestricted
    @loader.command(ru_doc="Показать статистику модуля FunStat.", en_doc="Show FunStat module statistics.")
    async def fsstatus(self, message: Message):
        """Показать статистику модуля без аргументов."""
        started = self._session_started_at or 0
        uptime = self._format_duration(datetime.now().timestamp() - started) if started and self.is_farming_active else "00:00:00"
        await utils.answer(
            message,
            self.strings["status"].format(
                "🟢 Активен" if self.is_farming_active else "🔴 Остановлен",
                self.config["search_bot_username"],
                self.config["target_bot_username"],
                self.config["farm_delay"],
                uptime,
                self._get_stat("rand_sent", 0),
                self._get_stat("responses_received", 0),
                self._get_stat("forwarded", 0),
                self._get_stat("empty_responses", 0),
                self._get_stat("errors", 0),
                self._format_dt(self._get_stat("last_rand_at", 0)),
                self._format_dt(self._get_stat("last_forward_at", 0)),
                utils.escape_html(self._get_stat("last_error", "—")),
            ),
        )

    @loader.raw_handler()
    async def watcher(self, message):
        if not self.is_farming_active or not self.search_bot_id:
            return

        if getattr(message, "sender_id", None) != self.search_bot_id:
            return

        self._inc_stat("responses_received")

        if not self.target_bot_id:
            self._set_last_error(f"Target bot ID not found: {self.config['target_bot_username']}")
            await self._notify(self.strings["target_error"].format(self.config["target_bot_username"]))
            self.is_farming_active = False
            self.reply_chat_id = None
            if self._farm_task:
                self._farm_task.cancel()
                self._farm_task = None
            return

        channel_link_message_text = getattr(message, "text", None)
        if not channel_link_message_text:
            self._inc_stat("empty_responses")
            return

        try:
            await self._forward_payload(channel_link_message_text)
        except Exception as e:
            self._set_last_error(str(e))
            await self._notify(
                self.strings["forward_error"].format(
                    self.config["target_bot_username"],
                    utils.escape_html(str(e)),
                )
            )
            self.is_farming_active = False
            self.reply_chat_id = None
            if self._farm_task:
                self._farm_task.cancel()
                self._farm_task = None