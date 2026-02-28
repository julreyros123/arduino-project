import serial
import time

class SerialHandler:
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None

    def connect(self):
        try:
            self.serial_connection = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Wait for the connection to establish
        except serial.SerialException as e:
            print(f"Error connecting to serial port {self.port}: {e}")
            self.serial_connection = None

    def disconnect(self):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

    def send_data(self, data):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.write(data.encode())

    def receive_data(self):
        if self.serial_connection and self.serial_connection.is_open:
            if self.serial_connection.in_waiting > 0:
                return self.serial_connection.readline().decode().strip()
        return None

    def is_connected(self):
        return self.serial_connection is not None and self.serial_connection.is_open