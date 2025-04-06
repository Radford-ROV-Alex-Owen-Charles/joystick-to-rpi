import sys
import os
import socket

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
    # Add root directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    print("===== ROV Client Launcher =====")
    
    # If no IP is provided, ask user for server IP
    if len(sys.argv) <= 1:
        local_ip = get_local_ip()
        ip_base = '.'.join(local_ip.split('.')[:3])
        
        server_ip = input(f"Enter server IP address (default: {ip_base}.65): ")
        if not server_ip:
            server_ip = f"{ip_base}.65"
        
        sys.argv = [sys.argv[0], server_ip]
    
    # Import and run client
    from src.client.network_client import main as client_main
    client_main()

if __name__ == "__main__":
    main()