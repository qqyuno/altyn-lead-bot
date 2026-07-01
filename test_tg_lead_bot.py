import unittest

import tg_lead_bot


class CollectionReportTests(unittest.TestCase):
    def test_parses_added_and_updated_counts(self):
        output = "Done. Added 3 leads, updated 7 leads in data/leads.csv"

        self.assertEqual(tg_lead_bot.parsed_collection_counts(output, 0), (3, 7))


if __name__ == "__main__":
    unittest.main()
