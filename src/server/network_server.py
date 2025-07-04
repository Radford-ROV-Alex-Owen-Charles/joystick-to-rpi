import socket
import json
import threading
import time
import struct
import sys
import serial
import ipaddress
from zeroconf import ServiceInfo, Zeroconf
import io
import base64
from threading import Thread
import numpy as np
from PIL import Image

# Replace picamera with picamera2
from picamera2 import Picamera2
from libcamera import controls

class SimpleServer:
    def __init__(self, host='0.0.0.0', port=5000, ipv6=True):
        # Network settings
        self.host = host
        self.port = port
        self.ipv6_enabled = ipv6
        self.server_socket = None
        self.server_socket_v6 = None  # Add IPv6 socket
        self.client_socket = None
        self.running = False
        
        # Serial port for Arduino
        self.serial_port = None
        self.baud_rate = 115200
        
        # Motor states and watchdog
        self.last_command_time = 0
        self.watchdog_timeout = 2.0  # seconds
        
        # Zeroconf service
        self.zeroconf = None
        self.service_info = None
        
        # Camera settings
        self.camera = None
        self.camera_running = False
        self.camera_thread = None
    
    def connect_to_arduino(self, port=None):
        """Connect to Arduino over serial"""
        if port is None:
            # Try to auto-detect Arduino
            import glob
            if sys.platform.startswith('win'):
                ports = ['COM%s' % (i + 1) for i in range(256)]
            else:
                ports = glob.glob('/dev/tty[A-Za-z]*')
            
            for p in ports:
                try:
                    print(f"Trying port: {p}")  # Add this line
                    self.serial_port = serial.Serial(p, self.baud_rate, timeout=1)
                    time.sleep(2)
                    print(f"Connected to Arduino on {p}")
                    return True
                except Exception as e:
                    print(f"Failed to connect on {p}: {e}")  # Add this line
                    continue
        
            print("No Arduino found. Motor commands will be simulated.")
            return False
        else:
            try:
                print(f"Trying specified port: {port}")  # Add this line
                self.serial_port = serial.Serial(port, self.baud_rate, timeout=1)
                time.sleep(2)
                print(f"Connected to Arduino on {port}")
                return True
            except Exception as e:
                print(f"Error connecting to Arduino on {port}: {e}")  # More detail
                return False
    
    def send_to_arduino(self, motor_commands):
        """Send motor commands to Arduino"""
        if not self.serial_port:
            # Just simulate if no Arduino
            print(f"Simulated motors: {motor_commands}")
            return
        
        try:
            # Format command for 5 motors:
            # M,FL_DIR,FL_SPD,FR_DIR,FR_SPD,RL_DIR,RL_SPD,RR_DIR,RR_SPD,V_DIR,V_SPD\n
            front_left = motor_commands.get('front_left_motor', {'direction': 0, 'speed': 0})
            front_right = motor_commands.get('front_right_motor', {'direction': 0, 'speed': 0})
            rear_left = motor_commands.get('rear_left_motor', {'direction': 0, 'speed': 0})
            rear_right = motor_commands.get('rear_right_motor', {'direction': 0, 'speed': 0})
            vertical = motor_commands.get('vertical_motor', {'direction': 0, 'speed': 0})
            
            # Fallback for compatibility with old clients that use left/right motors
            if 'left_motor' in motor_commands and 'front_left_motor' not in motor_commands:
                left = motor_commands.get('left_motor', {'direction': 0, 'speed': 0})
                right = motor_commands.get('right_motor', {'direction': 0, 'speed': 0})
                
                # Map tank controls to corner motors
                front_left = {'direction': left['direction'], 'speed': left['speed']}
                front_right = {'direction': right['direction'], 'speed': right['speed']}
                rear_left = {'direction': left['direction'], 'speed': left['speed']}
                rear_right = {'direction': right['direction'], 'speed': right['speed']}
            
            cmd = f"M,{front_left['direction']},{front_left['speed']}," + \
                  f"{front_right['direction']},{front_right['speed']}," + \
                  f"{rear_left['direction']},{rear_left['speed']}," + \
                  f"{rear_right['direction']},{rear_right['speed']}," + \
                  f"{vertical['direction']},{vertical['speed']}\n"
            
            self.serial_port.write(cmd.encode('utf-8'))
            print(f"Sent to Arduino: {cmd.strip()}")
        except Exception as e:
            print(f"Error sending to Arduino: {e}")
    
    def register_zeroconf_service(self):
        """Register this server as a Zeroconf service for auto-discovery with IPv6 support"""
        try:
            # Get the best IP address for client connections
            local_ip = self._get_best_local_ip()
            if not local_ip or local_ip == '127.0.0.1':
                print("Warning: Could not determine local IP for Zeroconf")
                return False
            
            print(f"Registering with primary IP: {local_ip}")

            # Get all local IPs for debugging
            all_ips = self._get_local_ips()
            print(f"All available IPs: {all_ips}")
            
            # Prepare service info with IPv4 addresses (Zeroconf typically uses IPv4)
            addresses = []
            for ip in all_ips:
                if ':' not in ip and ip != '127.0.0.1':  # IPv4 only for Zeroconf
                    try:
                        addresses.append(socket.inet_aton(ip))
                    except:
                        pass
                        
            if not addresses:
                addresses = [socket.inet_aton(local_ip)]
            
            # Prepare service info
            service_name = "ROV Control Server._rovcontrol._tcp.local."
            self.service_info = ServiceInfo(
                "_rovcontrol._tcp.local.",
                service_name,
                addresses=addresses,
                port=self.port,
                properties={
                    "version": "1.0",
                    "name": "ROV Control",
                    "ipv6_supported": "true" if self.ipv6_enabled else "false"
                },
                server=f"rovserver-{socket.gethostname().replace('.', '-')}.local."
            )
            
            # Register service
            self.zeroconf = Zeroconf()
            self.zeroconf.register_service(self.service_info)
            print(f"Registered Zeroconf service: {service_name}")
            print(f"Service is discoverable at {local_ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Error registering Zeroconf service: {e}")
            return False
    
    def _get_local_ips(self):
        """Get all local IP addresses including IPv6 link-local addresses"""
        local_ips = []
        local_ipv6 = []
        
        try:
            # Get all network interfaces for both IPv4 and IPv6
            hostname = socket.gethostname()
            
            # Get IPv4 addresses
            try:
                ipv4_addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
                for addr in ipv4_addrs:
                    ip = addr[4][0]
                    if ip != '127.0.0.1':
                        local_ips.append(ip)
            except:
                pass
            
            # Get IPv6 addresses
            try:
                ipv6_addrs = socket.getaddrinfo(hostname, None, socket.AF_INET6)
                for addr in ipv6_addrs:
                    ip = addr[4][0]
                    # Skip loopback and extract scope ID if present
                    if ip != '::1' and not ip.startswith('::1'):
                        # Handle zone ID (scope) for link-local addresses
                        if '%' in ip:
                            local_ipv6.append(ip)
                        else:
                            local_ipv6.append(ip)
            except:
                pass
            
            # Try to get more complete interface information
            try:
                import netifaces
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    
                    # IPv4 addresses
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            if ip != '127.0.0.1' and ip not in local_ips:
                                local_ips.append(ip)
                    
                    # IPv6 addresses
                    if netifaces.AF_INET6 in addrs:
                        for addr in addrs[netifaces.AF_INET6]:
                            ip = addr['addr']
                            if ip != '::1' and ip not in local_ipv6:
                                # Add interface name for link-local addresses
                                if ip.startswith('fe80::'):
                                    ip_with_scope = f"{ip}%{interface}"
                                    local_ipv6.append(ip_with_scope)
                                else:
                                    local_ipv6.append(ip)
            except ImportError:
                print("netifaces not available, limited IPv6 discovery")
        
        except Exception as e:
            print(f"Error getting local IPs: {e}")
        
        # Combine IPv4 and IPv6 addresses
        all_ips = local_ips + local_ipv6
        return list(set(all_ips))
    
    def _get_best_local_ip(self):
        """Get the best IP address for client connections (IPv4 preferred)"""
        try:
            # Try IPv4 first
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            # Fall back to first available non-loopback IP
            ips = self._get_local_ips()
            for ip in ips:
                if ip != '127.0.0.1' and ip != '::1':
                    return ip
            return '127.0.0.1'
    
    def start(self):
        """Start the server with dual-stack support"""
        try:
            # Create IPv4 server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(10)
            
            # Create IPv6 server socket if enabled
            if self.ipv6_enabled:
                try:
                    self.server_socket_v6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    self.server_socket_v6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    # Disable IPv4-mapped IPv6 addresses to avoid conflicts
                    self.server_socket_v6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    self.server_socket_v6.settimeout(10)
                    print("IPv6 socket created successfully")
                except Exception as e:
                    print(f"IPv6 socket creation failed: {e}")
                    self.server_socket_v6 = None
                    self.ipv6_enabled = False
            
            # Bind IPv4 socket
            try:
                self.server_socket.bind(('0.0.0.0', self.port))
                self.server_socket.listen(1)
                print(f"IPv4 server listening on 0.0.0.0:{self.port}")
            except socket.error as e:
                print(f"Failed to bind IPv4 socket: {e}")
                raise
            
            # Bind IPv6 socket
            if self.server_socket_v6:
                try:
                    self.server_socket_v6.bind(('::', self.port))
                    self.server_socket_v6.listen(1)
                    print(f"IPv6 server listening on [::]:{self.port}")
                except socket.error as e:
                    print(f"Failed to bind IPv6 socket: {e}")
                    self.server_socket_v6.close()
                    self.server_socket_v6 = None
                    self.ipv6_enabled = False
            
            # Get local IP addresses to help user connect
            local_ips = self._get_local_ips()
            print(f"Local IP addresses for client connection:")
            for ip in local_ips:
                if ':' in ip:
                    print(f"  [IPv6] {ip}")
                else:
                    print(f"  [IPv4] {ip}")
                
            self.running = True
            
            # Register Zeroconf service for discovery
            self.register_zeroconf_service()
            
            # Start the watchdog thread
            watchdog_thread = threading.Thread(target=self.watchdog_loop)
            watchdog_thread.daemon = True
            watchdog_thread.start()
            
            # Main accept loop with dual-stack support
            while self.running:
                try:
                    print("Waiting for client connection...")
                    
                    # Use select to handle both IPv4 and IPv6 sockets
                    import select
                    
                    sockets_to_check = [self.server_socket]
                    if self.server_socket_v6:
                        sockets_to_check.append(self.server_socket_v6)
                    
                    # Wait for incoming connections on either socket
                    ready_sockets, _, _ = select.select(sockets_to_check, [], [], 1.0)
                    
                    for sock in ready_sockets:
                        self.client_socket, addr = sock.accept()
                        if sock == self.server_socket_v6:
                            print(f"IPv6 client connected from [{addr[0]}]:{addr[1]}")
                        else:
                            print(f"IPv4 client connected from {addr[0]}:{addr[1]}")
                        
                        # Set timeout for client operations
                        self.client_socket.settimeout(5)
                        
                        # Handle this client
                        self.handle_client()
                        break
                    
                except Exception as e:
                    if self.running:
                        print(f"Error in connection handling: {e}")
                        time.sleep(1)
            
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.stop()
    
    def handle_client(self):
        """Handle communication with a connected client"""
        try:
            while self.running:
                # Read message length
                header = self.client_socket.recv(4)
                if not header:
                    print("Client disconnected")
                    break
                
                # Unpack message length
                msg_len = struct.unpack('!I', header)[0]
                
                # Read the full message
                data = b''
                while len(data) < msg_len:
                    chunk = self.client_socket.recv(min(1024, msg_len - len(data)))
                    if not chunk:
                        break
                    data += chunk
                
                # Process the message
                if len(data) == msg_len:
                    try:
                        motor_commands = json.loads(data.decode('utf-8'))
                        print(f"Received commands: {motor_commands}")
                        
                        # Update watchdog timer
                        self.last_command_time = time.time()
                        
                        # Send to Arduino
                        self.send_to_arduino(motor_commands)
                        
                        # Send telemetry back to client
                        self.send_telemetry()
                        
                    except json.JSONDecodeError:
                        print("Received invalid JSON data")
        
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            try:
                if self.client_socket:
                    self.client_socket.close()
                    self.client_socket = None
            except:
                pass
    
    def send_telemetry(self):
        """Send telemetry data back to the client"""
        if not self.client_socket:
            return
        
        # Mock telemetry data (could be read from Arduino)
        telemetry = {
            'voltage': 12.0,
            'current': 1.5,
            'depth': 0.0,
            'temperature': 25.0,
            'timestamp': time.time()
        }
        
        try:
            # Encode as JSON
            json_data = json.dumps(telemetry).encode('utf-8')
            
            # Add length header
            header = struct.pack('!I', len(json_data))
            
            # Send message
            self.client_socket.sendall(header + json_data)
        except Exception as e:
            print(f"Error sending telemetry: {e}")
    
    def watchdog_loop(self):
        """Watch for stale commands and stop motors if needed"""
        while self.running:
            if time.time() - self.last_command_time > self.watchdog_timeout:
                # No commands recently, stop motors
                stop_cmd = {
                    'front_left_motor': {'direction': 0, 'speed': 0},
                    'front_right_motor': {'direction': 0, 'speed': 0},
                    'rear_left_motor': {'direction': 0, 'speed': 0},
                    'rear_right_motor': {'direction': 0, 'speed': 0},
                    'vertical_motor': {'direction': 0, 'speed': 0}
                }
                print("Watchdog: No commands received recently, stopping motors")
                self.send_to_arduino(stop_cmd)
            
            time.sleep(0.5)
    
    def stop(self):
        """Stop the server"""
        self.running = False
        
        # Stop camera
        if hasattr(self, 'camera') and self.camera:
            self.camera_running = False
            if self.camera_thread:
                self.camera_thread.join(timeout=2.0)
            try:
                self.camera.stop()
                self.camera.close()
            except:
                pass
            self.camera = None
    
        # Unregister Zeroconf service
        if self.zeroconf and self.service_info:
            try:
                print("Unregistering Zeroconf service...")
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
            except:
                pass
            self.zeroconf = None
            self.service_info = None
        
        # Close client socket
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        
        # Close IPv4 server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        # Close IPv6 server socket
        if self.server_socket_v6:
            try:
                self.server_socket_v6.close()
            except:
                pass
            self.server_socket_v6 = None
        
        # Close Arduino connection
        if self.serial_port:
            try:
                # Stop motors first
                stop_cmd = {
                    'front_left_motor': {'direction': 0, 'speed': 0},
                    'front_right_motor': {'direction': 0, 'speed': 0},
                    'rear_left_motor': {'direction': 0, 'speed': 0},
                    'rear_right_motor': {'direction': 0, 'speed': 0},
                    'vertical_motor': {'direction': 0, 'speed': 0}
                }
                self.send_to_arduino(stop_cmd)
                time.sleep(0.2)  # Give time to process
                
                self.serial_port.close()
            except:
                pass
            self.serial_port = None
        
        print("Server stopped")

    def initialize_camera(self):
        """Initialize the Raspberry Pi camera using PiCamera2 with JPEG encoding"""
        try:
            # Create Picamera2 instance
            self.camera = Picamera2()
            
            # Configure camera for JPEG output
            camera_config = self.camera.create_video_configuration(
                main={"size": (640, 480), "format": "RGB888"},
                encode="main"
            )
            self.camera.configure(camera_config)
            
            # Create JPEG encoder
            from picamera2.encoders import JpegEncoder
            from picamera2.outputs import FileOutput
            
            self.encoder = JpegEncoder(q=20)  # Quality 20 for smaller files
            
            # Set camera controls
            self.camera.set_controls({
                "Brightness": 0.1,
                "Contrast": 1.1,
                "ExposureTime": 20000,
                "AnalogueGain": 1.0,
            })
            
            # Start camera
            self.camera.start()
            time.sleep(2)
            
            # Start the camera stream in a thread
            self.camera_running = True
            self.camera_thread = Thread(target=self.camera_loop_jpeg)
            self.camera_thread.daemon = True
            self.camera_thread.start()
            
            print("PiCamera2 with JPEG encoder initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing PiCamera2: {e}")
            self.camera = None
            return False

    def camera_loop_jpeg(self):
        """Continuously capture JPEG frames from the camera"""
        if not hasattr(self, 'camera') or not self.camera:
            print("Camera not initialized")
            return
        
        try:
            frame_count = 0
            last_fps_time = time.time()
            
            while self.camera_running:
                try:
                    # Capture JPEG directly to memory
                    stream = io.BytesIO()
                    self.camera.capture_file(stream, format='jpeg')
                    frame_data = stream.getvalue()
                    stream.close()
                    
                    # Only send if a client is connected
                    if self.client_socket:
                        try:
                            self.send_camera_frame(frame_data)
                            frame_count += 1
                            
                            # Log FPS occasionally
                            current_time = time.time()
                            if current_time - last_fps_time > 5.0:  # Every 5 seconds
                                fps = frame_count / (current_time - last_fps_time)
                                print(f"Camera streaming at {fps:.1f} FPS")
                                frame_count = 0
                                last_fps_time = current_time
                                
                        except Exception as e:
                            print(f"Error sending frame: {e}")
                        
                except Exception as e:
                    if self.camera_running:
                        print(f"JPEG capture error: {e}")
                    time.sleep(0.1)
                
        except Exception as e:
            print(f"Camera loop error: {e}")
        finally:
            print("Camera stream stopped")

    def send_camera_frame(self, frame_data):
        """Send a camera frame to the connected client"""
        if not self.client_socket:
            return
        
        try:
            # frame_data is already JPEG bytes from camera_loop_jpeg
            # No need to re-encode with cv2
            
            # Create message with camera frame
            message = {
                'type': 'camera_frame',
                'data': base64.b64encode(frame_data).decode('utf-8'),
                'timestamp': time.time()
            }
            
            # Encode as JSON
            json_data = json.dumps(message).encode('utf-8')
            
            # Add length header
            header = struct.pack('!I', len(json_data))
            
            # Send message
            self.client_socket.sendall(header + json_data)
        except Exception as e:
            print(f"Error sending camera frame: {e}")
    
def is_valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def get_local_ip():
    """Get the local machine's IP address that would be used to connect to internet"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't need to be reachable, just used to get local interface IP
        s.connect(('8.8.8.8', 1))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return '127.0.0.1'

def main():
    # Get command line arguments
    host = sys.argv[1] if len(sys.argv) > 1 else '0.0.0.0'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    arduino_port = sys.argv[3] if len(sys.argv) > 3 else None
    enable_ipv6 = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else True
    
    print("====== ROV Server ======")
    print(f"Starting server on {host}:{port}")
    print(f"IPv6 support: {'Enabled' if enable_ipv6 else 'Disabled'}")
    
    # Create server instance with IPv6 support
    server = SimpleServer(host, port, ipv6=enable_ipv6)
    
    # Connect to Arduino
    server.connect_to_arduino(arduino_port)
    
    # Initialize camera
    server.initialize_camera()
    
    try:
        # Start the server
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.stop()

if __name__ == "__main__":
    main()