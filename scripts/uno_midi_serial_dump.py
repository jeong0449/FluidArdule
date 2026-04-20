import serial

PORT = '/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_75834353930351211140-if00'
ser = serial.Serial(PORT, 31250)

while True:
    b = ser.read(1)
    print(hex(b[0]), end=' ', flush=True)
