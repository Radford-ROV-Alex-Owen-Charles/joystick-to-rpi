import socket
import json
import threading
import time
import struct
import sys
import serial
import ipaddress
from zeroconf import ServiceInfo, Zeroconf  # Add this import

class SimpleServer:
    def __init__(self, host='0.0.0.0', port=5000):
        # Network settings
        self.host = host
        self.port = port
        self.server_socket = None
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
    
    def connect_to_arduino(self, port=None):
        """Connect to Arduino over serial"""
        if port is None:
            # Try to auto-detect Arduino
            import glob
            if sys.platform.startswith('win'):
                ports = ['COM%s' % (i + 1) for i in range(256)]
            else:
                ports = glob.glob('/dev/tty[A-Za-z]*')
            
            # Try each port
            for p in ports:
                try:
                    self.serial_port = serial.Serial(p, self.baud_rate, timeout=1)
                    time.sleep(2)  # Give Arduino time to reset
                    print(f"Connected to Arduino on {p}")
                    return True
                except:
                    continue
            
            print("No Arduino found. Motor commands will be simulated.")
            return False
        else:
            try:
                self.serial_port = serial.Serial(port, self.baud_rate, timeout=1)
                time.sleep(2)  # Give Arduino time to reset
                print(f"Connected to Arduino on {port}")
                return True
            except Exception as e:
                print(f"Error connecting to Arduino: {e}")
                return False
    
    def send_to_arduino(self, motor_commands):
        """Send motor commands to Arduino"""
        if not self.serial_port:
            # Just simulate if no Arduino
            print(f"Simulated motors: {motor_commands}")
            return
        
        try:
            # Format command: M,L_DIR,L_SPD,R_DIR,R_SPD,V_DIR,V_SPD\n
            left = motor_commands.get('left_motor', {'direction': 0, 'speed': 0})
            right = motor_commands.get('right_motor', {'direction': 0, 'speed': 0})
            vertical = motor_commands.get('vertical_motor', {'direction': 0, 'speed': 0})
            
            cmd = f"M,{left['direction']},{left['speed']},{right['direction']},{right['speed']},{vertical['direction']},{vertical['speed']}\n"
            self.serial_port.write(cmd.encode('utf-8'))
            print(f"Sent to Arduino: {cmd.strip()}")
        except Exception as e:
            print(f"Error sending to Arduino: {e}")
    
    def register_zeroconf_service(self):
        """Register this server as a Zeroconf service for auto-discovery"""
        try:
            # Get the best IP address for client connections
            local_ip = self._get_best_local_ip()
            if not local_ip or local_ip == '127.0.0.1':
                print("Warning: Could not determine local IP for Zeroconf")
                return False
            
            print(f"Registering with IP: {local_ip}")

            # Get all local IPs for debugging
            all_ips = self._get_local_ips()
            print(f"All available IPs: {all_ips}")
            
            # Prepare service info with ALL addresses to improve discovery odds
            addresses = []
            for ip in all_ips:
                if ip != '127.0.0.1':
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
                addresses=addresses,  # Use all addresses
                port=self.port,
                properties={
                    "version": "1.0",
                    "name": "ROV Control"
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
    
    def _get_best_local_ip(self):
        """Get the best IP address for client connections"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # We don't actually connect to Google DNS
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            # Get all local IPs and use first non-loopback
            ips = self._get_local_ips()
            for ip in ips:
                if ip != '127.0.0.1':
                    return ip
            return '127.0.0.1'
    
    def _get_local_ips(self):
        """Get all local IP addresses including direct connection interfaces"""
        local_ips = []
        try:
            # Get all network interfaces
            interfaces = socket.getaddrinfo(socket.gethostname(), None)
            for interface in interfaces:
                ip = interface[4][0]
                # Don't add loopback addresses
                if ip != '127.0.0.1' and not ip.startswith('::'):
                    local_ips.append(ip)
                    
            # For direct connections, also look for link-local addresses (169.254.x.x)
            try:
                import netifaces
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            if ip != '127.0.0.1':
                                local_ips.append(ip)
                                # If this is a direct connection (likely 169.254.x.x), prioritize it
                                if ip.startswith('169.254'):
                                    print(f"Found likely direct connection IP: {ip}")
                                    # Put it at the beginning of the list
                                    local_ips.insert(0, ip)
            except ImportError:
                # Fall back to subnet scanning for direct connection IPs
                for subnet in ["169.254", "192.168", "10.0", "172.16"]:
                    try:
                        # Use common direct connection subnets
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.bind((f"{subnet}.1.1", 0))
                        s.close()
                        local_ips.append(f"{subnet}.1.1")
                    except:
                        pass
        except:
            pass
            
        # Remove duplicates
        return list(set(local_ips))
    
    def start(self):
        """Start the server"""
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Allow quick reuse of the port - important for testing/restarting
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Increase socket timeouts to handle slower connections
            self.server_socket.settimeout(10)
            
            # Always bind to all interfaces - required for direct connections
            self.host = '0.0.0.0'
            print(f"Binding to all interfaces ({self.host}:{self.port})")
            
            try:
                self.server_socket.bind((self.host, self.port))
            except socket.error as e:
                print(f"Failed to bind: {e}")
                raise
                    
            self.server_socket.listen(1)
            
            # Get local IP addresses to help user connect
            local_ips = self._get_local_ips()
            print(f"Server listening on {self.host}:{self.port}")
            print(f"Local IP addresses for client connection:")
            for ip in local_ips:
                print(f"  {ip}")
                
            self.running = True
            
            # Register Zeroconf service for discovery
            self.register_zeroconf_service()
            
            # Start the watchdog thread
            watchdog_thread = threading.Thread(target=self.watchdog_loop)
            watchdog_thread.daemon = True
            watchdog_thread.start()
            
            # Main accept loop
            while self.running:
                try:
                    print("Waiting for client connection...")
                    self.server_socket.settimeout(None)  # No timeout during accept
                    self.client_socket, addr = self.server_socket.accept()
                    print(f"Client connected from {addr}")
                    
                    # Set a reasonable timeout for client operations
                    self.client_socket.settimeout(5)
                    
                    # Handle this client
                    self.handle_client()
                    
                except Exception as e:
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
                    'left_motor': {'direction': 0, 'speed': 0},
                    'right_motor': {'direction': 0, 'speed': 0}, 
                    'vertical_motor': {'direction': 0, 'speed': 0}
                }
                print("Watchdog: No commands received recently, stopping motors")
                self.send_to_arduino(stop_cmd)
            
            time.sleep(0.5)
    
    def stop(self):
        """Stop the server"""
        self.running = False
        
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
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        # Close Arduino connection
        if self.serial_port:
            try:
                # Stop motors first
                stop_cmd = {
                    'left_motor': {'direction': 0, 'speed': 0},
                    'right_motor': {'direction': 0, 'speed': 0}, 
                    'vertical_motor': {'direction': 0, 'speed': 0}
                }
                self.send_to_arduino(stop_cmd)
                time.sleep(0.2)  # Give time to process
                
                self.serial_port.close()
            except:
                pass
            self.serial_port = None
        
        print("Server stopped")

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
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    arduino_port = sys.argv[3] if len(sys.argv) > 3 else None
    
    print("====== ROV Server ======")
    print(f"Starting server on {host}:{port}")
    
    # Create server instance
    server = SimpleServer(host, port)
    
    # Connect to Arduino
    server.connect_to_arduino(arduino_port)
    
    try:
        # Start the server
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.stop()

if __name__ == "__main__":
    main()