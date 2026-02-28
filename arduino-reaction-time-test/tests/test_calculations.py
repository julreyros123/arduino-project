import unittest
from src.utils.calculations import calculate_reaction_time

class TestCalculations(unittest.TestCase):

    def test_calculate_reaction_time(self):
        # Test with a known start and end time
        start_time = 0.0
        end_time = 1.5
        expected_reaction_time = 1.5
        self.assertEqual(calculate_reaction_time(start_time, end_time), expected_reaction_time)

    def test_calculate_reaction_time_negative(self):
        # Test with end time less than start time
        start_time = 2.0
        end_time = 1.0
        expected_reaction_time = 0.0  # Assuming we return 0 for invalid input
        self.assertEqual(calculate_reaction_time(start_time, end_time), expected_reaction_time)

    def test_calculate_reaction_time_zero(self):
        # Test with both times being zero
        start_time = 0.0
        end_time = 0.0
        expected_reaction_time = 0.0
        self.assertEqual(calculate_reaction_time(start_time, end_time), expected_reaction_time)

if __name__ == '__main__':
    unittest.main()