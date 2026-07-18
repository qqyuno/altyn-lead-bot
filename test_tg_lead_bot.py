import unittest
from unittest.mock import patch

import tg_lead_bot


class CollectionReportTests(unittest.TestCase):
    def test_general_collection_prioritizes_tourist_queries(self):
        command = tg_lead_bot.collection_command(100, telegram_only=True)

        self.assertIn("--telegram-only", command)
        self.assertIn("--query-only", command)
        self.assertEqual(
            command[command.index("--priority-queries") + 1],
            str(tg_lead_bot.TOURIST_QUERIES),
        )
        self.assertEqual(command[command.index("--max-queries") + 1], "120")

    def test_parses_added_and_updated_counts(self):
        output = "Done. Added 3 leads, updated 7 leads in data/leads.csv"

        self.assertEqual(tg_lead_bot.parsed_collection_counts(output, 0), (3, 7))

    def test_work_queue_contains_only_unique_telegram_contacts(self):
        email_only = {
            "Название проекта": "Email only",
            "Telegram": "",
            "Email": "sales@example.com",
            "Оценка 1-10 для покупки франшизы": "10",
        }
        telegram_lead = {
            "Название проекта": "Telegram lead",
            "Telegram": "@telegram_lead",
            "Email": "sales@example.com",
            "Оценка 1-10 для покупки франшизы": "8",
        }

        with patch.object(tg_lead_bot, "load_rows", return_value=[email_only, telegram_lead]):
            rows = tg_lead_bot.ranked_rows()

        self.assertEqual(
            [row["Название проекта"] for row in rows],
            ["Telegram lead"],
        )

    def test_lead_keyboard_keeps_only_open_send_and_skip_actions(self):
        row = {
            "Название проекта": "Telegram lead",
            "Telegram": "@telegram_lead",
            "Email": "",
            "Оценка 1-10 для покупки франшизы": "8",
        }

        keyboard = tg_lead_bot.lead_keyboard(row)
        buttons = [button["text"] for line in keyboard["inline_keyboard"] for button in line]

        self.assertEqual(buttons, ["Открыть чат", "Отправил → следующий", "Пропустить"])

    def test_sent_today_counts_unique_contacts_for_selected_day(self):
        state = {
            "contacted": ["lead-a", "lead-b"],
            "skipped": [],
            "sent_events": [
                {"lead_id": "lead-a", "day": "2026-07-16"},
                {"lead_id": "lead-a", "day": "2026-07-16"},
                {"lead_id": "lead-b", "day": "2026-07-16"},
                {"lead_id": "lead-c", "day": "2026-07-15"},
            ],
        }

        self.assertEqual(tg_lead_bot.sent_today(state, "2026-07-16"), 2)

    def test_telegram_rows_returns_unique_contacts_in_priority_order(self):
        rows = [
            {
                "Название проекта": "Lower score",
                "Telegram": "@same_contact",
                "Email": "",
                "Оценка 1-10 для покупки франшизы": "7",
            },
            {
                "Название проекта": "Best lead",
                "Telegram": "https://t.me/best_contact",
                "Email": "",
                "Оценка 1-10 для покупки франшизы": "9",
            },
            {
                "Название проекта": "Duplicate",
                "Telegram": "https://t.me/same_contact",
                "Email": "",
                "Оценка 1-10 для покупки франшизы": "6",
            },
            {
                "Название проекта": "Email only",
                "Telegram": "",
                "Email": "sales@example.com",
                "Оценка 1-10 для покупки франшизы": "10",
            },
        ]

        with patch.object(tg_lead_bot, "load_rows", return_value=rows):
            selected = tg_lead_bot.telegram_rows(10)

        self.assertEqual(
            [row["Название проекта"] for row in selected],
            ["Best lead", "Lower score"],
        )


if __name__ == "__main__":
    unittest.main()
