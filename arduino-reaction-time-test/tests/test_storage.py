import unittest
from src.data.storage import ReactionTimeStorage
from src.data.models import ReactionTimeRecord

class TestReactionTimeStorage(unittest.TestCase):

    def setUp(self):
        self.storage = ReactionTimeStorage()
        self.test_record = ReactionTimeRecord(timestamp="2023-10-01 12:00:00", reaction_time=250)

    def test_save_reaction_time(self):
        self.storage.save_reaction_time(self.test_record)
        retrieved_record = self.storage.get_reaction_time(self.test_record.timestamp)
        self.assertEqual(retrieved_record.reaction_time, self.test_record.reaction_time)

    def test_get_reaction_time_non_existent(self):
        retrieved_record = self.storage.get_reaction_time("2023-10-01 12:01:00")
        self.assertIsNone(retrieved_record)

    def test_get_all_reaction_times(self):
        self.storage.save_reaction_time(self.test_record)
        all_records = self.storage.get_all_reaction_times()
        self.assertIn(self.test_record, all_records)

if __name__ == '__main__':
    unittest.main()