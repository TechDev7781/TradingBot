import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramService:
    _bot: Bot | None = None
    _dispatcher: Dispatcher | None = None
    _polling_task: asyncio.Task[None] | None = None

    _router = Router()

    @_router.message(CommandStart())
    async def _handle_start(message: Message) -> None:
        chat_id = message.chat.id
        await message.answer(
            f"Привет! Ваш chat id:`{chat_id}`\n\n",
            parse_mode="Markdown",
        )

    @classmethod
    def _get_bot(cls) -> Bot | None:
        if not settings.telegram_bot_token:
            return None
        if cls._bot is None:
            cls._bot = Bot(token=settings.telegram_bot_token)
        return cls._bot

    @classmethod
    def _get_dispatcher(cls) -> Dispatcher:
        if cls._dispatcher is None:
            cls._dispatcher = Dispatcher()
            cls._dispatcher.include_router(cls._router)
        return cls._dispatcher

    @classmethod
    async def start_polling(cls) -> None:
        bot = cls._get_bot()
        if bot is None:
            logger.warning("Telegram polling не запущен: TELEGRAM_BOT_TOKEN пуст")
            return
        if cls._polling_task and not cls._polling_task.done():
            return

        dispatcher = cls._get_dispatcher()
        cls._polling_task = asyncio.create_task(
            dispatcher.start_polling(bot, handle_signals=False)
        )
        logger.info("Telegram polling запущен")

    @classmethod
    async def stop_polling(cls) -> None:
        if cls._dispatcher is not None:
            await cls._dispatcher.stop_polling()
        if cls._polling_task is not None:
            await cls._polling_task
            cls._polling_task = None
        if cls._bot is not None:
            await cls._bot.session.close()
            cls._bot = None
        logger.info("Telegram polling остановлен")

    @classmethod
    async def broadcast(cls, text: str) -> None:
        bot = cls._get_bot()
        if bot is None or not settings.telegram_chat_ids:
            logger.warning(
                "Telegram не настроен (token/chat_ids пусты), сообщение пропущено"
            )
            return

        for chat_id in settings.telegram_chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    disable_web_page_preview=True,
                )
            except TelegramAPIError as e:
                logger.exception(
                    "Ошибка отправки в Telegram chat_id=%s: %s", chat_id, e
                )
