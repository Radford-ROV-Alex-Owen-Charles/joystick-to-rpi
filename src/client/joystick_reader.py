class JoystickReader:
    def __init__(self):
        import pygame
        pygame.init()
        self.joystick = None
        self.connect_joystick()

    def connect_joystick(self):
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise Exception("No joystick detected. Please connect a joystick.")
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

    def read_inputs(self):
        pygame.event.pump()
        axes = [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())]
        buttons = [self.joystick.get_button(i) for i in range(self.joystick.get_numbuttons())]
        return axes, buttons

    def close(self):
        pygame.quit()