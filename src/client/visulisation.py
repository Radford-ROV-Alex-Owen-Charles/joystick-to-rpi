import pygame
import sys
import math
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# Initialize pygame
pygame.init()

# Initialize the joystick
pygame.joystick.init()
if pygame.joystick.get_count() == 0:
    print("No joystick detected. Please connect a PS4 controller.")
    sys.exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Connected to {joystick.get_name()}")

# Visualization setup
screen_width, screen_height = 1200, 800  # Larger screen for multiple views
screen = pygame.display.set_mode((screen_width, screen_height), DOUBLEBUF | OPENGL)
pygame.display.set_caption("ROV Control Visualization - Multiple Views")
clock = pygame.time.Clock()

# Setup viewport sizes
main_view_width = 800
main_view_height = 600
side_view_width = 400
side_view_height = 200

# ROV state
rov_rot_z = 0  # Only Z rotation (yaw) - no pitch or roll
rot_speed = 2  # Rotation speed

# Movement indicators
horizontal_movement = [0, 0]  # [x, z] direction
vertical_movement = 0  # y direction (elevation)
arrow_scale = 1.0  # Scale of the direction arrows

# Advanced control parameters (imported from ESP32 code)
MOTOR_MAX_SPEED_DEFAULT = 255  # Default maximum motor speed
MOTOR_MIN_SPEED = 50           # Minimum effective motor speed
STICK_DEAD_ZONE = 0.1          # Minimum stick movement to register (normalized from 0-1)
TRIGGER_DEAD_ZONE = 0.1        # Minimum trigger movement to register
SPEED_INCREMENT = 15           # Speed increment/decrement step with D-pad
DAMPENING_FACTOR = 0.2         # Dampening factor (0.0-1.0, lower = more dampening)
STRAIGHT_DAMPENING_BOOST = 3.0 # Boost factor when straightening from a turn
MAX_STICK_THRESHOLD = 0.9      # Threshold to snap to full speed (0-1)

# Motor state tracking (for dampening)
class MotorState:
    def __init__(self):
        self.speed = 0         # Current speed
        self.target_speed = 0  # Target speed for dampening
        self.was_turning = False  # Flag to track if motor was previously turning

# Create motor state objects
left_motor = MotorState()
right_motor = MotorState()
vertical_motor = MotorState()

# Speed control
current_max_speed = MOTOR_MAX_SPEED_DEFAULT
last_dpad_time = 0

# ROV LED color (simulating the controller LED)
rov_led_color = (0, 255, 0)  # Start with green

# Stick drift management
class StickCalibration:
    def __init__(self):
        self.center_x = 0
        self.center_y = 0
        self.center_rx = 0
        self.center_ry = 0
        self.deadzone = STICK_DEAD_ZONE
        self.calibrated = False

# Create calibration data
calibration_data = StickCalibration()

# Calibrate joystick
def calibrate_joystick():
    calibration_data.center_x = joystick.get_axis(0)
    calibration_data.center_y = joystick.get_axis(1)
    calibration_data.center_rx = joystick.get_axis(2)
    calibration_data.center_ry = joystick.get_axis(3)
    calibration_data.calibrated = True
    print(f"Controller calibrated - Center values: X={calibration_data.center_x:.3f}, Y={calibration_data.center_y:.3f}, RX={calibration_data.center_rx:.3f}, RY={calibration_data.center_ry:.3f}")

# Apply deadzone to stick value
def apply_deadzone(value, center, deadzone):
    offset = value - center
    if abs(offset) < deadzone:
        return center
    return value

# Get drift-compensated stick values
def get_compensated_axis(axis_id, center, deadzone):
    value = joystick.get_axis(axis_id)
    return apply_deadzone(value, center, deadzone)

# Apply dampening to motor speed with adaptive response
def apply_dampening(current_speed, target_speed, was_turning, is_straight):
    if current_speed == target_speed:
        return current_speed
    
    factor = DAMPENING_FACTOR
    
    # Boost response when straightening from a turn
    if was_turning and is_straight and current_speed < target_speed:
        factor = DAMPENING_FACTOR * STRAIGHT_DAMPENING_BOOST
    
    diff = target_speed - current_speed
    change = diff * factor
    
    # Ensure we make at least a small change if needed
    if diff > 0 and change < 0.01:
        change = 0.01
    if diff < 0 and change > -0.01:
        change = -0.01
    
    return current_speed + change

# Update LED color based on speed
def update_led_color(speed):
    global rov_led_color
    normalized_speed = speed / MOTOR_MAX_SPEED_DEFAULT
    red = int(normalized_speed * 255)
    green = int((1 - normalized_speed) * 255)
    blue = 0
    rov_led_color = (red, green, blue)

def setup_main_view():
    """Setup the main perspective view (45 degrees looking down)"""
    glViewport(screen_width - main_view_width, screen_height - main_view_height, 
               main_view_width, main_view_height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, (main_view_width / main_view_height), 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glTranslatef(0.0, -1.0, -7.0)  # Move back and slightly down
    glRotatef(45, 1, 0, 0)  # Rotate 45 degrees around x-axis to look down

def setup_top_view():
    """Setup the top-down orthographic view"""
    glViewport(0, screen_height - side_view_height, side_view_width, side_view_height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(-5, 5, -5, 5, -10, 10)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glTranslatef(0, -5, 0)  # Position above the ROV
    glRotatef(90, 1, 0, 0)  # Look straight down

def setup_front_view():
    """Setup the front orthographic view"""
    glViewport(0, screen_height - 2*side_view_height, side_view_width, side_view_height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(-5, 5, -5, 5, -10, 10)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glTranslatef(0, 0, -5)  # Position in front of the ROV

def setup_side_view():
    """Setup the side orthographic view"""
    glViewport(0, screen_height - 3*side_view_height, side_view_width, side_view_height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(-5, 5, -5, 5, -10, 10)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    glTranslatef(-5, 0, 0)  # Position to the side of the ROV
    glRotatef(90, 0, 1, 0)  # Look at the ROV from the side

def draw_rov():
    """Draw the ROV in 3D with direction indicators."""
    glPushMatrix()
    
    # Apply ROV rotation (only Z rotation)
    glRotatef(rov_rot_z, 0, 1, 0)  # Rotate around Y-axis (this is yaw in OpenGL)
    
    # Draw ROV body (simple cuboid) with LED color
    glBegin(GL_QUADS)
    
    # Top face with LED color
    r, g, b = rov_led_color
    glColor3f(r/255, g/255, b/255)  # LED indicator color
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
    
    # Draw direction indicator (white line)
    glColor3f(1.0, 1.0, 1.0)
    glBegin(GL_LINES)
    glVertex3f(0, 0, 0.7)
    glVertex3f(0, 0, 1.0)
    glEnd()
    
    # Draw thrusters
    draw_thrusters()
    
    # Draw movement arrows
    draw_movement_arrows()
    
    glPopMatrix()
    
    # Display grid for reference
    draw_grid()

def draw_thrusters():
    """Draw ROV thrusters."""
    # Vertical thrusters
    glColor3f(0.7, 0.7, 0.7)
    
    # Front left thruster
    glPushMatrix()
    glTranslatef(-0.4, 0.2, 0.5)
    glRotatef(90, 1, 0, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()
    
    # Front right thruster
    glPushMatrix()
    glTranslatef(0.4, 0.2, 0.5)
    glRotatef(90, 1, 0, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()
    
    # Rear left thruster
    glPushMatrix()
    glTranslatef(-0.4, 0.2, -0.3)
    glRotatef(90, 1, 0, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()
    
    # Rear right thruster
    glPushMatrix()
    glTranslatef(0.4, 0.2, -0.3)
    glRotatef(90, 1, 0, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()
    
    # Horizontal thrusters
    # Left thruster
    glPushMatrix()
    glTranslatef(-0.5, 0, 0.1)
    glRotatef(90, 0, 1, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()
    
    # Right thruster
    glPushMatrix()
    glTranslatef(0.5, 0, 0.1)
    glRotatef(90, 0, 1, 0)
    draw_cylinder(0.1, 0.1)
    glPopMatrix()

def draw_movement_arrows():
    """Draw arrows showing the movement direction."""
    # Horizontal movement arrow (red)
    if abs(horizontal_movement[0]) > 0.1 or abs(horizontal_movement[1]) > 0.1:
        glColor3f(1.0, 0.0, 0.0)  # Red for horizontal movement
        
        # Start from ROV center
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        
        # Calculate arrow endpoint with respect to ROV rotation
        end_x = horizontal_movement[0] * arrow_scale
        end_z = horizontal_movement[1] * arrow_scale
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
    if abs(vertical_movement) > 0.1:
        glColor3f(0.0, 0.0, 1.0)  # Blue for vertical movement
        
        # Draw vertical arrow
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, vertical_movement * arrow_scale, 0)
        
        # Draw arrow head for vertical movement
        arrow_head_size = 0.2
        if vertical_movement > 0:
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(arrow_head_size, vertical_movement * arrow_scale - arrow_head_size, 0)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(-arrow_head_size, vertical_movement * arrow_scale - arrow_head_size, 0)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(0, vertical_movement * arrow_scale - arrow_head_size, arrow_head_size)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(0, vertical_movement * arrow_scale - arrow_head_size, -arrow_head_size)
        else:
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(arrow_head_size, vertical_movement * arrow_scale + arrow_head_size, 0)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(-arrow_head_size, vertical_movement * arrow_scale + arrow_head_size, 0)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(0, vertical_movement * arrow_scale + arrow_head_size, arrow_head_size)
            
            glVertex3f(0, vertical_movement * arrow_scale, 0)
            glVertex3f(0, vertical_movement * arrow_scale + arrow_head_size, -arrow_head_size)
        
        glEnd()

def draw_cylinder(radius, height, segments=20):
    """Draw a simple cylinder."""
    glBegin(GL_QUAD_STRIP)
    for i in range(int(segments) + 1):  # Convert segments to integer
        angle = 2.0 * math.pi * i / segments
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        glVertex3f(x, 0, z)
        glVertex3f(x, height, z)
    glEnd()

def draw_grid():
    """Draw a reference grid."""
    glPushMatrix()
    glColor3f(0.3, 0.3, 0.3)
    glBegin(GL_LINES)
    
    # Draw grid on xz plane
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

def draw_view_labels():
    """Draw the view labels using pygame 2D rendering."""
    # We need to temporarily disable OpenGL to draw 2D text
    glDisable(GL_DEPTH_TEST)
    
    # Create an overlay surface for text
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    
    # Create font and labels
    font = pygame.font.SysFont('Arial', 24)
    main_label = font.render('Main View', True, (255, 255, 255))
    top_label = font.render('Top View', True, (255, 255, 255))
    front_label = font.render('Front View', True, (255, 255, 255))
    side_label = font.render('Side View', True, (255, 255, 255))
    
    # Add status information
    status_label = font.render(f'Speed Setting: {current_max_speed}/{MOTOR_MAX_SPEED_DEFAULT}', True, (255, 255, 255))
    calibration_label = font.render('Calibrated' if calibration_data.calibrated else 'Not Calibrated', True, (255, 255, 255))
    
    # Draw labels on overlay
    overlay.blit(main_label, (screen_width - main_view_width + 10, 10))
    overlay.blit(top_label, (10, 10))
    overlay.blit(front_label, (10, side_view_height + 10))
    overlay.blit(side_label, (10, 2*side_view_height + 10))
    
    # Draw status information
    overlay.blit(status_label, (screen_width - 300, screen_height - 30))
    overlay.blit(calibration_label, (screen_width - 300, screen_height - 60))
    
    # Draw overlay on the screen
    pygame.display.get_surface().blit(overlay, (0, 0))
    
    # Re-enable OpenGL depth testing
    glEnable(GL_DEPTH_TEST)

# Auto-calibrate on startup
calibrate_joystick()

# Initialize OpenGL
glEnable(GL_DEPTH_TEST)

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
    horizontal_movement[0] = x_from_forward + x_from_strafe
    horizontal_movement[1] = z_from_forward + z_from_strafe
    vertical_movement = elevation_control
    
    # Update LED color based on highest speed
    max_speed = max(left_motor.speed, right_motor.speed, vertical_motor.speed)
    max_speed_scaled = max_speed * current_max_speed
    update_led_color(max_speed_scaled)
    
    # Clear the entire screen
    glClearColor(0.1, 0.1, 0.2, 1.0)  # Dark blue-ish background
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    
    # Render all views
    setup_main_view()
    draw_rov()
    
    setup_top_view()
    draw_rov()
    
    setup_front_view()
    draw_rov()
    
    setup_side_view()
    draw_rov()
    
    # Draw view labels and status info
    draw_view_labels()
    
    # Swap buffers
    pygame.display.flip()

    # Limit frame rate
    clock.tick(60)

# Quit pygame
pygame.quit()