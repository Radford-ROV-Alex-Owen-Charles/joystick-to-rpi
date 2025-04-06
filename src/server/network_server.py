import socket
import json
import threading
import time
from src.server.motor_controller import MotorController
from src.common.protocol import Protocol

class ROVServer:
    def __init__(self, host='0.0.0.0', control_port=5000, video_port=5001):
        self.host = host
        self.control_port = control_port
        self.video_port = video_port
        self.control_socket = None
        self.video_socket = None
        self.client_socket = None
        self.motor_controller = MotorController()
        self.running = False
        self.protocol = Protocol()
        
        # For watchdog functionality
        self.last_command_time = 0
        self.watchdog_timeout = 1.0  # seconds
        
    def start(self):
        self.running = True
        
        # Start the control server in a separate thread
        control_thread = threading.Thread(target=self.start_control_server)
        control_thread.daemon = True
        control_thread.start()
        
        # Start the video server in a separate thread
        video_thread = threading.Thread(target=self.start_video_server)
        video_thread.daemon = True
        video_thread.start()
        
        # Start the watchdog in a separate thread
        watchdog_thread = threading.Thread(target=self.watchdog_loop)
        watchdog_thread.daemon = True
        watchdog_thread.start()
        
        print(f"ROV server started on {self.host}")
        print(f"Control port: {self.control_port}")
        print(f"Video port: {self.video_port}")

    def start_control_server(self):
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.control_socket.bind((self.host, self.control_port))
        self.control_socket.listen(1)
        print(f"Control server listening on {self.host}:{self.control_port}")

        while self.running:
            try:
                client_socket, addr = self.control_socket.accept()
                print(f"Control connection from {addr}")
                self.receive_control_data(client_socket)
            except Exception as e:
                print(f"Control server error: {e}")
                time.sleep(1)  # Prevent tight loop if continuous errors

    def start_video_server(self):
        # This would be implemented with a video streaming library like opencv or picamera
        # For simplicity, just showing the structure here
        print("Video streaming server would start here")
        # Video streaming implementation

    def receive_control_data(self, client_socket):
        while self.running:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                # Update the last command time for the watchdog
                self.last_command_time = time.time()
                
                # Decode and process the command
                control_data = self.protocol.decode_control_command(data)
                if control_data:
                    self.process_control_data(control_data)
                    
                    # Send telemetry data back to the client
                    telemetry = self.get_telemetry()
                    telemetry_data = self.protocol.encode_telemetry(telemetry)
                    client_socket.send(telemetry_data)
                    
            except Exception as e:
                print(f"Error receiving control data: {e}")
                break

        client_socket.close()
        print("Control connection closed")

    def process_control_data(self, control_data):
        print(f"Processing control data: {control_data}")
        
        # Extract and apply motor commands
        left_motor = control_data.get('left_motor', {})
        right_motor = control_data.get('right_motor', {})
        vertical_motor = control_data.get('vertical_motor', {})
        
        # Send commands to the motor controller
        self.motor_controller.set_left_motor(
            left_motor.get('direction', 0),
            left_motor.get('speed', 0)
        )
        
        self.motor_controller.set_right_motor(
            right_motor.get('direction', 0),
            right_motor.get('speed', 0)
        )
        
        self.motor_controller.set_vertical_motor(
            vertical_motor.get('direction', 0),
            vertical_motor.get('speed', 0)
        )

    def get_telemetry(self):
        # Get sensor data and other telemetry
        return {
            'voltage': self.motor_controller.get_voltage(),
            'current': self.motor_controller.get_current(),
            'depth': self.motor_controller.get_depth(),
            'temperature': self.motor_controller.get_temperature(),
            'timestamp': time.time()
        }

    def watchdog_loop(self):
        """Safety watchdog that stops motors if no commands received for a while"""
        while self.running:
            if time.time() - self.last_command_time > self.watchdog_timeout:
                print("Watchdog: No commands received recently, stopping motors")
                self.motor_controller.stop_all_motors()
            time.sleep(0.1)  # Check 10 times per second

    def stop(self):
        self.running = False
        if self.control_socket:
            self.control_socket.close()
        if self.video_socket:
            self.video_socket.close()
        print("ROV server stopped")

if __name__ == "__main__":
    server = ROVServer()
    try:
        server.start()
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutdown requested...")
    finally:
        server.stop()