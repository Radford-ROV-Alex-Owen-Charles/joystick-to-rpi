import json
import struct

class Protocol:
    """
    Protocol class for standardizing communication between client and server
    and between server and Arduino
    """
    
    # Message types
    TYPE_CONTROL = 0x01
    TYPE_TELEMETRY = 0x02
    TYPE_CALIBRATION = 0x03
    TYPE_STATUS = 0x04
    
    # Header structure: [MAGIC_BYTE(1), MSG_TYPE(1), DATA_LENGTH(2)]
    HEADER_SIZE = 4
    MAGIC_BYTE = 0xAA
    
    def __init__(self):
        pass
    
    def encode_control_command(self, command_data):
        """
        Encode a control command to be sent to the server
        
        command_data should be a dictionary with the following structure:
        {
            'left_motor': {'direction': int, 'speed': int},
            'right_motor': {'direction': int, 'speed': int},
            'vertical_motor': {'direction': int, 'speed': int}
        }
        """
        json_data = json.dumps(command_data).encode('utf-8')
        header = struct.pack('BBH', self.MAGIC_BYTE, self.TYPE_CONTROL, len(json_data))
        return header + json_data
    
    def decode_control_command(self, data):
        """Decode a control command received from the client"""
        if len(data) < self.HEADER_SIZE:
            print("Data too short to contain header")
            return None
            
        magic, msg_type, data_length = struct.unpack('BBH', data[:self.HEADER_SIZE])
        
        if magic != self.MAGIC_BYTE:
            print(f"Invalid magic byte: {magic}")
            return None
            
        if msg_type != self.TYPE_CONTROL:
            print(f"Unexpected message type: {msg_type}")
            return None
            
        if len(data) < self.HEADER_SIZE + data_length:
            print("Data length mismatch")
            return None
            
        try:
            json_data = data[self.HEADER_SIZE:self.HEADER_SIZE + data_length].decode('utf-8')
            return json.loads(json_data)
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            return None
    
    def encode_telemetry(self, telemetry_data):
        """Encode telemetry data to be sent back to the client"""
        json_data = json.dumps(telemetry_data).encode('utf-8')
        header = struct.pack('BBH', self.MAGIC_BYTE, self.TYPE_TELEMETRY, len(json_data))
        return header + json_data
    
    def decode_telemetry(self, data):
        """Decode telemetry data received from the server"""
        if len(data) < self.HEADER_SIZE:
            print("Data too short to contain header")
            return None
            
        magic, msg_type, data_length = struct.unpack('BBH', data[:self.HEADER_SIZE])
        
        if magic != self.MAGIC_BYTE:
            print(f"Invalid magic byte: {magic}")
            return None
            
        if msg_type != self.TYPE_TELEMETRY:
            print(f"Unexpected message type: {msg_type}")
            return None
            
        if len(data) < self.HEADER_SIZE + data_length:
            print("Data length mismatch")
            return None
            
        try:
            json_data = data[self.HEADER_SIZE:self.HEADER_SIZE + data_length].decode('utf-8')
            return json.loads(json_data)
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            return None
    
    def format_arduino_command(self, left_dir, left_speed, right_dir, right_speed, vertical_dir, vertical_speed):
        """
        Format a command to be sent to the Arduino
        Format: M,L_DIR,L_SPD,R_DIR,R_SPD,V_DIR,V_SPD\n
        """
        return f"M,{left_dir},{left_speed},{right_dir},{right_speed},{vertical_dir},{vertical_speed}\n"
    
    def parse_arduino_response(self, response):
        """
        Parse a response from the Arduino
        Expected format: R,VOLTAGE,CURRENT,DEPTH,TEMP\n
        """
        if not response.startswith('R,'):
            return None
            
        try:
            parts = response.strip().split(',')
            if len(parts) < 5:
                return None
                
            return {
                'voltage': float(parts[1]),
                'current': float(parts[2]),
                'depth': float(parts[3]),
                'temperature': float(parts[4])
            }
        except Exception as e:
            print(f"Error parsing Arduino response: {e}")
            return None