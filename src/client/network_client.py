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
from OpenGL.GL import *
from OpenGL.GLU import *
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange  # Add this import

# Add this new class to handle Zeroconf discovery
class ROVServiceListener:
    def __init__(self):
        self.found_services = []
        self.discovery_complete = threading.Event()
    
    def remove_service(self, zeroconf, type, name):
        pass
    
    def update_service(self, zeroconf, type, name):
        # This method is now required by Zeroconf
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
        
        # Visualization state
        self.rov_rot_z = 0
        self.horizontal_movement = [0, 0]
        self.vertical_movement = 0
        self.arrow_scale = 1.0
        self.rov_led_color = (0, 255, 0)
        
        # Camera control
        self.camera_rot_x = 45  # Initial camera rotation around X axis
        self.camera_rot_y = 0   # Initial camera rotation around Y axis
        self.mouse_pressed = False
        self.last_mouse_pos = None
        
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
        
        # Initialize pygame and joystick
        pygame.init()
        pygame.joystick.init()
        
    def initialize_visualization(self):
        """Initialize OpenGL visualization"""
        # Set up display
        self.screen_width, self.screen_height = 1200, 800
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("ROV Control Visualization")
        self.clock = pygame.time.Clock()
        
        # Setup viewport sizes
        self.main_view_width = 800
        self.main_view_height = 600
        self.side_view_width = 400
        self.side_view_height = 200
        
        # Initialize OpenGL
        glEnable(GL_DEPTH_TEST)
        
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
        self.rov_rot_z += right_stick_x * 2
        self.rov_rot_z %= 360
        
        # Update movement vectors for visualization
        angle_rad = math.radians(self.rov_rot_z)
        x_from_forward = forward_component * math.sin(angle_rad)
        z_from_forward = forward_component * math.cos(angle_rad)
        
        x_from_strafe = strafe_component * math.cos(angle_rad)
        z_from_strafe = -strafe_component * math.sin(angle_rad)
        
        self.horizontal_movement[0] = x_from_forward + x_from_strafe
        self.horizontal_movement[1] = z_from_forward + z_from_strafe
        
        # Update vertical movement for visualization
        self.vertical_movement = elevation_control
        
        # Update LED color
        self._update_led_color()
        
        return True
    
    def _update_led_color(self):
        """Update LED color based on speed"""
        max_speed = max(
            self.motor_commands['left_motor']['speed'],
            self.motor_commands['right_motor']['speed'],
            self.motor_commands['vertical_motor']['speed']
        )
        
        normalized_speed = min(1.0, max_speed / 255.0)
        red = int(normalized_speed * 255)
        green = int((1 - normalized_speed) * 255)
        blue = 0
        self.rov_led_color = (red, green, blue)
    
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
        """Render the ROV visualization"""
        # Clear the screen
        glClearColor(0.1, 0.1, 0.2, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # Render all views
        self._setup_main_view()
        self._draw_rov()
        
        self._setup_top_view()
        self._draw_rov()
        
        self._setup_front_view()
        self._draw_rov()
        
        self._setup_side_view()
        self._draw_rov()
        
        # Draw labels and telemetry data
        self._draw_view_labels()
        
        # Swap buffers
        pygame.display.flip()
    
    def _setup_main_view(self):
        """Setup the main perspective view with mouse-controlled rotation"""
        glViewport(self.screen_width - self.main_view_width, 
                  self.screen_height - self.main_view_height,
                  self.main_view_width, self.main_view_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, (self.main_view_width / self.main_view_height), 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0.0, -1.0, -7.0)
        # Apply camera rotations from mouse control
        glRotatef(self.camera_rot_x, 1, 0, 0)
        glRotatef(self.camera_rot_y, 0, 1, 0)
        
    def _setup_top_view(self):
        """Setup the top-down orthographic view"""
        glViewport(0, self.screen_height - self.side_view_height, 
                  self.side_view_width, self.side_view_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-5, 5, -5, 5, -10, 10)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0, -5, 0)
        glRotatef(90, 1, 0, 0)
        
    def _setup_front_view(self):
        """Setup the front orthographic view"""
        glViewport(0, self.screen_height - 2*self.side_view_height, 
                  self.side_view_width, self.side_view_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-5, 5, -5, 5, -10, 10)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0, 0, -5)
        
    def _setup_side_view(self):
        """Setup the side orthographic view"""
        glViewport(0, self.screen_height - 3*self.side_view_height, 
                  self.side_view_width, self.side_view_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-5, 5, -5, 5, -10, 10)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(-5, 0, 0)
        glRotatef(90, 0, 1, 0)
        
    def _draw_rov(self):
        """Draw the ROV model with direction indicators"""
        glPushMatrix()
        
        # Apply ROV rotation
        glRotatef(self.rov_rot_z, 0, 1, 0)
        
        # Draw ROV body
        glBegin(GL_QUADS)
        
        # Top face with LED color
        r, g, b = self.rov_led_color
        glColor3f(r/255, g/255, b/255)
        glVertex3f(-0.5, 0.2, -0.5)
        glVertex3f(-0.5, 0.2, 0.7)
        glVertex3f(0.5, 0.2, 0.7)
        glVertex3f(0.5, 0.2, -0.5)
        
        # Front face (green)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(-0.5, -0.2, 0.7)
        glVertex3f(0.5, -0.2, 0.7)
        glVertex3f(0.5, 0.2, 0.7)
        glVertex3f(-0.5, 0.2, 0.7)
        
        # Back face (blue)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(-0.5, -0.2, -0.5)
        glVertex3f(-0.5, 0.2, -0.5)
        glVertex3f(0.5, 0.2, -0.5)
        glVertex3f(0.5, -0.2, -0.5)
        
        # Bottom face (yellow)
        glColor3f(1.0, 1.0, 0.0)
        glVertex3f(-0.5, -0.2, -0.5)
        glVertex3f(0.5, -0.2, -0.5)
        glVertex3f(0.5, -0.2, 0.7)
        glVertex3f(-0.5, -0.2, 0.7)
        
        # Right face (magenta)
        glColor3f(1.0, 0.0, 1.0)
        glVertex3f(0.5, -0.2, -0.5)
        glVertex3f(0.5, 0.2, -0.5)
        glVertex3f(0.5, 0.2, 0.7)
        glVertex3f(0.5, -0.2, 0.7)
        
        # Left face (red)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(-0.5, -0.2, -0.5)
        glVertex3f(-0.5, -0.2, 0.7)
        glVertex3f(-0.5, 0.2, 0.7)
        glVertex3f(-0.5, 0.2, -0.5)
        
        glEnd()
        
        # Draw direction indicator
        glColor3f(1.0, 1.0, 1.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0.7)
        glVertex3f(0, 0, 1.0)
        glEnd()
        
        # Draw thrusters
        self._draw_thrusters()
        
        # Draw movement arrows
        self._draw_movement_arrows()
        
        glPopMatrix()
        
        # Draw reference grid
        self._draw_grid()
        
    def _draw_thrusters(self):
        """Draw the ROV thrusters"""
        # Vertical thrusters
        glColor3f(0.7, 0.7, 0.7)
        
        # Front left thruster
        glPushMatrix()
        glTranslatef(-0.4, 0.2, 0.5)
        glRotatef(90, 1, 0, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
        # Front right thruster
        glPushMatrix()
        glTranslatef(0.4, 0.2, 0.5)
        glRotatef(90, 1, 0, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
        # Rear left thruster
        glPushMatrix()
        glTranslatef(-0.4, 0.2, -0.3)
        glRotatef(90, 1, 0, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
        # Rear right thruster
        glPushMatrix()
        glTranslatef(0.4, 0.2, -0.3)
        glRotatef(90, 1, 0, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
        # Horizontal thrusters
        # Left thruster
        glPushMatrix()
        glTranslatef(-0.5, 0, 0.1)
        glRotatef(90, 0, 1, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
        # Right thruster
        glPushMatrix()
        glTranslatef(0.5, 0, 0.1)
        glRotatef(90, 0, 1, 0)
        self._draw_cylinder(0.1, 0.1)
        glPopMatrix()
        
    def _draw_cylinder(self, radius, height, segments=20):
        """Draw a simple cylinder"""
        glBegin(GL_QUAD_STRIP)
        for i in range(int(segments) + 1):
            angle = 2.0 * math.pi * i / segments
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            glVertex3f(x, 0, z)
            glVertex3f(x, height, z)
        glEnd()
        
    def _draw_movement_arrows(self):
        """Draw arrows showing movement direction"""
        # Horizontal movement arrow (red)
        if abs(self.horizontal_movement[0]) > 0.1 or abs(self.horizontal_movement[1]) > 0.1:
            glColor3f(1.0, 0.0, 0.0)
            
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            
            end_x = self.horizontal_movement[0] * self.arrow_scale
            end_z = self.horizontal_movement[1] * self.arrow_scale
            glVertex3f(end_x, 0, end_z)
            
            # Draw arrow head
            arrow_head_size = 0.2
            angle = math.atan2(end_z, end_x)
            
            # First arrow head line
            head_angle1 = angle + math.pi * 3/4
            head_x1 = end_x - arrow_head_size * math.cos(head_angle1)
            head_z1 = end_z - arrow_head_size * math.sin(head_angle1)
            glVertex3f(end_x, 0, end_z)
            glVertex3f(head_x1, 0, head_z1)
            
            # Second arrow head line
            head_angle2 = angle - math.pi * 3/4
            head_x2 = end_x - arrow_head_size * math.cos(head_angle2)
            head_z2 = end_z - arrow_head_size * math.sin(head_angle2)
            glVertex3f(end_x, 0, end_z)
            glVertex3f(head_x2, 0, head_z2)
            
            glEnd()
        
        # Vertical movement arrow (blue)
        if abs(self.vertical_movement) > 0.1:
            glColor3f(0.0, 0.0, 1.0)
            
            glBegin(GL_LINES)
            glVertex3f(0, 0, 0)
            glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
            
            # Draw arrow head
            arrow_head_size = 0.2
            if self.vertical_movement > 0:
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(arrow_head_size, self.vertical_movement * self.arrow_scale - arrow_head_size, 0)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(-arrow_head_size, self.vertical_movement * self.arrow_scale - arrow_head_size, 0)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(0, self.vertical_movement * self.arrow_scale - arrow_head_size, arrow_head_size)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(0, self.vertical_movement * self.arrow_scale - arrow_head_size, -arrow_head_size)
            else:
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(arrow_head_size, self.vertical_movement * self.arrow_scale + arrow_head_size, 0)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(-arrow_head_size, self.vertical_movement * self.arrow_scale + arrow_head_size, 0)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(0, self.vertical_movement * self.arrow_scale + arrow_head_size, arrow_head_size)
                
                glVertex3f(0, self.vertical_movement * self.arrow_scale, 0)
                glVertex3f(0, self.vertical_movement * self.arrow_scale + arrow_head_size, -arrow_head_size)
            
            glEnd()
            
    def _draw_grid(self):
        """Draw a reference grid"""
        glPushMatrix()
        glColor3f(0.3, 0.3, 0.3)
        glBegin(GL_LINES)
        
        grid_size = 10
        grid_step = 1
        
        for i in range(-grid_size, grid_size + 1, grid_step):
            # X axis lines
            glVertex3f(i, -2, -grid_size)
            glVertex3f(i, -2, grid_size)
            
            # Z axis lines
            glVertex3f(-grid_size, -2, i)
            glVertex3f(grid_size, -2, i)
        
        glEnd()
        glPopMatrix()
        
    def _draw_view_labels(self):
        """Draw view labels and telemetry data"""
        glDisable(GL_DEPTH_TEST)
        
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        
        # Fonts for different sizes
        title_font = pygame.font.SysFont('Arial', 24)
        info_font = pygame.font.SysFont('Arial', 18)
        
        # View labels
        main_label = title_font.render('Main View', True, (255, 255, 255))
        top_label = title_font.render('Top View', True, (255, 255, 255))
        front_label = title_font.render('Front View', True, (255, 255, 255))
        side_label = title_font.render('Side View', True, (255, 255, 255))
        
        # Draw view labels
        overlay.blit(main_label, (self.screen_width - self.main_view_width + 10, 10))
        overlay.blit(top_label, (10, 10))
        overlay.blit(front_label, (10, self.side_view_height + 10))
        overlay.blit(side_label, (10, 2*self.side_view_height + 10))
        
        # Connection status
        status = "CONNECTED" if self.connected else "OFFLINE"
        status_color = (0, 255, 0) if self.connected else (255, 0, 0)
        status_text = info_font.render(f"Status: {status}", True, status_color)
        overlay.blit(status_text, (self.screen_width - 200, 40))
        
        # Draw telemetry data
        y_pos = 70
        if self.connected:
            telemetry_items = [
                f"Voltage: {self.telemetry.get('voltage', 0):.1f}V",
                f"Current: {self.telemetry.get('current', 0):.2f}A",
                f"Depth: {self.telemetry.get('depth', 0):.2f}m",
                f"Temp: {self.telemetry.get('temperature', 0):.1f}°C"
            ]
            
            for item in telemetry_items:
                text = info_font.render(item, True, (255, 255, 255))
                overlay.blit(text, (self.screen_width - 200, y_pos))
                y_pos += 25
        
        # Draw motor info
        y_pos = 200
        motor_info = [
            f"Left Motor: {self.motor_commands['left_motor']['speed']}",
            f"Right Motor: {self.motor_commands['right_motor']['speed']}",
            f"Vertical Motor: {self.motor_commands['vertical_motor']['speed']}"
        ]
        
        for info in motor_info:
            text = info_font.render(info, True, (255, 255, 255))
            overlay.blit(text, (self.screen_width - 200, y_pos))
            y_pos += 25
        
        # Draw instructions
        instructions = [
            "Left Stick: Forward/Turn",
            "Right Stick: Rotate View",
            "L2/R2: Up/Down",
            "Triangle: Calibrate Controller",
            "Press Ctrl+C to exit"
        ]
        
        y_pos = self.screen_height - 150
        for instruction in instructions:
            text = info_font.render(instruction, True, (200, 200, 200))
            overlay.blit(text, (self.screen_width - 250, y_pos))
            y_pos += 25
        
        # Apply overlay
        pygame.display.get_surface().blit(overlay, (0, 0))
        
        glEnable(GL_DEPTH_TEST)
    
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
    
    def handle_mouse_control(self, event):
        """Handle mouse events for rotating the main view"""
        # Check if the mouse is in the main view area
        x, y = event.pos
        in_main_view = (x >= self.screen_width - self.main_view_width and 
                       y <= self.main_view_height)
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and in_main_view:
            self.mouse_pressed = True
            self.last_mouse_pos = event.pos
        
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.mouse_pressed = False
        
        elif event.type == pygame.MOUSEMOTION and self.mouse_pressed:
            if self.last_mouse_pos:
                # Calculate mouse movement deltas
                dx = event.pos[0] - self.last_mouse_pos[0]
                dy = event.pos[1] - self.last_mouse_pos[1]
                
                # Update camera angles (adjust sensitivity as needed)
                self.camera_rot_y += dx * 0.5
                self.camera_rot_x += dy * 0.5
                
                # Apply limits to prevent camera flipping
                self.camera_rot_x = max(0, min(89, self.camera_rot_x))
                
                self.last_mouse_pos = event.pos
    
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
    
    print("====== ROV Control Client with Visualization ======")
    
    # Create client with placeholder IP (will be updated)
    client = ROVClient("discovering...", server_port)
    
    # Connect to joystick first
    if not client.connect_to_joystick():
        print("Exiting: No joystick available")
        return
    
    # Initialize visualization
    client.initialize_visualization()
    
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
        print("\nAutomatic discovery failed. Please enter the Raspberry Pi's IP address:")
        user_ip = input("> ").strip()
        if user_ip:
            server_ip = user_ip
        else:
            server_ip = "127.0.0.1"  # Last resort default
        
    client.server_ip = server_ip
    client.server_port = server_port
    print(f"Connecting to server at {server_ip}:{server_port}")
    client.connect_to_server()
    
    print("\nControls:")
    print("  Left Stick: Forward/Turn")
    print("  Right Stick: Rotate view")
    print("  L2/R2 Triggers: Up/Down")
    print("  Triangle (Y): Calibrate controller")
    print("  Close window or Ctrl+C to exit")
    
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
                elif event.type == pygame.JOYBUTTONDOWN:
                    # Y button (Triangle on PS4) for calibration
                    if event.button == 3:  # Adjust for your controller
                        client.calibrate_joystick()
                # Handle mouse events
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                    client.handle_mouse_control(event)
            
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