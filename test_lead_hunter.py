import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lead_hunter


class TelegramContactTests(unittest.TestCase):
    def test_accepts_virtual_card_service_without_exchange_keywords(self):
        title = "Виртуальные карты Visa для международных сервисов"
        text = "Выпуск виртуальной карты Visa, оплата подписок и пополнение через СБП."

        self.assertTrue(lead_hunter.is_target_project(title, text))
        sphere, score = lead_hunter.classify_and_score(text, ["@card_manager"], ["sales@cards.example"])
        self.assertEqual(sphere, "виртуальные карты")
        self.assertGreaterEqual(score, 6)

    def test_accepts_steam_topup_service_without_crypto_keywords(self):
        title = "Пополнение баланса Steam"
        text = "Автоматическое пополнение Steam через СБП и Telegram-бота."

        self.assertTrue(lead_hunter.is_target_project(title, text))
        sphere, score = lead_hunter.classify_and_score(text, ["@steam_manager"], [])
        self.assertEqual(sphere, "игровые платежи / пополнение")
        self.assertGreaterEqual(score, 5)

    def test_rejects_editorial_steam_instruction(self):
        title = "Как пополнить Steam из России"
        text = "Обзор способов пополнения Steam и сравнение комиссий."

        self.assertFalse(lead_hunter.is_target_project(title, text))

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

    def test_upsert_adds_telegram_to_existing_project_without_duplicate(self):
        old = {
            "Название проекта": "Demo USDT Exchange",
            "Сфера": "криптообменник",
            "Telegram": "",
            "Email": "hello@demo.exchange",
            "Оценка 1-10 для покупки франшизы": "8",
        }
        fresh = {
            "Название проекта": "Demo USDT Exchange",
            "Сфера": "криптообменник",
            "Telegram": "@demo_partner",
            "Email": "sales@demo.exchange",
            "Оценка 1-10 для покупки франшизы": "10",
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leads.csv"
            lead_hunter.upsert_rows(path, [old])
            added, updated = lead_hunter.upsert_rows(path, [fresh])
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual((added, updated), (0, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Telegram"], "@demo_partner")
        self.assertIn("hello@demo.exchange", rows[0]["Email"])
        self.assertIn("sales@demo.exchange", rows[0]["Email"])
        self.assertEqual(rows[0]["Оценка 1-10 для покупки франшизы"], "10")

    def test_upsert_keeps_generic_titles_from_different_domains_separate(self):
        first = {
            "Название проекта": "Обменный пункт электронных валют",
            "Сфера": "криптообменник",
            "Telegram": "",
            "Email": "support@first.exchange",
            "Оценка 1-10 для покупки франшизы": "8",
        }
        second = {
            **first,
            "Email": "support@second.exchange",
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leads.csv"
            lead_hunter.upsert_rows(path, [first, second])
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(len(rows), 2)

    def test_accepts_email_when_telegram_is_missing(self):
        email_only = {"Telegram": "", "Email": "sales@demo.exchange"}
        with_telegram = {"Telegram": "@demo_partner", "Email": "sales@demo.exchange"}
        without_contacts = {"Telegram": "", "Email": ""}

        self.assertTrue(lead_hunter.has_required_contact(email_only))
        self.assertTrue(lead_hunter.has_required_contact(with_telegram))
        self.assertFalse(lead_hunter.has_required_contact(without_contacts))


if __name__ == "__main__":
    unittest.main()
