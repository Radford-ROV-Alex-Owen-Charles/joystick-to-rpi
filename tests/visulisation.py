import pygame
import sys
import math
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

class ROVVisualization:
    """
    Wrapper class for the visualization code that can be used with the networked client.
    This integrates the original visualization code into the client/server architecture.
    """
    
    def __init__(self):
        # Initialize pygame and OpenGL
        pygame.init()
        
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
        
        # ROV state
        self.rov_rot_z = 0
        self.horizontal_movement = [0, 0]
        self.vertical_movement = 0
        self.arrow_scale = 1.0
        
        # LED color
        self.rov_led_color = (0, 255, 0)
        
        # Initialize OpenGL
        glEnable(GL_DEPTH_TEST)
        
    def update(self, joystick_data, telemetry):
        """Update visualization with current joystick and telemetry data"""
        # Extract joystick and command data
        raw_inputs = joystick_data.get('raw_inputs', {})
        motor_commands = joystick_data.get('motor_commands', {})
        
        # Update visualization state
        left_stick = raw_inputs.get('left_stick', {'x': 0, 'y': 0})
        right_stick = raw_inputs.get('right_stick', {'x': 0, 'y': 0})
        
        # Update ROV rotation from right stick
        self.rov_rot_z += right_stick['x'] * 2  # Adjust sensitivity as needed
        self.rov_rot_z %= 360
        
        # Calculate movement vector for visualization
        angle_rad = math.radians(self.rov_rot_z)
        forward_component = -left_stick['y']  # Negate for intuitive control
        
        # Update movement indicators for visualization
        self.horizontal_movement[0] = forward_component * math.sin(angle_rad) + left_stick['x'] * math.cos(angle_rad)
        self.horizontal_movement[1] = forward_component * math.cos(angle_rad) - left_stick['x'] * math.sin(angle_rad)
        
        # Get vertical movement from triggers
        if 'triggers' in raw_inputs:
            self.vertical_movement = raw_inputs['triggers']['r2'] - raw_inputs['triggers']['l2']
        
        # Update LED color based on max motor speed
        left_speed = motor_commands.get('left_motor', {}).get('speed', 0)
        right_speed = motor_commands.get('right_motor', {}).get('speed', 0)
        vertical_speed = motor_commands.get('vertical_motor', {}).get('speed', 0)
        max_speed = max(left_speed, right_speed, vertical_speed)
        self._update_led_color(max_speed)
        
        # Render the visualization
        self._render()
        
        # Limit frame rate
        self.clock.tick(60)
        
    def _update_led_color(self, speed):
        """Update LED color based on speed"""
        normalized_speed = min(1.0, speed / 255.0)
        red = int(normalized_speed * 255)
        green = int((1 - normalized_speed) * 255)
        blue = 0
        self.rov_led_color = (red, green, blue)
        
    def _render(self):
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
        
        # Draw labels
        self._draw_view_labels()
        
        # Swap buffers
        pygame.display.flip()
        
    def _setup_main_view(self):
        """Setup the main perspective view"""
        glViewport(self.screen_width - self.main_view_width, 
                  self.screen_height - self.main_view_height,
                  self.main_view_width, self.main_view_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, (self.main_view_width / self.main_view_height), 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(0.0, -1.0, -7.0)
        glRotatef(45, 1, 0, 0)
        
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
        """Draw view labels using pygame 2D rendering"""
        glDisable(GL_DEPTH_TEST)
        
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        
        font = pygame.font.SysFont('Arial', 24)
        main_label = font.render('Main View', True, (255, 255, 255))
        top_label = font.render('Top View', True, (255, 255, 255))
        front_label = font.render('Front View', True, (255, 255, 255))
        side_label = font.render('Side View', True, (255, 255, 255))
        
        # Draw labels
        overlay.blit(main_label, (self.screen_width - self.main_view_width + 10, 10))
        overlay.blit(top_label, (10, 10))
        overlay.blit(front_label, (10, self.side_view_height + 10))
        overlay.blit(side_label, (10, 2*self.side_view_height + 10))
        
        # Draw status info (could add telemetry data here)
        pygame.display.get_surface().blit(overlay, (0, 0))
        
        glEnable(GL_DEPTH_TEST)

def run_visualization():
    """Run the standalone ROV visualization"""
    # Constants
    STICK_DEAD_ZONE = 0.1
    TRIGGER_DEAD_ZONE = 0.1
    MAX_STICK_THRESHOLD = 0.95
    MOTOR_MAX_SPEED_DEFAULT = 255
    MOTOR_MIN_SPEED = 50
    SPEED_INCREMENT = 10
    
    # Initialize pygame and joystick
    pygame.init()
    pygame.joystick.init()
    
    if pygame.joystick.get_count() == 0:
        print("No joystick detected.")
        return
    
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    
    # Motor simulation classes
    class Motor:
        def __init__(self):
            self.speed = 0
            self.target_speed = 0
            self.was_turning = False
    
    left_motor = Motor()
    right_motor = Motor()
    vertical_motor = Motor()
    
    # Calibration data structure
    class CalibrationData:
        def __init__(self):
            self.calibrated = False
            self.center_x = 0
            self.center_y = 0
            self.center_rx = 0
            self.center_ry = 0
            self.deadzone = STICK_DEAD_ZONE
    
    calibration_data = CalibrationData()
    
    # Variables for visualization
    horizontal_movement = [0, 0]
    vertical_movement = 0
    rov_rot_z = 0
    rot_speed = 2
    current_max_speed = MOTOR_MAX_SPEED_DEFAULT // 2
    last_dpad_time = 0
    
    # Initialize the ROV visualization
    rov_vis = ROVVisualization()
    clock = pygame.time.Clock()
    
    def calibrate_joystick():
        """Calibrate joystick to compensate for drift"""
        print("Calibrating joystick. Please center all sticks...")
        pygame.time.wait(1000)  # Wait for user to center sticks
        
        # Read current position as center
        calibration_data.center_x = joystick.get_axis(0)
        calibration_data.center_y = joystick.get_axis(1)
        calibration_data.center_rx = joystick.get_axis(2)
        calibration_data.center_ry = joystick.get_axis(3)
        calibration_data.calibrated = True
        
        print("Calibration complete!")
    
    def get_compensated_axis(axis_id, center_value, deadzone):
        """Get axis value with drift compensation applied"""
        value = joystick.get_axis(axis_id) - center_value
        if abs(value) < deadzone:
            return 0
        return value
    
    def apply_dampening(current, target, was_turning, is_straight):
        """Apply dampening to motor speeds for smoother control"""
        # Determine dampening factor based on circumstances
        damp_factor = 0.1  # Default dampening
        
        if is_straight and was_turning:
            # Faster stabilization when going straight after a turn
            damp_factor = 0.2
        elif abs(current - target) > 0.5:
            # Faster response for big changes
            damp_factor = 0.15
            
        # Apply dampening
        new_speed = current + (target - current) * damp_factor
        
        # Return result with small value cleanup
        if abs(new_speed) < 0.01:
            return 0
        return new_speed
    
    def update_led_color(speed):
        """Update the LED color based on motor speed"""
        normalized_speed = min(1.0, speed / MOTOR_MAX_SPEED_DEFAULT)
        red = int(normalized_speed * 255)
        green = int((1 - normalized_speed) * 255)
        blue = 0
        rov_vis.rov_led_color = (red, green, blue)
    
    # Auto-calibrate on startup
    calibrate_joystick()
    
    # Main loop
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.JOYBUTTONDOWN:
                # Y button for calibration (on PS4, this is Triangle)
                if event.button == 3:  # Adjust based on your controller
                    calibrate_joystick()
    
        # Read joystick axes with drift compensation
        pygame.event.pump()
        if calibration_data.calibrated:
            left_stick_x = get_compensated_axis(0, calibration_data.center_x, calibration_data.deadzone)
            left_stick_y = get_compensated_axis(1, calibration_data.center_y, calibration_data.deadzone)
            right_stick_x = get_compensated_axis(2, calibration_data.center_rx, calibration_data.deadzone)
            right_stick_y = get_compensated_axis(3, calibration_data.center_ry, calibration_data.deadzone)
        else:
            left_stick_x = joystick.get_axis(0)
            left_stick_y = joystick.get_axis(1)
            right_stick_x = joystick.get_axis(2)
            right_stick_y = joystick.get_axis(3)
        
        # Get trigger values for elevation
        elevation_control = 0
        # PS4 controller typically has L2 on axis 4 and R2 on axis 5
        if joystick.get_numaxes() > 4:
            l2_trigger = (joystick.get_axis(4) + 1) / 2  # Convert -1 to 1 range to 0 to 1
            r2_trigger = (joystick.get_axis(5) + 1) / 2 if joystick.get_numaxes() > 5 else 0
            
            # Apply deadzone to triggers
            l2_trigger = 0 if l2_trigger < TRIGGER_DEAD_ZONE else l2_trigger
            r2_trigger = 0 if r2_trigger < TRIGGER_DEAD_ZONE else r2_trigger
            
            elevation_control = r2_trigger - l2_trigger
        
        # Apply deadzone to sticks
        left_stick_x = 0 if abs(left_stick_x) < STICK_DEAD_ZONE else left_stick_x
        left_stick_y = 0 if abs(left_stick_y) < STICK_DEAD_ZONE else left_stick_y
        right_stick_x = 0 if abs(right_stick_x) < STICK_DEAD_ZONE else right_stick_x
        
        # D-pad for speed control
        dpad_up = joystick.get_button(11) if joystick.get_numbuttons() > 11 else False  # Adjust as needed
        dpad_down = joystick.get_button(12) if joystick.get_numbuttons() > 12 else False  # Adjust as needed
        
        # Handle D-pad speed control with debouncing
        current_time = pygame.time.get_ticks()
        if current_time - last_dpad_time > 200:  # Debounce D-pad
            if dpad_up and current_max_speed < MOTOR_MAX_SPEED_DEFAULT:
                current_max_speed += SPEED_INCREMENT
                if current_max_speed > MOTOR_MAX_SPEED_DEFAULT:
                    current_max_speed = MOTOR_MAX_SPEED_DEFAULT
                last_dpad_time = current_time
                print(f"Max speed increased: {current_max_speed}")
            elif dpad_down and current_max_speed > MOTOR_MIN_SPEED:
                current_max_speed -= SPEED_INCREMENT
                if current_max_speed < MOTOR_MIN_SPEED:
                    current_max_speed = MOTOR_MIN_SPEED
                last_dpad_time = current_time
                print(f"Max speed decreased: {current_max_speed}")
        
        # Snap to full speed if close enough to max
        if abs(left_stick_y) > MAX_STICK_THRESHOLD:
            left_stick_y = 1.0 if left_stick_y > 0 else -1.0
    
        # Update rotation with right stick and apply dampening
        rot_target = right_stick_x * rot_speed
        rov_rot_z += rot_target
        rov_rot_z %= 360
    
        # Calculate movement vectors
        angle_rad = math.radians(rov_rot_z)
        
        # Calculate left & right motor target speeds (for simulating differential drive)
        forward_component = -left_stick_y  # Negate for intuitive control
        strafe_component = left_stick_x
        
        # Target speeds for motors (normalized 0-1 values)
        if abs(forward_component) > STICK_DEAD_ZONE:
            base_power = abs(forward_component)
            
            # Calculate turn adjustment
            turn_adjustment = 0
            if abs(strafe_component) > STICK_DEAD_ZONE:
                turn_adjustment = abs(strafe_component)
            
            # Calculate motor speeds with turning
            if strafe_component > STICK_DEAD_ZONE:
                # Turn right: reduce right motor speed
                left_motor.target_speed = min(base_power, 1.0)
                right_motor.target_speed = max(0, min(base_power - turn_adjustment, 1.0))
                left_motor.was_turning = True
                right_motor.was_turning = True
            elif strafe_component < -STICK_DEAD_ZONE:
                # Turn left: reduce left motor speed
                left_motor.target_speed = max(0, min(base_power - turn_adjustment, 1.0))
                right_motor.target_speed = min(base_power, 1.0)
                left_motor.was_turning = True
                right_motor.was_turning = True
            else:
                # Straight: equal motor speeds
                left_motor.target_speed = min(base_power, 1.0)
                right_motor.target_speed = min(base_power, 1.0)
        else:
            # No forward/backward motion
            left_motor.target_speed = 0
            right_motor.target_speed = 0
            left_motor.was_turning = False
            right_motor.was_turning = False
        
        # Map normalized values to arrow visualization vectors
        x_from_forward = forward_component * math.sin(angle_rad)
        z_from_forward = forward_component * math.cos(angle_rad)
        
        x_from_strafe = strafe_component * math.cos(angle_rad)
        z_from_strafe = -strafe_component * math.sin(angle_rad)
        
        # Check if going straight for adaptive dampening
        is_straight = abs(strafe_component) <= STICK_DEAD_ZONE and abs(forward_component) > STICK_DEAD_ZONE
        
        # Apply dampening to motor speeds
        left_motor.speed = apply_dampening(left_motor.speed, left_motor.target_speed, left_motor.was_turning, is_straight)
        right_motor.speed = apply_dampening(right_motor.speed, right_motor.target_speed, right_motor.was_turning, is_straight)
        
        # Clear turning flags if we're now going straight with equal speeds
        if is_straight and abs(left_motor.speed - left_motor.target_speed) < 0.01 and abs(right_motor.speed - right_motor.target_speed) < 0.01:
            left_motor.was_turning = False
            right_motor.was_turning = False
        
        # Apply dampening to vertical motor
        vertical_motor.target_speed = abs(elevation_control)
        vertical_motor.speed = apply_dampening(vertical_motor.speed, vertical_motor.target_speed, False, False)
        
        # Scale motor speeds for visualization
        rov_vis.horizontal_movement[0] = x_from_forward + x_from_strafe
        rov_vis.horizontal_movement[1] = z_from_forward + z_from_strafe
        rov_vis.vertical_movement = elevation_control
        rov_vis.rov_rot_z = rov_rot_z
        
        # Update LED color based on highest speed
        max_speed = max(left_motor.speed, right_motor.speed, vertical_motor.speed)
        max_speed_scaled = max_speed * current_max_speed
        update_led_color(max_speed_scaled)
        
        # Create joystick data dictionary to pass to ROV visualization
        joystick_data = {
            'raw_inputs': {
                'left_stick': {'x': left_stick_x, 'y': left_stick_y},
                'right_stick': {'x': right_stick_x, 'y': right_stick_y},
                'triggers': {'l2': l2_trigger, 'r2': r2_trigger}
            },
            'motor_commands': {
                'left_motor': {'speed': left_motor.speed * current_max_speed},
                'right_motor': {'speed': right_motor.speed * current_max_speed},
                'vertical_motor': {'speed': vertical_motor.speed * current_max_speed}
            }
        }
        
        # Update and render the visualization
        rov_vis.update(joystick_data, {})
        
        # Limit frame rate
        clock.tick(60)
    
    # Quit pygame
    pygame.quit()


# Execute the visualization if this module is run directly
if __name__ == "__main__":
    run_visualization()