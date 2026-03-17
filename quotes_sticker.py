# requires: aiohttp Pillow
# scope: hikka_only
# meta name: HQuotes
# meta developer: @ItzNeedlemouseNB
# meta version: 1.0.2

from __future__ import annotations

import asyncio
import html
import io
import math
import unicodedata
from typing import List, Optional, Tuple

from aiohttp import ClientSession
from PIL import Image, ImageDraw, ImageFont, ImageOps
from telethon.tl.types import Message

from .. import loader, utils


@loader.tds
class HQuotesMod(loader.Module):
    """Create neat quote stickers from replied messages."""

    strings = {
        "name": "HQuotes",
        "_cls_doc": "Create neat quote stickers from replied messages.",
        "no_reply": "<b>Reply to a message.</b>",
        "processing": "<i>Creating sticker...</i>",
        "failed": "<b>Failed to create sticker.</b>",
        "too_long": "<b>Text is too long to render.</b>",
    }

    strings_ru = {
        "_cls_doc": "Создание аккуратных quote-стикеров из сообщений.",
        "no_reply": "<b>Ответьте на сообщение.</b>",
        "processing": "<i>Создаю стикер...</i>",
        "failed": "<b>Не удалось создать стикер.</b>",
        "too_long": "<b>Текст слишком длинный для рендера.</b>",
    }

    strings_ja = {
        "_cls_doc": "返信したメッセージから見やすい引用ステッカーを作成します。",
        "no_reply": "<b>メッセージに返信してください。</b>",
        "processing": "<i>ステッカーを作成中...</i>",
        "failed": "<b>ステッカーを作成できませんでした。</b>",
        "too_long": "<b>テキストが長すぎて描画できません。</b>",
    }

    authors = ["@bsod4ik_plugins", "@bsod4ik"]
    author = "@ItzNeedlemouseNB"
    credits = ["@bsod4ik_plugins", "@bsod4ik"]
    creators = ["@bsod4ik_plugins", "@bsod4ik"]

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    @loader.command(
        ru_doc="Стикер-цитата из реплая",
        en_doc="Quote sticker from reply",
    )
    async def q(self, message: Message):
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings("no_reply"))
            return

        status = await utils.answer(message, self.strings("processing"))
        try:
            sticker = await self._build_sticker(reply, custom_text=None)
            await message.client.send_file(
                message.to_id,
                sticker,
                reply_to=reply.id if reply else None,
                force_document=False,
            )
            await status.delete()
            await message.delete()
        except Exception:
            await utils.answer(status, self.strings("failed"))

    @loader.command(
        ru_doc="Стикер-цитата со своим текстом",
        en_doc="Quote sticker with custom text",
    )
    async def fsq(self, message: Message):
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings("no_reply"))
            return

        custom_text = utils.get_args_raw(message)
        status = await utils.answer(message, self.strings("processing"))
        try:
            sticker = await self._build_sticker(reply, custom_text=custom_text or None)
            await message.client.send_file(
                message.to_id,
                sticker,
                reply_to=reply.id if reply else None,
                force_document=False,
            )
            await status.delete()
            await message.delete()
        except Exception:
            await utils.answer(status, self.strings("failed"))

    async def _build_sticker(self, reply: Message, custom_text: Optional[str] = None) -> io.BytesIO:
        sender = await reply.get_sender()
        display_name = self._get_display_name(sender, reply)
        text = self._extract_text(reply, custom_text)
        avatar = await self._get_avatar(reply)
        media_preview = await self._get_media_preview(reply)
        image = await asyncio.to_thread(self._render_quote, display_name, text, avatar, media_preview)

        output = io.BytesIO()
        output.name = "quote.webp"
        image.save(output, format="WEBP", lossless=True)
        output.seek(0)
        return output

    def _extract_text(self, reply: Message, custom_text: Optional[str]) -> str:
        if custom_text is not None and custom_text.strip():
            return self._normalize_text(custom_text).strip()

        parts = []
        if getattr(reply, "message", None):
            parts.append(self._normalize_text(reply.message))
        if getattr(reply, "media", None) and not parts:
            parts.append("📎 Медиа")

        result = "\n".join(p.strip() for p in parts if p and p.strip()).strip()
        return result or "…"

    def _get_display_name(self, sender, reply: Message) -> str:
        if sender:
            first = getattr(sender, "first_name", None) or ""
            last = getattr(sender, "last_name", None) or ""
            title = getattr(sender, "title", None) or ""
            full = " ".join(x for x in [first, last] if x).strip()
            if full:
                return self._normalize_text(html.unescape(full))
            if title:
                return self._normalize_text(html.unescape(title))
            username = getattr(sender, "username", None)
            if username:
                return self._normalize_text(f"@{username}")
        return "Unknown"

    async def _download_bytes(self, message: Message, thumb: bool = False) -> Optional[bytes]:
        try:
            data = await message.download_media(bytes, thumb=-1 if thumb else None)
            return data if isinstance(data, (bytes, bytearray)) else None
        except Exception:
            return None

    async def _get_avatar(self, reply: Message) -> Optional[Image.Image]:
        try:
            sender = await reply.get_sender()
            if not sender:
                return None
            buf = io.BytesIO()
            await self.client.download_profile_photo(sender, file=buf)
            raw = buf.getvalue()
            if not raw:
                return None
            return await asyncio.to_thread(self._open_image, raw)
        except Exception:
            return None

    async def _get_media_preview(self, reply: Message) -> Optional[Image.Image]:
        if not getattr(reply, "media", None):
            return None

        data = await self._download_bytes(reply)
        if data:
            image = await asyncio.to_thread(self._safe_open_media, data)
            if image:
                return image

        thumb = await self._download_bytes(reply, thumb=True)
        if thumb:
            image = await asyncio.to_thread(self._safe_open_media, thumb)
            if image:
                return image

        return None

    def _open_image(self, raw: bytes) -> Image.Image:
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        return image

    def _safe_open_media(self, raw: bytes) -> Optional[Image.Image]:
        try:
            return self._open_image(raw)
        except Exception:
            return None

    def _get_font_candidates(self, bold: bool = False) -> List[str]:
        common_bold = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.otf",
            "/usr/share/fonts/truetype/noto/NotoSerifJP-Bold.otf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansJP-Bold.otf",
            "/usr/share/fonts/opentype/noto/NotoSerifJP-Bold.otf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansHebrew-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArmenian-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansGeorgian-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/noto/NotoEmoji-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            "/System/Library/Fonts/Apple Color Emoji.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/NotoSans-Bold.ttf",
            "/Library/Fonts/Noto Sans CJK JP.ttc",
            "/Library/Fonts/Noto Serif CJK JP.ttc",
            "/Library/Fonts/Osaka.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/seguisb.ttf",
            "C:/Windows/Fonts/seguiemj.ttf",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/malgunbd.ttf",
            "C:/Windows/Fonts/NirmalaB.ttf",
            "C:/Windows/Fonts/LeelawUIB.ttf",
            "C:/Windows/Fonts/seguisym.ttf",
            "C:/Windows/Fonts/NotoSans-Bold.ttf",
        ]
        common_regular = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.otf",
            "/usr/share/fonts/truetype/noto/NotoSerifJP-Regular.otf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArmenian-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansGeorgian-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
            "/usr/share/fonts/opentype/noto/NotoSerifJP-Regular.otf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Apple Color Emoji.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/Library/Fonts/NotoSans-Regular.ttf",
            "/Library/Fonts/Noto Sans CJK JP.ttc",
            "/Library/Fonts/Noto Serif CJK JP.ttc",
            "/Library/Fonts/Osaka.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/seguiemj.ttf",
            "C:/Windows/Fonts/seguisym.ttf",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/YuGothR.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/Nirmala.ttf",
            "C:/Windows/Fonts/LeelawUI.ttf",
            "C:/Windows/Fonts/NotoSans-Regular.ttf",
        ]
        return common_bold if bold else common_regular

    def _load_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        for path in self._get_font_candidates(bold):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _load_font_chain(self, size: int, bold: bool = False) -> List[ImageFont.ImageFont]:
        fonts: List[ImageFont.ImageFont] = []
        seen = set()

        for path in self._get_font_candidates(bold):
            if path in seen:
                continue
            seen.add(path)
            try:
                fonts.append(ImageFont.truetype(path, size=size))
            except Exception:
                continue

        try:
            fonts.append(ImageFont.load_default())
        except Exception:
            pass

        return fonts or [ImageFont.load_default()]

    def _measure_text(self, text: str, fonts: List[ImageFont.ImageFont]) -> Tuple[int, int]:
        probe = Image.new("RGBA", (4096, 4096), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)
        sample = text or "…"

        for font in fonts:
            try:
                bbox = draw.textbbox((0, 0), sample, font=font)
                return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])
            except Exception:
                continue

        bbox = draw.textbbox((0, 0), sample, font=ImageFont.load_default())
        return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])

    def _measure_multiline_text(
        self,
        text: str,
        fonts: List[ImageFont.ImageFont],
        spacing: int,
    ) -> Tuple[int, int]:
        probe = Image.new("RGBA", (4096, 4096), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)
        sample = text or "…"

        for font in fonts:
            try:
                bbox = draw.multiline_textbbox((0, 0), sample, font=font, spacing=spacing)
                return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])
            except Exception:
                continue

        bbox = draw.multiline_textbbox((0, 0), sample, font=ImageFont.load_default(), spacing=spacing)
        return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])

    def _draw_multiline_with_fallback(
        self,
        draw: ImageDraw.ImageDraw,
        position: Tuple[int, int],
        text: str,
        fonts: List[ImageFont.ImageFont],
        fill: Tuple[int, int, int, int],
        spacing: int,
    ) -> None:
        sample = text or "…"
        last_error = None

        for font in fonts:
            try:
                draw.multiline_text(position, sample, font=font, fill=fill, spacing=spacing)
                return
            except Exception as e:
                last_error = e
                continue

        if last_error:
            draw.multiline_text(position, sample, font=ImageFont.load_default(), fill=fill, spacing=spacing)

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFC", str(text))
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\u00a0", " ").replace("\u200b", "")
        text = text.replace("\u2060", "").replace("\ufeff", "")
        return text

    def _is_combining_char(self, char: str) -> bool:
        if not char:
            return False
        return bool(unicodedata.combining(char)) or unicodedata.category(char) in {"Mn", "Mc", "Me"}

    def _is_variation_selector(self, char: str) -> bool:
        if not char:
            return False
        code = ord(char)
        return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF

    def _is_skin_tone_modifier(self, char: str) -> bool:
        if not char:
            return False
        code = ord(char)
        return 0x1F3FB <= code <= 0x1F3FF

    def _is_regional_indicator(self, char: str) -> bool:
        if not char:
            return False
        code = ord(char)
        return 0x1F1E6 <= code <= 0x1F1FF

    def _is_joiner_char(self, char: str) -> bool:
        return char in {"\u200d", "\u200c"}

    def _is_cjk_char(self, char: str) -> bool:
        if not char:
            return False
        code = ord(char)
        return (
            0x2E80 <= code <= 0x2FDF
            or 0x3000 <= code <= 0x303F
            or 0x3040 <= code <= 0x309F
            or 0x30A0 <= code <= 0x30FF
            or 0x3100 <= code <= 0x312F
            or 0x3130 <= code <= 0x318F
            or 0x31A0 <= code <= 0x31BF
            or 0x31F0 <= code <= 0x31FF
            or 0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xA960 <= code <= 0xA97F
            or 0xAC00 <= code <= 0xD7AF
            or 0xD7B0 <= code <= 0xD7FF
            or 0xF900 <= code <= 0xFAFF
            or 0xFE30 <= code <= 0xFE4F
            or 0xFF00 <= code <= 0xFFEF
            or 0x1B000 <= code <= 0x1B16F
            or 0x1F200 <= code <= 0x1F2FF
            or 0x20000 <= code <= 0x2FA1F
        )

    def _is_symbol_char(self, char: str) -> bool:
        if not char:
            return False
        code = ord(char)
        category = unicodedata.category(char)
        return (
            category.startswith("S")
            or category in {"Po", "Pd", "Ps", "Pe", "Pi", "Pf"}
            or 0x2190 <= code <= 0x21FF
            or 0x2300 <= code <= 0x23FF
            or 0x2460 <= code <= 0x24FF
            or 0x2500 <= code <= 0x257F
            or 0x25A0 <= code <= 0x25FF
            or 0x2600 <= code <= 0x27BF
            or 0x2900 <= code <= 0x297F
            or 0x2B00 <= code <= 0x2BFF
            or 0x1F000 <= code <= 0x1FAFF
        )

    def _is_no_space_token(self, token: str) -> bool:
        if not token:
            return False
        return all(self._is_cjk_char(ch) or self._is_symbol_char(ch) for ch in token)

    def _split_graphemes(self, text: str) -> List[str]:
        if not text:
            return []

        clusters: List[str] = []
        i = 0
        length = len(text)

        while i < length:
            cluster = text[i]
            i += 1

            if self._is_regional_indicator(cluster) and i < length and self._is_regional_indicator(text[i]):
                cluster += text[i]
                i += 1

            while i < length:
                current = text[i]
                if self._is_combining_char(current) or self._is_variation_selector(current) or self._is_skin_tone_modifier(current):
                    cluster += current
                    i += 1
                    continue

                if self._is_joiner_char(current):
                    cluster += current
                    i += 1
                    if i < length:
                        cluster += text[i]
                        i += 1
                        while i < length:
                            tail = text[i]
                            if self._is_combining_char(tail) or self._is_variation_selector(tail) or self._is_skin_tone_modifier(tail):
                                cluster += tail
                                i += 1
                                continue
                            break
                    continue

                break

            clusters.append(cluster)

        return clusters

    def _tokenize_for_wrap(self, text: str) -> List[str]:
        clusters = self._split_graphemes(text)
        if not clusters:
            return []

        tokens: List[str] = []
        current = ""

        for cluster in clusters:
            if cluster.isspace():
                if current:
                    tokens.append(current)
                    current = ""
                tokens.append(cluster)
                continue

            if any(self._is_cjk_char(ch) or self._is_symbol_char(ch) for ch in cluster):
                if current:
                    tokens.append(current)
                    current = ""
                tokens.append(cluster)
                continue

            current += cluster

        if current:
            tokens.append(current)

        return tokens

    def _split_token_by_width(self, token: str, max_width_px: int, fonts: List[ImageFont.ImageFont]) -> List[str]:
        if max_width_px <= 0:
            return [token]

        clusters = self._split_graphemes(token)
        if not clusters:
            return [token]

        parts: List[str] = []
        current = ""

        for cluster in clusters:
            candidate = current + cluster
            width, _ = self._measure_text(candidate, fonts)
            if current and width > max_width_px:
                parts.append(current)
                current = cluster
            else:
                current = candidate

        if current:
            parts.append(current)

        return parts or [token]

    def _wrap_block_pixels(self, block: str, max_width_px: int, fonts: List[ImageFont.ImageFont]) -> List[str]:
        if max_width_px <= 0:
            return [block]

        tokens = self._tokenize_for_wrap(block)
        if not tokens:
            return [""]

        lines: List[str] = []
        current = ""

        for token in tokens:
            if not token:
                continue

            if token.isspace():
                if current and not current.endswith(" "):
                    current += " "
                continue

            token_width, _ = self._measure_text(token, fonts)
            if token_width > max_width_px:
                if current.strip():
                    lines.append(current.rstrip())
                    current = ""
                lines.extend(part.rstrip() for part in self._split_token_by_width(token, max_width_px, fonts) if part)
                continue

            candidate = token if not current.strip() else current + token
            candidate_width, _ = self._measure_text(candidate.rstrip(), fonts)

            if current.strip() and candidate_width > max_width_px:
                lines.append(current.rstrip())
                current = token.lstrip()
                continue

            current = candidate

        if current.strip() or not lines:
            lines.append(current.rstrip())

        return lines

    def _wrap_text_pixels(self, text: str, max_width_px: int, fonts: List[ImageFont.ImageFont]) -> str:
        normalized = self._normalize_text(text)
        lines: List[str] = []
        for block in normalized.split("\n"):
            stripped = block.strip()
            if not stripped:
                lines.append("")
                continue
            lines.extend(self._wrap_block_pixels(stripped, max_width_px, fonts))
        result = "\n".join(lines).strip()
        return result[:4000]

    def _fit_media(self, image: Image.Image, width: int, max_height: int) -> Image.Image:
        img = image.convert("RGBA")
        ratio = min(width / img.width, max_height / img.height)
        ratio = min(ratio, 1.0)
        new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
        img = img.resize(new_size, Image.LANCZOS)
        return img

    def _round_mask(self, size: Tuple[int, int], radius: int) -> Image.Image:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
        return mask

    def _prepare_avatar(self, avatar: Optional[Image.Image], size: int) -> Image.Image:
        if avatar is None:
            img = Image.new("RGBA", (size, size), (90, 110, 255, 255))
        else:
            img = ImageOps.fit(avatar.convert("RGBA"), (size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(img, (0, 0), mask)
        return result

    def _render_quote(
        self,
        display_name: str,
        text: str,
        avatar: Optional[Image.Image],
        media_preview: Optional[Image.Image],
    ) -> Image.Image:
        canvas_width = 512
        max_canvas_height = 512
        outer_padding = 20
        bubble_padding_x = 18
        bubble_padding_y = 16
        avatar_size = 52
        gap = 12
        bubble_radius = 26
        name_spacing = 4
        text_spacing = 6
        text_gap = 8
        media_gap = 12
        bottom_reserve = 6

        bubble_x = outer_padding + avatar_size + gap
        bubble_w = canvas_width - bubble_x - outer_padding
        content_width = bubble_w - bubble_padding_x * 2

        name_fonts = self._load_font_chain(24, bold=True)
        text_fonts = self._load_font_chain(23, bold=False)

        wrapped_name = self._wrap_text_pixels(display_name, content_width, name_fonts)
        wrapped_text = self._wrap_text_pixels(text or "…", content_width, text_fonts)

        _, name_h = self._measure_multiline_text(wrapped_name, name_fonts, spacing=name_spacing)
        _, text_h = self._measure_multiline_text(wrapped_text or "…", text_fonts, spacing=text_spacing)

        media_img = None
        media_h = 0
        available_media_h = max(120, max_canvas_height - outer_padding * 2 - bubble_padding_y * 2 - name_h - text_h - text_gap - media_gap - 24)
        if media_preview is not None:
            media_img = self._fit_media(media_preview, content_width, min(220, available_media_h))
            media_h = media_img.height + media_gap

        content_h = name_h + text_gap + text_h + media_h
        bubble_h = max(avatar_size, bubble_padding_y * 2 + content_h + bottom_reserve)
        total_height = outer_padding * 2 + bubble_h

        canvas = Image.new("RGBA", (canvas_width, total_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        bubble_y = outer_padding
        avatar_img = self._prepare_avatar(avatar, avatar_size)
        avatar_y = bubble_y + max(0, (bubble_h - avatar_size) // 2)
        canvas.paste(avatar_img, (outer_padding, avatar_y), avatar_img)

        bubble_rect = (bubble_x, bubble_y, bubble_x + bubble_w, bubble_y + bubble_h)

        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (bubble_rect[0], bubble_rect[1] + 3, bubble_rect[2], bubble_rect[3] + 3),
            radius=bubble_radius,
            fill=(0, 0, 0, 70),
        )
        canvas.alpha_composite(shadow)

        draw.rounded_rectangle(bubble_rect, radius=bubble_radius, fill=(33, 33, 38, 245))

        tx = bubble_x + bubble_padding_x
        ty = bubble_y + bubble_padding_y

        self._draw_multiline_with_fallback(
            draw,
            (tx, ty),
            wrapped_name,
            name_fonts,
            (118, 181, 255, 255),
            name_spacing,
        )
        ty += name_h + text_gap

        body_text = (wrapped_text or "…")[:4000]
        self._draw_multiline_with_fallback(
            draw,
            (tx, ty),
            body_text,
            text_fonts,
            (255, 255, 255, 255),
            text_spacing,
        )
        ty += text_h

        if media_img is not None:
            ty += media_gap
            mask = self._round_mask(media_img.size, 18)
            framed = Image.new("RGBA", media_img.size, (0, 0, 0, 0))
            framed.paste(media_img, (0, 0), mask)
            canvas.paste(framed, (tx, ty), framed)

        max_side = max(canvas.size)
        if max_side > 512:
            ratio = 512 / max_side
            new_size = (max(1, int(canvas.width * ratio)), max(1, int(canvas.height * ratio)))
            canvas = canvas.resize(new_size, Image.LANCZOS)
        elif canvas.width < 512 or canvas.height < 512:
            bg = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            x = (512 - canvas.width) // 2
            y = (512 - canvas.height) // 2
            bg.paste(canvas, (x, y), canvas)
            canvas = bg

        return canvas