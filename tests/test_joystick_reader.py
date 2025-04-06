import unittest
from src.client.joystick_reader import JoystickReader

class TestJoystickReader(unittest.TestCase):
    def setUp(self):
        self.joystick_reader = JoystickReader()

    def test_read_joystick_input(self):
        # Simulate joystick input and test the output
        self.joystick_reader.read_joystick_input()
        # Assuming the read_joystick_input method updates some internal state
        # Check if the internal state reflects expected joystick input
        self.assertIsNotNone(self.joystick_reader.joystick_data)

    def test_process_input(self):
        # Simulate joystick input data
        test_input = {'x': 0.5, 'y': -0.5}
        processed_data = self.joystick_reader.process_input(test_input)
        # Check if the processed data is as expected
        self.assertEqual(processed_data['x'], 0.5)
        self.assertEqual(processed_data['y'], -0.5)

if __name__ == '__main__':
    unittest.main()