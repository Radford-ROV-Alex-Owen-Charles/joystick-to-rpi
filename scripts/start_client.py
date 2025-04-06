import json
import socket
import pygame
import time
from src.client.joystick_reader import JoystickReader
from src.client.network_client import NetworkClient

def main():
    # Initialize Pygame for joystick input
    pygame.init()
    
    # Load client configuration
    with open('config/client_config.json') as config_file:
        config = json.load(config_file)
    
    server_ip = config['server_ip']
    server_port = config['server_port']
    
    # Create joystick reader and network client
    joystick_reader = JoystickReader()
    network_client = NetworkClient(server_ip, server_port)
    
    # Connect to the server
    network_client.connect()
    
    try:
        while True:
            # Read joystick inputs
            joystick_data = joystick_reader.read_inputs()
            
            # Send joystick data to the server
            network_client.send_data(joystick_data)
            
            # Delay to limit the sending rate
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Client stopped.")
    finally:
        network_client.disconnect()
        pygame.quit()

if __name__ == "__main__":
    main()