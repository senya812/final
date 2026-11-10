"""«Живой экран» админки: в чате остаётся одно актуальное сообщение.

Новый экран отправляется первым, и только потом удаляются прежние: чат никогда не остаётся пустым.
Вместе с ними бот удаляет и сообщения самого админа (команды, ответы в диалогах) — в личном чате это разрешено.
Telegram не даёт удалять сообщения старше 48 часов; такие ошибки игнорируются.
"""
import logging
from typing import Iterable, Optional

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, Message

import database as db

log = logging.getLogger(__name__)


async def delete_ids(bot, chat_id: int, ids: Iterable[int]) -> None:
    unique = [i for i in dict.fromkeys(ids) if i]
    for start in range(0, len(unique), 100):
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=unique[start:start + 100])
        except TelegramAPIError as e:
            log.info("Не удалось удалить старые сообщения админки: %s", e)


async def show_screen(msg: Message, text: str, kb: Optional[InlineKeyboardMarkup] = None, *,
                      also_delete: Iterable[int] = (), keep: Iterable[int] = ()):
    """Показывает новый экран. Удаляет прежние экраны админки и also_delete (например, сообщение админа
    или сообщение с нажатой кнопкой). keep — id сообщений, которые должны остаться (например, предпросмотр рассылки)."""
    chat_id = msg.chat.id
    keep = set(keep)
    old = db.admin_msgs_pop(chat_id)
    sent = await msg.answer(text, reply_markup=kb)
    new_id = getattr(sent, "message_id", None)
    db.admin_msgs_add(chat_id, [*keep, *([new_id] if new_id else [])])
    await delete_ids(msg.bot, chat_id, [i for i in [*old, *also_delete] if i not in keep and i != new_id])
    return sent
