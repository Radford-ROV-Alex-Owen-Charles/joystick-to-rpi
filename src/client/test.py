import serial
s = serial.Serial('COM8', 115200, timeout=1)
print("Opened:", s.name)
s.close()