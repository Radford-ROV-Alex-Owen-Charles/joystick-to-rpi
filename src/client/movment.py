import pygame
import math
import numpy as np

class OmniDirectionalControl:
    def __init__(self):
        """Initialize the omnidirectional control system"""
        # Controller deadzone
        self.stick_dead_zone = 0.1
        self.trigger_dead_zone = 0.1
        
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

    def process_input(self, joystick):
        """Process joystick input and calculate motor values for omnidirectional movement"""
        if not joystick:
            return self.motor_commands
        
        # Update pygame events
        pygame.event.pump()
        
        # Get movement vectors from joystick
        # Forward/backward from left stick Y-axis (inverted)
        forward = -joystick.get_axis(1)
        # Left/right strafe from left stick X-axis
        strafe = joystick.get_axis(0)
        # Rotation from right stick X-axis
        rotation = joystick.get_axis(2)
        
        # Apply deadzone to sticks
        forward = 0 if abs(forward) < self.stick_dead_zone else forward
        strafe = 0 if abs(strafe) < self.stick_dead_zone else strafe
        rotation = 0 if abs(rotation) < self.stick_dead_zone else rotation
        
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
    
    def visualize_motor_outputs(self, surface, x, y, scale=100):
        """Draw a visualization of the motor outputs on a pygame surface"""
        # Draw the ROV body
        body_color = (100, 100, 200)
        body_size = int(scale * 0.6)
        pygame.draw.rect(surface, body_color, 
                       (x - body_size//2, y - body_size//2, body_size, body_size))
        
        # Draw each motor with its current power
        motor_positions = {
            'front_left': (-1, -1),
            'front_right': (1, -1),
            'rear_left': (-1, 1),
            'rear_right': (1, 1)
        }
        
        for motor, pos in motor_positions.items():
            motor_x = x + pos[0] * scale//2
            motor_y = y + pos[1] * scale//2
            
            # Get motor value
            value = self.motor_outputs[motor]
            
            # Calculate color based on value
            if value > 0:
                color = (0, min(255, int(value * 255)), 0)  # Green for forward
            else:
                color = (min(255, int(abs(value) * 255)), 0, 0)  # Red for reverse
            
            # Size based on power
            size = int(5 + abs(value) * 10)
            
            # Draw motor
            pygame.draw.circle(surface, color, (motor_x, motor_y), size)
            
            # Draw line showing power
            line_length = int(abs(value) * scale//3)
            angle = 0
            if pos == (-1, -1):  # front-left
                angle = 45
            elif pos == (1, -1):  # front-right
                angle = 135
            elif pos == (-1, 1):  # rear-left
                angle = 315
            else:  # rear-right
                angle = 225
                
            if value < 0:
                angle = (angle + 180) % 360
                
            end_x = motor_x + line_length * math.cos(math.radians(angle))
            end_y = motor_y + line_length * math.sin(math.radians(angle))
            pygame.draw.line(surface, color, (motor_x, motor_y), (end_x, end_y), 2)
        
        # Draw vertical thruster
        vert_value = self.motor_outputs['vertical']
        if abs(vert_value) > 0.05:
            if vert_value > 0:
                color = (0, 0, 255)  # Blue for up
            else:
                color = (255, 0, 255)  # Purple for down
                
            # Draw vertical indicator
            vert_length = int(abs(vert_value) * scale//2)
            pygame.draw.rect(surface, color, 
                           (x - 5, y - vert_length if vert_value > 0 else y, 
                            10, vert_length))

def calculate_movement_vector(joystick):
    """Calculate the overall movement vector from joystick input"""
    # Get movement components
    forward = -joystick.get_axis(1)  # Invert Y axis
    strafe = joystick.get_axis(0)
    
    # Apply deadzone
    deadzone = 0.1
    forward = 0 if abs(forward) < deadzone else forward
    strafe = 0 if abs(strafe) < deadzone else strafe
    
    # Calculate magnitude and direction
    magnitude = min(1.0, math.sqrt(forward**2 + strafe**2))
    angle = math.degrees(math.atan2(strafe, forward))
    
    return magnitude, angle

def integrate_with_client(client):
    """Integrate this omnidirectional control with the existing client"""
    # Create the control system
    omni_control = OmniDirectionalControl()
    
    # Replace client's read_joystick method
    original_read_joystick = client.read_joystick
    
    def new_read_joystick():
        """Replacement for the client's read_joystick method"""
        if not client.joystick:
            return False
            
        # Process joystick input with omnidirectional control
        client.motor_commands = omni_control.process_input(client.joystick)
        
        # Update visualization variables (for 2D client)
        magnitude, angle = calculate_movement_vector(client.joystick)
        client.horizontal_movement[0] = magnitude * math.sin(math.radians(angle))
        client.horizontal_movement[1] = magnitude * math.cos(math.radians(angle))
        
        # Get rotation from right stick
        client.rov_rotation += client.joystick.get_axis(2) * 2
        client.rov_rotation %= 360
        
        # Get vertical movement
        if client.joystick.get_numaxes() > 4:
            l2_trigger = (client.joystick.get_axis(4) + 1) / 2
            r2_trigger = (client.joystick.get_axis(5) + 1) / 2 if client.joystick.get_numaxes() > 5 else 0
            client.vertical_movement = r2_trigger - l2_trigger
        
        return True
    
    # Replace the client's read_joystick method
    client.read_joystick = new_read_joystick
    
    return omni_control

# Example usage in the main client
if __name__ == "__main__":
    print("This module provides omnidirectional control for an ROV with corner motors.")
    print("Import and use it in your main client.")