# scope: hikka_only
# meta name: SimpleTest
# meta developer: @bsod4ik_plugins
# meta version: 1.0.0

from .. import loader, utils
from telethon.tl.types import Message


@loader.tds
class SimpleTestMod(loader.Module):
    """Простой тестовый модуль для проверки загрузки и работы команд."""

    strings = {
        "name": "SimpleTest",
        "module_desc": "Простой тестовый модуль для проверки работы userbot.",
        "stest_desc": "Проверить, что модуль успешно загружен и работает.",
        "ok": (
            "<b><a href=\"tg://emoji?id=5206607081334906820\">✔️</a> "
            "Модуль <code>SimpleTest</code> работает корректно.</b>\n"
            "<i>Команда успешно обработана.</i>"
        ),
    }

    strings_ru = {
        "module_desc": "Простой тестовый модуль для проверки работы userbot.",
        "stest_desc": "Проверить, что модуль успешно загружен и работает.",
        "ok": (
            "<b><a href=\"tg://emoji?id=5206607081334906820\">✔️</a> "
            "Модуль <code>SimpleTest</code> работает корректно.</b>\n"
            "<i>Команда успешно обработана.</i>"
        ),
    }

    author = "@bsod4ik_plugins, @bsod4ik"
    credits = ("@bsod4ik_plugins", "@bsod4ik")

    async def client_ready(self, client, db):
        self.db = db

    @loader.command(
        ru_doc="Проверить, что тестовый модуль загружен и работает.",
        en_doc="Check that the test module is loaded and working.",
    )
    async def stest(self, message: Message):
        """Проверка работоспособности модуля."""
        await utils.answer(message, self.strings("ok"))