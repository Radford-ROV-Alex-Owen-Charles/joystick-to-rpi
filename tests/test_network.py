import unittest
from src.client.network_client import NetworkClient
from src.server.network_server import NetworkServer
import socket
import threading

class TestNetworkCommunication(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = NetworkServer()
        cls.server_thread = threading.Thread(target=cls.server.start)
        cls.server_thread.start()

        cls.client = NetworkClient('127.0.0.1', cls.server.port)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.server.stop()
        cls.server_thread.join()

    def test_send_receive_data(self):
        test_data = {'axis_x': 0.5, 'axis_y': -0.5}
        self.client.send_data(test_data)

        received_data = self.server.receive_data()
        self.assertEqual(received_data, test_data)

    def test_connection(self):
        self.assertTrue(self.client.is_connected())

    def test_disconnect(self):
        self.client.close()
        self.assertFalse(self.client.is_connected())

if __name__ == '__main__':
    unittest.main()