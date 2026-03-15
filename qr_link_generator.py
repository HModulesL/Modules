# requires: qrcode[pil]
# scope: hikka_only
# meta name: qrlink
# meta developer: @ItzNeedlemouseNB
# meta version: 1.0.0

from io import BytesIO
from urllib.parse import urlparse

import qrcode
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class QRLinkGeneratorMod(loader.Module):
    """Генерирует QR-код по ссылке."""

    strings = {
        "name": "qrlink",
        "no_link": "<b>Укажи ссылку в команде или ответь на сообщение со ссылкой.</b>",
        "invalid_link": "<b>Это не похоже на корректную ссылку.</b>",
        "processing": "<b>Генерирую QR-код...</b>",
        "caption": "<b>QR-код для:</b> <code>{}</code>",
        "gen_error": "<b>Не удалось сгенерировать QR-код.</b>",
    }

    strings_ru = {
        "no_link": "<b>Укажи ссылку в команде или ответь на сообщение со ссылкой.</b>",
        "invalid_link": "<b>Это не похоже на корректную ссылку.</b>",
        "processing": "<b>Генерирую QR-код...</b>",
        "caption": "<b>QR-код для:</b> <code>{}</code>",
        "gen_error": "<b>Не удалось сгенерировать QR-код.</b>",
    }

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

    async def _build_qr(self, link: str) -> BytesIO:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(link)
        qr.make(fit=True)

        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.name = "qr.png"
        buffer.seek(0)
        return buffer

    @loader.command(
        ru_doc="<ссылка> — Сгенерировать QR-код по ссылке из аргументов или из replied-сообщения",
        en_doc="<link> — Generate a QR code from a link in arguments or from a replied message",
    )
    async def qrlink(self, message: Message):
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
            qr_file = await self._build_qr(link)
            await message.client.send_file(
                message.peer_id,
                qr_file,
                caption=self.strings("caption").format(utils.escape_html(link)),
                reply_to=message.reply_to_msg_id,
            )
        except Exception:
            await utils.answer(status, self.strings("gen_error"))
            return

        await status.delete()