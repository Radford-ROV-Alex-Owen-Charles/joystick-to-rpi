import serial
import time
import threading
import glob
import sys
import os

class MotorController:
    """
    Motor controller for ROV that communicates with Arduino Mega over serial
    """
    
    def __init__(self, baud_rate=115200, timeout=1):
        self.serial_port = None
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.running = False
        self.lock = threading.Lock()  # For thread safety
        
        # Last known telemetry values
        self.voltage = 0.0
        self.current = 0.0
        self.depth = 0.0
        self.temperature = 0.0
        
        # Current motor states
        self.left_motor_dir = 0
        self.left_motor_speed = 0
        self.right_motor_dir = 0
        self.right_motor_speed = 0
        self.vertical_motor_dir = 0
        self.vertical_motor_speed = 0
        
        # Try to auto-connect to Arduino
        self.connect()
        
        # Start reading thread if connected
        if self.is_connected():
            self.running = True
            self.read_thread = threading.Thread(target=self.read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
    
    def find_arduino_port(self):
        """Auto-detect Arduino serial port"""
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # This excludes your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            raise EnvironmentError('Unsupported platform')
        
        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        
        # Most likely Arduino ports based on common names
        for port in result:
            if 'usb' in port.lower() or 'acm' in port.lower() or 'arduino' in port.lower():
                return port
        
        # If no obvious Arduino port, return the first one or None
        return result[0] if result else None
    
    def connect(self, port=None):
        """Connect to the Arduino"""
        try:
            if not port:
                port = self.find_arduino_port()
                if not port:
                    print("No Arduino detected. Please connect Arduino or specify port.")
                    return False
            
            self.serial_port = serial.Serial(
                port=port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            
            # Allow Arduino to reset after connection
            time.sleep(2)
            
            # Flush any pending data
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            
            print(f"Connected to Arduino on {port}")
            return True
            
        except Exception as e:
            print(f"Error connecting to Arduino: {e}")
            self.serial_port = None
            return False
    
    def is_connected(self):
        """Check if Arduino is connected"""
        return self.serial_port is not None and self.serial_port.is_open
    
    def read_loop(self):
        """Background thread to continuously read from Arduino"""
        if not self.is_connected():
            return
            
        while self.running:
            try:
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    self.process_arduino_response(line)
            except Exception as e:
                print(f"Error reading from Arduino: {e}")
                time.sleep(0.1)
    
    def process_arduino_response(self, response):
        """Process responses from Arduino"""
        if not response:
            return
            
        # Check if it's a telemetry response (starts with 'R,')
        if response.startswith('R,'):
            try:
                parts = response.split(',')
                if len(parts) >= 5:
                    with self.lock:
                        self.voltage = float(parts[1])
                        self.current = float(parts[2])
                        self.depth = float(parts[3])
                        self.temperature = float(parts[4])
            except Exception as e:
                print(f"Error parsing telemetry: {e}")
        else:
            print(f"Arduino: {response}")
    
    def send_command(self, command):
        """Send a raw command to the Arduino"""
        if not self.is_connected():
            print("Not connected to Arduino")
            return False
            
        try:
            self.serial_port.write(command.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Error sending command to Arduino: {e}")
            return False
    
    def set_left_motor(self, direction, speed):
        """Set the left motor direction and speed"""
        with self.lock:
            self.left_motor_dir = direction
            self.left_motor_speed = speed
            self._update_motors()
    
    def set_right_motor(self, direction, speed):
        """Set the right motor direction and speed"""
        with self.lock:
            self.right_motor_dir = direction
            self.right_motor_speed = speed
            self._update_motors()
    
    def set_vertical_motor(self, direction, speed):
        """Set the vertical motor direction and speed"""
        with self.lock:
            self.vertical_motor_dir = direction
            self.vertical_motor_speed = speed
            self._update_motors()
    
    def _update_motors(self):
        """Send the current motor settings to the Arduino"""
        command = f"M,{self.left_motor_dir},{self.left_motor_speed},{self.right_motor_dir},{self.right_motor_speed},{self.vertical_motor_dir},{self.vertical_motor_speed}\n"
        self.send_command(command)
    
    def stop_all_motors(self):
        """Emergency stop all motors"""
        with self.lock:
            self.left_motor_dir = 0
            self.left_motor_speed = 0
            self.right_motor_dir = 0
            self.right_motor_speed = 0
            self.vertical_motor_dir = 0
            self.vertical_motor_speed = 0
            self._update_motors()
    
    def request_telemetry(self):
        """Request telemetry data from Arduino"""
        self.send_command("S\n")
    
    def get_voltage(self):
        """Get the last known voltage"""
        with self.lock:
            return self.voltage
    
    def get_current(self):
        """Get the last known current"""
        with self.lock:
            return self.current
    
    def get_depth(self):
        """Get the last known depth"""
        with self.lock:
            return self.depth
    
    def get_temperature(self):
        """Get the last known temperature"""
        with self.lock:
            return self.temperature
    
    def close(self):
        """Close the connection to the Arduino"""
        self.running = False
        if self.serial_port:
            try:
                self.stop_all_motors()  # Safety first
                time.sleep(0.2)  # Give time for the command to be sent
                self.serial_port.close()
                print("Disconnected from Arduino")
            except Exception as e:
                print(f"Error disconnecting from Arduino: {e}")