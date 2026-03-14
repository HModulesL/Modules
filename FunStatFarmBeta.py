# requires: aiohttp
# scope: hikka_only
# meta name: FunStatFarm
# meta developer: @ItzNeedlemouseNB
# meta version: 1.3.0

from .. import loader, utils
from telethon.tl.types import Message
import asyncio
import contextlib
from datetime import datetime
import aiohttp


@loader.tds
class FunStatFarmMod(loader.Module):
    """Модуль для фарма в FunStat с двумя режимами генерации запросов: стандартный /rand и ChatGPT-режим со случайными словами на выбранном языке."""

    strings = {
        "name": "FunStatFarm",
        "already_active": "ℹ️ Фарм уже активен. Используйте <code>.stopfs</code> для остановки.",
        "not_active": "ℹ️ Фарм не активен.",
        "stopped": "✅ Фарм FunStat остановлен.",
        "started": "✅ Фарм FunStat запущен в режиме <code>{}</code>. Бот поиска: <code>{}</code>.",
        "search_error": "🚫 <b>Ошибка:</b> Не удалось получить ID бота <code>{}</code>. Убедитесь, что бот существует и доступен.",
        "target_error": "🚫 <b>Ошибка:</b> Не удалось получить ID бота <code>{}</code>. Убедитесь, что бот существует и доступен.",
        "runtime_error": "❌ <b>Фарм остановлен из-за ошибки:</b> <code>{}</code>",
        "mode_set": "✅ Режим фарма установлен: <code>{}</code>",
        "invalid_mode": "🚫 <b>Неверный режим.</b> Доступно: <code>rand</code>, <code>chatgpt</code>",
        "chatgpt_key_missing": "🚫 <b>ChatGPT API key не указан.</b> Укажите его в конфиге <code>chatgpt_api_key</code>.",
        "chatgpt_error": "❌ <b>Ошибка ChatGPT:</b> <code>{}</code>",
        "language_set": "✅ Язык ChatGPT установлен: <code>{}</code>",
        "invalid_language": (
            "🚫 <b>Неверный язык.</b> Доступно: <code>ru</code>, <code>en</code>, <code>ar</code>, "
            "<code>zh</code>, <code>ja</code>, <code>pt-br</code>, <code>de</code>"
        ),
        "status": (
            "<b>FunStat Farm — статус</b>\n\n"
            "<b>Состояние:</b> {}\n"
            "<b>Режим:</b> <code>{}</code>\n"
            "<b>Язык ChatGPT:</b> <code>{}</code>\n"
            "<b>Бот поиска:</b> <code>{}</code>\n"
            "<b>Целевой бот:</b> <code>{}</code>\n"
            "<b>Задержка:</b> <code>{}</code> сек.\n"
            "<b>Аптайм текущей сессии:</b> <code>{}</code>\n\n"
            "<b>Отправлено запросов:</b> <code>{}</code>\n"
            "<b>Получено ответов:</b> <code>{}</code>\n"
            "<b>Переслано сообщений:</b> <code>{}</code>\n"
            "<b>Пустых ответов:</b> <code>{}</code>\n"
            "<b>Ошибок:</b> <code>{}</code>\n"
            "<b>Последний запрос:</b> <code>{}</code>\n"
            "<b>Последняя пересылка:</b> <code>{}</code>\n"
            "<b>Последнее слово ChatGPT:</b> <code>{}</code>\n"
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
            loader.ConfigValue(
                "farm_mode",
                "rand",
                "Режим фарма: rand или chatgpt.",
                validator=loader.validators.Choice(["rand", "chatgpt"]),
            ),
            loader.ConfigValue(
                "chatgpt_api_key",
                "none",
                "API key для ChatGPT/OpenAI-compatible API.",
                validator=loader.validators.String(min_len=1, max_len=512),
            ),
            loader.ConfigValue(
                "chatgpt_api_base",
                "https://api.openai.com/v1",
                "Базовый URL ChatGPT/OpenAI-compatible API.",
                validator=loader.validators.String(min_len=8, max_len=256),
            ),
            loader.ConfigValue(
                "chatgpt_model",
                "gpt-4o-mini",
                "Модель ChatGPT/OpenAI-compatible API.",
                validator=loader.validators.String(min_len=1, max_len=128),
            ),
            loader.ConfigValue(
                "chatgpt_language",
                "ru",
                "Язык случайных слов для ChatGPT.",
                validator=loader.validators.Choice(["ru", "en", "ar", "zh", "ja", "pt-br", "de"]),
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
        self._language_names = {
            "ru": "Russian",
            "en": "English",
            "ar": "Arabic",
            "zh": "Chinese",
            "ja": "Japanese",
            "pt-br": "Brazilian Portuguese",
            "de": "German",
        }

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

    async def _get_chatgpt_word(self):
        api_key = self.config["chatgpt_api_key"].strip()
        if not api_key or api_key == "none":
            raise ValueError("ChatGPT API key is not configured")

        language_code = self.config["chatgpt_language"].strip().lower()
        language_name = self._language_names.get(language_code, "English")
        base_url = self.config["chatgpt_api_base"].strip().rstrip("/")
        model = self.config["chatgpt_model"].strip()
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate exactly one random common word with no extra text.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Return exactly one random common word in {language_name}. "
                        "Only one word, without punctuation, translation, explanation, quotes, emoji, or extra text."
                    ),
                },
            ],
            "temperature": 1.2,
            "max_tokens": 8,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                data = await response.json(content_type=None)
                if response.status != 200:
                    error = data.get("error", {}) if isinstance(data, dict) else {}
                    raise ValueError(error.get("message", f"HTTP {response.status}"))

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Empty ChatGPT response")

        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        if not text:
            raise ValueError("ChatGPT returned empty text")

        word = text.split()[0].strip("\n\r\t .,!?:;'\"`()[]{}<>|/\\")
        if not word:
            raise ValueError("ChatGPT returned invalid word")

        self._set_stat("last_chatgpt_word", word)
        return word

    async def _send_search_request(self):
        mode = self.config["farm_mode"]
        if mode == "rand":
            payload = "/rand"
        else:
            payload = await self._get_chatgpt_word()

        await self.client.send_message(self.search_bot_id, payload)
        self._inc_stat("rand_sent")
        self._set_stat("last_rand_at", int(datetime.now().timestamp()))

    async def _forward_payload(self, payload):
        await self.client.send_message(self.target_bot_id, payload)
        self._inc_stat("forwarded")
        self._set_stat("last_forward_at", int(datetime.now().timestamp()))

    async def _farm_loop(self):
        try:
            while self.is_farming_active:
                await self._send_search_request()
                await asyncio.sleep(self.config["farm_delay"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._set_last_error(str(e))
            error_text = self.strings["runtime_error"].format(utils.escape_html(str(e)))
            if self.config["farm_mode"] == "chatgpt":
                error_text += "\n" + self.strings["chatgpt_error"].format(utils.escape_html(str(e)))
            await self._notify(error_text)
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

        if self.config["farm_mode"] == "chatgpt":
            api_key = self.config["chatgpt_api_key"].strip()
            if not api_key or api_key == "none":
                await utils.answer(message, self.strings["chatgpt_key_missing"])
                return

        self.is_farming_active = True
        self.reply_chat_id = message.chat_id
        self._session_started_at = datetime.now().timestamp()
        self._farm_task = asyncio.create_task(self._farm_loop())

        await utils.answer(message, self.strings["started"].format(self.config["farm_mode"], self.config["search_bot_username"]))

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
                self.config["farm_mode"],
                self.config["chatgpt_language"],
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
                utils.escape_html(self._get_stat("last_chatgpt_word", "—")),
                utils.escape_html(self._get_stat("last_error", "—")),
            ),
        )

    @loader.unrestricted
    @loader.command(ru_doc="Установить режим фарма: <rand|chatgpt>.", en_doc="Set farm mode: <rand|chatgpt>.")
    async def fsmode(self, message: Message):
        """<rand|chatgpt> - Установить режим фарма."""
        args = utils.get_args_raw(message).strip().lower()
        if args not in {"rand", "chatgpt"}:
            await utils.answer(message, self.strings["invalid_mode"])
            return

        self.config["farm_mode"] = args
        await utils.answer(message, self.strings["mode_set"].format(args))

    @loader.unrestricted
    @loader.command(ru_doc="Установить язык ChatGPT: <ru|en|ar|zh|ja|pt-br|de>.", en_doc="Set ChatGPT language: <ru|en|ar|zh|ja|pt-br|de>.")
    async def fslang(self, message: Message):
        """<ru|en|ar|zh|ja|pt-br|de> - Установить язык ChatGPT."""
        args = utils.get_args_raw(message).strip().lower()
        if args not in {"ru", "en", "ar", "zh", "ja", "pt-br", "de"}:
            await utils.answer(message, self.strings["invalid_language"])
            return

        self.config["chatgpt_language"] = args
        await utils.answer(message, self.strings["language_set"].format(args))

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