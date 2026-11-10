import unittest

from config import DEFAULT_ABOUT, DEFAULT_TAGLINE, load_config, normalize_contact, parse_admin_ids
from utils import (
    MAX_LOOK_ITEMS, NAME_W, article_line, button_label, catalog_tables, category_header, clamp, esc, low_stock_text,
    paginate_blocks, stock_status, format_price, format_ts, look_text, normalize_size, parse_args, parse_quick,
    parse_sizes, plural, product_caption, sizes_block, stock_line, truncate,
)


class TestFormatting(unittest.TestCase):
    def test_price(self):
        self.assertEqual(format_price(12990), "12\u00a0990\u00a0₽")
        self.assertEqual(format_price(0), "0\u00a0₽")
        self.assertEqual(format_price(1500000), "1\u00a0500\u00a0000\u00a0₽")
        self.assertEqual(format_price(None), "—")

    def test_esc(self):
        self.assertEqual(esc("a<b>&c"), "a&lt;b&gt;&amp;c")
        self.assertEqual(esc(None), "")
        self.assertEqual(esc("T_shirt *x*"), "T_shirt *x*")

    def test_truncate(self):
        self.assertEqual(truncate("abc", 5), "abc")
        self.assertEqual(truncate("abcdefgh", 5), "abcd…")
        self.assertEqual(truncate(None, 5), "")

    def test_clamp(self):
        self.assertEqual(clamp(5, 3), 2)
        self.assertEqual(clamp(-1, 3), 0)
        self.assertEqual(clamp(1, 0), 0)


class TestParseArgs(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(parse_args("tg:5:2:0", "tg", 3), (5, 2, 0))
        self.assertEqual(parse_args("a:dc:7", "a:dc", 1), (7,))

    def test_bad_input_returns_none(self):
        self.assertIsNone(parse_args("tg:5:2", "tg", 3))
        self.assertIsNone(parse_args("tg:x:2:0", "tg", 3))
        self.assertIsNone(parse_args("cat:1", "pg", 1))
        self.assertIsNone(parse_args(None, "pg", 1))
        self.assertIsNone(parse_args("a:dcy:1", "a:dc", 1))  # префиксы не путаются


class TestTexts(unittest.TestCase):
    def test_caption_escapes_html(self):
        text = product_caption("Куртка <Zara> & Co", "тёплая_*куртка*", 4990)
        self.assertIn("&lt;Zara&gt; &amp; Co", text)
        self.assertIn("4\u00a0990\u00a0₽", text)
        self.assertNotIn("<Zara>", text)

    def test_caption_without_description(self):
        text = product_caption("A", "", 1)
        self.assertNotIn("\n\n\n", text)
        self.assertNotIn("blockquote", text)

    def test_caption_layout(self):
        text = product_caption("Парка", "тёплая", 4990, "Куртки")
        self.assertEqual(
            text,
            "<i>Куртки</i>\n<b>Парка</b>\n\n<blockquote>тёплая</blockquote>\n\n<b>4\u00a0990\u00a0₽</b>",
        )

    def test_caption_escapes_category(self):
        self.assertIn("&lt;x&gt;", product_caption("A", "d", 1, "<x>"))

    def test_caption_fits_telegram_limit(self):
        self.assertLess(len(product_caption("N" * 500, "D" * 5000, 10 ** 6)), 1024)

    def test_look_text_total(self):
        items = [(1, "Парка", 5000, 10), (2, "Шарф", 1500, 11)]
        text = look_text(items)
        self.assertIn("1 · Парка — 5\u00a0000\u00a0₽", text)
        self.assertIn("2 · Шарф — 1\u00a0500\u00a0₽", text)
        self.assertIn("<b>Сумма образа · 6\u00a0500\u00a0₽</b>", text)
        self.assertIn("<i>2 вещи</i>", text)

    def test_look_text_handles_missing_price(self):
        self.assertIn("1\u00a0000\u00a0₽", look_text([(1, "A", None, 1), (2, "B", 1000, 2)]))

    def test_max_look_items_fits_button_limit(self):
        self.assertLessEqual(MAX_LOOK_ITEMS + 1, 100)  # Telegram: максимум 100 кнопок


class TestSizes(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_size(" xl "), "XL")
        self.assertEqual(normalize_size("М"), "M")        # кириллическая М
        self.assertEqual(normalize_size("ХL"), "XL")      # кириллическая Х + латинская L
        self.assertEqual(normalize_size("42"), "42")
        self.assertEqual(normalize_size("2XL"), "2XL")
        for bad in ("", "toolongsize", "S M", "Ю", "<b>"):
            self.assertIsNone(normalize_size(bad), bad)

    def test_parse_sizes_ok(self):
        self.assertEqual(parse_sizes("S2 M3 xl10"), [("S", 2), ("M", 3), ("XL", 10)])
        self.assertEqual(parse_sizes("42:2, 43:1"), [("42", 2), ("43", 1)])
        self.assertEqual(parse_sizes("2XL:4 ХL0"), [("2XL", 4), ("XL", 0)])
        self.assertEqual(parse_sizes("М2 L1"), [("M", 2), ("L", 1)])
        self.assertEqual(parse_sizes("S=1;M=2"), [("S", 1), ("M", 2)])

    def test_parse_sizes_errors(self):
        for bad in ("", "   ", "S", "S M", "42 2", "S2 S3", "S-1", "S99999", "<b>2"):
            with self.assertRaises(ValueError, msg=bad):
                parse_sizes(bad)
        with self.assertRaises(ValueError):
            parse_sizes(" ".join(f"A{i}:1" for i in range(21)))

    def test_parse_quick(self):
        self.assertEqual(parse_quick("12 M"), (12, "M", -1))
        self.assertEqual(parse_quick("12 м 2"), (12, "M", -2))
        self.assertEqual(parse_quick("№12 xl -3"), (12, "XL", -3))
        self.assertEqual(parse_quick("12 M +3"), (12, "M", 3))
        self.assertEqual(parse_quick("  7   42  "), (7, "42", -1))
        for bad in ("12", "M 12", "12 M 0", "12 M +0", "привет", "12 M extra", "12 toolongsize"):
            self.assertIsNone(parse_quick(bad), bad)

    def test_quick_regex_gate_matches_parser(self):
        import re
        from utils import QUICK_RE
        for text in ("12 M", "12 M 2", "№5 XL +1", "привет", "12", "12 M extra"):
            self.assertEqual(bool(re.match(QUICK_RE, text)), parse_quick(text) is not None, text)

    def test_sizes_block(self):
        self.assertEqual(sizes_block([]), "")
        self.assertEqual(sizes_block([("S", 5), ("M", 5)]), "S  ·  M")
        self.assertEqual(sizes_block([("S", 5), ("M", 1), ("L", 0)]),
                         "S  ·  M  ·  <s>L</s>\n<i>Осталось мало: M</i>")
        self.assertEqual(sizes_block([("S", 0), ("M", 0)]), "<b>Нет в наличии</b>")

    def test_one_size_is_hidden_from_customers(self):
        self.assertEqual(sizes_block([("ONE", 9)]), "")                           # достаточно — ничего не показываем
        self.assertEqual(sizes_block([("ONE", 3)]), "")
        self.assertEqual(sizes_block([("ONE", 2)]), "<i>Осталось мало</i>")
        self.assertEqual(sizes_block([("ONE", 1)]), "<i>Осталось мало</i>")
        self.assertEqual(sizes_block([("ONE", 0)]), "<b>Нет в наличии</b>")
        self.assertNotIn("ONE", product_caption("Сумка", "d", 100, "Сумки", sizes=[("ONE", 1)], product_id=5))
        self.assertIn("Нет в наличии", product_caption("Сумка", "d", 100, sizes=[("ONE", 0)]))

    def test_one_size_only_special_when_it_is_the_single_size(self):
        self.assertEqual(sizes_block([("ONE", 5), ("M", 5)]), "ONE  ·  M")        # смешанный список — обычный вид

    def test_one_size_for_admin_and_table(self):
        self.assertEqual(stock_line([("ONE", 5)]), "без размера · 5 шт.")
        self.assertEqual(parse_sizes("ONE5"), [("ONE", 5)])
        self.assertEqual(parse_quick("12 one"), (12, "ONE", -1))
        self.assertEqual(parse_quick("12 ONE +5"), (12, "ONE", 5))
        table = catalog_tables([("Сумки", [(7, "Шоппер", [("ONE", 14)]), (8, "Клатч", [("ONE", 0)])])])[0]
        self.assertIn("  7  Шоппер", table); self.assertIn("14", table); self.assertNotIn("ONE", table)   # в таблице — просто число штук

    def test_stock_line(self):
        self.assertEqual(stock_line([("S", 2), ("M", 0)]), "S 2  ·  M 0")
        self.assertEqual(stock_line([]), "размеры не заведены")

    def test_caption_with_sizes_and_article(self):
        text = product_caption("Парка", "тёплая", 4990, "Куртки", sizes=[("S", 3), ("M", 0)], product_id=12)
        self.assertEqual(
            text,
            "<i>Куртки</i>\n<b>Парка</b>\n\n<blockquote>тёплая</blockquote>\n\n"
            "S  ·  <s>M</s>\n\n<b>4\u00a0990\u00a0₽</b>  ·  <i>арт. 12</i>",
        )

    def test_caption_sold_out(self):
        self.assertIn("<b>Нет в наличии</b>", product_caption("A", "d", 1, sizes=[("S", 0)]))

    def test_format_ts(self):
        self.assertEqual(format_ts("2026-10-20 14:05:00", 3), "20.10 17:05")
        self.assertEqual(format_ts("2026-10-20 23:30:00", 3), "21.10 02:30")
        self.assertEqual(format_ts("garbage", 3), "garbage")


class TestAdminFormat(unittest.TestCase):
    def test_header_and_lines(self):
        self.assertEqual(category_header("Куртки"), "<b>КУРТКИ</b>")
        self.assertEqual(category_header(None), "<b>БЕЗ КАТЕГОРИИ</b>")
        self.assertEqual(category_header("A<b>&"), "<b>A&lt;B&gt;&amp;</b>")
        self.assertEqual(article_line(12, "Парка"), "<code>12</code> - Парка")
        self.assertEqual(article_line(12, "A<b>"), "<code>12</code> - A&lt;b&gt;")
        self.assertEqual(button_label(12, "Парка"), "12 - Парка")
        self.assertLessEqual(len(button_label(10 ** 9, "я" * 99)), 36)
        self.assertEqual(button_label(7, "Парка"), "7 - Парка")

    def test_stock_status(self):
        self.assertEqual(stock_status([]), "")
        self.assertEqual(stock_status([("S", 9), ("M", 9)]), "")
        self.assertEqual(stock_status([("S", 9), ("M", 2)]), "low")
        self.assertEqual(stock_status([("S", 9), ("M", 0)]), "low")
        self.assertEqual(stock_status([("S", 0), ("M", 0)]), "out")

    def test_catalog_tables_exact_format(self):
        blocks = catalog_tables([
            ("Куртки", [(12, "Парка", [("S", 2), ("M", 9)]), (13, "Тренч", []), (14, "Пуховик", [("S", 0)])]),
            ("Обувь", []),
        ])
        self.assertEqual(blocks[0], "\n".join([
            "<b>КУРТКИ</b>",
            "<pre>АРТ  НАЗВАНИЕ            ШТ",
            " 12  Парка               11",
            " 13  Тренч                —",
            " 14  Пуховик              0</pre>",
        ]))
        self.assertEqual(blocks[1], "<b>ОБУВЬ</b>\n<i>пока пусто</i>")

    def test_table_rows_are_aligned_and_fit_the_screen(self):
        groups = [("К", [(1, "Короткое", [("S", 5)]), (22, "Очень длинное название товара", []),
                         (333, "ё" * 30, [("M", 1), ("L", 0)]), (123456, "x", [("S", 100)])])]
        pre = catalog_tables(groups)[0].split("<pre>")[1].split("</pre>")[0]
        widths = {len(line) for line in pre.split("\n")}
        self.assertEqual(len(widths), 1, pre)                       # все строки одной ширины — столбцы ровные
        self.assertLessEqual(widths.pop(), 6 + 2 + NAME_W + 2 + 4)  # и не шире экрана телефона
        self.assertIn("…", pre)                                     # длинные названия обрезаны
        self.assertNotIn("!", pre)                                  # никаких значков — только числа

    def test_table_escapes_html_and_collapses_whitespace(self):
        block = catalog_tables([("A<b>", [(1, "X<script>&\nY", [])])])[0]
        self.assertIn("<b>A&lt;B&gt;</b>", block)
        self.assertNotIn("<script>", block)
        self.assertIn("X&lt;script&gt;&amp; Y", block)             # перенос строки в названии не ломает таблицу

    def test_table_chunks_keep_tags_balanced_and_lose_no_rows(self):
        items = [(i, "Товар & номер %d" % i, [("S", i % 4)]) for i in range(1, 401)]
        blocks = catalog_tables([("Куртки", items)], chunk_chars=800)
        self.assertGreater(len(blocks), 5)
        for block in blocks:
            self.assertLessEqual(len(block), 800)
            self.assertEqual(block.count("<pre>"), 1); self.assertEqual(block.count("</pre>"), 1)
            self.assertTrue(block.startswith("<b>КУРТКИ</b>")); self.assertIn("АРТ  НАЗВАНИЕ", block)
        self.assertTrue(all("продолжение" in b for b in blocks[1:])); self.assertNotIn("продолжение", blocks[0])
        self.assertEqual(sum(b.count("Товар &amp; номер") for b in blocks), 400)

    def test_table_chunk_limit_holds_for_names_that_expand_when_escaped(self):
        items = [(i, "&" * 40, []) for i in range(1, 80)]
        for block in catalog_tables([("К", items)], chunk_chars=1000):
            self.assertLessEqual(len(block), 1000)

    def test_table_pages_via_paginate_never_split_a_table(self):
        groups = [(f"Категория {k}", [(i, "Товар %d" % i, [("S", 3)]) for i in range(1, 70)]) for k in range(6)]
        pages = paginate_blocks(catalog_tables(groups), 3000)
        self.assertGreater(len(pages), 1)
        for page in pages:
            self.assertLessEqual(len(page), 3000); self.assertEqual(page.count("<pre>"), page.count("</pre>"))

    def test_paginate_blocks(self):
        self.assertEqual(paginate_blocks([]), [""])
        self.assertEqual(paginate_blocks(["a", "b"]), ["a\n\nb"])
        pages = paginate_blocks(["x" * 60, "y" * 60, "z" * 60], limit=100)
        self.assertEqual(pages, ["x" * 60, "y" * 60, "z" * 60])           # не помещаются вместе — отдельные страницы
        self.assertTrue(all(len(p) <= 100 for p in pages))

    def test_paginate_splits_a_huge_category_and_loses_nothing(self):
        lines = [f"<code>{i}</code> - Товар {i}" for i in range(300)]
        block = "\n".join(["<b>КУРТКИ</b>"] + lines)
        pages = paginate_blocks([block], limit=500)
        self.assertGreater(len(pages), 3)
        self.assertTrue(all(len(p) <= 500 for p in pages))
        self.assertTrue(all(p.startswith("<b>КУРТКИ</b>") for p in pages))             # заголовок на каждой странице
        self.assertEqual("\n".join(pages).count("Товар"), 300)                         # ни одна строка не потеряна

    def test_low_stock_text_groups_by_category_and_product(self):
        rows = [(12, "Парка", "M", 0, "Куртки"), (12, "Парка", "S", 1, "Куртки"), (20, "Ботинки", "42", 2, "Обувь")]
        self.assertEqual(low_stock_text(rows), "\n".join([
            "<b>КУРТКИ</b>", "<code>12</code> - Парка · M 0  ·  S 1", "", "<b>ОБУВЬ</b>", "<code>20</code> - Ботинки · 42 2",
        ]))
        self.assertEqual(low_stock_text([]), "")


class TestPlural(unittest.TestCase):
    def test_forms(self):
        forms = ("вещь", "вещи", "вещей")
        expected = {1: "вещь", 2: "вещи", 4: "вещи", 5: "вещей", 11: "вещей", 12: "вещей",
                    14: "вещей", 20: "вещей", 21: "вещь", 22: "вещи", 101: "вещь", 111: "вещей"}
        for n, word in expected.items():
            self.assertEqual(plural(n, forms), word, n)


class TestConfig(unittest.TestCase):
    def test_ok(self):
        cfg = load_config({"BOT_TOKEN": " 1:abc ", "ADMIN_ID": "42", "PROXY_URL": ""})
        self.assertEqual((cfg.token, cfg.admin_id, cfg.proxy, cfg.welcome_photo), ("1:abc", 42, None, None))

    def test_brand_defaults(self):
        brand = load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": "1"}).brand
        self.assertEqual((brand.name, brand.tagline, brand.about, brand.contact_url),
                         ("Outfit", DEFAULT_TAGLINE, DEFAULT_ABOUT, None))

    def test_brand_from_env(self):
        brand = load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": "1", "BRAND_NAME": " Atelier 9 ",
                             "BRAND_TAGLINE": "Одежда с характером", "BRAND_ABOUT": "Первая строка\\nВторая",
                             "CONTACT_URL": "@atelier9"}).brand
        self.assertEqual(brand.name, "Atelier 9")
        self.assertEqual(brand.tagline, "Одежда с характером")
        self.assertEqual(brand.about, "Первая строка\nВторая")
        self.assertEqual(brand.contact_url, "https://t.me/atelier9")

    def test_normalize_contact(self):
        self.assertEqual(normalize_contact("https://example.com/x"), "https://example.com/x")
        self.assertEqual(normalize_contact("tg://resolve?domain=shop"), "tg://resolve?domain=shop")
        self.assertEqual(normalize_contact("@shop"), "https://t.me/shop")
        for bad in ("", "   ", "@", "shop", "javascript:alert(1)", "t.me/shop"):
            self.assertIsNone(normalize_contact(bad), bad)

    def test_parse_admin_ids(self):
        self.assertEqual(parse_admin_ids("42"), (42,))
        self.assertEqual(parse_admin_ids("111, 222;333 222"), (111, 222, 333))   # дубли убираются
        for bad in ("", "  ", "abc", "1,x", "-5", "1.5", "１２"):
            self.assertEqual(parse_admin_ids(bad), (), bad)

    def test_several_admins_and_timezone(self):
        cfg = load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": "111, 222", "TZ_OFFSET": "-5"})
        self.assertEqual(cfg.admin_ids, (111, 222)); self.assertEqual(cfg.admin_id, 111); self.assertEqual(cfg.tz_offset, -5)
        self.assertEqual(load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": "1"}).tz_offset, 3)

    def test_bad_timezone(self):
        for bad in ("x", "15", "-13", "2.5"):
            with self.assertRaises(SystemExit, msg=bad):
                load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": "1", "TZ_OFFSET": bad})

    def test_catalog_mode(self):
        base = {"BOT_TOKEN": "1:abc", "ADMIN_ID": "1"}
        self.assertEqual(load_config(base).catalog_mode, "carousel")
        self.assertEqual(load_config({**base, "CATALOG_MODE": " FEED "}).catalog_mode, "feed")
        self.assertEqual(load_config({**base, "CATALOG_MODE": ""}).catalog_mode, "carousel")
        with self.assertRaises(SystemExit):
            load_config({**base, "CATALOG_MODE": "grid"})

    def test_missing_token(self):
        with self.assertRaises(SystemExit):
            load_config({"ADMIN_ID": "42"})

    def test_bad_admin_id(self):
        for bad in ("", "abc", "12.5", "-1"):
            with self.assertRaises(SystemExit, msg=bad):
                load_config({"BOT_TOKEN": "1:abc", "ADMIN_ID": bad})


if __name__ == "__main__":
    unittest.main()
