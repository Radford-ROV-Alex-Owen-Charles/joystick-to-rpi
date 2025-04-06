import pygame
import sys
import time

class RawJoystickReader:
    def __init__(self, joystick_index=0):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("No joystick detected. Please connect a joystick.")
            sys.exit(1)

        self.joystick = pygame.joystick.Joystick(joystick_index)
        self.joystick.init()
        print(f"Connected to {self.joystick.get_name()}")

    def read_inputs(self):
        pygame.event.pump()

        # Read all axis values
        axes = [self.joystick.get_axis(i) for i in range(self.joystick.get_numaxes())]

        # Read all button states
        buttons = [self.joystick.get_button(i) for i in range(self.joystick.get_numbuttons())]

        # Read D-pad state
        dpad = self.joystick.get_hat(0) if self.joystick.get_numhats() > 0 else (0, 0)

        print("Axes:", axes)
        print("Buttons:", buttons)
        print("D-pad:", dpad)

    def close(self):
        pygame.quit()

if __name__ == "__main__":
    reader = RawJoystickReader()

    try:
        while True:
            reader.read_inputs()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        reader.close()
