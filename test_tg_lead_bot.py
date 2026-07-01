import unittest
from unittest.mock import patch

import tg_lead_bot


class CollectionReportTests(unittest.TestCase):
    def test_parses_added_and_updated_counts(self):
        output = "Done. Added 3 leads, updated 7 leads in data/leads.csv"

        self.assertEqual(tg_lead_bot.parsed_collection_counts(output, 0), (3, 7))

    def test_work_queue_hides_historical_email_only_leads(self):
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

        self.assertEqual([row["Название проекта"] for row in rows], ["Telegram lead"])


if __name__ == "__main__":
    unittest.main()
