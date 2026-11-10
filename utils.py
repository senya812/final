"""Чистые функции без зависимостей от aiogram — их легко тестировать."""
import html
import re
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

MAX_LOOK_ITEMS = 20  # лимит вещей в образе (и защита от лимита Telegram в 100 кнопок)
NBSP = "\u00a0"
LOW_STOCK = 2  # «осталось мало» — когда в размере не больше стольких штук
ONE_SIZE = "ONE"  # служебный «размер» для товаров без размеров (сумка, шарф): ведётся только количество

# Кириллические буквы, похожие на латинские: на русской раскладке «М» и «Х» легко набрать вместо M и X.
_LOOKALIKES = str.maketrans("АВЕКМНОРСТХ", "ABEKMHOPCTX")
SIZE_RE = r"[A-Za-zА-Яа-я0-9./\-]{1,8}"
QUICK_RE = rf"^\s*№?\s*(\d{{1,9}})\s+({SIZE_RE})(?:\s+([+\-]?\d{{1,4}}))?\s*$"


def esc(value) -> str:
    """Экранирует текст для parse_mode=HTML."""
    return html.escape("" if value is None else str(value), quote=False)


def format_price(value) -> str:
    """12990 -> '12 990 ₽' (с неразрывными пробелами)."""
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", NBSP) + f"{NBSP}₽"


def truncate(text: Optional[str], limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clamp(index: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(index, total - 1))


def parse_args(data: Optional[str], prefix: str, count: int) -> Optional[Tuple[int, ...]]:
    """'tg:5:2:0' + prefix 'tg' + count 3 -> (5, 2, 0). При любой ошибке — None."""
    if not data or not data.startswith(prefix + ":"):
        return None
    parts = data[len(prefix) + 1:].split(":")
    if len(parts) != count:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def plural(n: int, forms: Tuple[str, str, str]) -> str:
    """plural(1, ('вещь','вещи','вещей')) -> 'вещь'; 3 -> 'вещи'; 5 -> 'вещей'; 11 -> 'вещей'."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return forms[2]
    last = n % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def product_caption(name: str, description: Optional[str], price, category: Optional[str] = None,
                    sizes: Optional[Sequence[Tuple[str, int]]] = None,
                    product_id: Optional[int] = None) -> str:
    lines = []
    if category:
        lines.append(f"<i>{esc(truncate(category, 40))}</i>")
    lines.append(f"<b>{esc(truncate(name, 100))}</b>")
    desc = truncate(description, 700)
    if desc:
        lines += ["", f"<blockquote>{esc(desc)}</blockquote>"]
    block = sizes_block(sizes or [])
    if block:
        lines += ["", block]
    price_line = f"<b>{format_price(price)}</b>"
    if product_id is not None:
        price_line += f"  ·  <i>арт. {product_id}</i>"
    lines += ["", price_line]
    return "\n".join(lines)


def look_text(items: Sequence[Iterable]) -> str:
    """items: (cart_id, name, price, product_id)."""
    n = len(items)
    lines = ["<b>Мой образ</b>", f"<i>{n} {plural(n, ('вещь', 'вещи', 'вещей'))}</i>", ""]
    total = 0
    for i, (_, name, price, _pid) in enumerate(items, 1):
        lines.append(f"{i} · {esc(name)} — {format_price(price)}")
        total += price or 0
    lines += ["", f"<b>Сумма образа · {format_price(total)}</b>"]
    return "\n".join(lines)


# ---------- размеры и остатки ----------

def normalize_size(raw: str) -> Optional[str]:
    """'xl' -> 'XL', кириллическая 'М' -> 'M'. Недопустимое — None."""
    size = (raw or "").strip().upper().translate(_LOOKALIKES)
    return size if re.fullmatch(r"[A-Z0-9./\-]{1,8}", size) else None


def parse_sizes(text: str) -> List[Tuple[str, int]]:
    """'S2 M3 L1' или '42:2 43:1' -> [('S',2), ('M',3), ('L',1)]. При ошибке — ValueError с понятным текстом."""
    tokens = [t for t in re.split(r"[,;\s]+", (text or "").strip()) if t]
    if not tokens:
        raise ValueError("Пусто. Пример: S2 M3 L1")
    result, seen = [], set()
    for token in tokens:
        m = re.fullmatch(r"([A-Za-zА-Яа-я]+)(\d{1,4})", token) or re.fullmatch(
            rf"({SIZE_RE})[:=](\d{{1,4}})", token)
        if not m:
            raise ValueError(f"Не понял «{token}». Пишите размер и количество слитно: S2 M3, а для чисел через двоеточие: 42:2 43:1")
        size = normalize_size(m.group(1))
        if size is None:
            raise ValueError(f"Размер «{m.group(1)}» не подходит: до 8 символов, буквы/цифры.")
        if size in seen:
            raise ValueError(f"Размер {size} указан дважды.")
        seen.add(size)
        result.append((size, int(m.group(2))))
    if len(result) > 20:
        raise ValueError("Слишком много размеров (максимум 20).")
    return result


def parse_quick(text: str) -> Optional[Tuple[int, str, int]]:
    """'12 M' -> (12, 'M', -1); '12 M 2' -> (12,'M',-2); '12 M +3' -> (12,'M',3). Не подошло — None."""
    m = re.match(QUICK_RE, text or "")
    if not m:
        return None
    size = normalize_size(m.group(2))
    if size is None:
        return None
    raw = m.group(3)
    if raw is None:
        delta = -1
    elif raw.startswith("+"):
        delta = int(raw[1:])
    else:
        delta = -abs(int(raw))
    return (int(m.group(1)), size, delta) if delta != 0 else None


def sizes_block(sizes: Sequence[Tuple[str, int]]) -> str:
    """Строка размеров для клиента: закончившиеся зачёркнуты, плюс пометка про «мало».
    У товара без размеров (служебный ONE) клиент видит только «Осталось мало» / «Нет в наличии»."""
    if not sizes:
        return ""
    if len(sizes) == 1 and sizes[0][0] == ONE_SIZE:
        qty = sizes[0][1]
        if qty <= 0:
            return "<b>Нет в наличии</b>"
        return "<i>Осталось мало</i>" if qty <= LOW_STOCK else ""
    if all(q <= 0 for _, q in sizes):
        return "<b>Нет в наличии</b>"
    parts = [esc(s) if q > 0 else f"<s>{esc(s)}</s>" for s, q in sizes]
    lines = ["  ·  ".join(parts)]
    low = [esc(s) for s, q in sizes if 0 < q <= LOW_STOCK]
    if low:
        lines.append(f"<i>Осталось мало: {', '.join(low)}</i>")
    return "\n".join(lines)


def stock_line(sizes: Sequence[Tuple[str, int]]) -> str:
    """Для админа: 'S 2 · M 0 · L 1', 'без размера · 5 шт.' или пометка, что учёта нет."""
    if not sizes:
        return "размеры не заведены"
    if len(sizes) == 1 and sizes[0][0] == ONE_SIZE:
        return f"без размера · {sizes[0][1]} шт."
    return "  ·  ".join(f"{esc(s)} {q}" for s, q in sizes)


def format_ts(ts: str, tz_offset: int = 0) -> str:
    """'2026-10-20 14:05:00' (UTC) -> '20.10 17:05' с учётом часового пояса."""
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S") + timedelta(hours=tz_offset)
    except (ValueError, TypeError):
        return str(ts)
    return dt.strftime("%d.%m %H:%M")


# ---------- единый вид списков в админке: КАТЕГОРИЯ → АРТИКУЛ - НАЗВАНИЕ ----------

def category_header(name: Optional[str]) -> str:
    """'Куртки' -> '<b>КУРТКИ</b>'"""
    return f"<b>{esc((name or 'Без категории').strip().upper())}</b>"


def article_line(product_id: int, name: str, limit: int = 40) -> str:
    """'12 - Парка'. Артикул в <code>: в Telegram по нему можно тапнуть и скопировать."""
    return f"<code>{product_id}</code> - {esc(truncate(name, limit))}"


def button_label(product_id: int, name: str, limit: int = 36) -> str:
    """Текст кнопки (без HTML): '12 - Парка'. Вся подпись не длиннее limit знаков."""
    return truncate(f"{product_id} - {name}", limit)


def stock_status(sizes: Sequence[Tuple[str, int]]) -> str:
    """'' — учёт не ведётся или всё в порядке, 'low' — какой-то размер на исходе, 'out' — всё распродано."""
    if not sizes:
        return ""
    if all(q <= 0 for _, q in sizes):
        return "out"
    return "low" if any(0 < q <= LOW_STOCK or q == 0 for _, q in sizes) else ""


NAME_W = 18  # ширина столбца «название» — вся строка около 30 знаков и помещается на экран телефона


def _qty_cell(sizes: Sequence[Tuple[str, int]]) -> str:
    """Столбец «ШТ»: всего штук на складе; «—» — учёт размеров не ведётся."""
    if not sizes:
        return "—"
    return str(sum(q for _, q in sizes))


def catalog_tables(groups, chunk_chars: int = 2700) -> List[str]:
    """groups: [(категория, [(артикул, название, [(size, qty), ...]), ...]), ...] -> блоки-таблицы.

        КУРТКИ
        АРТ  НАЗВАНИЕ            ШТ
         12  Парка               11
         13  Тренч                —

    Таблица — моноширинный блок <pre>: только так столбцы ровно выстраиваются в Telegram.
    Длинные категории режутся на несколько таблиц (каждая не длиннее chunk_chars), теги не ломаются."""
    blocks = []
    for category, items in groups:
        header = category_header(category)
        if not items:
            blocks.append(f"{header}\n<i>пока пусто</i>")
            continue
        cells = [(str(pid), " ".join(truncate(" ".join(name.split()), NAME_W).split()), _qty_cell(sizes))
                 for pid, name, sizes in items]
        art_w = max(3, max(len(c[0]) for c in cells))
        qty_w = max(2, max(len(c[2]) for c in cells))
        head_row = f"{'АРТ'.rjust(art_w)}  {'НАЗВАНИЕ'.ljust(NAME_W)}  {'ШТ'.rjust(qty_w)}"
        rows = [f"{a.rjust(art_w)}  {n.ljust(NAME_W)}  {q.rjust(qty_w)}" for a, n, q in cells]

        chunk, first = [], True

        def flush():
            nonlocal chunk, first
            if chunk:
                title = header if first else f"{header}\n<i>продолжение</i>"
                blocks.append(f"{title}\n<pre>{esc(head_row)}\n" + "\n".join(esc(r) for r in chunk) + "</pre>")
                chunk, first = [], False

        size = len(head_row) + 80
        for row in rows:
            cost = len(esc(row)) + 1
            if chunk and size + cost > chunk_chars:
                flush()
                size = len(head_row) + 80
            chunk.append(row)
            size += cost
        flush()
    return blocks


def paginate_blocks(blocks: Sequence[str], limit: int = 3500) -> List[str]:
    """Склеивает блоки в страницы не длиннее limit (лимит Telegram — 4096). Длинный блок режется по строкам."""
    parts = []
    for block in blocks:
        if len(block) <= limit:
            parts.append(block)
            continue
        lines = block.split("\n")
        header, chunk = lines[0], [lines[0]]
        for line in lines[1:]:
            if len("\n".join(chunk + [line])) > limit:
                parts.append("\n".join(chunk))
                chunk = [header, "<i>продолжение</i>"]
            chunk.append(line)
        parts.append("\n".join(chunk))
    pages, current = [], ""
    for part in parts:
        if current and len(current) + 2 + len(part) > limit:
            pages.append(current)
            current = part
        else:
            current = part if not current else current + "\n\n" + part
    if current:
        pages.append(current)
    return pages or [""]


def low_stock_text(rows) -> str:
    """rows: [(артикул, название, size, qty, категория), ...] -> блоки по категориям."""
    groups = {}
    for pid, name, size, qty, category in rows:
        groups.setdefault(category or "", {}).setdefault((pid, name), []).append((size, qty))
    blocks = []
    for category in sorted(groups, key=lambda c: c.lower()):
        lines = [category_header(category)]
        for (pid, name), sizes in sorted(groups[category].items()):
            lines.append(f"{article_line(pid, name, 30)} · {stock_line(sizes)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
