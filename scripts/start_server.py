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
    
    # Get local IP to suggest
    local_ip = get_local_ip()
    
    print("===== ROV Server Launcher =====")
    print(f"Local IP: {local_ip}")
    
    # Update args if needed
    if len(sys.argv) <= 1:
        sys.argv = [sys.argv[0], local_ip, "5000"]

if __name__ == "__main__":
    main()