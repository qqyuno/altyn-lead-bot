import unittest
from unittest.mock import patch

import lead_hunter


class TelegramContactTests(unittest.TestCase):
    def test_prefers_partnership_contact_over_support_channel_and_bot(self):
        page = """
        <a href="https://t.me/demo_news">Новости и курсы</a>
        <a href="https://t.me/demo_support">Техническая поддержка</a>
        <a href="https://t.me/demo_partner">Сотрудничество и партнёры</a>
        <a href="https://t.me/demo_exchange_bot">Telegram bot</a>
        """

        ranked = lead_hunter.extract_telegram_candidates(page, "https://demo.exchange/contacts")

        self.assertEqual(ranked[0][1], "@demo_partner")

    def test_understands_tg_resolve_links(self):
        page = '<a href="tg://resolve?domain=demo_manager">Связаться с менеджером</a>'

        ranked = lead_hunter.extract_telegram_candidates(page, "https://demo.exchange")

        self.assertEqual(ranked[0][1], "@demo_manager")

    def test_uses_support_as_fallback_when_it_is_the_only_contact(self):
        page = '<a href="https://t.me/demo_support">Поддержка</a>'

        ranked = lead_hunter.extract_telegram_candidates(page, "https://demo.exchange")

        self.assertEqual(ranked[0][1], "@demo_support")

    def test_scans_contact_page_even_when_homepage_has_email(self):
        pages = {
            "https://demo.exchange": """
                <title>Demo USDT Exchange</title>
                <p>Обмен USDT TRC20 на RUB и СБП.</p>
                <a href="mailto:hello@demo.exchange">Email</a>
                <a href="/contacts">Контакты</a>
            """,
            "https://demo.exchange/contacts": """
                <title>Контакты Demo Exchange</title>
                <a href="https://t.me/demo_news">Новости</a>
                <a href="https://t.me/demo_support">Поддержка</a>
                <a href="https://t.me/demo_partner">Партнёрство</a>
            """,
        }

        with patch.object(lead_hunter, "fetch", side_effect=lambda url, timeout=5: pages.get(url, "")):
            row = lead_hunter.scan_site("https://demo.exchange", scan_pages=4)

        self.assertEqual(row["Telegram"], "@demo_partner")
        self.assertIn("hello@demo.exchange", row["Email"])

    def test_opens_internal_telegram_news_page_as_fallback(self):
        pages = {
            "https://demo.exchange": """
                <title>Demo USDT Exchange</title>
                <p>Обмен USDT TRC20 на RUB.</p>
                <a href="/telegram-news">Наши каналы в Telegram</a>
            """,
            "https://demo.exchange/telegram-news": """
                <title>Telegram Demo Exchange</title>
                <a href="https://t.me/demo_public">Telegram</a>
            """,
        }

        with patch.object(lead_hunter, "fetch", side_effect=lambda url, timeout=5: pages.get(url, "")):
            row = lead_hunter.scan_site("https://demo.exchange", scan_pages=3)

        self.assertEqual(row["Telegram"], "@demo_public")


if __name__ == "__main__":
    unittest.main()
