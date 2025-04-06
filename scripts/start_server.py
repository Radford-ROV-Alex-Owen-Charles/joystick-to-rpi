import sys
import socket
import json
from src.server.network_server import NetworkServer
from src.server.motor_controller import MotorController

def main():
    # Load server configuration
    with open('config/server_config.json') as config_file:
        config = json.load(config_file)

    server_ip = config.get('server_ip', '0.0.0.0')
    server_port = config.get('server_port', 8080)

    # Initialize motor controller
    motor_controller = MotorController()

    # Start the network server
    server = NetworkServer(server_ip, server_port, motor_controller)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("Server is shutting down.")
        server.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()