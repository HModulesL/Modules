# requires: aiohttp
# scope: hikka_only
# meta name: qrlink
# meta developer: @ItzNeedlemouseNB
# meta version: 1.1.1

from io import BytesIO
from urllib.parse import quote, urlparse

import aiohttp
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class QRLinkGeneratorMod(loader.Module):
    """Генерирует QR-код по ссылке и читает QR-коды из изображений."""

    strings = {
        "name": "qrlink",
        "no_link": "<b>Укажи ссылку в команде или ответь на сообщение со ссылкой.</b>",
        "invalid_link": "<b>Это не похоже на корректную ссылку.</b>",
        "processing": "<b>Генерирую QR-код...</b>",
        "caption": "<b>QR-код для:</b> <code>{}</code>",
        "gen_error": "<b>Не удалось сгенерировать QR-код.</b>",
        "no_qr_reply": "<b>Ответь на сообщение с изображением или файлом, содержащим QR-код.</b>",
        "read_processing": "<b>Считываю QR-код...</b>",
        "read_error": "<b>Не удалось прочитать QR-код.</b>",
        "qr_not_found": "<b>QR-код не найден или не содержит читаемых данных.</b>",
        "qr_result": "<b>Содержимое QR-кода:</b>\n<code>{}</code>",
    }

    strings_ru = {
        "no_link": "<b>Укажи ссылку в команде или ответь на сообщение со ссылкой.</b>",
        "invalid_link": "<b>Это не похоже на корректную ссылку.</b>",
        "processing": "<b>Генерирую QR-код...</b>",
        "caption": "<b>QR-код для:</b> <code>{}</code>",
        "gen_error": "<b>Не удалось сгенерировать QR-код.</b>",
        "no_qr_reply": "<b>Ответь на сообщение с изображением или файлом, содержащим QR-код.</b>",
        "read_processing": "<b>Считываю QR-код...</b>",
        "read_error": "<b>Не удалось прочитать QR-код.</b>",
        "qr_not_found": "<b>QR-код не найден или не содержит читаемых данных.</b>",
        "qr_result": "<b>Содержимое QR-кода:</b>\n<code>{}</code>",
    }

    author = "@HModulesL, @ItzNeedlemouseNB"

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    def _extract_url(self, text: str) -> str:
        if not text:
            return ""

        candidate = text.strip().split()[0].strip()
        if candidate.startswith("www."):
            candidate = f"https://{candidate}"

        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate

        return ""

    async def _get_link(self, message: Message) -> str:
        args = utils.get_args_raw(message)
        if args:
            link = self._extract_url(args)
            if link:
                return link

        reply = await message.get_reply_message()
        if not reply:
            return ""

        sources = []
        if getattr(reply, "raw_text", None):
            sources.append(reply.raw_text)
        if getattr(reply, "message", None):
            sources.append(reply.message)

        entities = getattr(reply, "entities", None) or []
        for entity in entities:
            url = getattr(entity, "url", None)
            if url:
                sources.append(url)

        for source in sources:
            link = self._extract_url(source)
            if link:
                return link

        return ""

    async def _build_qr_link(self, link: str) -> str:
        return f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&format=png&data={quote(link, safe='')}"

    async def _download_qr_image(self, link: str) -> BytesIO:
        qr_url = await self._build_qr_link(link)
        async with aiohttp.ClientSession() as session:
            async with session.get(qr_url) as resp:
                if resp.status != 200:
                    return None

                data = await resp.read()

        if not data:
            return None

        file = BytesIO(data)
        file.name = "qrcode.png"
        file.seek(0)
        return file

    async def _read_qr_from_bytes(self, data: bytes) -> str:
        form = aiohttp.FormData()
        form.add_field("file", data, filename="qr.png", content_type="application/octet-stream")

        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.qrserver.com/v1/read-qr-code/", data=form) as resp:
                if resp.status != 200:
                    return ""

                payload = await resp.json(content_type=None)

        if not isinstance(payload, list) or not payload:
            return ""

        first = payload[0] if isinstance(payload[0], dict) else {}
        symbols = first.get("symbol") or []
        if not symbols or not isinstance(symbols[0], dict):
            return ""

        symbol = symbols[0]
        if symbol.get("error"):
            return ""

        return symbol.get("data") or ""

    @loader.command(
        ru_doc="<ссылка> — Сгенерировать QR-код по ссылке из аргументов или из replied-сообщения",
        en_doc="<link> — Generate a QR code from a link in arguments or from a replied message",
    )
    async def qr(self, message: Message):
        """<link> - Generate a QR code from a link in arguments or from a replied message"""
        link = await self._get_link(message)
        if not link:
            await utils.answer(message, self.strings("no_link"))
            return

        if not self._extract_url(link):
            await utils.answer(message, self.strings("invalid_link"))
            return

        status = await utils.answer(message, self.strings("processing"))

        try:
            qr_file = await self._download_qr_image(link)
            if not qr_file:
                await utils.answer(status, self.strings("gen_error"))
                return

            await message.client.send_file(
                message.peer_id,
                qr_file,
                caption=self.strings("caption").format(utils.escape_html(link)),
                reply_to=message.reply_to_msg_id,
                force_document=False,
            )
        except Exception:
            await utils.answer(status, self.strings("gen_error"))
            return

        await status.delete()

    @loader.command(
        ru_doc="— Считать QR-код из replied-изображения или файла",
        en_doc="— Read a QR code from a replied image or file",
    )
    async def rq(self, message: Message):
        """Read a QR code from a replied image or file"""
        reply = await message.get_reply_message()
        if not reply or not getattr(reply, "media", None):
            await utils.answer(message, self.strings("no_qr_reply"))
            return

        status = await utils.answer(message, self.strings("read_processing"))

        try:
            data = await message.client.download_media(reply, file=bytes)
            if isinstance(data, bytearray):
                data = bytes(data)

            if not data or not isinstance(data, (bytes, bytearray)):
                await utils.answer(status, self.strings("read_error"))
                return

            result = await self._read_qr_from_bytes(data)
            if not result:
                await utils.answer(status, self.strings("qr_not_found"))
                return

            await utils.answer(status, self.strings("qr_result").format(utils.escape_html(result)))
        except Exception:
            await utils.answer(status, self.strings("read_error"))