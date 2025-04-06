class NetworkClient:
    def __init__(self, server_ip, server_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = None

    def connect(self):
        import socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.server_ip, self.server_port))

    def send_data(self, data):
        if self.socket:
            self.socket.sendall(data.encode('utf-8'))

    def close(self):
        if self.socket:
            self.socket.close()