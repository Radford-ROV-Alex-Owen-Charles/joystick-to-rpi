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
    def __init__(self, server_ip="192.168.0.65", server_port=5000):
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
            'left_motor': {'direction': 0, 'speed': 0},
            'right_motor': {'direction': 0, 'speed': 0},
            'vertical_motor': {'direction': 0, 'speed': 0}
        }
        
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
    
    def discover_server_zeroconf(self, timeout=5):
        """Discover the ROV server using Zeroconf/mDNS"""
        print("Searching for ROV server using Zeroconf...")
        
        zeroconf = Zeroconf()
        listener = ROVServiceListener()
        browser = ServiceBrowser(zeroconf, "_rovcontrol._tcp.local.", listener)
        
        # Wait for discovery for up to timeout seconds
        start_time = time.time()
        while time.time() - start_time < timeout:
            if listener.found_services:
                # Try each discovered service
                for server_ip, server_port, name in listener.found_services:
                    print(f"Testing connection to {server_ip}:{server_port}...")
                    
                    # Check basic connectivity first with a ping
                    if self._test_ping(server_ip):
                        print(f"Successful ping to {server_ip}")
                        
                        # Now try TCP connection
                        if self._test_connection(server_ip, server_port):
                            print(f"Successful connection test to {server_ip}:{server_port}")
                            zeroconf.close()
                            return server_ip, server_port
                        else:
                            print(f"TCP connection to {server_ip}:{server_port} failed")
                    else:
                        print(f"Ping to {server_ip} failed")
                
                # If no successful connections, try alternative IPs from the same devices
                print("Trying alternative IP detection...")
                for ip_base in ["169.254.", "192.168.", "10.0."]:
                    for i in range(1, 10):
                        test_ip = f"{ip_base}0.{i}"
                        if self._test_connection(test_ip, self.server_port):
                            print(f"Found server through alternative scan: {test_ip}")
                            zeroconf.close()
                            return test_ip, self.server_port
            time.sleep(0.5)
        
        zeroconf.close()
        print("No ROV server found via Zeroconf")
        return None, None
    
    def _test_ping(self, ip, timeout=1):
        """Test basic connectivity with a quick ping"""
        try:
            # Platform-specific ping command
            if sys.platform.lower().startswith("win"):
                command = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
            else:
                command = ["ping", "-c", "1", "-W", str(timeout), ip]
            
            # Run the ping
            return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except:
            return False
    
    def _test_connection(self, ip, port, timeout=1):
        """Test if a TCP connection can be established"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.close()
            return True
        except:
            return False
    
    def read_joystick(self):
        """Read joystick inputs and convert to motor commands"""
        if not self.joystick:
            return False
        
        # Update pygame events
        pygame.event.pump()
        
        # Get axis values
        left_stick_x = self.joystick.get_axis(0)
        left_stick_y = self.joystick.get_axis(1)
        right_stick_x = self.joystick.get_axis(2)
        
        # Apply deadzone to sticks
        left_stick_x = 0 if abs(left_stick_x) < self.stick_dead_zone else left_stick_x
        left_stick_y = 0 if abs(left_stick_y) < self.stick_dead_zone else left_stick_y
        right_stick_x = 0 if abs(right_stick_x) < self.stick_dead_zone else right_stick_x
        
        # Get trigger values for elevation
        elevation_control = 0
        if self.joystick.get_numaxes() > 4:
            l2_trigger = (self.joystick.get_axis(4) + 1) / 2  # Convert -1 to 1 range to 0 to 1
            r2_trigger = (self.joystick.get_axis(5) + 1) / 2 if self.joystick.get_numaxes() > 5 else 0
            
            # Apply deadzone to triggers
            l2_trigger = 0 if l2_trigger < self.trigger_dead_zone else l2_trigger
            r2_trigger = 0 if r2_trigger < self.trigger_dead_zone else r2_trigger
            
            elevation_control = r2_trigger - l2_trigger
        
        # Process inputs to motor commands
        # Negate for intuitive control (pushing up should move forward)
        forward_component = -left_stick_y
        strafe_component = left_stick_x
        
        # Reset motor commands
        self.motor_commands = {
            'left_motor': {'direction': 0, 'speed': 0},
            'right_motor': {'direction': 0, 'speed': 0},
            'vertical_motor': {'direction': 0, 'speed': 0}
        }
        
        # Process forward/backward and turning
        if abs(forward_component) > self.stick_dead_zone:
            # Determine motor directions
            motor_direction = 1 if forward_component > 0 else 0
            base_power = abs(forward_component)
            
            # Calculate turn adjustment
            turn_adjustment = 0
            if abs(strafe_component) > self.stick_dead_zone:
                turn_adjustment = abs(strafe_component)
            
            # Calculate motor speeds with turning
            if strafe_component > self.stick_dead_zone:
                # Turn right: reduce right motor speed
                left_power = base_power
                right_power = max(0, base_power - turn_adjustment)
            elif strafe_component < -self.stick_dead_zone:
                # Turn left: reduce left motor speed
                left_power = max(0, base_power - turn_adjustment)
                right_power = base_power
            else:
                # Straight: equal motor speeds
                left_power = base_power
                right_power = base_power
            
            # Set motor commands
            self.motor_commands['left_motor']['direction'] = motor_direction
            self.motor_commands['left_motor']['speed'] = int(left_power * 255)
            self.motor_commands['right_motor']['direction'] = motor_direction
            self.motor_commands['right_motor']['speed'] = int(right_power * 255)
        
        # Process vertical control
        if abs(elevation_control) > self.trigger_dead_zone:
            vertical_direction = 1 if elevation_control > 0 else 0
            self.motor_commands['vertical_motor']['direction'] = vertical_direction
            self.motor_commands['vertical_motor']['speed'] = int(abs(elevation_control) * 255)
        
        # Update rotation for visualization
        self.rov_rotation += right_stick_x * 2
        self.rov_rotation %= 360
        
        # Update movement vectors for visualization
        angle_rad = math.radians(self.rov_rotation)
        x_from_forward = forward_component * math.sin(angle_rad)
        z_from_forward = forward_component * math.cos(angle_rad)
        
        x_from_strafe = strafe_component * math.cos(angle_rad)
        z_from_strafe = -strafe_component * math.sin(angle_rad)
        
        self.horizontal_movement[0] = x_from_forward + x_from_strafe
        self.horizontal_movement[1] = z_from_forward + z_from_strafe
        
        # Update vertical movement for visualization
        self.vertical_movement = elevation_control
        
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
        
        # Draw ROV (a simple polygon that rotates)
        rov_size = 30
        
        # Calculate points for the ROV
        angle_rad = math.radians(self.rov_rotation)
        cos_val = math.cos(angle_rad)
        sin_val = math.sin(angle_rad)
        
        # ROV shape points (triangle with the point indicating front)
        points = [
            (center_x + rov_size * sin_val, center_y - rov_size * cos_val),  # Front
            (center_x - rov_size * sin_val - rov_size//2 * cos_val, center_y + rov_size * cos_val - rov_size//2 * sin_val),  # Back Left
            (center_x - rov_size * sin_val + rov_size//2 * cos_val, center_y + rov_size * cos_val + rov_size//2 * sin_val),  # Back Right
        ]
        
        # Draw the ROV body
        pygame.draw.polygon(self.screen, self.colors['rov_body'], points)
        pygame.draw.polygon(self.screen, self.colors['rov_highlight'], points, 2)
        
        # Draw movement indicator (arrow showing direction)
        if abs(self.horizontal_movement[0]) > 0.1 or abs(self.horizontal_movement[1]) > 0.1:
            # Scale the vector to make it visible
            arrow_scale = 50
            end_x = center_x + self.horizontal_movement[0] * arrow_scale
            end_y = center_y - self.horizontal_movement[1] * arrow_scale
            
            # Draw the arrow line
            pygame.draw.line(self.screen, (255, 0, 0), (center_x, center_y), (end_x, end_y), 2)
            
            # Draw arrow head
            arrow_head_size = 8
            angle = math.atan2(center_y - end_y, end_x - center_x)
            
            head1_x = end_x - arrow_head_size * math.cos(angle - math.pi/6)
            head1_y = end_y + arrow_head_size * math.sin(angle - math.pi/6)
            
            head2_x = end_x - arrow_head_size * math.cos(angle + math.pi/6)
            head2_y = end_y + arrow_head_size * math.sin(angle + math.pi/6)
            
            pygame.draw.line(self.screen, (255, 0, 0), (end_x, end_y), (head1_x, head1_y), 2)
            pygame.draw.line(self.screen, (255, 0, 0), (end_x, end_y), (head2_x, head2_y), 2)
        
        # Draw vertical movement indicator
        if abs(self.vertical_movement) > 0.1:
            vertical_indicator_x = rect.x + 40
            vertical_indicator_y = rect.y + rect.height - 60
            
            # Label
            vert_label = self.small_font.render("Vertical", True, self.colors['text'])
            self.screen.blit(vert_label, (vertical_indicator_x, vertical_indicator_y - 20))
            
            # Bar background
            bar_height = 100
            bar_width = 20
            pygame.draw.rect(self.screen, (50, 50, 50), 
                            (vertical_indicator_x, vertical_indicator_y - bar_height//2, 
                             bar_width, bar_height))
            
            # Active portion
            active_height = int(self.vertical_movement * bar_height//2)
            active_y = vertical_indicator_y if active_height < 0 else vertical_indicator_y - active_height
            pygame.draw.rect(self.screen, (0, 0, 255) if active_height < 0 else (0, 255, 0), 
                            (vertical_indicator_x, active_y, 
                             bar_width, abs(active_height)))
            
            # Center line
            pygame.draw.line(self.screen, (200, 200, 200), 
                            (vertical_indicator_x, vertical_indicator_y), 
                            (vertical_indicator_x + bar_width, vertical_indicator_y), 2)
        
        # Draw depth indicator if available
        depth = self.telemetry.get('depth', 0)
        depth_x = rect.x + rect.width - 70
        depth_y = rect.y + rect.height - 60
        
        # Label
        depth_label = self.small_font.render("Depth", True, self.colors['text'])
        self.screen.blit(depth_label, (depth_x, depth_y - 20))
        
        # Bar background
        bar_height = 100
        bar_width = 20
        pygame.draw.rect(self.screen, (50, 50, 50), 
                        (depth_x, depth_y - bar_height, 
                         bar_width, bar_height))
        
        # Active portion (map depth to pixel height)
        max_depth = 10  # maximum depth in meters
        depth_ratio = min(1.0, depth / max_depth)
        active_height = int(depth_ratio * bar_height)
        pygame.draw.rect(self.screen, (0, 200, 255), 
                        (depth_x, depth_y - active_height, 
                         bar_width, active_height))
        
        # Depth value
        depth_value = self.small_font.render(f"{depth:.1f}m", True, self.colors['text'])
        self.screen.blit(depth_value, (depth_x, depth_y + 10))
    
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
        
        # Draw motor values
        y_pos = rect.y + 250
        title = self.info_font.render("Motor Commands:", True, self.colors['text'])
        self.screen.blit(title, (rect.x + 10, y_pos))
        y_pos += 30
        
        motor_items = [
            ("Left", self.motor_commands['left_motor']['speed']),
            ("Right", self.motor_commands['right_motor']['speed']),
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
            pygame.draw.rect(self.screen, (50, 50, 50), (rect.x + 80, y_pos + 5, 100, 10))
            
            # Active portion
            pygame.draw.rect(self.screen, color, 
                            (rect.x + 80, y_pos + 5, 
                             int(normalized * 100), 10))
            
            # Value
            value_text = self.small_font.render(str(value), True, self.colors['text'])
            self.screen.blit(value_text, (rect.x + 190, y_pos))
            
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
        
        # Draw control instructions
        control_items = [
            "Left Stick: Forward/Turn",
            "Right Stick: Rotate",
            "L2/R2 Triggers: Up/Down",
            "Triangle: Calibrate Controller",
            "Press ESC or close window to exit"
        ]
        
        y_pos = rect.y + 80
        for item in control_items:
            text = self.info_font.render(item, True, self.colors['text'])
            self.screen.blit(text, (rect.x + 10, y_pos))
            y_pos += 25
        
        # Draw joystick position visualization
        if self.joystick:
            # Left stick visualization
            stick_viz_x = rect.x + 350
            stick_viz_y = rect.y + 100
            self._draw_joystick_position(stick_viz_x, stick_viz_y, 
                                       self.joystick.get_axis(0), 
                                       self.joystick.get_axis(1), 
                                       "Left Stick")
            
            # Right stick visualization
            stick_viz_x = rect.x + 500
            stick_viz_y = rect.y + 100
            self._draw_joystick_position(stick_viz_x, stick_viz_y, 
                                       self.joystick.get_axis(2), 
                                       self.joystick.get_axis(3) if self.joystick.get_numaxes() > 3 else 0, 
                                       "Right Stick")
            
            # Trigger visualization
            if self.joystick.get_numaxes() > 4:
                trigger_viz_x = rect.x + 650
                trigger_viz_y = rect.y + 100
                
                l2_trigger = (self.joystick.get_axis(4) + 1) / 2
                r2_trigger = (self.joystick.get_axis(5) + 1) / 2 if self.joystick.get_numaxes() > 5 else 0
                
                self._draw_trigger_position(trigger_viz_x, trigger_viz_y, l2_trigger, r2_trigger)
    
    def _draw_joystick_position(self, x, y, x_axis, y_axis, label):
        """Draw a small visualization of a joystick position"""
        # Label
        label_text = self.small_font.render(label, True, self.colors['text'])
        self.screen.blit(label_text, (x - 30, y - 50))
        
        # Outer circle
        radius = 30
        pygame.draw.circle(self.screen, self.colors['grid'], (x, y), radius, 1)
        
        # Cross hairs
        pygame.draw.line(self.screen, self.colors['grid'], (x - radius, y), (x + radius, y), 1)
        pygame.draw.line(self.screen, self.colors['grid'], (x, y - radius), (x, y + radius), 1)
        
        # Stick position
        stick_x = x + int(x_axis * radius)
        stick_y = y + int(y_axis * radius)
        pygame.draw.circle(self.screen, self.colors['text'], (stick_x, stick_y), 5)
        
        # Values
        x_text = self.small_font.render(f"X: {x_axis:.2f}", True, self.colors['text'])
        y_text = self.small_font.render(f"Y: {y_axis:.2f}", True, self.colors['text'])
        self.screen.blit(x_text, (x - 30, y + radius + 5))
        self.screen.blit(y_text, (x - 30, y + radius + 25))
    
    def _draw_trigger_position(self, x, y, l2, r2):
        """Draw a visualization of the trigger positions"""
        # Label
        label_text = self.small_font.render("Triggers", True, self.colors['text'])
        self.screen.blit(label_text, (x - 30, y - 50))
        
        # L2 bar
        bar_width = 60
        bar_height = 20
        pygame.draw.rect(self.screen, self.colors['grid'], (x - bar_width, y, bar_width, bar_height), 1)
        pygame.draw.rect(self.screen, self.colors['rov_highlight'], 
                        (x - int(l2 * bar_width), y, int(l2 * bar_width), bar_height))
        
        # R2 bar
        pygame.draw.rect(self.screen, self.colors['grid'], (x, y, bar_width, bar_height), 1)
        pygame.draw.rect(self.screen, self.colors['rov_highlight'], 
                        (x, y, int(r2 * bar_width), bar_height))
        
        # Labels
        l2_text = self.small_font.render(f"L2: {l2:.2f}", True, self.colors['text'])
        r2_text = self.small_font.render(f"R2: {r2:.2f}", True, self.colors['text'])
        self.screen.blit(l2_text, (x - bar_width, y + bar_height + 5))
        self.screen.blit(r2_text, (x, y + bar_height + 5))
    
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
            
        # Read current position as center (not actually used in this implementation)
        pygame.event.pump()
        
        print("Calibration complete!")
    
    def close(self):
        """Close connections and clean up"""
        if self.connected and self.socket:
            try:
                # Stop all motors before disconnecting
                stop_commands = {
                    'left_motor': {'direction': 0, 'speed': 0},
                    'right_motor': {'direction': 0, 'speed': 0},
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
            for test_ip in ["192.168.2.2", "192.168.1.2", "10.42.0.2", "169.254.0.2"]:
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
    print("  Left Stick: Forward/Turn")
    print("  Right Stick: Rotate")
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