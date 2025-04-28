import socket
import json
import pygame
import time
import sys
import struct
import threading
import math
import subprocess
from pygame.locals import *
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

class OmniDirectionalControl:
    def __init__(self):
        """Initialize the omnidirectional control system"""
        # Controller deadzone
        self.stick_dead_zone = 0.1
        self.trigger_dead_zone = 0.1
        
        # Calibration offsets
        self.left_stick_x_offset = 0.0
        self.left_stick_y_offset = 0.0
        self.right_stick_x_offset = 0.0
        
        # Motor mapping (45 degree corner positions)
        # Each motor contributes to movement in specific directions
        self.motor_mapping = {
            'front_left': {'x': -1, 'y': 1, 'rotation': 1},   # Front left motor
            'front_right': {'x': 1, 'y': 1, 'rotation': -1},  # Front right motor
            'rear_left': {'x': -1, 'y': -1, 'rotation': -1},  # Rear left motor
            'rear_right': {'x': 1, 'y': -1, 'rotation': 1}    # Rear right motor
        }
        
        # Motor output values normalized from -1.0 to 1.0
        self.motor_outputs = {
            'front_left': 0,
            'front_right': 0,
            'rear_left': 0,
            'rear_right': 0,
            'vertical': 0  # Vertical motor for up/down
        }
        
        # Direction and speed format (for the server)
        self.motor_commands = {
            'front_left_motor': {'direction': 0, 'speed': 0},
            'front_right_motor': {'direction': 0, 'speed': 0},
            'rear_left_motor': {'direction': 0, 'speed': 0},
            'rear_right_motor': {'direction': 0, 'speed': 0},
            'vertical_motor': {'direction': 0, 'speed': 0}
        }

    def process_input(self, joystick, rov_rotation=0):
        """Process joystick input and calculate motor values for omnidirectional movement"""
        if not joystick:
            return self.motor_commands
        
        # Update pygame events
        pygame.event.pump()
        
        # Get raw movement vectors from joystick
        # Forward/backward from left stick Y-axis (inverted)
        raw_forward = -joystick.get_axis(1) - self.left_stick_y_offset
        # Left/right strafe from left stick X-axis
        raw_strafe = joystick.get_axis(0) - self.left_stick_x_offset
        # Rotation from right stick X-axis
        rotation = joystick.get_axis(2) - self.right_stick_x_offset
        
        # Apply deadzone to sticks
        raw_forward = 0 if abs(raw_forward) < self.stick_dead_zone else raw_forward
        raw_strafe = 0 if abs(raw_strafe) < self.stick_dead_zone else raw_strafe
        rotation = 0 if abs(rotation) < self.stick_dead_zone else rotation
        
        # Convert ROV rotation to radians
        rotation_rad = math.radians(rov_rotation)
        
        # Rotate the input based on ROV orientation
        # This makes forward always relative to the ROV's current facing
        forward = raw_forward * math.cos(rotation_rad) - raw_strafe * math.sin(rotation_rad)
        strafe = raw_forward * math.sin(rotation_rad) + raw_strafe * math.cos(rotation_rad)
        
        # Get vertical movement from triggers
        vertical = 0
        if joystick.get_numaxes() > 4:
            # L2 trigger for down
            l2_trigger = (joystick.get_axis(4) + 1) / 2  # Convert -1 to 1 range to 0 to 1
            # R2 trigger for up
            r2_trigger = (joystick.get_axis(5) + 1) / 2 if joystick.get_numaxes() > 5 else 0
            
            # Apply deadzone to triggers
            l2_trigger = 0 if l2_trigger < self.trigger_dead_zone else l2_trigger
            r2_trigger = 0 if r2_trigger < self.trigger_dead_zone else r2_trigger
            
            # Calculate vertical movement (positive = up, negative = down)
            vertical = r2_trigger - l2_trigger
        
        # Calculate base motor values for omnidirectional movement
        for motor, mapping in self.motor_mapping.items():
            # Combine all movement components with proper direction for each motor
            self.motor_outputs[motor] = (
                forward * mapping['y'] +  # Y contribution (forward/backward)
                strafe * mapping['x'] +   # X contribution (left/right)
                rotation * mapping['rotation']  # Rotation contribution
            )
        
        # Set vertical motor
        self.motor_outputs['vertical'] = vertical
        
        # Normalize motor values if any exceed 1.0
        max_value = max(abs(value) for value in self.motor_outputs.values())
        if max_value > 1.0:
            for motor in self.motor_outputs:
                self.motor_outputs[motor] /= max_value
        
        # Convert normalized values (-1.0 to 1.0) to direction/speed format
        for motor in self.motor_mapping:
            output = self.motor_outputs[motor]
            cmd_motor = f"{motor}_motor"
            
            # Motor direction: 1 for positive, 0 for negative
            direction = 1 if output >= 0 else 0
            
            # Motor speed: absolute value mapped to 0-255
            speed = int(abs(output) * 255)
            
            self.motor_commands[cmd_motor] = {
                'direction': direction,
                'speed': speed
            }
        
        # Handle vertical motor
        vertical_output = self.motor_outputs['vertical']
        self.motor_commands['vertical_motor'] = {
            'direction': 1 if vertical_output >= 0 else 0,
            'speed': int(abs(vertical_output) * 255)
        }
        
        return self.motor_commands

class ROVServiceListener:
    def __init__(self):
        self.found_services = []
        self.discovery_complete = threading.Event()
    
    def remove_service(self, zeroconf, type, name):
        pass
    
    def update_service(self, zeroconf, type, name):
        # This method is required by Zeroconf
        pass
    
    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            if len(info.addresses) > 0:
                server_ip = socket.inet_ntoa(info.addresses[0])
                server_port = info.port
                self.found_services.append((server_ip, server_port, name))
                print(f"Found ROV service: {name} at {server_ip}:{server_port}")

class ROVClient:
    def __init__(self, server_ip="192.168.0.201", server_port=5000):
        # Network settings
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = None
        self.connected = False
        
        # Joystick settings
        self.joystick = None
        self.stick_dead_zone = 0.1
        self.trigger_dead_zone = 0.1
        
        # Movement state
        self.rov_rotation = 0
        self.horizontal_movement = [0, 0]
        self.vertical_movement = 0
        
        # Motor states and control
        self.motor_commands = {
            'front_left_motor': {'direction': 0, 'speed': 0},
            'front_right_motor': {'direction': 0, 'speed': 0},
            'rear_left_motor': {'direction': 0, 'speed': 0},
            'rear_right_motor': {'direction': 0, 'speed': 0},
            'vertical_motor': {'direction': 0, 'speed': 0}
        }
        
        # Create omnidirectional control system
        self.omni_control = OmniDirectionalControl()
        
        # Telemetry data received from server
        self.telemetry = {
            'voltage': 0.0,
            'current': 0.0,
            'depth': 0.0,
            'temperature': 0.0,
            'timestamp': 0.0
        }
        
        # Initialize pygame
        pygame.init()
        pygame.joystick.init()
        
        # UI Colors
        self.colors = {
            'background': (30, 30, 40),
            'text': (255, 255, 255),
            'warning': (255, 100, 100),
            'success': (100, 255, 100),
            'rov_body': (100, 100, 200),
            'rov_highlight': (150, 150, 255),
            'grid': (60, 60, 80),
            'motor_off': (50, 50, 50),
            'motor_low': (0, 255, 0),
            'motor_high': (255, 0, 0)
        }
    
    def initialize_visualization(self):
        """Initialize 2D visualization"""
        # Set up display
        self.screen_width, self.screen_height = 1000, 700
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("ROV Control - 2D Visualization")
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.title_font = pygame.font.SysFont('Arial', 24)
        self.info_font = pygame.font.SysFont('Arial', 18)
        self.small_font = pygame.font.SysFont('Arial', 14)
    
    def connect_to_server(self):
        """Connect to the ROV server"""
        try:
            print(f"Attempting to connect to {self.server_ip}:{self.server_port}...")
            
            # Create socket with timeout
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # Longer timeout for direct connections
            
            # Try to connect
            self.socket.connect((self.server_ip, self.server_port))
            self.connected = True
            print(f"Successfully connected to server at {self.server_ip}:{self.server_port}")
            
            # Start receiving thread
            recv_thread = threading.Thread(target=self.receive_data)
            recv_thread.daemon = True
            recv_thread.start()
            
            return True
        except Exception as e:
            print(f"Error connecting to server: {e}")
            if self.socket:
                self.socket.close()
            self.socket = None
            self.connected = False
            return False
    
    def connect_to_joystick(self, joystick_id=0):
        """Initialize the joystick"""
        if pygame.joystick.get_count() == 0:
            print("No joystick detected")
            return False
        
        try:
            self.joystick = pygame.joystick.Joystick(joystick_id)
            self.joystick.init()
            print(f"Connected to joystick: {self.joystick.get_name()}")
            return True
        except Exception as e:
            print(f"Error initializing joystick: {e}")
            return False
    
    def read_joystick(self):
        """Read joystick inputs and convert to motor commands using omnidirectional control"""
        if not self.joystick:
            return False
        
        # Process joystick input with omnidirectional control
        self.motor_commands = self.omni_control.process_input(self.joystick, self.rov_rotation)
        
        # Update visualization variables
        # Get joystick values for visualization
        pygame.event.pump()
        forward = -self.joystick.get_axis(1)  # Invert Y axis
        strafe = self.joystick.get_axis(0)
        
        # Calculate magnitude and direction for visualization
        magnitude = min(1.0, math.sqrt(forward**2 + strafe**2))
        angle = math.atan2(strafe, forward)
        
        # Update movement vector for visualization
        self.horizontal_movement[0] = magnitude * math.sin(angle)
        self.horizontal_movement[1] = magnitude * math.cos(angle)
        
        # Update rotation from right stick - APPLY CALIBRATION OFFSET
        rotation_value = self.joystick.get_axis(2) - self.omni_control.right_stick_x_offset

        # Apply deadzone to rotation
        if abs(rotation_value) < self.stick_dead_zone:
            rotation_value = 0

        # Update rotation
        self.rov_rotation += rotation_value * 2
        self.rov_rotation %= 360
        
        # Get vertical movement
        if self.joystick.get_numaxes() > 4:
            l2_trigger = (self.joystick.get_axis(4) + 1) / 2
            r2_trigger = (self.joystick.get_axis(5) + 1) / 2 if self.joystick.get_numaxes() > 5 else 0
            self.vertical_movement = r2_trigger - l2_trigger
        
        # Add this in your main loop or in read_joystick for debugging
        for i in range(self.joystick.get_numaxes()):
            print(f"Axis {i}: {self.joystick.get_axis(i):.3f}")
        
        return True
    
    def send_motor_commands(self):
        """Send motor commands to the server"""
        if not self.connected or not self.socket:
            return False
        
        try:
            # Encode the motor commands as JSON
            json_data = json.dumps(self.motor_commands).encode('utf-8')
            
            # Simple protocol: [LENGTH(4 bytes)][JSON DATA]
            msg_len = len(json_data)
            header = struct.pack('!I', msg_len)
            
            # Send the message with its length prefix
            self.socket.sendall(header + json_data)
            return True
        except Exception as e:
            print(f"Error sending commands: {e}")
            self.connected = False
            return False
    
    def receive_data(self):
        """Background thread to receive data from the server"""
        while self.connected:
            try:
                # First read the message length (4 bytes)
                header = self.socket.recv(4)
                if not header:
                    self.connected = False
                    print("Server closed connection")
                    break
                
                # Unpack the message length
                msg_len = struct.unpack('!I', header)[0]
                
                # Read the full message
                data = b''
                while len(data) < msg_len:
                    chunk = self.socket.recv(min(1024, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                # Process the message
                if len(data) == msg_len:
                    try:
                        self.telemetry = json.loads(data.decode('utf-8'))
                        # Print only occasionally to avoid spamming the console
                        if time.time() % 5 < 0.1:  # Print roughly every 5 seconds
                            print(f"Telemetry: {self.telemetry}")
                    except json.JSONDecodeError:
                        print("Received invalid JSON data")
                
            except socket.timeout:
                # Just a timeout, continue
                pass
            except Exception as e:
                print(f"Error receiving data: {e}")
                self.connected = False
                break
    
    def discover_server_zeroconf(self):
        """Discover ROV server using Zeroconf"""
        print("Searching for ROV servers on the network...")
        
        zeroconf = Zeroconf()
        listener = ROVServiceListener()
        browser = ServiceBrowser(zeroconf, "_rov._tcp.local.", listener)
        
        # Wait for discovery (with timeout)
        discovery_timeout = 5.0  # seconds
        start_time = time.time()
        
        while time.time() - start_time < discovery_timeout:
            if listener.found_services:
                # Service found, stop browsing
                break
            time.sleep(0.1)  # Small pause to prevent CPU hogging
        
        # Clean up
        zeroconf.close()
        
        # Return the first found service, or None if none found
        if listener.found_services:
            server_ip, server_port, service_name = listener.found_services[0]
            print(f"Discovered ROV server: {service_name} at {server_ip}:{server_port}")
            return server_ip, server_port
        else:
            print("No ROV servers discovered on the network")
            return None, None
    
    def render(self):
        """Render the 2D visualization"""
        # Fill background
        self.screen.fill(self.colors['background'])
        
        # Draw main sections
        main_view_rect = pygame.Rect(200, 50, 550, 400)
        telemetry_rect = pygame.Rect(770, 50, 200, 400)
        control_rect = pygame.Rect(200, 470, 770, 200)
        
        # Draw borders for sections
        pygame.draw.rect(self.screen, self.colors['grid'], main_view_rect, 2)
        pygame.draw.rect(self.screen, self.colors['grid'], telemetry_rect, 2)
        pygame.draw.rect(self.screen, self.colors['grid'], control_rect, 2)
        
        # Draw ROV visualization
        self._draw_rov_visualization(main_view_rect)
        
        # Draw telemetry panel
        self._draw_telemetry_panel(telemetry_rect)
        
        # Draw control panel
        self._draw_control_panel(control_rect)
        
        # Draw connection status and help
        self._draw_status_and_help()
        
        # Update the display
        pygame.display.flip()
    
    def _draw_rov_visualization(self, rect):
        """Draw a 2D visualization of the ROV and its movement"""
        # Draw section title
        title = self.title_font.render("ROV Status", True, self.colors['text'])
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        # Draw grid
        cell_size = 20
        for x in range(rect.x + cell_size, rect.x + rect.width, cell_size):
            pygame.draw.line(self.screen, self.colors['grid'], 
                            (x, rect.y + 40), 
                            (x, rect.y + rect.height - 10), 1)
        
        for y in range(rect.y + 40 + cell_size, rect.y + rect.height, cell_size):
            pygame.draw.line(self.screen, self.colors['grid'], 
                            (rect.x + 10, y), 
                            (rect.x + rect.width - 10, y), 1)
        
        # Calculate ROV position in the view
        center_x = rect.x + rect.width // 2
        center_y = rect.y + rect.height // 2
        
        # Draw ROV body (now a rectangle to better show corner motors)
        rov_size = 60
        rov_rect = pygame.Rect(
            center_x - rov_size//2, 
            center_y - rov_size//2,
            rov_size, rov_size
        )
        
        # Rotate the ROV - for simplicity we'll just rotate the corner motor positions
        angle_rad = math.radians(self.rov_rotation)
        cos_val = math.cos(angle_rad)
        sin_val = math.sin(angle_rad)
        
        # Draw the ROV body
        rotated_points = [
            (center_x + rov_size//2 * sin_val + rov_size//2 * cos_val, 
             center_y - rov_size//2 * cos_val + rov_size//2 * sin_val),  # Front right
            (center_x - rov_size//2 * sin_val + rov_size//2 * cos_val, 
             center_y + rov_size//2 * cos_val + rov_size//2 * sin_val),  # Front left
            (center_x - rov_size//2 * sin_val - rov_size//2 * cos_val, 
             center_y + rov_size//2 * cos_val - rov_size//2 * sin_val),  # Rear left
            (center_x + rov_size//2 * sin_val - rov_size//2 * cos_val, 
             center_y - rov_size//2 * cos_val - rov_size//2 * sin_val),  # Rear right
        ]
        
        # Draw ROV body
        pygame.draw.polygon(self.screen, self.colors['rov_body'], rotated_points)
        pygame.draw.polygon(self.screen, self.colors['rov_highlight'], rotated_points, 2)
        
        # Draw front indicator (small triangle at front)
        front_point = (
            center_x + (rov_size//2 + 10) * sin_val, 
            center_y - (rov_size//2 + 10) * cos_val
        )
        pygame.draw.circle(self.screen, (255, 255, 0), (int(front_point[0]), int(front_point[1])), 5)
        
        # Draw corner motors with power indicators
        motor_positions = {
            'front_right_motor': rotated_points[0],
            'front_left_motor': rotated_points[1],
            'rear_left_motor': rotated_points[2],
            'rear_right_motor': rotated_points[3],
        }
        
        for motor_name, pos in motor_positions.items():
            motor_speed = self.motor_commands[motor_name]['speed']
            motor_dir = self.motor_commands[motor_name]['direction']
            
            # Color based on direction and speed
            if motor_speed == 0:
                color = self.colors['motor_off']
            elif motor_dir == 1:  # Forward
                intensity = min(255, motor_speed)
                color = (0, intensity, 0)  # Green for forward
            else:  # Reverse
                intensity = min(255, motor_speed)
                color = (intensity, 0, 0)  # Red for reverse
            
            # Draw motor
            motor_size = 5 + (motor_speed / 255) * 10
            pygame.draw.circle(self.screen, color, (int(pos[0]), int(pos[1])), int(motor_size))
            
            # Draw motor label
            label = self.small_font.render(f"{motor_speed}", True, self.colors['text'])
            self.screen.blit(label, (int(pos[0]) - 10, int(pos[1]) - 20))
        
        # Draw vertical motor in center
        vert_motor = self.motor_commands['vertical_motor']
        vert_speed = vert_motor['speed']
        vert_dir = vert_motor['direction']
        
        if vert_speed > 0:
            if vert_dir == 1:  # Up
                color = (0, 0, 255)  # Blue for up
            else:  # Down
                color = (255, 0, 255)  # Purple for down
                
            # Draw vertical motor indicator
            vert_length = max(5, int(vert_speed / 255 * 30))
            vert_rect = pygame.Rect(
                center_x - 5,
                center_y - vert_length if vert_dir == 1 else center_y,
                10,
                vert_length
            )
            pygame.draw.rect(self.screen, color, vert_rect)
        
        # Draw movement indicator (arrow showing direction)
        if abs(self.horizontal_movement[0]) > 0.1 or abs(self.horizontal_movement[1]) > 0.1:
            # Scale the vector to make it visible
            arrow_scale = 50
            end_x = center_x + self.horizontal_movement[0] * arrow_scale
            end_y = center_y - self.horizontal_movement[1] * arrow_scale
            
            # Draw the arrow line
            pygame.draw.line(self.screen, (255, 255, 0), (center_x, center_y), (end_x, end_y), 2)
            
            # Draw arrow head
            arrow_head_size = 8
            angle = math.atan2(center_y - end_y, end_x - center_x)
            
            head1_x = end_x - arrow_head_size * math.cos(angle - math.pi/6)
            head1_y = end_y + arrow_head_size * math.sin(angle - math.pi/6)
            
            head2_x = end_x - arrow_head_size * math.cos(angle + math.pi/6)
            head2_y = end_y + arrow_head_size * math.sin(angle + math.pi/6)
            
            pygame.draw.line(self.screen, (255, 255, 0), (end_x, end_y), (head1_x, head1_y), 2)
            pygame.draw.line(self.screen, (255, 255, 0), (end_x, end_y), (head2_x, head2_y), 2)
    
    def _draw_telemetry_panel(self, rect):
        """Draw the telemetry information panel"""
        # Draw section title
        title = self.title_font.render("Telemetry", True, self.colors['text'])
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        # Connection status
        status_text = "CONNECTED" if self.connected else "DISCONNECTED"
        status_color = self.colors['success'] if self.connected else self.colors['warning']
        status = self.info_font.render(status_text, True, status_color)
        self.screen.blit(status, (rect.x + 10, rect.y + 50))
        
        # IP address
        ip_text = self.info_font.render(f"IP: {self.server_ip}", True, self.colors['text'])
        self.screen.blit(ip_text, (rect.x + 10, rect.y + 80))
        
        # Draw telemetry values
        y_pos = rect.y + 120
        if self.connected:
            telemetry_items = [
                ("Voltage", f"{self.telemetry.get('voltage', 0):.1f}V"),
                ("Current", f"{self.telemetry.get('current', 0):.2f}A"),
                ("Depth", f"{self.telemetry.get('depth', 0):.2f}m"),
                ("Temp", f"{self.telemetry.get('temperature', 0):.1f}°C")
            ]
            
            for label, value in telemetry_items:
                label_text = self.info_font.render(f"{label}:", True, self.colors['text'])
                value_text = self.info_font.render(value, True, self.colors['text'])
                self.screen.blit(label_text, (rect.x + 10, y_pos))
                self.screen.blit(value_text, (rect.x + 100, y_pos))
                y_pos += 30
        
        # Draw motor values - updated for 5 motors
        y_pos = rect.y + 250
        title = self.info_font.render("Motor Commands:", True, self.colors['text'])
        self.screen.blit(title, (rect.x + 10, y_pos))
        y_pos += 30
        
        motor_items = [
            ("Front Left", self.motor_commands['front_left_motor']['speed']),
            ("Front Right", self.motor_commands['front_right_motor']['speed']),
            ("Rear Left", self.motor_commands['rear_left_motor']['speed']),
            ("Rear Right", self.motor_commands['rear_right_motor']['speed']),
            ("Vertical", self.motor_commands['vertical_motor']['speed'])
        ]
        
        for label, value in motor_items:
            # Normalize value to 0-1 range
            normalized = value / 255.0
            
            # Color gradient from green to red
            color = (int(normalized * 255), int((1-normalized) * 255), 0)
            
            # Label
            label_text = self.info_font.render(f"{label}:", True, self.colors['text'])
            self.screen.blit(label_text, (rect.x + 10, y_pos))
            
            # Bar background
            pygame.draw.rect(self.screen, (50, 50, 50), (rect.x + 90, y_pos + 5, 80, 10))
            
            # Active portion
            pygame.draw.rect(self.screen, color, 
                            (rect.x + 90, y_pos + 5, 
                             int(normalized * 80), 10))
            
            # Value
            value_text = self.small_font.render(str(value), True, self.colors['text'])
            self.screen.blit(value_text, (rect.x + 180, y_pos))
            
            y_pos += 25
    
    def _draw_control_panel(self, rect):
        """Draw the control information panel"""
        # Draw section title
        title = self.title_font.render("Controls", True, self.colors['text'])
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        # Draw joystick info
        if self.joystick:
            joystick_name = self.info_font.render(f"Joystick: {self.joystick.get_name()}", True, self.colors['text'])
            self.screen.blit(joystick_name, (rect.x + 10, rect.y + 50))
        else:
            joystick_name = self.info_font.render("No joystick connected", True, self.colors['warning'])
            self.screen.blit(joystick_name, (rect.x + 10, rect.y + 50))
        
        # Draw control instructions - updated for omnidirectional
        control_items = [
            "Left Stick: Omnidirectional Movement",
            "Right Stick X: Rotate",
            "L2/R2 Triggers: Up/Down",
            "Triangle: Calibrate Controller",
            "Press ESC or close window to exit"
        ]
        
        y_pos = rect.y + 80
        for item in control_items:
            text = self.info_font.render(item, True, self.colors['text'])
            self.screen.blit(text, (rect.x + 10, y_pos))
            y_pos += 25
    
    def _draw_status_and_help(self):
        """Draw status information at the top of the screen"""
        # Draw app title
        title = self.title_font.render("ROV Control System", True, self.colors['text'])
        self.screen.blit(title, (20, 10))
        
        # Draw server info
        server_info = self.info_font.render(
            f"Server: {self.server_ip}:{self.server_port} - {'Connected' if self.connected else 'Disconnected'}", 
            True, 
            self.colors['success'] if self.connected else self.colors['warning'])
        self.screen.blit(server_info, (300, 15))
    
    def calibrate_joystick(self):
        """Calibrate joystick to compensate for drift"""
        if not self.joystick:
            return
            
        print("Calibrating joystick. Please center all sticks...")
        time.sleep(1)  # Wait for user to center sticks
        
        # Just a visual indicator
        for i in range(3):
            print(f"Calibrating in {3-i}...")
            time.sleep(0.5)
            
        # Read current position and store as offsets
        pygame.event.pump()
        
        # Store current joystick positions as the zero position
        self.omni_control.left_stick_x_offset = self.joystick.get_axis(0)
        self.omni_control.left_stick_y_offset = self.joystick.get_axis(1)
        self.omni_control.right_stick_x_offset = self.joystick.get_axis(2)
        
        print("Calibration complete!")
        print(f"Offsets: X={self.omni_control.left_stick_x_offset:.3f}, Y={self.omni_control.left_stick_y_offset:.3f}, Rot={self.omni_control.right_stick_x_offset:.3f}")
    
    def close(self):
        """Close connections and clean up"""
        if self.connected and self.socket:
            try:
                # Stop all motors before disconnecting
                stop_commands = {
                    'front_left_motor': {'direction': 0, 'speed': 0},
                    'front_right_motor': {'direction': 0, 'speed': 0},
                    'rear_left_motor': {'direction': 0, 'speed': 0},
                    'rear_right_motor': {'direction': 0, 'speed': 0},
                    'vertical_motor': {'direction': 0, 'speed': 0}
                }
                
                # Encode the motor commands as JSON
                json_data = json.dumps(stop_commands).encode('utf-8')
                msg_len = len(json_data)
                header = struct.pack('!I', msg_len)
                self.socket.sendall(header + json_data)
                
                # Close socket
                self.socket.close()
            except:
                pass
                
        pygame.quit()

def main():
    # Allow command-line override but use discovery by default
    use_discovery = True
    server_ip = None
    server_port = 5000
    
    if len(sys.argv) > 1:
        if sys.argv[1].lower() != "auto":
            server_ip = sys.argv[1]
            use_discovery = False
    
    if len(sys.argv) > 2:
        server_port = int(sys.argv[2])
    
    print("====== ROV Control Client with 2D Visualization ======")
    
    # Create client with placeholder IP (will be updated)
    client = ROVClient("discovering...", server_port)
    
    # Connect to joystick first
    if not client.connect_to_joystick():
        print("Warning: No joystick available. Continuing with keyboard control.")
    
    # Initialize visualization
    client.initialize_visualization()
    
    # Show direct connection instructions
    print("\nDirect Connection Tips:")
    print("1. Make sure both computers are on the same subnet (192.168.1.x)")
    print("2. Disable firewalls or add exceptions for this application")
    print("3. Try using command line: python network_client_2d.py 192.168.1.x 5000")
    print("4. For direct Ethernet connections, check link-local addressing (169.254.x.x)\n")
    
    # Auto-discover server if requested
    if use_discovery:
        discovered_ip, discovered_port = client.discover_server_zeroconf()
        if discovered_ip:
            server_ip = discovered_ip
            server_port = discovered_port
        else:
            # Discovery failed - try common direct-connected IP ranges
            print("Trying common direct-connect IP addresses...")
            for test_ip in ["192.168.2.2", "192.168.1.2", "10.42.0.2", "169.254.0.2", "192.168.0.201"]:
                print(f"Testing {test_ip}...")
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.settimeout(1)
                    test_socket.connect((test_ip, server_port))
                    test_socket.close()
                    print(f"Connection successful to {test_ip}")
                    server_ip = test_ip
                    break
                except:
                    pass
    
    # Connect to server (fallback to default if not discovered)
    if server_ip is None:
        # Ask user for IP address
        print("\nAutomatic discovery failed. Please enter the server's IP address:")
        user_ip = input("> ").strip()
        if user_ip:
            server_ip = user_ip
        else:
            server_ip = "127.0.0.1"  # Last resort default
        
    client.server_ip = server_ip
    client.server_port = server_port
    print(f"Connecting to server at {server_ip}:{server_port}")
    success = client.connect_to_server()
    
    if not success:
        print("\nConnection failed! Please check:")
        print("1. Is the server running on the other machine?")
        print("2. Is the correct IP address being used?")
        print("3. Are there any firewalls blocking the connection?")
        print("4. Try running both programs as administrator")
    
    print("\nControls:")
    print("  Left Stick: Omnidirectional Movement")
    print("  Right Stick X: Rotate")
    print("  L2/R2 Triggers: Up/Down")
    print("  Triangle (Y): Calibrate controller")
    print("  Close window or ESC to exit")
    
    # Main loop
    try:
        last_send_time = 0
        send_interval = 0.05  # Send commands 20 times per second
        
        running = True
        while running:
            # Process pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                elif event.type == pygame.JOYBUTTONDOWN:
                    # Y button (Triangle on PS4) for calibration
                    if event.button == 3:  # Adjust for your controller
                        client.calibrate_joystick()
            
            # Read joystick and update motor commands
            client.read_joystick()
            
            # Send commands to server periodically if connected
            current_time = time.time()
            if client.connected and current_time - last_send_time >= send_interval:
                client.send_motor_commands()
                last_send_time = current_time
            
            # Render visualization
            client.render()
            
            # Limit frame rate
            pygame.time.Clock().tick(60)
            
    except KeyboardInterrupt:
        print("\nExiting client...")
    finally:
        client.close()
        print("Client shut down.")

if __name__ == "__main__":
    main()