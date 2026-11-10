import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
import ui
from messaging import msg_of, show_text
from screens import delete_ids, show_screen
from utils import (
    LOW_STOCK, article_line, catalog_tables, category_header, esc, paginate_blocks, parse_args, parse_sizes,
    plural, stock_line,
)

log = logging.getLogger(__name__)

# Фильтр «только админ» навешивается на этот роутер в main.py.
router = Router(name="admin")

ADMIN_TITLE = "<b>Панель администратора</b>"  # на случай, если база недоступна


HOME_PAGE_LIMIT = 3000  # знаков таблиц на странице: вместе со сводкой должно поместиться в 4096
TABLE_LEGEND = "<i>ШТ — всего на складе · — учёт размеров не ведётся</i>"


def admin_home_screen(page: int = 0, note: str = ""):
    """Главный экран /admin: сводка, затем весь ассортимент в виде
    КАТЕГОРИЯ / АРТИКУЛ - НАЗВАНИЕ. Возвращает (текст, клавиатура)."""
    groups = [(name, db.category_stock(cid)) for cid, name in db.get_categories()]
    _users, products, _carts = db.get_crm_stats()
    low = len(db.low_stock(LOW_STOCK, 1000))
    lines = [note, ""] if note else []
    lines += [
        "<b>Панель администратора</b>",
        f"Категорий: <b>{len(groups)}</b> · Товаров: <b>{products}</b>",
    ]
    if low:
        lines.append(f"⚠️ Заканчивается: <b>{low}</b> {plural(low, ('размер', 'размера', 'размеров'))}")
    lines.append("")
    pages = paginate_blocks(catalog_tables(groups), HOME_PAGE_LIMIT) if groups else []
    page = page % len(pages) if pages else 0
    if pages:
        lines.append(pages[page])
    else:
        lines.append("<i>Пока нет категорий. Нажмите «Категории», чтобы добавить первую.</i>")
    if pages:
        lines += ["", TABLE_LEGEND]
    lines += ["", "<i>Отправьте артикул (например</i> <code>12</code><i>) — откроется карточка товара.</i>"]
    return "\n".join(lines), ui.admin_home_kb(page, len(pages) or 1)
MAX_NAME, MAX_DESC, MAX_CATEGORY, MAX_PRICE = 60, 700, 40, 10_000_000


class AdminStates(StatesGroup):
    cat_name = State()
    p_name = State()
    p_desc = State()
    p_price = State()
    p_photo = State()
    p_sizes = State()
    bc_text = State()
    bc_photo = State()
    bc_confirm = State()


# ---------- меню ----------

@router.message(Command("admin"))
async def cmd_admin(m: Message, state: FSMContext):
    await state.clear()
    text, kb = admin_home_screen()
    await show_screen(m, text, kb, also_delete=[m.message_id])  # новая панель; старые сообщения и сама команда удаляются


@router.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    was_active = await state.get_state() is not None
    await state.clear()
    text, kb = admin_home_screen(note="Отменено." if was_active else "")
    await show_screen(m, text, kb, also_delete=[m.message_id])


@router.callback_query(F.data == "a:menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = admin_home_screen()
    await show_text(c, text, kb)
    await c.answer()


@router.callback_query(F.data.startswith("a:home:"))
async def cb_home_page(c: CallbackQuery):
    args = parse_args(c.data, "a:home", 1)
    text, kb = admin_home_screen(args[0] if args else 0)
    await show_text(c, text, kb)
    await c.answer()


@router.callback_query(F.data == "a:exit")
async def cb_exit(c: CallbackQuery, state: FSMContext):
    await state.clear()
    msg = msg_of(c)
    if msg:
        old = db.admin_msgs_pop(msg.chat.id)
        await msg.answer("🚪 Вы вышли из админки.", reply_markup=ui.main_reply_kb())
        await delete_ids(msg.bot, msg.chat.id, [*old, msg.message_id])  # чат остаётся чистым
    await c.answer()


@router.callback_query(F.data == "a:stats")
async def cb_stats(c: CallbackQuery):
    users, products, carts = db.get_crm_stats()
    text = (
        "📊 <b>Статистика Outfit</b>\n\n"
        f"👥 Клиентов в базе: <b>{users}</b>\n"
        f"📦 Товаров на витрине: <b>{products}</b>\n"
        f"🧥 Клиентов с непустым образом: <b>{carts}</b>"
    )
    await show_text(c, text, ui.back_to_admin_kb())
    await c.answer()


# ---------- список товаров: КАТЕГОРИЯ → АРТИКУЛ - НАЗВАНИЕ ----------

@router.callback_query(F.data.startswith("a:plist"))
async def cb_product_list(c: CallbackQuery):
    args = parse_args(c.data, "a:plist", 1)
    page = args[0] if args else 0
    groups = [(name, db.category_stock(cid)) for cid, name in db.get_categories()]
    if not groups:
        await c.answer("Категорий пока нет", show_alert=True)
        return
    pages = paginate_blocks(catalog_tables(groups))
    page = page % len(pages)
    await show_text(c, f"<b>Список товаров</b>\n\n{pages[page]}\n\n{TABLE_LEGEND}", ui.plist_kb(page, len(pages)))
    await c.answer()


# ---------- категории ----------

@router.callback_query(F.data == "a:cats")
async def cb_categories(c: CallbackQuery):
    cats = db.get_categories()
    lines = ["<b>Категории</b>", ""]
    if not cats:
        lines.append("<i>Пока нет ни одной.</i>")
    for cid, name in cats:
        lines.append(f"{category_header(name)} · {db.count_products(cid)} шт.")
    await show_text(c, "\n".join(lines), ui.admin_cats_menu_kb())
    await c.answer()




@router.callback_query(F.data == "a:addc")
async def cb_add_category(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.cat_name)
    msg = msg_of(c)
    if msg:
        await show_screen(msg, f"✏️ Название категории (до {MAX_CATEGORY} символов):", ui.cancel_kb(),
                          also_delete=[msg.message_id])
    await c.answer()


@router.message(AdminStates.cat_name, F.text)
async def msg_category_name(m: Message, state: FSMContext):
    name = m.text.strip()
    if not name or len(name) > MAX_CATEGORY or name.startswith("/"):
        await show_screen(m, f"⚠️ Название должно быть от 1 до {MAX_CATEGORY} символов. Попробуйте ещё раз:",
                          ui.cancel_kb(), also_delete=[m.message_id])
        return
    db.add_category(name)
    await state.clear()
    text, kb = admin_home_screen(note=f"✅ Категория «{esc(name)}» добавлена")
    await show_screen(m, text, kb, also_delete=[m.message_id])


@router.callback_query(F.data == "a:delc")
async def cb_del_category(c: CallbackQuery):
    cats = db.get_categories()
    if not cats:
        await c.answer("Категорий нет!", show_alert=True)
        return
    await show_text(c, "🗑 Какую категорию удалить?", ui.admin_cats_kb(cats, "a:dc", "🗑"))
    await c.answer()


@router.callback_query(F.data.startswith("a:dc:"))
async def cb_del_category_confirm(c: CallbackQuery):
    args = parse_args(c.data, "a:dc", 1)
    name = db.get_category(args[0]) if args else None
    if name is None:
        await c.answer("Категория уже удалена", show_alert=True)
        return
    n = db.count_products(args[0])
    await show_text(
        c,
        f"Удалить категорию {category_header(name)} и все её товары ({n} шт.)?\nЭто необратимо.",
        ui.confirm_kb(f"a:dcy:{args[0]}", "🗑 Да, удалить"),
    )
    await c.answer()


@router.callback_query(F.data.startswith("a:dcy:"))
async def cb_del_category_do(c: CallbackQuery):
    args = parse_args(c.data, "a:dcy", 1)
    if args:
        db.delete_category(args[0])
    text, kb = admin_home_screen(note="✅ Категория удалена")
    await show_text(c, text, kb)
    await c.answer()


# ---------- добавление товара ----------

@router.callback_query(F.data == "a:addp")
async def cb_add_product(c: CallbackQuery, state: FSMContext):
    await state.clear()
    cats = db.get_categories()
    if not cats:
        await c.answer("Сначала создайте категорию!", show_alert=True)
        return
    await show_text(c, "<b>Добавить товар</b>\nВыберите категорию:", ui.admin_cats_kb(cats, "a:ap"))
    await c.answer()


@router.callback_query(F.data.startswith("a:ap:"))
async def cb_add_product_category(c: CallbackQuery, state: FSMContext):
    args = parse_args(c.data, "a:ap", 1)
    if not args or db.get_category(args[0]) is None:
        await c.answer("Категория не найдена", show_alert=True)
        return
    await state.update_data(c_id=args[0])
    await state.set_state(AdminStates.p_name)
    msg = msg_of(c)
    if msg:
        await show_screen(msg, f"✏️ Название товара (до {MAX_NAME} символов):", ui.cancel_kb(),
                          also_delete=[msg.message_id])
    await c.answer()


@router.message(AdminStates.p_name, F.text)
async def msg_product_name(m: Message, state: FSMContext):
    name = m.text.strip()
    if not name or len(name) > MAX_NAME or name.startswith("/"):
        await show_screen(m, f"⚠️ Название — от 1 до {MAX_NAME} символов. Ещё раз:", ui.cancel_kb(),
                          also_delete=[m.message_id])
        return
    await state.update_data(n=name)
    await state.set_state(AdminStates.p_desc)
    await show_screen(m, f"✏️ Описание товара (до {MAX_DESC} символов):", ui.cancel_kb(), also_delete=[m.message_id])


@router.message(AdminStates.p_desc, F.text)
async def msg_product_desc(m: Message, state: FSMContext):
    desc = m.text.strip()
    if not desc or len(desc) > MAX_DESC or desc.startswith("/"):
        await show_screen(m, f"⚠️ Описание — от 1 до {MAX_DESC} символов. Ещё раз:", ui.cancel_kb(),
                          also_delete=[m.message_id])
        return
    await state.update_data(d=desc)
    await state.set_state(AdminStates.p_price)
    await show_screen(m, "💰 Цена в рублях (только цифры):", ui.cancel_kb(), also_delete=[m.message_id])


@router.message(AdminStates.p_price, F.text)
async def msg_product_price(m: Message, state: FSMContext):
    raw = m.text.strip().replace(" ", "")
    if not (raw.isascii() and raw.isdigit()) or not (0 < int(raw) <= MAX_PRICE):
        await show_screen(m, "⚠️ Введите целое число больше нуля, например 4990:", ui.cancel_kb(),
                          also_delete=[m.message_id])
        return
    await state.update_data(pr=int(raw))
    await state.set_state(AdminStates.p_photo)
    await show_screen(m, "🖼 Отправьте фото товара (как фото, не файлом):", ui.cancel_kb(), also_delete=[m.message_id])


@router.message(AdminStates.p_photo, F.photo)
async def msg_product_photo(m: Message, state: FSMContext):
    await state.update_data(ph=m.photo[-1].file_id)
    await state.set_state(AdminStates.p_sizes)
    await show_screen(
        m,
        "📏 Размеры и количество через пробел:\n"
        "<code>S2 M3 L1</code> — буквенные, <code>42:2 43:1</code> — числовые.\n"
        "Товар без размеров, но с учётом количества (сумка, шарф): <code>ONE5</code> — 5 шт.\n"
        "Совсем без учёта — отправьте «<code>-</code>».",
        ui.cancel_kb(), also_delete=[m.message_id],
    )


@router.message(AdminStates.p_sizes, F.text)
async def msg_product_sizes(m: Message, state: FSMContext):
    raw = m.text.strip()
    try:
        sizes = [] if raw in ("-", "—") else parse_sizes(raw)
    except ValueError as e:
        await show_screen(m, f"⚠️ {esc(str(e))}", ui.cancel_kb(), also_delete=[m.message_id])
        return
    data = await state.get_data()
    if db.get_category(data.get("c_id", -1)) is None:
        await state.clear()
        text, kb = admin_home_screen(note="⚠️ Категорию успели удалить. Начните заново.")
        await show_screen(m, text, kb, also_delete=[m.message_id])
        return
    product_id = db.add_product(data["c_id"], data["n"], data["d"], data["pr"], data["ph"])
    if sizes:
        db.touch_admin(m.from_user.id, m.from_user.first_name or m.from_user.username or str(m.from_user.id))
        db.set_stock(product_id, sizes, m.from_user.id)
    await state.clear()
    note = (
        f"🎉 Товар добавлен\n{category_header(db.get_category(data['c_id']))}\n"
        f"{article_line(product_id, data['n'])}\n{stock_line(sizes)}\n"
        "<i>Артикул напишите на бирке — по нему удобно отмечать продажи.</i>"
    )
    text, kb = admin_home_screen(note=note)
    await show_screen(m, text, kb, also_delete=[m.message_id])


# ---------- удаление товара ----------

async def _render_product_list(c: CallbackQuery, category_id: int, note: str = ""):
    name = db.get_category(category_id)
    if name is None:
        await c.answer("Категория не найдена", show_alert=True)
        return
    products = db.get_products_by_category(category_id)
    if not products:
        await show_text(c, f"{note}{category_header(name)}\nБольше нет товаров.", ui.admin_menu_kb())
        return
    await show_text(
        c, f"{note}{category_header(name)}\nКакой товар удалить?",
        ui.admin_products_kb(products, category_id),
    )


@router.callback_query(F.data == "a:delp")
async def cb_del_product(c: CallbackQuery):
    cats = db.get_categories()
    if not cats:
        await c.answer("Категорий нет!", show_alert=True)
        return
    await show_text(c, "📁 Выберите категорию:", ui.admin_cats_kb(cats, "a:dpc"))
    await c.answer()


@router.callback_query(F.data.startswith("a:dpc:"))
async def cb_del_product_category(c: CallbackQuery):
    args = parse_args(c.data, "a:dpc", 1)
    if args:
        await _render_product_list(c, args[0])
    await c.answer()


@router.callback_query(F.data.startswith("a:dp:"))
async def cb_del_product_do(c: CallbackQuery):
    args = parse_args(c.data, "a:dp", 2)
    if not args:
        await c.answer()
        return
    db.delete_product(args[0])
    await _render_product_list(c, args[1], note="✅ Удалено.\n\n")
    await c.answer("Удалено")


# ---------- рассылка ----------

@router.callback_query(F.data == "a:bc")
async def cb_broadcast(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.bc_text)
    msg = msg_of(c)
    if msg:
        await show_screen(
            msg, "✍️ Пришлите текст рассылки. Жирный, курсив и ссылки — обычным форматированием Telegram.",
            ui.cancel_kb(), also_delete=[msg.message_id],
        )
    await c.answer()


@router.message(AdminStates.bc_text, F.text)
async def msg_broadcast_text(m: Message, state: FSMContext):
    text = m.html_text
    if text.startswith("/"):
        await show_screen(m, "⚠️ Пришлите обычный текст, не команду.", ui.cancel_kb(), also_delete=[m.message_id])
        return
    await state.update_data(text=text)
    if len(text) <= 1024:
        await show_screen(m, "Добавить изображение к рассылке?", ui.broadcast_image_kb(), also_delete=[m.message_id])
    else:
        # Подпись к фото ограничена 1024 символами — для длинного текста только без фото.
        await state.update_data(photo=None)
        await _show_preview(m, state, also_delete=[m.message_id])


@router.callback_query(AdminStates.bc_text, F.data == "a:bc_skip")
async def cb_broadcast_skip(c: CallbackQuery, state: FSMContext):
    await state.update_data(photo=None)
    msg = msg_of(c)
    if msg:
        await _show_preview(msg, state, also_delete=[msg.message_id])
    await c.answer()


@router.callback_query(AdminStates.bc_text, F.data == "a:bc_img")
async def cb_broadcast_image(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.bc_photo)
    await show_text(c, "🖼 Отправьте изображение для рассылки:", ui.cancel_kb())
    await c.answer()


@router.message(AdminStates.bc_photo, F.photo)
async def msg_broadcast_photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await _show_preview(m, state, also_delete=[m.message_id])


async def _send_one(bot, chat_id: int, text: str, photo):
    if photo:
        return await bot.send_photo(chat_id=chat_id, photo=photo, caption=text)
    return await bot.send_message(chat_id=chat_id, text=text)


async def _show_preview(m: Message, state: FSMContext, also_delete=()):
    data = await state.get_data()
    users = db.get_all_users()
    try:  # заодно проверяем, что разметка корректна — до отправки всем
        preview = await _send_one(m.bot, m.chat.id, data["text"], data.get("photo"))
    except TelegramBadRequest as e:
        await state.clear()
        text, kb = admin_home_screen(note=f"❌ Telegram не принял сообщение: {esc(e.message)}\nНачните рассылку заново.")
        await show_screen(m, text, kb, also_delete=also_delete)
        return
    preview_id = getattr(preview, "message_id", None)
    if preview_id:
        db.admin_msgs_add(m.chat.id, [preview_id])  # предпросмотр исчезнет вместе с остальными, когда рассылка закончится
    await state.set_state(AdminStates.bc_confirm)
    await show_screen(
        m, f"👆 Так сообщение увидят клиенты. Отправить {len(users)} получателям?",
        ui.broadcast_confirm_kb(len(users)), also_delete=also_delete, keep=[preview_id] if preview_id else (),
    )


@router.callback_query(AdminStates.bc_confirm, F.data == "a:bc_go")
async def cb_broadcast_go(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()  # повторный клик по кнопке уже ничего не запустит
    await c.answer("Запускаю…")
    msg = msg_of(c)
    if msg is None:
        return
    users = db.get_all_users()
    if not users:
        text, kb = admin_home_screen(note="❌ База пуста, рассылать некому.")
        await show_screen(msg, text, kb, also_delete=[msg.message_id])
        return
    await show_text(c, f"🚀 Рассылка запущена: {len(users)} получателей…", None)
    ok, blocked, failed = await run_broadcast(c.bot, users, data["text"], data.get("photo"))
    note = (
        "📊 <b>Итог рассылки</b>\n"
        f"✅ Доставлено: {ok}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"⚠️ Другие ошибки: {failed}"
    )
    text, kb = admin_home_screen(note=note)
    await show_screen(msg, text, kb, also_delete=[msg.message_id])  # предпросмотр и «Запущено…» удаляются


async def run_broadcast(bot, users, text: str, photo):
    ok = blocked = failed = 0
    for uid in users:
        status = await _send_with_retry(bot, uid, text, photo)
        if status == "ok":
            ok += 1
        elif status == "blocked":
            blocked += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 сообщений/сек, лимит Telegram — 30
    return ok, blocked, failed


async def _send_with_retry(bot, uid: int, text: str, photo) -> str:
    for _attempt in range(2):
        try:
            await _send_one(bot, uid, text, photo)
            return "ok"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramAPIError as e:
            log.warning("Рассылка: ошибка для %s: %s", uid, e)
            return "failed"
    return "failed"


# ---------- неверный тип сообщения в диалоге ----------

@router.message(AdminStates.p_photo)
@router.message(AdminStates.bc_photo)
async def need_photo(m: Message):
    await show_screen(m, "🖼 Нужно именно фото (не файл и не текст).", ui.cancel_kb(), also_delete=[m.message_id])


@router.message(AdminStates.cat_name)
@router.message(AdminStates.p_name)
@router.message(AdminStates.p_desc)
@router.message(AdminStates.p_price)
@router.message(AdminStates.p_sizes)
@router.message(AdminStates.bc_text)
async def need_text(m: Message):
    await show_screen(m, "✏️ Здесь нужен обычный текст.", ui.cancel_kb(), also_delete=[m.message_id])
