# scope: hikka_only
# meta name: FynoraStorageUploader
# meta developer: @BModulesL
# meta version: 1.0.3
import asyncio

from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class FynoraStorageUploader(loader.Module):
    strings = {
        "name": "FynoraStorageUploader",
        "no_reply": "<b>Ответь на файл, фото, видео или другое медиа.</b>",
        "no_media": "<b>В реплае нет файла или медиа для отправки.</b>",
        "uploading": "<b>Отправляю файл в</b> <code>@fynora_storage_bot</code><b>...</b>",
        "waiting": "<b>Файл отправлен. Жду 3 секунды перед получением ссылки от</b> <code>@fynora_storage_bot</code><b>...</b>",
        "success": "<b>Ссылка:</b> {link}",
        "bot_unavailable": "<b>Не удалось связаться с</b> <code>@fynora_storage_bot</code><b>.</b>",
        "link_not_found": "<b>Бот ответил, но ссылка не найдена.</b>",
        "timeout": "<b>Бот не прислал ответ вовремя.</b>",
        "failed": "<b>Ошибка:</b> <code>{error}</code>",
    }

    strings_ru = strings
    authors = ("@HModulesL", "@Napstablook23", "@bsod4ik_plugins", "@bsod4ik")

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    async def _extract_link(self, text: str) -> str:
        if not text:
            return ""

        parts = text.replace("\n", " ").split()
        for part in parts:
            if part.startswith("http://") or part.startswith("https://"):
                return part.strip()

        return ""

    async def _extract_link_from_message(self, msg) -> str:
        link = await self._extract_link(msg.raw_text or "")
        if link:
            return link

        if msg.buttons:
            for row in msg.buttons:
                for button in row:
                    url = getattr(button, "url", None)
                    if url:
                        return url

        return ""

    async def _wait_bot_answer(self, chat_id: int, min_id: int, timeout: int = 120):
        async def _check(event):
            return getattr(event, "chat_id", None) == chat_id and getattr(event.message, "id", 0) > min_id

        return await self.client.wait_event(
            loader.events.NewMessage(chats=[chat_id], incoming=True, func=_check),
            timeout=timeout,
        )

    async def _scan_recent_bot_messages(self, bot, min_id: int, limit: int = 2) -> str:
        scanned = []
        async for hist_msg in self.client.iter_messages(bot, limit=limit, min_id=min_id):
            scanned.append(hist_msg)

        scanned.reverse()

        for hist_msg in scanned:
            link = await self._extract_link_from_message(hist_msg)
            if link:
                return link

        return ""

    @loader.command(ru_doc="Отправляет медиа в облако @fynora_storage_bot и получает ссылку оттуда", en_doc="Sends media to the @fynora_storage_bot cloud and gets a link from there")
    async def fynupcmd(self, message: Message):
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings("no_reply"))
            return

        if not reply.media and not getattr(reply, "file", None):
            await utils.answer(message, self.strings("no_media"))
            return

        status = await utils.answer(message, self.strings("uploading"))

        try:
            bot = await self.client.get_entity("@fynora_storage_bot")
        except Exception:
            await utils.answer(status, self.strings("bot_unavailable"))
            return

        try:
            async with self.client.conversation(bot, timeout=120) as conv:
                last_outgoing_id = 0
                async for msg in self.client.iter_messages(bot, limit=1):
                    last_outgoing_id = msg.id
                    break

                await conv.send_file(reply)

                await utils.answer(status, self.strings("waiting"))
                await asyncio.sleep(3)

                link = await self._scan_recent_bot_messages(bot, last_outgoing_id, limit=2)

                if not link:
                    response = await conv.get_response()
                    link = await self._extract_link_from_message(response)

                if not link:
                    link = await self._scan_recent_bot_messages(bot, last_outgoing_id, limit=2)

                if not link:
                    await utils.answer(status, self.strings("link_not_found"))
                    return

                await utils.answer(status, self.strings("success").format(link=link))
        except TimeoutError:
            await utils.answer(status, self.strings("timeout"))
        except Exception as e:
            await utils.answer(status, self.strings("failed").format(error=utils.escape_html(str(e))))
